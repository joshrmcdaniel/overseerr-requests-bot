import asyncio
import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientConnectionError

from overseerrapi import OverseerrAPI
from overseerrapi.types import ErrorResponse, Request, RequestAssignmentError


def request_payload(media_type="movie", owner=99, **overrides):
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


class RequestAttributionTests(unittest.TestCase):
    def setUp(self):
        login_response = SimpleNamespace(
            raise_for_status=Mock(), cookies={"connect.sid": "service-session"}
        )
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            redirect_stdout(io.StringIO()),
        ):
            post.return_value = login_response
            self.client = OverseerrAPI(
                "https://example.invalid/api/v1",
                email="bot@example.invalid",
                password="test-password",
                api_key="test-key",
                log_file=io.StringIO(),
            )

    def submit(self, media_type="movie", **kwargs):
        return asyncio.run(
            self.client.post_request(
                media_id=123, media_type=media_type, user_id=7, **kwargs
            )
        )

    def test_movie_created_with_cookie_then_assigned_with_key(self):
        created = request_payload(serverId=0, profileId=5, rootFolder="/movies", tags=[])
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
        ):
            post.return_value = created

            async def assign(url, *, body, headers):
                post.assert_awaited_once_with(
                    "https://example.invalid/api/v1/request",
                    body={"mediaId": 123, "mediaType": "movie"},
                    headers={"Content-Type": "application/json"},
                    cookies={"connect.sid": "service-session"},
                )
                self.assertEqual(url, "https://example.invalid/api/v1/request/42")
                self.assertEqual(
                    headers,
                    {"Content-Type": "application/json", "X-Api-Key": "test-key"},
                )
                self.assertEqual(
                    body,
                    {
                        "mediaType": "movie",
                        "userId": 7,
                        "is4k": False,
                        "serverId": 0,
                        "profileId": 5,
                        "rootFolder": "/movies",
                        "tags": [],
                    },
                )
                return {**created, "requestedBy": {"id": 7}}

            put.side_effect = assign
            result = self.submit()
            self.assertIsInstance(result, Request)
            self.assertEqual(result.requested_by.id, 7)
            self.assertEqual(result.status, 1)
            post.assert_awaited_once()
            put.assert_awaited_once()
            self.assertEqual(self.client._cookies, {"connect.sid": "service-session"})
            self.assertNotIn("X-Api-Key", self.client._headers)

    def test_tv_edit_uses_only_created_seasons_and_preserves_settings(self):
        for selection in ("all", [0, 1, 2]):
            with (
                self.subTest(selection=selection),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
                patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
            ):
                created = request_payload(
                    "tv",
                    seasons=[{"seasonNumber": 0}, {"seasonNumber": 2}],
                    languageProfileId=4,
                    profileId=9,
                    tags=[3],
                )
                post.return_value = created
                put.return_value = {**created, "requestedBy": {"id": 7}}
                result = self.submit("tv", seasons=selection)
                self.assertIsInstance(result, Request)
                self.assertEqual(result.status, 1)
                self.assertEqual(post.call_args.kwargs["body"]["seasons"], selection)
                self.assertNotIn("userId", post.call_args.kwargs["body"])
                self.assertNotIn("X-Api-Key", post.call_args.kwargs["headers"])
                self.assertEqual(
                    put.call_args.kwargs["body"],
                    {
                        "mediaType": "tv",
                        "userId": 7,
                        "is4k": False,
                        "profileId": 9,
                        "tags": [3],
                        "seasons": [0, 2],
                        "languageProfileId": 4,
                    },
                )

    def test_missing_authentication_stops_before_creation(self):
        for cookies, key in (({}, "test-key"), ({"connect.sid": "session"}, None)):
            with (
                self.subTest(cookies=bool(cookies), key=bool(key)),
                patch.object(self.client, "_OverseerrAPI__cookies", cookies),
                patch.object(self.client, "_api_key", key),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
                patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
            ):
                result = self.submit()
                self.assertIsInstance(result, ErrorResponse)
                self.assertNotIsInstance(result, RequestAssignmentError)
                self.assertIn("session and an API key", result.message)
                post.assert_not_awaited()
                put.assert_not_awaited()

    def test_failed_creation_never_reassigns_or_falls_back_to_api_key(self):
        error = ErrorResponse(message="Session expired")
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
        ):
            post.return_value = error
            self.assertIs(self.submit(), error)
            post.assert_awaited_once()
            self.assertNotIn("X-Api-Key", post.call_args.kwargs["headers"])
            put.assert_not_awaited()

    def test_non_pending_creation_reports_existing_request_without_editing(self):
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
        ):
            post.return_value = request_payload(status=2)
            result = self.submit()
            self.assertIsInstance(result, RequestAssignmentError)
            self.assertEqual(result.request_id, 42)
            self.assertIn("Only pending requests", result.message)
            put.assert_not_awaited()

    def test_reassignment_rejection_preserves_request_id_and_reason(self):
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
        ):
            post.return_value = request_payload()
            put.return_value = ErrorResponse(message="Movie Quota exceeded.")
            result = self.submit()
            self.assertIsInstance(result, RequestAssignmentError)
            self.assertEqual(result.request_id, 42)
            self.assertEqual(result.message, "Movie Quota exceeded.")
            post.assert_awaited_once()
            put.assert_awaited_once()

    def test_uncertain_reassignment_does_not_lose_created_request_id(self):
        outcomes = [
            TimeoutError(),
            ClientConnectionError("Connection lost"),
            None,
            {"id": 42},
            request_payload(owner=99),
            request_payload(owner=7, id=43),
            request_payload(owner=7, status=2),
        ]
        for outcome in outcomes:
            with (
                self.subTest(outcome=outcome),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
                patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
            ):
                post.return_value = request_payload()
                if isinstance(outcome, Exception):
                    put.side_effect = outcome
                else:
                    put.return_value = outcome
                result = self.submit()
                self.assertIsInstance(result, RequestAssignmentError)
                self.assertEqual(result.request_id, 42)
                self.assertTrue(result.message)
                post.assert_awaited_once()

    def test_tv_without_returned_seasons_is_not_edited(self):
        for seasons in (None, [], [{}]):
            with (
                self.subTest(seasons=seasons),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
                patch("overseerrapi.api.client.put", new_callable=AsyncMock) as put,
            ):
                post.return_value = request_payload("tv", seasons=seasons)
                result = self.submit("tv")
                self.assertIsInstance(result, RequestAssignmentError)
                self.assertEqual(result.request_id, 42)
                put.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
