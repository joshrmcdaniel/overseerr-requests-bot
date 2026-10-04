import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from overseerrapi import OverseerrAPI
from overseerrapi.types import ErrorResponse, Request, RequestAttributionError
from quota.api import QuotaAPI


def request_payload(media_type="movie", owner=7, **overrides):
    return {
        "id": 42,
        "status": 1,
        "type": media_type,
        "media": {"mediaType": media_type, "tmdbId": 123},
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "requestedBy": {"id": owner},
        "is4k": False,
        "serverId": None,
        "profileId": None,
        "rootFolder": None,
        "tags": None,
        **overrides,
    }


class RequestAttributionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = OverseerrAPI(
            "https://example.invalid/api/v1",
            api_key="test-key",
            log_file=io.StringIO(),
        )

    async def submit(self, media_type="movie", **kwargs):
        return await self.client.post_request(
            media_id=123, media_type=media_type, user_id=7, **kwargs
        )

    async def test_movie_is_created_directly_as_user_without_cookie_or_edit(self):
        created = request_payload(serverId=0, profileId=5, rootFolder="/movies", tags=[])
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.shared.networking.put", new_callable=AsyncMock) as put,
        ):
            post.return_value = created
            result = await self.submit()
            post.assert_awaited_once_with(
                "https://example.invalid/api/v1/request",
                body={"mediaId": 123, "mediaType": "movie"},
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": "test-key",
                    "X-API-User": "7",
                },
            )
            put.assert_not_awaited()
            self.assertIsInstance(result, Request)
            self.assertEqual(result.requested_by.id, 7)
            self.assertEqual(result.status, 1)
            self.assertEqual(result.server_id, 0)
            self.assertEqual(result.profile_id, 5)
            self.assertEqual(result.root_folder, "/movies")
            self.assertNotIn("X-API-User", self.client._headers)

    async def test_tv_creation_preserves_season_selection(self):
        for selection in ("all", [0, 1, 2]):
            with (
                self.subTest(selection=selection),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                post.return_value = request_payload(
                    "tv", seasons=[{"seasonNumber": 0}, {"seasonNumber": 2}]
                )
                result = await self.submit("tv", seasons=selection)
                self.assertIsInstance(result, Request)
                self.assertEqual(result.status, 1)
                self.assertEqual(result.requested_by.id, 7)
                self.assertEqual(post.call_args.kwargs["body"], {
                    "mediaId": 123, "mediaType": "tv", "seasons": selection,
                })
                self.assertEqual(post.call_args.kwargs["headers"]["X-API-User"], "7")
                post.assert_awaited_once()

    async def test_invalid_user_id_stops_before_creation(self):
        for user_id in (0, -1, "7", True, 7.5):
            with (
                self.subTest(user_id=user_id),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                result = await self.client.post_request(123, "movie", user_id=user_id)
                self.assertIsInstance(result, ErrorResponse)
                self.assertIn("valid Seerr user ID", result.message)
                post.assert_not_awaited()

    async def test_failed_creation_never_retries_as_admin(self):
        for message in ("User not found", "Permission denied", "Movie Quota exceeded."):
            error = ErrorResponse(message=message)
            with (
                self.subTest(message=message),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                post.return_value = error
                self.assertIs(await self.submit(), error)
                post.assert_awaited_once()
                self.assertEqual(post.call_args.kwargs["headers"]["X-API-User"], "7")

    async def test_seerr_native_approval_is_returned_without_reassignment(self):
        with patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post:
            post.return_value = request_payload(status=2)
            result = await self.submit()
            self.assertIsInstance(result, Request)
            self.assertEqual(result.requested_by.id, 7)
            self.assertEqual(result.status, 2)
            post.assert_awaited_once()

    async def test_wrong_requester_preserves_created_id_without_retry(self):
        with patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post:
            post.return_value = request_payload(owner=1, status=2)
            with self.assertLogs("overseerrapi.api.client", level="ERROR"):
                result = await self.submit()
            self.assertIsInstance(result, RequestAttributionError)
            self.assertEqual(result.request_id, 42)
            self.assertIn("expected requester", result.message)
            post.assert_awaited_once()

    async def test_incomplete_creation_response_is_not_resubmitted(self):
        for payload, request_id in ((None, None), ({}, None), ({"id": 42}, 42)):
            with (
                self.subTest(payload=payload),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                post.return_value = payload
                with self.assertLogs("overseerrapi.api.client", level="ERROR"):
                    result = await self.submit()
                self.assertIsInstance(result, RequestAttributionError)
                self.assertEqual(result.request_id, request_id)
                post.assert_awaited_once()

    async def test_concurrent_requests_do_not_leak_user_into_other_requests_or_approvals(self):
        calls = []

        async def send(url, *, headers, body=None):
            calls.append((url, headers))
            await asyncio.sleep(0)
            if url.endswith("/approve"):
                return request_payload(status=2)
            return request_payload(owner=int(headers["X-API-User"]))

        with (
            patch("overseerrapi.api.client.post", side_effect=send),
            patch("overseerrapi.api.client.get", new_callable=AsyncMock) as get,
        ):
            first, second, approved = await asyncio.gather(
                self.client.post_request(123, "movie", user_id=7),
                self.client.post_request(456, "movie", user_id=8),
                self.client.approve_request(42),
            )
            self.assertEqual(first.requested_by.id, 7)
            self.assertEqual(second.requested_by.id, 8)
            self.assertEqual(approved.status, 2)
            approval_headers = next(headers for url, headers in calls if url.endswith("/approve"))
            self.assertEqual(approval_headers, {
                "Content-Type": "application/json", "X-Api-Key": "test-key",
            })
            get.return_value = {"results": [{"id": 7}, {"id": 8}]}
            await self.client.users()
            self.assertEqual(get.call_args.kwargs["headers"], approval_headers)
            self.assertNotIn("cookies", get.call_args.kwargs)

    async def test_quota_approval_uses_admin_key_after_user_creation(self):
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("quota.api.request_json", new_callable=AsyncMock) as request_json,
        ):
            post.return_value = request_payload()
            created = await self.submit()
            request_json.return_value = request_payload(status=2)
            result = await QuotaAPI(self.client).approve(created.id)
            self.assertEqual(result["status"], 2)
            request_json.assert_awaited_once_with(
                "POST", "https://example.invalid/api/v1/request/42/approve",
                api_key="test-key", service="Seerr", params=None, body=None,
            )


if __name__ == "__main__":
    unittest.main()
