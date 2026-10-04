import asyncio
import logging

import discord

from .api import QuotaError
from .manager import media_type, owner_id
from .models import format_size

logger = logging.getLogger(__name__)


def quota_summary_embed(snapshot, *, title="Your storage allowance"):
    return discord.Embed(
        title=title[:256], color=discord.Color.blurple(),
        description=f"**Downloaded:** {format_size(snapshot.used)}\n"
        f"**Reserved for downloads:** {format_size(snapshot.reserved)}\n"
        f"**Remaining:** {format_size(snapshot.free)} of {format_size(snapshot.limit)}",
    )


class UserView(discord.ui.View):
    def __init__(self, manager, discord_user_id, seerr_user_id, request_id=None):
        super().__init__(timeout=300, disable_on_timeout=True)
        self.manager = manager
        self.discord_user_id = discord_user_id
        self.seerr_user_id = seerr_user_id
        self.request_id = request_id

    async def interaction_check(self, interaction):
        if interaction.user.id == self.discord_user_id:
            return True
        await interaction.response.send_message(
            "Use /quota to manage your own downloads.", ephemeral=True
        )
        return False

    def next_view(self, cls, *args):
        return cls(self.manager, self.discord_user_id, self.seerr_user_id, self.request_id, *args)

    async def show_storage(self, interaction, notice=None):
        view = self.next_view(StorageView)
        try:
            await view.load()
        except Exception:
            logger.exception("Could not load storage for Seerr user %s", self.seerr_user_id)
            view.stop()
            await interaction.edit_original_response(
                content=(notice + "\n" if notice else "")
                + "Could not read your storage usage. Try /quota again later.",
                embed=None, view=None,
            )
        else:
            await interaction.edit_original_response(content=notice, embed=view.embed, view=view)
        self.stop()


class QuotaActionsView(UserView):
    @discord.ui.button(label="Manage storage", style=discord.ButtonStyle.primary)
    async def manage(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        await self.show_storage(interaction)

    @discord.ui.button(label="Retry approval", style=discord.ButtonStyle.success)
    async def retry(self, button, interaction):
        if button.disabled or self.is_finished() or self.request_id is None:
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        result = await self.manager.auto_approve(self.seerr_user_id, self.request_id)
        view = self.next_view(QuotaActionsView)
        view.retry.disabled = result.approved
        if result.approved:
            view.request_id = None
        await interaction.edit_original_response(content=result.message, embed=None, view=view)
        self.stop()


class StorageView(UserView):
    PAGE_SIZE = 5

    def __init__(self, *args):
        super().__init__(*args)
        self.page = 0
        self.snapshot = None
        self.embed = None
        self.selector = discord.ui.Select(
            placeholder="Choose a download to remove",
            options=[discord.SelectOption(label="No downloads", value="none")],
            min_values=1, max_values=1, row=0, disabled=True,
        )
        self.selector.callback = self.select_download
        self.add_item(self.selector)
        self.retry.disabled = self.request_id is None

    async def load(self):
        self.snapshot = await self.manager.snapshot(self.seerr_user_id)
        self.render()

    def render(self):
        snapshot = self.snapshot
        last_page = max(0, (len(snapshot.items) - 1) // self.PAGE_SIZE)
        self.page = min(self.page, last_page)
        self.embed = quota_summary_embed(snapshot)
        items = snapshot.items[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        for item in items:
            detail = format_size(item.size)
            if not item.removable:
                detail += " · Shared; contact the bot owner to remove it."
            self.embed.add_field(name=item.title[:256], value=detail, inline=False)
        if not items:
            self.embed.add_field(name="Downloads", value="No downloaded requests are using your allowance.")
        self.embed.set_footer(
            text=f"Page {self.page + 1} of {last_page + 1} · Select a download to review its removal."
        )
        options = [
            discord.SelectOption(label=item.title[:100], value=item.key,
                                 description=f"Remove {format_size(item.size)} of downloaded files")
            for item in items if item.removable
        ]
        self.selector.options = options or [
            discord.SelectOption(label="No removable downloads on this page", value="none")
        ]
        self.selector.disabled = not options
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= last_page
        self.pending.disabled = not any(
            owner_id(r) == self.seerr_user_id and r["status"] == 1
            for r in snapshot.requests
        )

    async def select_download(self, interaction):
        if self.selector.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        key = self.selector.values[0]
        item = next((item for item in self.snapshot.items if item.key == key and item.removable), None)
        if item is None:
            self.render()
            await interaction.response.send_message("Refresh your storage list and try again.", ephemeral=True)
            return
        view = self.next_view(RemoveConfirmation, item)
        embed = discord.Embed(
            title="Delete downloaded files?",
            description=f"**{discord.utils.escape_markdown(item.title)}**\n"
            f"{format_size(item.size)}\n\n"
            "This removes the downloaded files and stops future downloads for this movie or season.",
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)
        self.stop()

    @discord.ui.button(label="Previous", row=1)
    async def previous(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.page = max(0, self.page - 1)
        self.render()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Next", row=1)
    async def next(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.page += 1
        self.render()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="Refresh usage", style=discord.ButtonStyle.primary, row=1)
    async def refresh(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        await self.show_storage(interaction)

    @discord.ui.button(label="Pending requests", row=2)
    async def pending(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        view = self.next_view(PendingRequestsView)
        await view.load(self.snapshot.requests)
        await interaction.edit_original_response(content=None, embed=view.embed, view=view)
        self.stop()

    @discord.ui.button(label="Retry approval", style=discord.ButtonStyle.success, row=2)
    async def retry(self, button, interaction):
        if self.request_id is None or button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        result = await self.manager.auto_approve(self.seerr_user_id, self.request_id)
        if result.approved:
            self.request_id = None
        await self.show_storage(interaction, result.message)


class PendingRequestsView(UserView):
    PAGE_SIZE = 10

    def __init__(self, *args):
        super().__init__(*args)
        self.page = 0
        self.requests = []
        self.titles = {}
        self.selector = discord.ui.Select(
            placeholder="Choose a request to retry approval",
            options=[discord.SelectOption(label="No pending requests", value="none")],
            min_values=1, max_values=1, row=0, disabled=True,
        )
        self.selector.callback = self.select_request
        self.add_item(self.selector)

    async def load(self, requests):
        self.requests = sorted(
            (r for r in requests if owner_id(r) == self.seerr_user_id and r["status"] == 1),
            key=lambda r: r["id"],
        )
        await self.render()

    async def title(self, request):
        if request["id"] not in self.titles:
            kind = media_type(request)
            try:
                details = await self.manager.api.seerr(
                    "GET", f"/{kind}/{request['media']['tmdbId']}"
                )
                title = details.get("title") or details.get("name")
            except Exception:
                title = None
            self.titles[request["id"]] = title or f"{kind.title()} request #{request['id']}"
        return self.titles[request["id"]]

    async def render(self):
        last_page = max(0, (len(self.requests) - 1) // self.PAGE_SIZE)
        self.page = min(self.page, last_page)
        requests = self.requests[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        titles = await asyncio.gather(*(self.title(r) for r in requests))
        self.embed = discord.Embed(
            title="Your pending requests", color=discord.Color.blurple(),
            description="Choose a request to check its storage allowance and retry approval."
            if requests else "You have no pending requests. Use /search to request something new.",
        )
        options = []
        for request, title in zip(requests, titles):
            details = "4K" if request.get("is4k") else "Standard quality"
            if request.get("seasons"):
                details += " · Seasons " + ", ".join(
                    str(s["seasonNumber"]) for s in request["seasons"]
                )
            self.embed.add_field(name=title[:256], value=details[:256], inline=False)
            options.append(discord.SelectOption(
                label=title[:100], value=str(request["id"]), description=details[:100]
            ))
        self.selector.options = options or [
            discord.SelectOption(label="No pending requests", value="none")
        ]
        self.selector.disabled = not options
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= last_page
        self.embed.set_footer(text=f"Page {self.page + 1} of {last_page + 1}")

    async def select_request(self, interaction):
        if self.selector.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        request_id = int(self.selector.values[0])
        if not any(r["id"] == request_id for r in self.requests):
            await self.show_storage(interaction, "Refresh your pending requests and try again.")
            return
        result = await self.manager.auto_approve(self.seerr_user_id, request_id)
        self.request_id = None if result.approved else request_id
        await self.show_storage(interaction, result.message)

    async def change_page(self, button, interaction, change):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        self.page = max(0, self.page + change)
        await self.render()
        self.back.disabled = False
        await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(label="Previous", row=1)
    async def previous(self, button, interaction):
        await self.change_page(button, interaction, -1)

    @discord.ui.button(label="Next", row=1)
    async def next(self, button, interaction):
        await self.change_page(button, interaction, 1)

    @discord.ui.button(label="Back to storage", row=1)
    async def back(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        await self.show_storage(interaction)


class RemoveConfirmation(UserView):
    def __init__(self, manager, discord_user_id, seerr_user_id, request_id, item):
        super().__init__(manager, discord_user_id, seerr_user_id, request_id)
        self.item = item

    @discord.ui.button(label="Delete files", style=discord.ButtonStyle.danger)
    async def confirm(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.edit_message(view=self)
        try:
            size = await self.manager.remove(self.seerr_user_id, self.item)
        except QuotaError as error:
            notice = str(error)
        except Exception:
            logger.exception("Removal could not be confirmed for storage item %s", self.item.key)
            notice = "Removal could not be confirmed. Refresh usage to check which files remain."
        else:
            notice = f"Removed {format_size(size)} of downloaded files."
            if self.request_id is not None:
                result = await self.manager.auto_approve(self.seerr_user_id, self.request_id)
                notice += " " + result.message
                if result.approved:
                    self.request_id = None
        await self.show_storage(interaction, notice)

    @discord.ui.button(label="Keep files", style=discord.ButtonStyle.secondary)
    async def cancel(self, button, interaction):
        if button.disabled or self.is_finished():
            await interaction.response.defer()
            return
        self.disable_all_items()
        await interaction.response.defer()
        await self.show_storage(interaction)
