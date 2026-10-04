import asyncio
import copy
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import discord

from quota.api import APIError, QuotaAPI, QuotaError, Server, request_json
from quota.manager import QuotaManager, tag_owners
from quota.models import GB, Approval, QuotaConfig, Snapshot, StorageItem
from quota.views import PendingRequestsView, QuotaActionsView, RemoveConfirmation, StorageView
from overseerrapi.types import MediaSearchResult, Request
from views import SearchView


def request(request_id, user_id=7, kind="movie", status=1, seasons=(), tmdb_id=None):
    tmdb_id = tmdb_id or request_id + 100
    return {
        "id": request_id, "status": status, "type": kind, "is4k": False,
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
        "requestedBy": {"id": user_id},
        "media": {"id": tmdb_id, "tmdbId": tmdb_id, "tvdbId": tmdb_id + 1000,
                  "mediaType": kind, "status": 5 if status == 5 else 2},
        "seasons": [{"seasonNumber": n} for n in seasons],
    }


def movie(item_id=11, tmdb_id=1001, size=480 * GB, tags=(70,)):
    return {"id": item_id, "tmdbId": tmdb_id, "title": f"Movie {item_id}",
            "hasFile": True, "sizeOnDisk": size, "tags": list(tags), "monitored": True}


class FakeAPI:
    def __init__(self):
        self.server_list = [
            Server("radarr", 0, "Radarr", "http://radarr", "radarr-key", is_default=True),
            Server("sonarr", 0, "Sonarr", "http://sonarr", "sonarr-key", is_default=True),
        ]
        self.tags = [{"id": 70, "label": "7-Josh"}, {"id": 80, "label": "8-Someone"}]
        self.movies = [movie()]
        self.series = []
        self.files = []
        self.episodes = []
        self.records = {1: request(1), 2: request(2)}
        self.queue = []
        self.calls = []
        self.approvals = []
        self.approval_error = None
        self.delete_error = None

    async def servers(self):
        return self.server_list

    async def requests(self):
        return copy.deepcopy(list(self.records.values()))

    async def request(self, request_id):
        return copy.deepcopy(self.records[request_id])

    async def approve(self, request_id):
        self.approvals.append(request_id)
        await asyncio.sleep(0)
        if self.approval_error:
            raise self.approval_error
        self.records[request_id]["status"] = 2
        return copy.deepcopy(self.records[request_id])

    async def seerr(self, method, endpoint, **kwargs):
        if endpoint.startswith("/tv/"):
            return {"seasons": [{"seasonNumber": 1, "episodeCount": 10},
                                {"seasonNumber": 2, "episodeCount": 10}]}
        raise AssertionError((method, endpoint, kwargs))

    async def arr(self, server, method, endpoint, params=None, body=None):
        self.calls.append((server.kind, method, endpoint, copy.deepcopy(params), copy.deepcopy(body)))
        if method == "GET":
            if endpoint == "/tag":
                value = self.tags
            elif endpoint == "/movie":
                value = self.movies
                if params:
                    value = [m for m in value if m["tmdbId"] == params["tmdbId"]]
            elif endpoint == "/series":
                value = self.series
            elif endpoint == "/episodefile":
                value = self.files
            elif endpoint == "/episode":
                value = self.episodes
            elif endpoint == "/queue":
                value = {"records": self.queue, "totalRecords": len(self.queue)}
            else:
                raise AssertionError((method, endpoint, params))
            return copy.deepcopy(value)
        if method == "PUT":
            if endpoint.startswith("/movie/"):
                self.movies = [body if m["id"] == body["id"] else m for m in self.movies]
            elif endpoint.startswith("/series/"):
                self.series = [body if s["id"] == body["id"] else s for s in self.series]
            elif endpoint == "/episode/monitor":
                for episode in self.episodes:
                    if episode["id"] in body["episodeIds"]:
                        episode["monitored"] = body["monitored"]
            else:
                raise AssertionError((method, endpoint, body))
            return copy.deepcopy(body)
        if method == "DELETE":
            if self.delete_error:
                raise self.delete_error
            item_id = int(endpoint.rsplit("/", 1)[1])
            if endpoint.startswith("/movie/"):
                self.movies = [m for m in self.movies if m["id"] != item_id]
            elif endpoint.startswith("/episodefile/"):
                self.files = [f for f in self.files if f["id"] != item_id]
                for episode in self.episodes:
                    if episode.get("episodeFileId") == item_id:
                        episode["episodeFileId"] = 0
                        episode["hasFile"] = False
            else:
                raise AssertionError((method, endpoint))
            return None
        raise AssertionError((method, endpoint))

    def add_shared_series(self):
        self.records[10] = request(10, kind="tv", status=5, seasons=[1], tmdb_id=500)
        self.records[20] = request(20, user_id=8, kind="tv", status=5, seasons=[2], tmdb_id=500)
        self.series = [{"id": 30, "tmdbId": 500, "tvdbId": 1500, "title": "Shared show",
                        "tags": [70, 80], "monitored": True,
                        "seasons": [{"seasonNumber": 1, "monitored": True},
                                    {"seasonNumber": 2, "monitored": True}]}]
        self.files = [{"id": 101, "seasonNumber": 1, "size": 30 * GB},
                      {"id": 102, "seasonNumber": 2, "size": 40 * GB}]
        self.episodes = [{"id": 201, "seasonNumber": 1, "hasFile": True, "episodeFileId": 101},
                         {"id": 202, "seasonNumber": 2, "hasFile": True, "episodeFileId": 102}]


class StorageQuotaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = QuotaConfig(state_file=str(Path(self.temp.name) / "quota.sqlite3"))
        self.api = FakeAPI()
        self.manager = QuotaManager(self.api, self.config)

    async def test_uid_matching_survives_rename_and_does_not_match_uid_prefixes(self):
        tags = [{"id": 1, "label": "7-old-name"}, {"id": 2, "label": "7 - new-name"},
                {"id": 3, "label": "70-other-user"}, {"id": 4, "label": "requests"}]
        self.assertEqual(tag_owners(tags, [1, 2, 4]), {7})
        self.assertEqual(tag_owners(tags, [3]), {70})
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.used, 480 * GB)
        self.assertEqual(snapshot.free, 20 * GB)
        self.assertEqual((await self.manager.snapshot(8)).used, 0)

    async def test_auto_approval_allows_exact_limit_and_reserves_queued_request(self):
        result = await self.manager.auto_approve(7, 1)
        self.assertTrue(result.approved)
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.reserved, 20 * GB)
        result = await self.manager.auto_approve(7, 2)
        self.assertFalse(result.approved)
        self.assertEqual(self.api.approvals, [1])

    async def test_concurrent_requests_cannot_both_spend_the_same_free_space(self):
        results = await asyncio.gather(self.manager.auto_approve(7, 1), self.manager.auto_approve(7, 2))
        self.assertEqual(sum(r.approved for r in results), 1)
        self.assertEqual(len(self.api.approvals), 1)

    async def test_actual_download_size_replaces_estimate(self):
        await self.manager.auto_approve(7, 1)
        self.api.records[1]["status"] = 5
        self.api.movies.append(movie(12, 101, 8 * GB))
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.used, 488 * GB)
        self.assertEqual(snapshot.reserved, 0)

    async def test_over_quota_and_other_user_never_approve(self):
        self.api.movies[0]["sizeOnDisk"] = 501 * GB
        self.assertFalse((await self.manager.auto_approve(7, 1)).approved)
        with self.assertLogs("quota.manager", level="ERROR"):
            self.assertFalse((await self.manager.auto_approve(8, 1)).approved)
        self.assertEqual(self.api.approvals, [])

    async def test_size_lookup_failure_never_counts_as_zero_usage(self):
        self.api.movies[0].pop("sizeOnDisk")
        with self.assertLogs("quota.manager", level="ERROR"):
            self.assertFalse((await self.manager.auto_approve(7, 1)).approved)
        self.assertEqual(self.api.approvals, [])

    async def test_unconfirmed_approval_reservation_survives_restart(self):
        self.api.approval_error = APIError("Seerr")
        with self.assertLogs("quota.manager", level="ERROR"):
            self.assertFalse((await self.manager.auto_approve(7, 1)).approved)
        restarted = QuotaManager(self.api, self.config)
        self.assertEqual((await restarted.snapshot(7)).reserved, 20 * GB)
        self.assertFalse((await restarted.auto_approve(7, 2)).approved)
        self.assertFalse((await restarted.auto_approve(7, 1)).approved)
        self.assertEqual(self.api.approvals, [1])

    async def test_definite_permission_rejection_releases_reservation(self):
        self.api.approval_error = APIError("Seerr", 403)
        with self.assertLogs("quota.manager", level="ERROR"):
            await self.manager.auto_approve(7, 1)
        self.assertEqual((await self.manager.snapshot(7)).reserved, 0)

    async def test_uncertain_request_missing_from_page_is_looked_up_before_releasing_space(self):
        self.manager.journal.reserve(1, 7, 20 * GB)
        self.api.requests = AsyncMock(return_value=[request(2)])
        self.api.records[1]["status"] = 2
        self.assertEqual((await self.manager.snapshot(7)).reserved, 20 * GB)
        self.assertFalse((await self.manager.auto_approve(7, 2)).approved)
        self.assertEqual(self.api.approvals, [])

    async def test_default_server_ignores_negative_override_and_previous_media_server(self):
        self.api.records[1]["serverId"] = -1
        self.api.records[1]["media"]["serviceId"] = 99
        self.assertTrue((await self.manager.auto_approve(7, 1)).approved)
        self.assertEqual(self.api.approvals, [1])

    async def test_4k_request_uses_4k_estimate_and_server(self):
        self.api.records[1]["is4k"] = True
        self.api.server_list[0] = replace(self.api.server_list[0], is_4k=True)
        self.api.movies[0]["sizeOnDisk"] = 421 * GB
        self.assertFalse((await self.manager.auto_approve(7, 1)).approved)
        self.api.movies[0]["sizeOnDisk"] = 420 * GB
        self.assertTrue((await self.manager.auto_approve(7, 1)).approved)
        self.assertEqual((await self.manager.snapshot(7)).reserved, 80 * GB)

    async def test_approved_request_reserves_space_before_arr_enables_monitoring(self):
        self.api.movies.append({**movie(12, 101, 0), "hasFile": False, "monitored": False})
        self.assertTrue((await self.manager.auto_approve(7, 1)).approved)
        self.assertEqual((await self.manager.snapshot(7)).reserved, 20 * GB)
        self.assertFalse((await self.manager.auto_approve(7, 2)).approved)

    async def test_downloaded_only_mode_is_explicitly_supported(self):
        manager = QuotaManager(self.api, replace(self.config, reserve_downloads=False))
        self.assertTrue((await manager.auto_approve(7, 1)).approved)
        self.assertTrue((await manager.auto_approve(7, 2)).approved)
        self.api.movies[0]["sizeOnDisk"] = 500 * GB
        self.api.records[3] = request(3)
        self.assertFalse((await manager.auto_approve(7, 3)).approved)

    async def test_tv_sizes_are_charged_to_the_requested_seasons(self):
        self.api.add_shared_series()
        self.assertEqual((await self.manager.snapshot(7)).used, 510 * GB)
        self.assertEqual((await self.manager.snapshot(8)).used, 40 * GB)

    async def test_partial_tv_download_reserves_only_missing_episodes(self):
        self.api.add_shared_series()
        self.api.records[10]["status"] = 2
        self.api.episodes.append({"id": 203, "seasonNumber": 1, "hasFile": False, "episodeFileId": 0})
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.reserved, 2 * GB)

    async def test_removing_a_shared_series_only_deletes_own_season(self):
        self.api.add_shared_series()
        snapshot = await self.manager.snapshot(7)
        season = next(i for i in snapshot.items if i.media_type == "tv")
        self.assertEqual(await self.manager.remove(7, season), 30 * GB)
        self.assertEqual([f["id"] for f in self.api.files], [102])
        self.assertFalse(self.api.series[0]["seasons"][0]["monitored"])
        self.assertTrue(self.api.series[0]["seasons"][1]["monitored"])
        self.assertEqual((await self.manager.snapshot(7)).used, 480 * GB)

    async def test_season_requested_by_someone_else_after_removal_does_not_charge_old_owner(self):
        self.api.add_shared_series()
        season = next(i for i in (await self.manager.snapshot(7)).items if i.media_type == "tv")
        await self.manager.remove(7, season)
        self.api.records[21] = request(21, user_id=8, kind="tv", status=5, seasons=[1], tmdb_id=500)
        self.api.files.append({"id": 103, "seasonNumber": 1, "size": 25 * GB})
        self.api.episodes[0].update(hasFile=True, episodeFileId=103)
        self.assertEqual((await self.manager.snapshot(7)).used, 480 * GB)
        snapshot = await self.manager.snapshot(8)
        self.assertEqual(snapshot.used, 65 * GB)
        self.assertTrue(all(item.removable for item in snapshot.items))

    async def test_movie_requested_by_someone_else_after_removal_does_not_charge_old_owner(self):
        self.api.records[99] = request(99, status=5, tmdb_id=1001)
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.remove(7, item)
        self.api.records[100] = request(100, user_id=8, status=5, tmdb_id=1001)
        self.api.movies.append(movie(12, 1001, 12 * GB, tags=[80]))
        self.assertEqual((await self.manager.snapshot(7)).used, 0)
        snapshot = await self.manager.snapshot(8)
        self.assertEqual(snapshot.used, 12 * GB)
        self.assertTrue(snapshot.items[0].removable)

    async def test_shared_movie_and_changed_ownership_are_protected(self):
        item = (await self.manager.snapshot(7)).items[0]
        self.api.movies[0]["tags"] = [70, 80]
        with self.assertRaises(QuotaError):
            await self.manager.remove(7, item)
        self.api.movies[0]["tags"] = [80]
        with self.assertRaises(QuotaError):
            await self.manager.remove(7, item)
        self.assertFalse(any(call[1] in ("PUT", "DELETE") for call in self.api.calls))

    async def test_shared_tag_without_request_history_prevents_season_deletion(self):
        self.api.add_shared_series()
        del self.api.records[20]
        seasons = [i for i in (await self.manager.snapshot(7)).items if i.media_type == "tv"]
        self.assertTrue(seasons)
        self.assertTrue(all(not item.removable for item in seasons))
        with self.assertRaises(QuotaError):
            await self.manager.remove(7, seasons[0])
        self.assertFalse(any(call[1] in ("PUT", "DELETE") for call in self.api.calls))

    async def test_incomplete_episode_mapping_prevents_season_deletion(self):
        self.api.add_shared_series()
        item = next(i for i in (await self.manager.snapshot(7)).items if i.media_type == "tv")
        self.api.episodes = []
        with self.assertRaisesRegex(QuotaError, "verify which episodes"):
            await self.manager.remove(7, item)
        self.assertFalse(any(call[1] in ("PUT", "DELETE") for call in self.api.calls))

    async def test_active_download_prevents_file_deletion(self):
        item = (await self.manager.snapshot(7)).items[0]
        self.api.queue = [{"movieId": item.item_id}]
        with self.assertRaisesRegex(QuotaError, "active download"):
            await self.manager.remove(7, item)
        self.assertFalse(any(call[1] in ("PUT", "DELETE") for call in self.api.calls))

    async def test_delete_failure_does_not_refund_existing_file_size(self):
        item = (await self.manager.snapshot(7)).items[0]
        self.api.delete_error = APIError("Radarr", 500)
        with self.assertRaises(APIError):
            await self.manager.remove(7, item)
        self.assertEqual((await self.manager.snapshot(7)).used, 480 * GB)

    async def test_deletion_stops_monitoring_and_frees_space_without_ghost_reservation(self):
        self.api.records[99] = request(99, status=2, tmdb_id=1001)
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.remove(7, item)
        changes = [call for call in self.api.calls if call[1] in ("PUT", "DELETE")]
        self.assertEqual(changes[0][1:3], ("PUT", "/movie/11"))
        self.assertFalse(changes[0][4]["monitored"])
        self.assertEqual(changes[1][3]["deleteFiles"], "true")
        snapshot = await QuotaManager(self.api, self.config).snapshot(7)
        self.assertEqual((snapshot.used, snapshot.reserved), (0, 0))
        self.assertTrue((await self.manager.auto_approve(7, 1)).approved)

    async def test_file_spanning_another_season_is_not_deleted(self):
        self.api.add_shared_series()
        item = next(i for i in (await self.manager.snapshot(7)).items if i.media_type == "tv")
        self.api.episodes.append({"id": 203, "seasonNumber": 2, "hasFile": True, "episodeFileId": 101})
        with self.assertRaisesRegex(QuotaError, "another season"):
            await self.manager.remove(7, item)
        self.assertFalse(any(call[1] in ("PUT", "DELETE") for call in self.api.calls))

    async def test_admin_keeps_movie_without_changing_files_tags_requests_or_monitoring(self):
        self.api.records[99] = request(99, status=5, tmdb_id=1001)
        before = copy.deepcopy((self.api.movies, self.api.records))
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        restarted = QuotaManager(self.api, self.config)
        snapshot = await restarted.snapshot(7)
        self.assertEqual((snapshot.used, snapshot.reserved), (0, 0))
        self.assertEqual(snapshot.items, [])
        self.assertEqual(len(snapshot.retained_items), 1)
        self.assertEqual(snapshot.retained_items[0].size, 480 * GB)
        self.assertEqual((self.api.movies, self.api.records), before)
        with self.assertRaises(QuotaError):
            await restarted.remove(7, item)
        self.assertTrue(all(call[1] == "GET" for call in self.api.calls))
        self.assertEqual(self.api.approvals, [])

    async def test_retained_movie_stays_exempt_after_file_upgrade_and_tag_rename(self):
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        self.api.tags[0]["label"] = "7-new-name"
        self.api.movies[0]["id"] = 123
        self.api.movies[0]["sizeOnDisk"] = 600 * GB
        self.assertEqual((await self.manager.snapshot(7)).used, 0)
        self.assertTrue((await self.manager.auto_approve(7, 1)).approved)

    async def test_retention_does_not_follow_reused_arr_id_to_a_different_movie(self):
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        self.api.movies[0]["tmdbId"] = 999
        self.assertEqual((await self.manager.snapshot(7)).used, 480 * GB)

    async def test_retention_only_applies_on_the_selected_server(self):
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        self.api.server_list[0] = replace(self.api.server_list[0], id=1)
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.used, 480 * GB)
        self.assertTrue(snapshot.items[0].removable)

    async def test_existing_quota_database_gains_retention_without_losing_state(self):
        connection = sqlite3.connect(self.config.state_file)
        try:
            with connection:
                connection.execute(
                    "CREATE TABLE approvals (request_id INTEGER PRIMARY KEY, user_id INTEGER, bytes INTEGER)"
                )
                connection.execute("INSERT INTO approvals VALUES (1, 7, ?)", (20 * GB,))
                connection.execute(
                    "CREATE TABLE removed_units (request_id INTEGER, season INTEGER, PRIMARY KEY (request_id, season))"
                )
                connection.execute("INSERT INTO removed_units VALUES (99, 1)")
        finally:
            connection.close()
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        self.assertEqual(self.manager.journal.pending(7), {1: 20 * GB})
        self.assertEqual(self.manager.journal.removed_units(), {(99, 1)})
        self.assertEqual(len(self.manager.journal.retained_items()), 1)

    async def test_admin_revalidates_identity_and_owner_before_retaining(self):
        item = (await self.manager.snapshot(7)).items[0]
        self.api.movies[0]["tmdbId"] = 999
        with self.assertRaisesRegex(QuotaError, "changed"):
            await self.manager.retain(7, item, 100)
        self.api.movies[0]["tmdbId"] = item.tmdb_id
        self.api.movies[0]["tags"] = [80]
        with self.assertRaises(QuotaError):
            await self.manager.retain(7, item, 100)
        self.assertEqual(self.manager.journal.retained_items(), [])

    async def test_shared_movie_only_releases_target_quota_and_is_protected_from_other_user(self):
        self.api.movies[0]["tags"] = [70, 80]
        item = (await self.manager.snapshot(7)).items[0]
        await self.manager.retain(7, item, 100)
        self.assertEqual((await self.manager.snapshot(7)).used, 0)
        # Even if the retained user's original attribution disappears, the files stay protected.
        self.api.movies[0]["tags"] = [80]
        snapshot = await self.manager.snapshot(8)
        self.assertEqual(snapshot.used, 480 * GB)
        self.assertFalse(snapshot.items[0].removable)
        with self.assertRaisesRegex(QuotaError, "administrator"):
            await self.manager.remove(8, snapshot.items[0])
        self.assertTrue(all(call[1] == "GET" for call in self.api.calls))

    async def test_retained_season_releases_missing_episodes_but_not_other_seasons(self):
        self.api.add_shared_series()
        self.api.records[10]["seasons"].append({"seasonNumber": 2})
        self.api.records[10]["status"] = 2
        self.api.episodes.extend([
            {"id": 203, "seasonNumber": 1, "hasFile": False},
            {"id": 204, "seasonNumber": 2, "hasFile": False},
        ])
        before = copy.deepcopy((self.api.files, self.api.series, self.api.episodes))
        item = next(i for i in (await self.manager.snapshot(7)).items if i.season == 1)
        await self.manager.retain(7, item, 100)
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.used, 520 * GB)
        self.assertEqual(snapshot.reserved, 2 * GB)
        self.assertEqual((self.api.files, self.api.series, self.api.episodes), before)

    async def test_keeping_whole_show_exempts_future_seasons_and_replaces_season_exceptions(self):
        self.api.add_shared_series()
        self.api.records[10]["seasons"].append({"seasonNumber": 2})
        item = next(i for i in (await self.manager.snapshot(7)).items if i.season == 1)
        await self.manager.retain(7, item, 100)
        item = next(i for i in (await self.manager.snapshot(7)).items if i.season == 2)
        await self.manager.retain(7, item, 100, whole_series=True)
        self.api.files.append({"id": 103, "seasonNumber": 3, "size": 90 * GB})
        self.api.episodes.append({"id": 205, "seasonNumber": 3, "hasFile": False})
        self.api.records[30] = request(30, kind="tv", status=2, seasons=[3], tmdb_id=500)
        snapshot = await self.manager.snapshot(7)
        self.assertEqual((snapshot.used, snapshot.reserved), (480 * GB, 0))
        self.assertEqual(len(snapshot.retained_items), 1)
        self.assertEqual(snapshot.retained_items[0].season, -1)
        other = await self.manager.snapshot(8)
        self.assertEqual(other.used, 40 * GB)
        self.assertFalse(other.items[0].removable)
        self.assertTrue(all(call[1] == "GET" for call in self.api.calls))

    async def test_restoring_quota_charges_actual_size_again_without_touching_files(self):
        item = (await self.manager.snapshot(7)).items[0]
        kept = await self.manager.retain(7, item, 100)
        self.api.movies[0]["sizeOnDisk"] = 510 * GB
        await self.manager.restore_retained(7, kept, 100)
        snapshot = await self.manager.snapshot(7)
        self.assertEqual(snapshot.used, 510 * GB)
        self.assertTrue(snapshot.items[0].removable)
        self.assertEqual(snapshot.retained_items, [])
        self.assertFalse((await self.manager.auto_approve(7, 1)).approved)
        self.assertTrue(all(call[1] == "GET" for call in self.api.calls))

    async def test_restoring_one_user_keeps_another_users_retention_protection(self):
        self.api.movies[0]["tags"] = [70, 80]
        item = (await self.manager.snapshot(7)).items[0]
        kept = await self.manager.retain(7, item, 100)
        other = (await self.manager.snapshot(8)).items[0]
        await self.manager.retain(8, other, 100)
        with self.assertRaises(QuotaError):
            await self.manager.restore_retained(8, kept, 100)
        await self.manager.restore_retained(7, kept, 100)
        self.assertFalse((await self.manager.snapshot(7)).items[0].removable)
        self.assertEqual((await self.manager.snapshot(8)).used, 0)

    async def test_pending_request_for_retained_show_reserves_no_new_space(self):
        self.api.add_shared_series()
        item = next(i for i in (await self.manager.snapshot(7)).items if i.season == 1)
        await self.manager.retain(7, item, 100, whole_series=True)
        self.api.records[30] = request(30, kind="tv", seasons=[3], tmdb_id=500)
        self.assertTrue((await self.manager.auto_approve(7, 30)).approved)
        self.assertEqual((await self.manager.snapshot(7)).reserved, 0)

    async def test_retention_releases_uncertain_reservation_without_allowing_duplicate_approval(self):
        self.api.add_shared_series()
        self.api.records[30] = request(30, kind="tv", seasons=[1], tmdb_id=500)
        self.manager.journal.reserve(30, 7, 20 * GB)
        item = next(i for i in (await self.manager.snapshot(7)).items if i.season == 1)
        await self.manager.retain(7, item, 100)
        self.assertEqual((await self.manager.snapshot(7)).reserved, 0)
        self.assertFalse((await self.manager.auto_approve(7, 30)).approved)
        self.assertEqual(self.api.approvals, [])


class QuotaAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_request_pagination_includes_completed_requests(self):
        api = QuotaAPI(SimpleNamespace())
        rows = [request(i, status=5) for i in range(1, 202)]
        api.seerr = AsyncMock(side_effect=[{"results": rows[:100]}, {"results": rows[100:200]}, {"results": rows[200:]}])
        self.assertEqual(len(await api.requests()), 201)
        self.assertEqual([call.kwargs["params"]["skip"] for call in api.seerr.await_args_list], [0, 100, 200])
        self.assertEqual(Request(rows[0]).status, 5)

    async def test_servers_discovered_with_zero_id_base_url_and_override(self):
        api = QuotaAPI(SimpleNamespace(), {"sonarr:0": "http://sonarr-proxy/sonarr"})
        api.seerr = AsyncMock(side_effect=[[
            {"id": 0, "name": "Films", "hostname": "radarr", "port": 7878,
             "useSsl": True, "baseUrl": "/radarr", "apiKey": "hidden", "isDefault": True}
        ], [{"id": 0, "apiKey": "other-hidden", "isDefault": True}]])
        servers = await api.servers()
        self.assertEqual(servers[0].url, "https://radarr:7878/radarr")
        self.assertEqual(servers[1].url, "http://sonarr-proxy/sonarr")
        self.assertNotIn("hidden", repr(servers))

    async def test_http_delete_accepts_empty_204_and_sends_only_service_key(self):
        response = SimpleNamespace(status=204, json=AsyncMock(), read=AsyncMock())
        response_context = AsyncMock()
        response_context.__aenter__.return_value = response
        session = Mock(request=Mock(return_value=response_context))
        session_context = AsyncMock()
        session_context.__aenter__.return_value = session
        with patch("quota.api.aiohttp.ClientSession", return_value=session_context) as factory:
            self.assertIsNone(await request_json("DELETE", "http://radarr/api/v3/movie/1", api_key="key", service="Radarr"))
        self.assertEqual(factory.call_args.kwargs["headers"], {"X-Api-Key": "key"})
        self.assertFalse(session.request.call_args.kwargs["allow_redirects"])
        response.json.assert_not_awaited()


def interaction(user_id=100):
    return SimpleNamespace(user=SimpleNamespace(id=user_id), response=SimpleNamespace(
        defer=AsyncMock(), edit_message=AsyncMock(), send_message=AsyncMock()), edit_original_response=AsyncMock())


class QuotaViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.item = StorageItem("radarr:0:11", "Movie", None, 11, "movie", 1001, None, None, 30 * GB,
                                frozenset({7}), (), True)
        self.snapshot = Snapshot(7, 500 * GB, 30 * GB, 0, [self.item], [])
        self.manager = SimpleNamespace(snapshot=AsyncMock(return_value=self.snapshot),
                                       remove=AsyncMock(return_value=30 * GB),
                                       auto_approve=AsyncMock(return_value=Approval(True, "Approved")), enabled=True)
        self.manager.api = SimpleNamespace(seerr=AsyncMock(return_value={"title": "Pending movie"}))

    async def test_only_original_discord_user_can_use_controls(self):
        view = StorageView(self.manager, 100, 7)
        self.addCleanup(view.stop)
        click = interaction(200)
        self.assertFalse(await view.interaction_check(click))
        click.response.send_message.assert_awaited_once()
        self.assertTrue(await view.interaction_check(interaction()))

    async def test_selection_requires_confirmation_and_deletion_retries_existing_request(self):
        view = StorageView(self.manager, 100, 7, 42)
        self.addCleanup(view.stop)
        await view.load()
        click = interaction()
        with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=[self.item.key]):
            await view.select_download(click)
        self.manager.remove.assert_not_awaited()
        confirmation = click.response.edit_message.call_args.kwargs["view"]
        self.addCleanup(confirmation.stop)
        self.assertIsInstance(confirmation, RemoveConfirmation)
        confirm_click = interaction()
        await confirmation.confirm.callback(confirm_click)
        self.manager.remove.assert_awaited_once_with(7, self.item)
        self.manager.auto_approve.assert_awaited_once_with(7, 42)
        next_view = confirm_click.edit_original_response.call_args.kwargs["view"]
        self.addCleanup(next_view.stop)
        self.assertTrue(next_view.retry.disabled)
        await confirmation.confirm.callback(interaction())
        self.manager.remove.assert_awaited_once()

    async def test_cancel_does_not_delete_or_approve(self):
        view = RemoveConfirmation(self.manager, 100, 7, 42, self.item)
        self.addCleanup(view.stop)
        click = interaction()
        await view.cancel.callback(click)
        self.addCleanup(click.edit_original_response.call_args.kwargs["view"].stop)
        self.manager.remove.assert_not_awaited()
        self.manager.auto_approve.assert_not_awaited()

    async def test_pending_requests_are_owned_paginated_and_retry_without_resubmitting(self):
        requests = [request(i) for i in range(1, 28)] + [request(50, user_id=8), request(60, status=2)]
        view = PendingRequestsView(self.manager, 100, 7)
        self.addCleanup(view.stop)
        await view.load(requests)
        self.assertEqual(len(view.requests), 27)
        self.assertEqual(len(view.selector.options), 10)
        self.assertTrue(view.previous.disabled)
        await view.next.callback(interaction())
        await view.next.callback(interaction())
        self.assertEqual(len(view.selector.options), 7)
        self.assertTrue(view.next.disabled)
        click = interaction()
        with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=["27"]):
            await view.select_request(click)
        self.manager.auto_approve.assert_awaited_once_with(7, 27)
        next_view = click.edit_original_response.call_args.kwargs["view"]
        self.addCleanup(next_view.stop)
        self.assertIsInstance(next_view, StorageView)
        self.assertTrue(next_view.retry.disabled)

    async def test_search_creates_and_assigns_before_quota_approval(self):
        events = []
        async def create(**kwargs):
            events.append("created-and-assigned")
            return Request(request(42))
        async def approve(user_id, request_id):
            events.append("quota-approval")
            self.assertEqual((user_id, request_id), (7, 42))
            return Approval(False, "Allowance full")
        client = SimpleNamespace(post_request=AsyncMock(side_effect=create))
        self.manager.auto_approve.side_effect = approve
        view = SearchView(client, "Movie", 100,
            MediaSearchResult({"page": 1, "totalPages": 1, "totalResults": 1,
                               "results": [{"id": 142, "mediaType": "movie", "title": "Movie"}]}),
            {"movie": {}, "tv": {}}, {100: 7}, quota_manager=self.manager)
        self.addCleanup(view.stop)
        view.embed.title = "Movie"
        click = interaction()
        await view.request.callback(click)
        self.assertEqual(events, ["created-and-assigned", "quota-approval"])
        actions = click.edit_original_response.call_args.kwargs["view"]
        self.addCleanup(actions.stop)
        self.assertIsInstance(actions, QuotaActionsView)
        self.assertFalse(actions.retry.disabled)


if __name__ == "__main__":
    unittest.main()
