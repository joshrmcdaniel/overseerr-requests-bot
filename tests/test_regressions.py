import asyncio
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from overseerrapi import OverseerrAPI
from overseerrapi.api.client import setup_logging
from overseerrapi.shared.networking import DECODER
from overseerrapi.types import (
    ErrorResponse,
    MediaSearchResult,
    MovieDetails,
    MovieResult,
    PersonResult,
    Requests,
    RequestAssignmentError,
    TvResult,
)
from views import RequestsView, SearchView


def search_payload(total=25, page=1):
    return {
        "page": page,
        "totalPages": (total + 19) // 20,
        "totalResults": total,
        "results": [
            {"id": i, "mediaType": "movie", "title": f"Movie {i}"}
            for i in range((page - 1) * 20 + 1, min(page * 20, total) + 1)
        ],
    }


def requests_payload(total=25, take=20, skip=0):
    return {
        "pageInfo": {
            "page": skip // take + 1,
            "pageSize": take,
            "pages": (total + take - 1) // take,
            "results": total,
        },
        "results": [
            {
                "id": i,
                "status": 1,
                "media": {"mediaType": "movie", "tmdbId": i},
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-01T00:00:00Z",
                "requestedBy": {"id": 1},
            }
            for i in range(skip + 1, min(skip + take, total) + 1)
        ],
    }


def interaction():
    return SimpleNamespace(
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(defer=AsyncMock(), edit_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )


class DataRegressionTests(unittest.TestCase):
    def test_decoder_preserves_falsy_values_and_normalizes_empty_dates(self):
        decoded = DECODER(
            '{"adult":false,"voteCount":0,"results":[],"metadata":{},'
            '"releaseDate":"","nested":{"count":0,"date":""}}'
        )
        self.assertIs(decoded["adult"], False)
        self.assertEqual(decoded["voteCount"], 0)
        self.assertEqual(decoded["results"], [])
        self.assertEqual(decoded["metadata"], {})
        self.assertIsNone(decoded["releaseDate"])
        self.assertEqual(decoded["nested"], {"count": 0, "date": None})

    def test_mixed_search_results_have_typed_fields_and_serialize(self):
        payload = {
            "page": 1,
            "totalPages": 1,
            "totalResults": 3,
            "results": [
                {
                    "id": 1,
                    "mediaType": "movie",
                    "title": "Movie",
                    "releaseDate": "",
                    "mediaInfo": {"status": 5},
                },
                {"id": 2, "mediaType": "tv", "name": "Show"},
                {"id": 3, "mediaType": "person", "name": "Actor"},
            ],
        }
        response = MediaSearchResult(DECODER(json.dumps(payload)))
        self.assertEqual(
            [type(result) for result in response.results],
            [MovieResult, TvResult, PersonResult],
        )
        self.assertEqual(response.results[0].media_info.status, 5)
        self.assertIsNone(response.results[0].release_date)
        restored = MediaSearchResult(response.to_json())
        self.assertEqual(
            [result.media_type for result in restored.results],
            ["movie", "tv", "person"],
        )


class AuthenticationRegressionTests(unittest.TestCase):
    def test_api_key_only_authenticates_search_request_and_approval(self):
        client = OverseerrAPI(
            "https://example.invalid/api/v1", api_key="test-key", log_file=io.StringIO()
        )
        with (
            patch("overseerrapi.api.client.get", new_callable=AsyncMock) as get,
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
        ):
            get.return_value = search_payload(total=1)
            results = asyncio.run(client.search("movie"))
            self.assertIsInstance(results.results[0], MovieResult)
            self.assertEqual(get.call_args.kwargs["headers"]["X-Api-Key"], "test-key")
            self.assertEqual(get.call_args.kwargs["cookies"], {})

            post.return_value = requests_payload(total=1)["results"][0]
            asyncio.run(client.post_request(media_id=1, media_type="movie"))
            self.assertEqual(post.call_args.kwargs["headers"]["X-Api-Key"], "test-key")
            asyncio.run(client.approve_request(1))
            self.assertEqual(post.call_args.kwargs["headers"]["X-Api-Key"], "test-key")

    def test_user_credentials_keep_session_permissions_for_requests(self):
        login_response = SimpleNamespace(
            raise_for_status=Mock(), cookies={"connect.sid": "test-session"}
        )
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            redirect_stdout(io.StringIO()),
        ):
            post.return_value = login_response
            client = OverseerrAPI(
                "https://example.invalid/api/v1",
                email="bot@example.invalid",
                password="test-password",
                api_key="test-key",
                log_file=io.StringIO(),
            )
            self.assertNotIn("X-Api-Key", post.call_args.kwargs["headers"])
            post.return_value = requests_payload(total=1)["results"][0]
            asyncio.run(client.post_request(media_id=1, media_type="movie"))
            self.assertNotIn("X-Api-Key", post.call_args.kwargs["headers"])
            self.assertEqual(
                post.call_args.kwargs["cookies"], {"connect.sid": "test-session"}
            )
            asyncio.run(client.approve_request(1))
            self.assertEqual(post.call_args.kwargs["headers"]["X-Api-Key"], "test-key")


class ViewRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        setup_logging()
        self.client = SimpleNamespace(
            search=AsyncMock(),
            get_all_requests=AsyncMock(),
            get_movie=AsyncMock(
                side_effect=lambda media_id: MovieDetails(
                    {"id": media_id, "title": f"Movie {media_id}"}
                )
            ),
            post_request=AsyncMock(),
            approve_request=AsyncMock(),
            deny_request=AsyncMock(),
        )

    def search_view(self, total=25, page=1, payload=None):
        if payload is None:
            payload = search_payload(total, page)
        results = MediaSearchResult(DECODER(json.dumps(payload)))
        view = SearchView(
            overseerr_client=self.client,
            search_query="movie",
            user_id=1,
            results=results,
            genre_id_map={"movie": {}, "tv": {}},
            discord_id_map={1: 7},
        )
        self.addCleanup(view.stop)
        return view

    def requests_view(self, total=25, take=20, skip=0):
        requests = Requests(DECODER(json.dumps(requests_payload(total, take, skip))))
        view = RequestsView(
            requests=requests,
            overseerr_client=self.client,
            genre_id_map={"movie": {}, "tv": {}},
            discord_id_map={},
            user_id=1,
            params={"take": take, "skip": skip, "filter_by": "pending", "sort": "added"},
        )
        self.addCleanup(view.stop)
        return view

    async def test_search_renders_each_media_type_and_disables_person_requests(self):
        for media_type, title in [
            ("movie", "Film"), ("tv", "Show"), ("person", "Actor")
        ]:
            with self.subTest(media_type=media_type):
                payload = search_payload(total=1)
                payload["results"] = [
                    {"id": 1, "mediaType": media_type, "title": title, "name": title}
                ]
                view = self.search_view(payload=payload)
                await view._edit_embed()
                self.assertEqual(view.embed.title, title)
                self.assertEqual(view.request.disabled, media_type == "person")
                self.assertTrue(view.previous.disabled)
                self.assertTrue(view.next.disabled)

    async def test_empty_search_renders_no_results(self):
        view = self.search_view(total=0)
        await view._edit_embed()
        self.assertEqual(view.embed.title, "No Results Found")
        self.assertEqual(view.children, [])
        self.assertTrue(view.is_finished())

    async def test_removed_media_and_missing_tv_seasons_can_be_requested_again(self):
        for kind, status, enabled in (
            ("movie", 7, True), ("tv", 7, True), ("tv", 4, True),
            ("movie", 4, False), ("movie", 5, False), ("tv", 6, False),
        ):
            with self.subTest(kind=kind, status=status):
                payload = search_payload(total=1)
                payload["results"] = [{
                    "id": 1, "mediaType": kind, "title": "Film", "name": "Show",
                    "mediaInfo": {"status": status},
                }]
                view = self.search_view(payload=payload)
                await view._edit_embed()
                self.assertEqual(view.request.disabled, not enabled)

    async def test_empty_request_queue_and_offset_beyond_end_render_no_requests(self):
        for total, skip in [(0, 0), (5, 20)]:
            with self.subTest(total=total, skip=skip):
                view = self.requests_view(total=total, skip=skip)
                await view._edit_embed()
                self.assertEqual(view.embed.title, "No requests")
                self.assertEqual(view.children, [])
                self.assertTrue(view.is_finished())

    async def test_search_paginates_both_ways_without_skips_or_overruns(self):
        for total in [1, 20, 21, 40, 45]:
            with self.subTest(total=total):
                self.client.search.side_effect = lambda query, page: MediaSearchResult(
                    search_payload(total, page)
                )
                view = self.search_view(total=total)
                await view._edit_embed()
                for expected_id in range(1, total + 1):
                    self.assertEqual(view.result.id, expected_id)
                    self.assertEqual(view.result_number, expected_id)
                    self.assertEqual(view.next.disabled, expected_id == total)
                    await view.next.callback(interaction())
                self.assertEqual(view.result.id, total)
                for expected_id in range(total, 0, -1):
                    self.assertEqual(view.result.id, expected_id)
                    self.assertEqual(view.previous.disabled, expected_id == 1)
                    await view.previous.callback(interaction())
                self.assertEqual(view.result.id, 1)

    async def test_search_can_start_on_last_page_and_go_back(self):
        self.client.search.return_value = MediaSearchResult(search_payload(25, 1))
        view = self.search_view(total=25, page=2)
        await view._edit_embed()
        await view.previous.callback(interaction())
        self.assertEqual(view.result.id, 20)
        self.assertEqual(view.result_number, 20)
        self.client.search.assert_awaited_once_with("movie", page=1)

    async def test_requests_pagination_respects_custom_sizes_and_offsets(self):
        for total, take, skip in [
            (45, 20, 0), (25, 10, 0), (24, 7, 3), (31, 20, 7), (3, 1, 0)
        ]:
            with self.subTest(total=total, take=take, skip=skip):
                self.client.get_all_requests.side_effect = lambda **params: Requests(
                    requests_payload(total, params["take"], params["skip"])
                )
                view = self.requests_view(total=total, take=take, skip=skip)
                await view._edit_embed()
                for expected_id in range(skip + 1, total + 1):
                    self.assertEqual(view.request.id, expected_id)
                    self.assertEqual(view.result_number, expected_id)
                    self.assertEqual(view.next.disabled, expected_id == total)
                    await view.next.callback(interaction())
                self.assertEqual(view.request.id, total)
                for expected_id in range(total, 0, -1):
                    self.assertEqual(view.request.id, expected_id)
                    self.assertEqual(view.result_number, expected_id)
                    self.assertEqual(view.previous.disabled, expected_id == 1)
                    await view.previous.callback(interaction())
                self.assertEqual(view.request.id, 1)

    async def test_failed_search_page_fetch_preserves_position_and_allows_retry(self):
        view = self.search_view()
        view._index = 19
        await view._edit_embed()
        self.client.search.return_value = ErrorResponse({"message": "Try again"})
        first_click = interaction()
        await view.next.callback(first_click)
        first_click.response.defer.assert_awaited_once()
        self.assertEqual(view.result.id, 20)
        self.assertIn(
            "Try again", first_click.edit_original_response.call_args.kwargs["content"]
        )
        self.assertFalse(view.next.disabled)
        self.client.search.return_value = MediaSearchResult(search_payload(25, 2))
        await view.next.callback(interaction())
        self.assertEqual(view.result.id, 21)

    async def test_failed_requests_page_fetch_preserves_offset_and_allows_retry(self):
        view = self.requests_view()
        view._index = 19
        await view._edit_embed()
        self.client.get_all_requests.return_value = ErrorResponse(
            {"message": "Try again"}
        )
        first_click = interaction()
        await view.next.callback(first_click)
        first_click.response.defer.assert_awaited_once()
        self.assertEqual(view.request.id, 20)
        self.assertEqual(view.result_number, 20)
        self.assertIn(
            "Try again", first_click.edit_original_response.call_args.kwargs["content"]
        )
        self.assertFalse(view.next.disabled)
        self.client.get_all_requests.return_value = Requests(
            requests_payload(25, 20, 20)
        )
        await view.next.callback(interaction())
        self.assertEqual(view.request.id, 21)
        self.assertEqual(view.result_number, 21)
        self.assertEqual(self.client.get_all_requests.call_args.kwargs["skip"], 20)

    async def test_assignment_failure_shows_created_id_and_prevents_resubmission(self):
        view = self.search_view(total=1)
        await view._edit_embed()
        self.client.post_request.return_value = RequestAssignmentError(
            request_id=42, message="Movie Quota exceeded."
        )
        first_click = interaction()
        await view.request.callback(first_click)
        content = first_click.edit_original_response.call_args.kwargs["content"]
        self.assertIn("was created (#42)", content)
        self.assertIn("Movie Quota exceeded.", content)
        self.assertNotIn("sent!", content)
        self.assertTrue(view.is_finished())
        self.assertEqual(view.children, [])

        repeated_click = interaction()
        await view.request.callback(repeated_click)
        repeated_click.response.defer.assert_awaited_once()
        self.client.post_request.assert_awaited_once()

    async def test_request_in_progress_ignores_a_second_click(self):
        view = self.search_view(total=1)
        await view._edit_embed()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def submit(**kwargs):
            started.set()
            await finish.wait()
            return Requests(requests_payload(total=1)).results[0]

        self.client.post_request.side_effect = submit
        first_click = asyncio.create_task(view.request.callback(interaction()))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            repeated_click = interaction()
            await view.request.callback(repeated_click)
            repeated_click.response.defer.assert_awaited_once()
            self.client.post_request.assert_awaited_once()
        finally:
            finish.set()
            await first_click

    async def test_failed_actions_report_error_and_can_be_retried_successfully(self):
        for callback, method, success in [
            ("request", "post_request", "sent! 🎉"),
            ("approve", "approve_request", "Approved! 🎉"),
            ("cancel", "deny_request", "denied"),
        ]:
            with self.subTest(action=method):
                view = (
                    self.search_view(total=1)
                    if callback == "request"
                    else self.requests_view(total=1)
                )
                await view._edit_embed()
                api_method = getattr(self.client, method)
                api_method.return_value = ErrorResponse(
                    {"message": "Permission denied"}
                )
                first_click = interaction()
                await getattr(view, callback).callback(first_click)
                content = first_click.edit_original_response.call_args.kwargs["content"]
                self.assertIn("could not complete the action", content)
                self.assertIn("Permission denied", content)
                self.assertFalse(view.is_finished())
                self.assertFalse(getattr(view, callback).disabled)
                if callback == "request":
                    self.assertEqual(api_method.call_args.kwargs["user_id"], 7)

                api_method.return_value = Requests(requests_payload(total=1)).results[0]
                retry = interaction()
                await getattr(view, callback).callback(retry)
                content = retry.edit_original_response.call_args.kwargs["content"]
                self.assertEqual(content, f"Request for Movie 1 {success}")
                self.assertTrue(view.is_finished())


if __name__ == "__main__":
    unittest.main()
