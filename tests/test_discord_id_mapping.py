import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from overseerrapi.api.client import setup_logging
from overseerrapi.types import User, UserSearchResult

with patch.dict(os.environ, {"GUILD_ID": "1"}):
    from overseerr import Overseerr


class DiscordIdMappingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        setup_logging()
        self.client = SimpleNamespace(users=AsyncMock(), user=AsyncMock())
        with patch("overseerr.OverseerrAPI", return_value=self.client):
            self.cog = Overseerr(Mock())

    def set_users(self, payloads):
        users = {payload["id"]: User(payload) for payload in payloads}
        self.client.users.return_value = UserSearchResult(
            {"results": [{"id": user_id} for user_id in users]}
        )
        self.client.user.side_effect = users.__getitem__

    async def refresh(self):
        await self.cog.map_discord_ids.coro(self.cog)

    async def test_maps_every_discord_id_to_its_overseerr_user(self):
        self.set_users([
            {
                "id": 7,
                "settings": {"discordIds": ["111111111111111111", "222222222222222222"]},
            },
            {"id": 8, "settings": {"discordIds": ["333333333333333333"]}},
        ])
        await self.refresh()
        self.assertEqual(self.cog._discord_id_map, {
            111111111111111111: 7,
            222222222222222222: 7,
            333333333333333333: 8,
        })

    async def test_skips_missing_null_and_empty_discord_id_lists(self):
        self.set_users([
            {"id": 1},
            {"id": 2, "settings": None},
            {"id": 3, "settings": {}},
            {"id": 4, "settings": {"discordIds": None}},
            {"id": 5, "settings": {"discordIds": []}},
            {"id": 6, "settings": {"discordIds": ["444444444444444444"]}},
        ])
        await self.refresh()
        self.assertEqual(self.cog._discord_id_map, {444444444444444444: 6})

    async def test_invalid_id_does_not_skip_other_ids_or_stop_refresh(self):
        self.set_users([
            {
                "id": 7,
                "settings": {
                    "discordIds": ["invalid", "0", "-1", "555555555555555555"]
                },
            },
            {"id": 8, "settings": {"discordIds": ["666666666666666666"]}},
        ])
        with self.assertLogs("overseerr", level="WARNING"):
            await self.refresh()
        self.assertEqual(self.cog._discord_id_map, {
            555555555555555555: 7,
            666666666666666666: 8,
        })

    async def test_refresh_removes_unlinked_ids(self):
        self.set_users([
            {
                "id": 7,
                "settings": {"discordIds": ["111111111111111111", "222222222222222222"]},
            },
        ])
        await self.refresh()
        self.set_users([
            {"id": 7, "settings": {"discordIds": ["222222222222222222"]}},
        ])
        await self.refresh()
        self.assertEqual(self.cog._discord_id_map, {222222222222222222: 7})


if __name__ == "__main__":
    unittest.main()
