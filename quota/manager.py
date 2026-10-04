import asyncio
import logging
import re
from collections import defaultdict

from .api import APIError, QuotaError
from .models import (
    Approval, ApprovalJournal, RetainedItem, Snapshot, StorageItem, format_size, retention_applies,
)

logger = logging.getLogger(__name__)
USER_TAG = re.compile(r"^([1-9][0-9]*)\s*-\s*.*$")


def owner_id(request):
    return (request.get("requestedBy") or {}).get("id")


def byte_count(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QuotaError("A media server returned an invalid file size.")
    return value


def tag_owners(tags, tag_ids):
    return frozenset(
        int(match.group(1))
        for tag in tags
        if tag.get("id") in tag_ids
        if (match := USER_TAG.fullmatch(tag.get("label", "")))
    )


def media_type(request):
    return request.get("type") or request["media"]["mediaType"]


def server_matches(request, server):
    if (media_type(request) == "movie") != (server.kind == "radarr"):
        return False
    if bool(request.get("is4k")) != server.is_4k:
        return False
    server_id = request.get("serverId")
    if server_id is None or server_id < 0:
        # Pending requests go to Seerr's current default, even if the media
        # previously existed on a different server.
        if request["status"] == 1:
            return server.is_default
        server_id = request["media"].get("serviceId4k" if server.is_4k else "serviceId")
    if server_id is None or server_id < 0:
        return server.is_default
    return server.id == server_id


def item_matches(request, item):
    media = request["media"]
    if media.get("tmdbId") and item.get("tmdbId") == media["tmdbId"]:
        return True
    return (
        media_type(request) == "tv"
        and bool(media.get("tvdbId"))
        and item.get("tvdbId") == media["tvdbId"]
    )


class QuotaManager:
    def __init__(self, api, config):
        self.api = api
        self.config = config
        self.journal = ApprovalJournal(config.state_file)
        # Serialize approval and deletion decisions, including two Discord IDs
        # linked to the same Seerr user. Run one bot instance per quota state file.
        self._lock = asyncio.Lock()
        self._reads = asyncio.Semaphore(4)

    @property
    def enabled(self):
        return self.config.limit > 0

    async def _arr_read(self, server, endpoint, params=None):
        async with self._reads:
            return await self.api.arr(server, "GET", endpoint, params=params)

    async def _inventory(self, server, requests, user_id, removed, protected):
        tags, catalog = await asyncio.gather(
            self._arr_read(server, "/tag"),
            self._arr_read(server, "/movie" if server.kind == "radarr" else "/series"),
        )
        if not isinstance(tags, list) or not isinstance(catalog, list):
            raise QuotaError(f"{server.name} returned an invalid library or tag list.")
        server_requests = [r for r in requests if server_matches(r, server)]
        by_tmdb, by_tvdb = defaultdict(list), defaultdict(list)
        for request in server_requests:
            if request["media"].get("tmdbId"):
                by_tmdb[request["media"]["tmdbId"]].append(request)
            if request["media"].get("tvdbId"):
                by_tvdb[request["media"]["tvdbId"]].append(request)
        inventory = {"server": server, "catalog": catalog, "files": {}, "episodes": {}}
        entries = []
        for item in catalog:
            tagged = tag_owners(tags, item.get("tags") or [])
            matching = {
                r["id"]: r
                for r in by_tmdb[item.get("tmdbId")] + by_tvdb[item.get("tvdbId")]
                if r["status"] != 3
            }
            known = list(matching.values())
            if user_id not in tagged and not any(owner_id(r) == user_id for r in known):
                continue
            title = item.get("title") or f"{server.kind} item {item['id']}"
            if server.is_4k:
                title += " (4K)"
            if server.kind == "radarr":
                known = [r for r in known if (r["id"], -1) not in removed]
                owners = tagged | frozenset(owner_id(r) for r in known if owner_id(r))
                if user_id not in owners:
                    continue
                if item.get("hasFile") is False:
                    size = 0
                else:
                    size = item.get("sizeOnDisk")
                    if size is None:
                        size = (item.get("movieFile") or {}).get("size")
                    size = byte_count(size)
                entries.append(StorageItem(
                    key=f"{server.key}:{item['id']}", title=title, server=server,
                    item_id=item["id"], media_type="movie", tmdb_id=item.get("tmdbId"),
                    tvdb_id=None, season=None, size=size, owners=owners,
                    request_ids=tuple(r["id"] for r in known), removable=owners == {user_id},
                    reason="This movie is also attributed to another user.",
                ))
                continue

            files, episodes = await asyncio.gather(
                self._arr_read(server, "/episodefile", {"seriesId": item["id"]}),
                self._arr_read(server, "/episode", {"seriesId": item["id"]}),
            )
            if not isinstance(files, list) or not isinstance(episodes, list):
                raise QuotaError(f"{server.name} returned invalid episode information.")
            inventory["files"][item["id"]] = files
            inventory["episodes"][item["id"]] = episodes
            seasons = {f["seasonNumber"] for f in files}
            for number in sorted(seasons):
                season_requests = [
                    r for r in known
                    if any(s["seasonNumber"] == number for s in r.get("seasons", []))
                    and (r["id"], number) not in removed
                ]
                # Seerr's request history can split a tagged series by season.
                # Without that history, shared tags are deliberately ambiguous.
                season_owners = frozenset(
                    owner_id(r) for r in season_requests if owner_id(r)
                )
                # A tagged user whose history is missing might also own this
                # season. Only split known users when their seasons are known.
                known_owners = frozenset(
                    owner_id(r) for r in known if owner_id(r) and r.get("seasons")
                )
                owners = (season_owners | (tagged - known_owners)) or tagged
                if user_id not in owners:
                    continue
                size = sum(byte_count(f.get("size")) for f in files if f["seasonNumber"] == number)
                entries.append(StorageItem(
                    key=f"{server.key}:{item['id']}:{number}",
                    title=f"{title} — Season {number}", server=server, item_id=item["id"],
                    media_type="tv", tmdb_id=item.get("tmdbId"), tvdb_id=item.get("tvdbId"),
                    season=number, size=size, owners=owners,
                    request_ids=tuple(r["id"] for r in season_requests),
                    removable=owners == {user_id},
                    reason="This season is also attributed to another user.",
                ))
        for entry in entries:
            if retention_applies(protected, entry.retention_key):
                entry.removable = False
                entry.reason = "An administrator is keeping this download in the library."
        inventory["entries"] = entries
        return inventory

    async def _remaining(self, request, inventories, removed, retained=frozenset()):
        matches = [i for i in inventories if server_matches(request, i["server"])]
        if len(matches) != 1:
            raise QuotaError("Cannot identify the media server for this request.")
        inventory = matches[0]
        items = [i for i in inventory["catalog"] if item_matches(request, i)]
        if len(items) > 1:
            raise QuotaError("The request matches more than one library item.")
        item = items[0] if items else None
        prefix = (inventory["server"].key, media_type(request), request["media"]["tmdbId"])
        id_field = "tvdbId" if media_type(request) == "tv" else "tmdbId"
        media_id = (item or {}).get(id_field) or request["media"].get(id_field)
        retention_prefix = (inventory["server"].key, media_type(request), media_id)
        if media_type(request) == "movie":
            if retention_applies(retained, (*retention_prefix, -1)):
                return {}
            if (request["id"], -1) in removed or (item and item.get("hasFile")):
                return {}
            estimate = self.config.movie_4k_estimate if request.get("is4k") else self.config.movie_estimate
            return {prefix + (-1,): estimate}

        requested = {s["seasonNumber"] for s in request.get("seasons", [])}
        if not requested:
            raise QuotaError("Seerr did not report the requested seasons.")
        requested = {
            number for number in requested
            if not retention_applies(retained, (*retention_prefix, number))
        }
        if not requested:
            return {}
        episodes = inventory["episodes"].get(item["id"], []) if item else []
        counts = {}
        if any(not any(e["seasonNumber"] == number for e in episodes) for number in requested):
            details = await self.api.seerr("GET", f"/tv/{request['media']['tmdbId']}")
            counts = {s["seasonNumber"]: s.get("episodeCount") for s in details.get("seasons", [])}
        estimate = self.config.episode_4k_estimate if request.get("is4k") else self.config.episode_estimate
        remaining = {}
        for number in requested:
            if (request["id"], number) in removed:
                continue
            season_episodes = [e for e in episodes if e["seasonNumber"] == number]
            if season_episodes:
                missing = sum(not e.get("hasFile", bool(e.get("episodeFileId"))) for e in season_episodes)
            else:
                missing = counts.get(number)
                if not isinstance(missing, int) or missing <= 0:
                    raise QuotaError(f"Cannot estimate the size of season {number} yet.")
            if missing:
                remaining[prefix + (number,)] = missing * estimate
        return remaining

    async def snapshot(self, user_id):
        servers, requests = await asyncio.gather(self.api.servers(), self.api.requests())
        if not servers:
            raise QuotaError("No Radarr or Sonarr servers are configured in Seerr.")
        pending = self.journal.pending(user_id)
        request_map = {r["id"]: r for r in requests}
        listed_request_ids = set(request_map)
        # A changing paginated list must not erase a durable reservation. Resolve
        # missing entries individually before counting approved downloads.
        for request_id in pending:
            if request_id not in request_map:
                try:
                    request = await self.api.request(request_id)
                except APIError as error:
                    if error.status != 404:
                        raise
                    self.journal.clear(request_id)
                else:
                    request_map[request_id] = request
        requests = list(request_map.values())
        removed = self.journal.removed_units()
        retained_items = self.journal.retained_items()
        protected = {item.retention_key for item in retained_items}
        user_retained = [item for item in retained_items if item.user_id == user_id]
        retained = {item.retention_key for item in user_retained}
        inventories = await asyncio.gather(*[
            self._inventory(server, requests, user_id, removed, protected) for server in servers
        ])
        all_items = [item for inv in inventories for item in inv["entries"] if item.size > 0]
        items = [item for item in all_items if not retention_applies(retained, item.retention_key)]
        for kept in user_retained:
            kept.size = sum(
                item.size for item in all_items
                if retention_applies({kept.retention_key}, item.retention_key)
            )
        reservations = {}
        if self.config.reserve_downloads:
            for request in requests:
                if owner_id(request) == user_id and request["status"] in (2, 4):
                    for key, size in (await self._remaining(request, inventories, removed, retained)).items():
                        reservations[key] = max(size, reservations.get(key, 0))

        uncertain = 0
        for request_id, size in self.journal.pending(user_id).items():
            request = request_map.get(request_id)
            if request is not None and request["status"] != 1:
                if request_id in listed_request_ids:
                    self.journal.clear(request_id)
            else:
                if request is not None and retained and self.config.reserve_downloads:
                    # Keep the uncertain approval marker, but stop reserving exempt titles.
                    remaining = await self._remaining(request, inventories, set(), retained)
                    size = min(size, sum(remaining.values()))
                uncertain += size
        return Snapshot(
            user_id=user_id, limit=self.config.limit,
            used=sum(item.size for item in items),
            reserved=sum(reservations.values()) + uncertain,
            items=sorted(items, key=lambda item: (-item.size, item.title)),
            requests=requests, inventories=list(inventories),
            retained_items=user_retained,
        )

    async def auto_approve(self, user_id, request_id):
        if not self.enabled:
            return Approval(False, "Your request is waiting for approval.")
        async with self._lock:
            try:
                request = await self.api.request(request_id)
                if owner_id(request) != user_id:
                    raise QuotaError("This request belongs to another user.")
                if request["status"] in (2, 5):
                    self.journal.clear(request_id)
                    return Approval(True, "Your request is approved.")
                if request["status"] != 1:
                    raise QuotaError("Only pending requests can be auto-approved.")
                snapshot = await self.snapshot(user_id)
                if not any(r["id"] == request_id for r in snapshot.requests):
                    raise QuotaError("The new request is not in Seerr's request list yet. Please retry.")
                if request_id in self.journal.pending(user_id):
                    return Approval(False, "An earlier approval could not be confirmed. "
                                    "Ask the bot owner to check this request in Seerr.", snapshot)
                size = 0
                if self.config.reserve_downloads:
                    size = sum((await self._remaining(
                        request, snapshot.inventories, set(),
                        {item.retention_key for item in snapshot.retained_items},
                    )).values())
                if snapshot.used + snapshot.reserved >= self.config.limit or size > snapshot.free:
                    return Approval(False,
                        f"Your request is waiting for approval. You have {format_size(snapshot.free)} "
                        f"free in your {format_size(snapshot.limit)} allowance"
                        + (f"; this request needs about {format_size(size)}." if size else ".")
                        + " Use Manage storage to remove older downloads, then retry approval.", snapshot)
                # Commit before the HTTP request so a timeout/restart cannot make
                # an approval already in progress disappear from accounting.
                latest = await self.api.request(request_id)
                scope = lambda r: (
                    owner_id(r), r["status"], r["media"]["id"], r.get("is4k"),
                    r.get("serverId"), sorted(s["seasonNumber"] for s in r.get("seasons", [])),
                )
                if scope(latest) != scope(request):
                    raise QuotaError("The request changed while checking its quota. Please retry.")
                self.journal.reserve(request_id, user_id, size)
                try:
                    result = await self.api.approve(request_id)
                except APIError as error:
                    if error.status in (400, 401, 403, 409, 422):
                        self.journal.clear(request_id)
                    raise
                if result.get("id") != request_id or result.get("status") not in (2, 5):
                    raise QuotaError("Seerr did not confirm approval. Please check the existing request.")
                self.journal.clear(request_id)
                return Approval(True, "Your request was auto-approved within your storage allowance.")
            except Exception:
                logger.exception("Quota approval could not be completed for request %s", request_id)
                return Approval(False, "Your request was submitted, but auto-approval could not be "
                                "confirmed. It has not been resubmitted. Try Manage storage later "
                                "or ask the bot owner to check Seerr.")

    async def retain(self, user_id, expected, admin_id, *, whole_series=False):
        """Release quota and protect files without changing Seerr or Arr ownership."""
        async with self._lock:
            snapshot = await self.snapshot(user_id)
            item = next((i for i in snapshot.items if i.key == expected.key), None)
            if item is None or user_id not in item.owners:
                raise QuotaError("That download no longer counts against this user. Refresh the list.")
            if item.retention_key != expected.retention_key:
                raise QuotaError("The library item changed. Refresh before keeping it.")
            kept = RetainedItem.from_storage(user_id, item, whole_series=whole_series)
            self.journal.retain(kept, admin_id)
            logger.info("Admin %s kept %s and released quota for Seerr user %s", admin_id, kept.key, user_id)
            return kept

    async def restore_retained(self, user_id, expected, admin_id):
        async with self._lock:
            item = next((i for i in self.journal.retained_items()
                         if i.user_id == user_id and i.key == expected.key), None)
            if item is None or expected.user_id != user_id:
                raise QuotaError("This quota exception no longer exists. Refresh the list.")
            self.journal.restore_retained(item)
            logger.info("Admin %s restored quota for %s to Seerr user %s", admin_id, item.key, user_id)

    async def _check_queue(self, item):
        page = 1
        while True:
            data = await self.api.arr(item.server, "GET", "/queue", params={
                "page": page, "pageSize": 100,
            })
            if not isinstance(data, dict) or not isinstance(data.get("records"), list):
                raise QuotaError("Could not check active downloads; nothing has been deleted.")
            field = "movieId" if item.media_type == "movie" else "seriesId"
            if any(record.get(field) == item.item_id for record in data["records"]):
                raise QuotaError("This title still has an active download. Wait for it to finish before removing it.")
            if page * 100 >= data.get("totalRecords", len(data["records"])):
                return
            page += 1

    async def remove(self, user_id, expected):
        async with self._lock:
            snapshot = await self.snapshot(user_id)
            item = next((i for i in snapshot.items if i.key == expected.key), None)
            if item is None:
                raise QuotaError("That download is no longer in your storage list. Refresh the list.")
            if not item.removable or item.owners != {user_id}:
                raise QuotaError(item.reason or "This download belongs to another user.")
            if (item.tmdb_id, item.tvdb_id) != (expected.tmdb_id, expected.tvdb_id):
                raise QuotaError("The library item changed. Refresh the list before deleting.")
            await self._check_queue(item)
            inventory = next(i for i in snapshot.inventories if i["server"].key == item.server.key)
            resource = next(i for i in inventory["catalog"] if i["id"] == item.item_id)
            if item.media_type == "movie":
                await self.api.arr(item.server, "PUT", f"/movie/{item.item_id}",
                                   body={**resource, "monitored": False})
                await self.api.arr(item.server, "DELETE", f"/movie/{item.item_id}", params={
                    "deleteFiles": "true", "addImportExclusion": "false",
                })
                remaining = await self.api.arr(item.server, "GET", "/movie", params={"tmdbId": item.tmdb_id})
                if remaining:
                    raise QuotaError("Radarr has not confirmed removal yet. Refresh your usage before retrying.")
            else:
                files = [f for f in inventory["files"][item.item_id] if f["seasonNumber"] == item.season]
                episodes = inventory["episodes"][item.item_id]
                file_ids = {f["id"] for f in files}
                if not any(s["seasonNumber"] == item.season for s in resource.get("seasons", [])):
                    raise QuotaError("The season is missing from Sonarr's series information. Refresh and retry.")
                if not file_ids <= {e.get("episodeFileId") for e in episodes}:
                    raise QuotaError("Cannot verify which episodes use these files. Refresh and retry.")
                if any(e.get("episodeFileId") in file_ids and e["seasonNumber"] != item.season for e in episodes):
                    raise QuotaError("A file contains episodes from another season; ask the bot owner to remove it.")
                seasons = [
                    {**season, "monitored": False} if season["seasonNumber"] == item.season else season
                    for season in resource["seasons"]
                ]
                await self.api.arr(item.server, "PUT", f"/series/{item.item_id}",
                                   body={**resource, "seasons": seasons})
                episode_ids = [e["id"] for e in episodes if e["seasonNumber"] == item.season]
                if episode_ids:
                    await self.api.arr(item.server, "PUT", "/episode/monitor", body={
                        "episodeIds": episode_ids, "monitored": False,
                    })
                for file_id in sorted(file_ids):
                    try:
                        await self.api.arr(item.server, "DELETE", f"/episodefile/{file_id}")
                    except APIError as error:
                        if error.status != 404:
                            raise
                remaining = await self.api.arr(item.server, "GET", "/episodefile", params={"seriesId": item.item_id})
                if any(f["seasonNumber"] == item.season for f in remaining):
                    raise QuotaError("Sonarr has not confirmed removal yet. Refresh your usage before retrying.")
            self.journal.mark_removed(item.request_ids, item.season)
            return item.size
