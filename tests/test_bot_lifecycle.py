import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

with patch.dict(os.environ, {"GUILD_ID": "1"}):
    from overseerr import Overseerr


class BotAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_credentials_do_not_trigger_login(self):
        with (
            patch.dict(os.environ, {
                "OVERSEERR_URL": "https://example.invalid/api/v1",
                "OVERSEERR_API_KEY": "test-key",
                "OVERSEERR_USER": "old-service-account",
                "OVERSEERR_PASS": "old-password",
            }),
            patch("overseerrapi.api.client.post", new_callable=AsyncMock) as post,
            patch("overseerrapi.api.client.get", new_callable=AsyncMock) as get,
        ):
            # Construction also works inside a running event loop without sync login.
            cog = Overseerr(Mock())
            self.addCleanup(cog.cog_unload)
            get.return_value = {"results": [{"id": 7}]}
            await cog.overseerr_client.users()
            self.assertEqual(get.call_args.kwargs["headers"], {
                "Content-Type": "application/json", "X-Api-Key": "test-key",
            })
            self.assertNotIn("cookies", get.call_args.kwargs)
            post.assert_not_awaited()
            self.assertFalse(hasattr(cog, "refresh_cookie"))

    async def test_repeated_ready_events_start_each_remaining_job_only_once(self):
        with patch("overseerr.OverseerrAPI", return_value=SimpleNamespace()):
            cog = Overseerr(Mock())
        jobs = []
        for name in ("map_discord_ids", "map_genre_ids"):
            job = Mock()
            job.is_running.return_value = False
            job.start.side_effect = lambda job=job: setattr(
                job.is_running, "return_value", True
            )
            setattr(cog, name, job)
            jobs.append(job)

        await cog.on_ready()
        await cog.on_ready()
        for job in jobs:
            job.start.assert_called_once_with()

        cog.cog_unload()
        for job in jobs:
            job.cancel.assert_called_once_with()
