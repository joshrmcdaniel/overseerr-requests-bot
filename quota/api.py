"""Read storage from Seerr's configured Radarr/Sonarr servers."""

from dataclasses import dataclass, field

import aiohttp


class QuotaError(RuntimeError):
    """A quota operation could not be completed safely."""


class APIError(QuotaError):
    def __init__(self, service, status=None):
        self.status = status
        suffix = f" (HTTP {status})" if status else ""
        super().__init__(f"Could not contact {service}{suffix}. Please try again later.")


@dataclass(frozen=True)
class Server:
    kind: str
    id: int
    name: str
    url: str
    api_key: str = field(repr=False)
    is_4k: bool = False
    is_default: bool = False

    @property
    def key(self):
        return f"{self.kind}:{self.id}"


async def request_json(method, url, *, api_key, service, params=None, body=None):
    # Do not log headers, settings responses, or URLs containing credentials.
    # A failed size lookup must never be interpreted as zero bytes used.
    try:
        async with aiohttp.ClientSession(
            headers={"X-Api-Key": api_key},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            async with session.request(
                method, url, params=params, json=body, allow_redirects=False
            ) as response:
                if not 200 <= response.status < 300:
                    raise APIError(service, response.status)
                if response.status == 204:
                    return None
                data = await response.read()
                if not data:
                    return None
                return await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        # Network exceptions can include URLs or credentials in their text.
        raise APIError(service) from None


class QuotaAPI:
    def __init__(self, seerr_client, server_urls=None):
        self.client = seerr_client
        self.server_urls = server_urls or {}

    async def seerr(self, method, endpoint, *, params=None, body=None):
        return await request_json(
            method,
            self.client._url.rstrip("/") + endpoint,
            api_key=self.client._api_key,
            service="Seerr",
            params=params,
            body=body,
        )

    async def arr(self, server, method, endpoint, *, params=None, body=None):
        return await request_json(
            method,
            server.url.rstrip("/") + "/api/v3" + endpoint,
            api_key=server.api_key,
            service=server.name,
            params=params,
            body=body,
        )

    async def servers(self):
        servers = []
        for kind in ("radarr", "sonarr"):
            settings = await self.seerr("GET", f"/settings/{kind}")
            if not isinstance(settings, list):
                raise QuotaError(f"Seerr returned invalid {kind} settings.")
            for config in settings:
                server_key = f"{kind}:{config['id']}"
                url = self.server_urls.get(server_key)
                if not url:
                    hostname = config["hostname"]
                    if ":" in hostname and not hostname.startswith("["):
                        hostname = f"[{hostname}]"
                    scheme = "https" if config.get("useSsl") else "http"
                    base = config.get("baseUrl", "").strip("/")
                    url = f"{scheme}://{hostname}:{config['port']}"
                    if base:
                        url += f"/{base}"
                if not url.startswith(("http://", "https://")):
                    raise QuotaError(f"Invalid URL override for {server_key}.")
                servers.append(Server(
                    kind=kind,
                    id=config["id"],
                    name=config.get("name") or kind.title(),
                    url=url,
                    api_key=config["apiKey"],
                    is_4k=bool(config.get("is4k")),
                    is_default=bool(config.get("isDefault")),
                ))
        return servers

    async def requests(self):
        results = {}
        skip = 0
        while True:
            page = await self.seerr("GET", "/request", params={
                "take": 100, "skip": skip, "filter": "all", "sort": "added",
            })
            if not isinstance(page, dict) or not isinstance(page.get("results"), list):
                raise QuotaError("Seerr returned an invalid request list.")
            items = page["results"]
            for request in items:
                results[request["id"]] = request
            if len(items) < 100:
                return list(results.values())
            skip += len(items)

    async def request(self, request_id):
        return await self.seerr("GET", f"/request/{int(request_id)}")

    async def approve(self, request_id):
        return await self.seerr("POST", f"/request/{int(request_id)}/approve")
