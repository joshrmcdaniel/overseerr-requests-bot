import asyncio
import io
import os
import unittest
from contextlib import redirect_stdout
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientConnectionError, ClientResponseError

from overseerrapi import OverseerrAPI

with patch.dict(os.environ, {"GUILD_ID": "1"}):
    from overseerr import Overseerr


def login_response(cookie="old-session"):
    cookies = SimpleCookie()
    if cookie is not None:
        cookies["connect.sid"] = cookie
    return SimpleNamespace(raise_for_status=Mock(), cookies=cookies)


class CookieRefreshTests(unittest.TestCase):
    def setUp(self):
        response = login_response()
        self.old_cookies = response.cookies
        with patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post:
            post.return_value = response
            self.client = OverseerrAPI(
                "https://example.invalid/api/v1",
                email="bot@example.invalid",
                password="test-password",
                api_key="test-key",
                log_file=io.StringIO(),
            )

    def test_refresh_replaces_cookie_used_by_subsequent_calls(self):
        replacement = login_response("new-session")
        output = io.StringIO()
        with (
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.get", new_callable=AsyncMock) as get,
            redirect_stdout(output),
        ):
            post.return_value = replacement
            self.assertTrue(asyncio.run(self.client.refresh_session()))
            post.assert_awaited_once_with(
                "https://example.invalid/api/v1/auth/local",
                body={"email": "bot@example.invalid", "password": "test-password"},
                headers={"Content-Type": "application/json"},
                raw=True,
            )
            self.assertIs(self.client._cookies, replacement.cookies)
            self.assertEqual(output.getvalue(), "")

            get.return_value = {
                "page": 1, "totalPages": 1, "totalResults": 0, "results": []
            }
            asyncio.run(self.client.search("movie"))
            self.assertIs(get.call_args.kwargs["cookies"], replacement.cookies)
            self.assertNotIn("X-Api-Key", get.call_args.kwargs["headers"])

    def test_http_login_failure_keeps_cookie_and_original_exception(self):
        error = ClientResponseError(
            SimpleNamespace(real_url="https://example.invalid/api/v1/auth/local"),
            (),
            status=403,
            message="Invalid credentials",
        )
        response = login_response("unusable-session")
        response.raise_for_status.side_effect = error
        with patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post:
            post.return_value = response
            with self.assertRaises(ClientResponseError) as raised:
                asyncio.run(self.client.refresh_session())
            self.assertIs(raised.exception, error)
            self.assertIs(self.client._cookies, self.old_cookies)
            post.assert_awaited_once()

    def test_missing_or_empty_session_cookie_does_not_replace_current_cookie(self):
        for value in (None, ""):
            with (
                self.subTest(cookie=value),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                response = login_response(value)
                response.cookies["XSRF-TOKEN"] = "csrf-token"
                post.return_value = response
                with self.assertRaisesRegex(RuntimeError, "session cookie"):
                    asyncio.run(self.client.refresh_session())
                self.assertIs(self.client._cookies, self.old_cookies)

    def test_network_failure_keeps_cookie(self):
        for error in (TimeoutError(), ClientConnectionError("Connection lost")):
            with (
                self.subTest(error=type(error).__name__),
                patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            ):
                post.side_effect = error
                with self.assertRaises(type(error)):
                    asyncio.run(self.client.refresh_session())
                self.assertIs(self.client._cookies, self.old_cookies)

    def test_api_key_only_client_skips_cookie_refresh(self):
        client = OverseerrAPI(
            "https://example.invalid/api/v1",
            api_key="test-key",
            log_file=io.StringIO(),
        )
        with patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post:
            self.assertFalse(asyncio.run(client.refresh_session()))
            post.assert_not_awaited()


class CookieRefreshJobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = SimpleNamespace(refresh_session=AsyncMock(return_value=True))
        with patch("overseerr.OverseerrAPI", return_value=self.client):
            self.cog = Overseerr(Mock())
        self.addCleanup(self.cog.cog_unload)

    async def test_daily_job_retries_failure_then_restores_daily_interval(self):
        job = self.cog.refresh_cookie
        self.assertEqual(job.hours, 24)
        self.client.refresh_session.side_effect = [TimeoutError(), True]
        with self.assertLogs("overseerr", level="ERROR") as logs:
            await job.coro(self.cog)
        self.assertIn("retrying in five minutes", logs.output[0])
        self.assertEqual(job.minutes, 5)
        self.assertEqual(job.hours, 0)

        await job.coro(self.cog)
        self.assertEqual(job.hours, 24)
        self.assertEqual(job.minutes, 0)
        self.assertEqual(self.client.refresh_session.await_count, 2)

    async def test_api_key_only_job_does_not_report_cookie_refreshed(self):
        self.client.refresh_session.return_value = False
        with self.assertNoLogs("overseerr", level="INFO"):
            await self.cog.refresh_cookie.coro(self.cog)
        self.assertEqual(self.cog.refresh_cookie.hours, 24)

    async def test_shutdown_cancellation_is_not_swallowed_as_a_login_failure(self):
        self.client.refresh_session.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.cog.refresh_cookie.coro(self.cog)
        self.assertEqual(self.cog.refresh_cookie.hours, 24)

    async def test_repeated_ready_events_start_each_job_only_once(self):
        jobs = []
        for name in ("refresh_cookie", "map_discord_ids", "map_genre_ids"):
            job = Mock()
            job.is_running.return_value = False
            job.start.side_effect = lambda job=job: setattr(
                job.is_running, "return_value", True
            )
            setattr(self.cog, name, job)
            jobs.append(job)

        await self.cog.on_ready()
        await self.cog.on_ready()
        for job in jobs:
            job.start.assert_called_once_with()

        self.cog.cog_unload()
        for job in jobs:
            job.cancel.assert_called_once_with()
