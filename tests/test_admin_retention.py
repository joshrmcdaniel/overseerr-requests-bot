import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import discord

from quota.admin import AdminRetentionList, RetentionConfirmation
from quota.api import QuotaError, Server
from quota.models import GB, RetainedItem, Snapshot, StorageItem


def interaction(*, user_id=100, admin=True, guild_id=1):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, guild_permissions=discord.Permissions(administrator=admin)),
        guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )


class AdminRetentionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        server = Server("sonarr", 0, "Sonarr", "http://sonarr", "key")
        self.item = StorageItem(
            "sonarr:0:11:1", "Show — Season 1", server, 11, "tv", 101, 1001, 1,
            30 * GB, frozenset({7}), (41,), True,
        )
        self.snapshot = Snapshot(7, 500 * GB, 30 * GB, 0, [self.item], [])
        self.manager = SimpleNamespace(
            snapshot=AsyncMock(return_value=self.snapshot), retain=AsyncMock(),
            restore_retained=AsyncMock(), remove=AsyncMock(), auto_approve=AsyncMock(),
        )
        self.args = (self.manager, 100, 7, "Member", 1)

    def view(self, cls, *args):
        view = cls(*self.args, *args)
        self.addCleanup(view.stop)
        return view

    def result_view(self, click):
        view = click.edit_original_response.call_args.kwargs["view"]
        if view is not None:
            self.addCleanup(view.stop)
        return view

    async def test_non_admin_other_admin_and_wrong_guild_cannot_open_management(self):
        view = self.view(AdminRetentionList)
        for options in ({"admin": False}, {"user_id": 200}, {"guild_id": None}, {"guild_id": 2}):
            with self.subTest(options=options):
                click = interaction(**options)
                await view.refresh.callback(click)
                click.response.send_message.assert_awaited_once()
                self.assertTrue(click.response.send_message.call_args.kwargs["ephemeral"])
        self.manager.snapshot.assert_not_awaited()

    async def test_selecting_a_download_requires_confirmation_before_retaining(self):
        view = self.view(AdminRetentionList)
        await view.load()
        click = interaction()
        with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=[view.selector.options[0].value]):
            await view.select_item(click)
        confirmation = self.result_view(click)
        self.assertIsInstance(confirmation, RetentionConfirmation)
        self.manager.retain.assert_not_awaited()
        self.assertIn("current and future", confirmation.embed.description)
        click = interaction()
        await confirmation.confirm.callback(click)
        self.result_view(click)
        self.manager.retain.assert_awaited_once_with(7, self.item, 100, whole_series=False)
        self.manager.remove.assert_not_awaited()
        self.manager.auto_approve.assert_not_awaited()
        await confirmation.confirm.callback(interaction())
        self.manager.retain.assert_awaited_once()

    async def test_permissions_are_rechecked_at_confirmation(self):
        view = self.view(RetentionConfirmation, self.item)
        await view.confirm.callback(interaction(admin=False))
        await view.whole_show.callback(interaction(user_id=200))
        self.manager.retain.assert_not_awaited()
        self.manager.snapshot.assert_not_awaited()

    async def test_keep_whole_show_is_explicit_and_keeps_files(self):
        view = self.view(RetentionConfirmation, self.item)
        click = interaction()
        await view.whole_show.callback(click)
        self.result_view(click)
        self.manager.retain.assert_awaited_once_with(7, self.item, 100, whole_series=True)
        self.manager.remove.assert_not_awaited()

    async def test_cancel_does_not_change_quota_or_files(self):
        view = self.view(RetentionConfirmation, self.item)
        click = interaction()
        await view.cancel.callback(click)
        self.result_view(click)
        self.manager.retain.assert_not_awaited()
        self.manager.restore_retained.assert_not_awaited()
        self.manager.remove.assert_not_awaited()

    async def test_retention_failure_reports_error_without_claiming_success(self):
        self.manager.retain.side_effect = QuotaError("The library item changed. Refresh before keeping it.")
        view = self.view(RetentionConfirmation, self.item)
        click = interaction()
        await view.confirm.callback(click)
        self.result_view(click)
        self.assertIn("library item changed", click.edit_original_response.call_args.kwargs["content"])
        self.manager.remove.assert_not_awaited()

    async def test_retained_items_can_be_restored_without_deletion(self):
        item = RetainedItem.from_storage(7, self.item, whole_series=True)
        self.snapshot.retained_items = [item]
        view = self.view(AdminRetentionList)
        await view.load()
        click = interaction()
        selected = next(option.value for option in view.selector.options if "Kept outside quota" in option.description)
        with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=[selected]):
            await view.select_item(click)
        confirmation = self.result_view(click)
        self.assertTrue(confirmation.restore)
        self.assertNotIn(confirmation.whole_show, confirmation.children)
        self.manager.restore_retained.assert_not_awaited()
        click = interaction()
        await confirmation.confirm.callback(click)
        self.result_view(click)
        self.manager.restore_retained.assert_awaited_once_with(7, item, 100)
        self.manager.remove.assert_not_awaited()

    async def test_individual_movies_are_visible_and_only_selected_movie_is_kept(self):
        server = Server("radarr", 0, "Radarr", "http://radarr", "key")
        movies = [StorageItem(
            f"radarr:0:{i}", title, server, i, "movie", 1000 + i, None, None,
            10 * GB, frozenset({7}), (i,), True,
        ) for i, title in ((11, "Movie A"), (12, "Movie B"))]
        self.snapshot.items = movies
        kept = RetainedItem.from_storage(7, replace(movies[0], tmdb_id=1013, title="Movie C"))
        self.snapshot.retained_items = [kept]
        view = self.view(AdminRetentionList)
        await view.load()
        self.assertEqual([option.label for option in view.selector.options], ["Movie A", "Movie B", "Movie C"])
        self.assertIn("Counts toward quota", view.selector.options[1].description)
        self.assertIn("Kept outside quota", view.selector.options[2].description)
        self.assertEqual(view.selector.max_values, 1)
        click = interaction()
        with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=[view.selector.options[1].value]):
            await view.select_item(click)
        confirmation = self.result_view(click)
        self.assertIs(confirmation.item, movies[1])
        self.assertEqual(confirmation.confirm.label, "Keep this movie")
        self.assertNotIn(confirmation.whole_show, confirmation.children)
        self.manager.retain.assert_not_awaited()
        click = interaction()
        await confirmation.confirm.callback(click)
        self.result_view(click)
        self.manager.retain.assert_awaited_once_with(7, movies[1], 100, whole_series=False)
        self.manager.restore_retained.assert_not_awaited()
        self.manager.remove.assert_not_awaited()
        self.assertIn("Movie B", click.edit_original_response.call_args.kwargs["content"])

    async def test_filters_only_change_visible_titles_and_keep_single_item_controls(self):
        kept = RetainedItem.from_storage(7, replace(self.item, season=2, title="Show — Season 2"))
        self.snapshot.retained_items = [kept]
        view = self.view(AdminRetentionList)
        await view.load()
        for selected, labels in (
            ("kept", ["Show — Season 2"]),
            ("charged", ["Show — Season 1"]),
            ("all", ["Show — Season 1", "Show — Season 2"]),
        ):
            with patch.object(discord.ui.Select, "values", new_callable=PropertyMock, return_value=[selected]):
                await view.select_filter(interaction())
            self.assertEqual([option.label for option in view.selector.options], labels)
            self.assertFalse(view.selector.disabled)
            self.assertFalse(view.filter_selector.disabled)
        self.manager.retain.assert_not_awaited()
        self.manager.restore_retained.assert_not_awaited()
        self.manager.remove.assert_not_awaited()

    async def test_list_paginates_large_libraries_and_refreshes_current_state(self):
        self.snapshot.items = [replace(self.item, key=str(i), title=f"Show {i}") for i in range(12)]
        view = self.view(AdminRetentionList)
        await view.load()
        self.assertTrue(view.previous.disabled)
        self.assertEqual(len(view.selector.options), 5)
        await view.next.callback(interaction())
        await view.next.callback(interaction())
        self.assertEqual(len(view.selector.options), 2)
        self.assertTrue(view.next.disabled)
        self.snapshot.items = []
        click = interaction()
        await view.refresh.callback(click)
        fresh = self.result_view(click)
        self.assertTrue(fresh.selector.disabled)
        self.assertEqual(fresh.page, 0)


if __name__ == "__main__":
    unittest.main()
