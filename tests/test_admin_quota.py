import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from quota.admin import AdminRetentionList
from quota.api import Server
from quota.models import GB, Snapshot, StorageItem

with patch.dict(os.environ, {"GUILD_ID": "1"}):
    from overseerr import Overseerr


class AdminQuotaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        with patch("overseerr.OverseerrAPI", return_value=Mock()):
            self.cog = Overseerr(Mock())
        self.addCleanup(self.cog.cog_unload)
        self.cog._discord_id_map = {200: 7, 201: 7}
        self.snapshot = Snapshot(
            user_id=7, limit=500 * GB, used=430 * GB, reserved=20 * GB,
            items=[StorageItem(
                f"radarr:0:{i}", f"Movie {i}",
                Server("radarr", 0, "Radarr", "http://radarr", "key"),
                i, "movie", 1000 + i, None, None, 215 * GB, frozenset({7}), (), True,
            ) for i in (11, 12)],
            requests=[
                {"id": 1, "requestedBy": {"id": 7}, "status": 1},
                {"id": 2, "requestedBy": {"id": 7}, "status": 2},
                {"id": 3, "requestedBy": {"id": 8}, "status": 1},
            ],
        )
        self.cog.quota_manager = SimpleNamespace(
            enabled=True, snapshot=AsyncMock(return_value=self.snapshot),
            remove=AsyncMock(), auto_approve=AsyncMock(),
        )
        self.target = SimpleNamespace(id=200, display_name="Test member")
        self.ctx = SimpleNamespace(
            author=SimpleNamespace(id=100, guild_permissions=discord.Permissions(administrator=True)),
            guild=SimpleNamespace(id=1),
            respond=AsyncMock(), defer=AsyncMock(), edit=AsyncMock(),
        )

    async def invoke(self):
        await self.cog._quota_user.callback(self.cog, self.ctx, self.target)

    async def test_command_registers_admin_permissions_and_member_selector(self):
        bot = discord.Bot(intents=discord.Intents.none())
        self.addAsyncCleanup(bot.close)
        bot.add_cog(self.cog)
        command = self.cog._quota_user
        self.assertEqual(command.name, "quota-user")
        self.assertTrue(command.default_member_permissions.administrator)
        self.assertEqual(len(command.options), 1)
        self.assertEqual(command.options[0].name, "user")
        self.assertEqual(command.options[0].input_type, discord.SlashCommandOptionType.user)
        self.assertTrue(command.options[0].required)

    async def test_unlinked_admin_can_view_target_quota_privately_without_mutating_media(self):
        await self.invoke()
        manager = self.cog.quota_manager
        manager.snapshot.assert_awaited_once_with(7)
        self.ctx.defer.assert_awaited_once_with(ephemeral=True)
        self.ctx.respond.assert_not_awaited()
        response = self.ctx.edit.call_args.kwargs
        self.assertIsInstance(response["view"], AdminRetentionList)
        self.addCleanup(response["view"].stop)
        embed = response["embed"]
        self.assertIn(self.target.display_name, embed.title)
        self.assertIn("**Downloaded:** 430.0 GB", embed.description)
        self.assertIn("**Reserved for downloads:** 20.0 GB", embed.description)
        self.assertIn("**Remaining:** 50.0 GB of 500.0 GB", embed.description)
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["Downloaded movies / seasons"], "2")
        self.assertEqual(fields["Pending requests"], "1")
        self.assertIn("Counts toward quota", fields["Movie 11"])
        self.assertIn("Counts toward quota", fields["Movie 12"])
        self.assertEqual([option.label for option in response["view"].selector.options], ["Movie 11", "Movie 12"])
        manager.remove.assert_not_awaited()
        manager.auto_approve.assert_not_awaited()

    async def test_non_admin_cannot_bypass_command_permissions(self):
        self.ctx.author.guild_permissions = discord.Permissions(manage_guild=True)
        await self.invoke()
        self.cog.quota_manager.snapshot.assert_not_awaited()
        self.ctx.defer.assert_not_awaited()
        self.assertTrue(self.ctx.respond.call_args.kwargs["ephemeral"])
        self.assertIn("Administrator", self.ctx.respond.call_args.args[0])

    async def test_direct_messages_cannot_read_other_quotas(self):
        self.ctx.guild = None
        del self.ctx.author.guild_permissions
        await self.invoke()
        self.cog.quota_manager.snapshot.assert_not_awaited()
        self.ctx.respond.assert_awaited_once()

    async def test_unlinked_target_does_not_query_another_account(self):
        self.target.id = 999
        await self.invoke()
        self.cog.quota_manager.snapshot.assert_not_awaited()
        self.ctx.respond.assert_awaited_once_with(
            "That member is not linked to a Seerr account.", ephemeral=True
        )

    async def test_quota_disabled_does_not_fetch_storage(self):
        self.cog.quota_manager.enabled = False
        await self.invoke()
        self.cog.quota_manager.snapshot.assert_not_awaited()
        self.ctx.respond.assert_awaited_once_with("Storage quotas are disabled.", ephemeral=True)

    async def test_other_discord_account_of_same_seerr_user_shares_quota(self):
        self.target.id = 201
        await self.invoke()
        self.cog.quota_manager.snapshot.assert_awaited_once_with(7)

    async def test_storage_error_does_not_display_misleading_zero_usage_or_exception(self):
        self.cog.quota_manager.snapshot.side_effect = RuntimeError("private connection details")
        with self.assertLogs("overseerr", level="ERROR"):
            await self.invoke()
        self.ctx.defer.assert_awaited_once_with(ephemeral=True)
        self.ctx.edit.assert_awaited_once_with(content="Could not read storage usage. Try again later.")


if __name__ == "__main__":
    unittest.main()
