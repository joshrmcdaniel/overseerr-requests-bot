import aiohttp
from ..types import ErrorResponse, _load_type
from typing import List, Optional, TypeVar, Dict
import json
import urllib.parse
import logging


logger = logging.getLogger("overseerapi.shared.networking")

R = TypeVar("R", Dict, List[Dict], ErrorResponse)


async def get(
    url: str,
    *,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    logger.debug("Sending GET requests to {}", url)
    # logger.trace("Parameters: {}", params)
    if params:
        params = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            try:
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                try:
                    res = _load_type(await r.json(), ErrorResponse)
                    return res
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {cre}")
                    raise e
            logger.debug("Received response {} from {}", r.status, url)
            logger.log(10, "Response: {}", await r.text())
            return await r.json()


async def post(
    url: str,
    *,
    load_json: bool = True,
    body: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    body = json.dumps(body).encode("ascii")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, data=body) as r:
            try:
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                try:
                    return (
                        _load_type(await r.json(), ErrorResponse)
                        if load_json
                        else await r.text()
                    )
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {e}")
                    raise e from cre
            return await r.json() if load_json else await r.text()
