"""Administrator controls for retaining downloads outside a user's quota."""

import logging

import discord

from .api import QuotaError
from .manager import owner_id
from .models import RetainedItem, format_size
from .views import quota_summary_embed

logger = logging.getLogger(__name__)


class AdminQuotaView(discord.ui.View):
    def __init__(self, manager, admin_id, user_id, display_name, guild_id):
        super().__init__(timeout=300, disable_on_timeout=True)
        self.manager = manager
        self.admin_id = admin_id
        self.user_id = user_id
        self.display_name = display_name
        self.guild_id = guild_id

    async def interaction_check(self, interaction):
        permissions = getattr(interaction.user, "guild_permissions", None)
        if (
            interaction.user.id == self.admin_id
            and interaction.guild is not None
            and interaction.guild.id == self.guild_id
            and permissions is not None and permissions.administrator
        ):
            return True
        await interaction.response.send_message(
            "Only the administrator who opened this view can manage these quota exceptions.",
            ephemeral=True,
        )
        return False

    def next_view(self, cls, *args):
        return cls(self.manager, self.admin_id, self.user_id, self.display_name, self.guild_id, *args)

    async def begin(self, control, interaction):
        if control.disabled or self.is_finished():
            await interaction.response.defer()
            return False
        if not await self.interaction_check(interaction):
            return False
        self.disable_all_items()
        await interaction.response.defer()
        return True

    async def show_list(self, interaction, *, notice=None, filter_by="all"):
        view = self.next_view(AdminRetentionList, filter_by)
        try:
            await view.load()
        except Exception:
            logger.exception("Could not read admin quota for Seerr user %s", self.user_id)
            view.stop()
            await interaction.edit_original_response(
                content=(notice + "\n" if notice else "")
                + "Could not refresh usage. Run /quota-user again later.", embed=None, view=None,
            )
        else:
            await interaction.edit_original_response(content=notice, embed=view.embed, view=view)
        self.stop()


class AdminRetentionList(AdminQuotaView):
    PAGE_SIZE = 5

    def __init__(self, manager, admin_id, user_id, display_name, guild_id, filter_by="all"):
        super().__init__(manager, admin_id, user_id, display_name, guild_id)
        self.filter_by = filter_by
        self.page = 0
        self.snapshot = None
        self.items = []
        self.selector = discord.ui.Select(
            placeholder="Choose one movie or TV season", row=0,
            min_values=1, max_values=1,
            options=[discord.SelectOption(label="No titles", value="none")], disabled=True,
        )
        self.selector.callback = self.select_item
        self.add_item(self.selector)
        self.filter_selector = discord.ui.Select(
            placeholder="Show all titles", row=1,
            options=[
                discord.SelectOption(label="All titles", value="all"),
                discord.SelectOption(label="Counts toward quota", value="charged"),
                discord.SelectOption(label="Kept outside quota", value="kept"),
            ],
        )
        self.filter_selector.callback = self.select_filter
        self.add_item(self.filter_selector)

    async def load(self):
        self.snapshot = await self.manager.snapshot(self.user_id)
        self.render()

    @staticmethod
    def item_value(item):
        state = "kept" if isinstance(item, RetainedItem) else "charged"
        return f"{state}:{item.key}"

    def render(self):
        self.items = []
        if self.filter_by != "kept":
            self.items.extend(self.snapshot.items)
        if self.filter_by != "charged":
            self.items.extend(self.snapshot.retained_items)
        self.items.sort(key=lambda item: (item.title.casefold(), self.item_value(item)))
        last_page = max(0, (len(self.items) - 1) // self.PAGE_SIZE)
        self.page = min(self.page, last_page)
        self.embed = quota_summary_embed(self.snapshot, title=f"Manage quota — {self.display_name}")
        self.embed.description += (
            "\n\nChoose one title below to keep it outside this user's quota or count it again. "
            "The files stay in the library."
        )
        self.embed.add_field(name="Downloaded movies / seasons", value=str(len(self.snapshot.items)))
        pending = sum(
            owner_id(request) == self.user_id and request["status"] == 1
            for request in self.snapshot.requests
        )
        self.embed.add_field(name="Pending requests", value=str(pending))
        page_items = self.items[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        options = []
        for item in page_items:
            retained = isinstance(item, RetainedItem)
            server = item.server_name if retained else item.server.name
            status = "Kept outside quota" if retained else "Counts toward quota"
            if item.media_type == "tv" and item.season == -1:
                status += " (whole show)"
            detail = f"{status} · {format_size(item.size)} · {server}"
            self.embed.add_field(name=item.title[:256], value=detail[:1024], inline=False)
            options.append(discord.SelectOption(
                label=item.title[:100], value=self.item_value(item), description=detail[:100]
            ))
        if not page_items:
            self.embed.add_field(
                name="Titles", value="No titles match this filter.",
            )
        self.selector.options = options or [discord.SelectOption(label="No titles", value="none")]
        self.selector.disabled = not options
        self.filter_selector.disabled = False
        for option in self.filter_selector.options:
            option.default = option.value == self.filter_by
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= last_page
        self.refresh.disabled = False
        self.embed.set_footer(
            text=f"Page {self.page + 1} of {last_page + 1} · Seerr user {self.user_id} "
            "· Changes apply to the selected title only."
        )

    async def select_item(self, interaction):
        if not await self.begin(self.selector, interaction):
            return
        selected = next((item for item in self.items if self.item_value(item) == self.selector.values[0]), None)
        if selected is None:
            await self.show_list(interaction, notice="Refresh the list and try again.")
            return
        view = self.next_view(RetentionConfirmation, selected, isinstance(selected, RetainedItem))
        await interaction.edit_original_response(content=None, embed=view.embed, view=view)
        self.stop()

    async def select_filter(self, interaction):
        if not await self.begin(self.filter_selector, interaction):
            return
        selected = self.filter_selector.values[0]
        if selected in {"all", "charged", "kept"}:
            self.filter_by = selected
        self.page = 0
        self.render()
        await interaction.edit_original_response(embed=self.embed, view=self)

    async def change_page(self, button, interaction, change):
        if not await self.begin(button, interaction):
            return
        self.page = max(0, self.page + change)
        self.render()
        await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(label="Previous", row=2)
    async def previous(self, button, interaction):
        await self.change_page(button, interaction, -1)

    @discord.ui.button(label="Next", row=2)
    async def next(self, button, interaction):
        await self.change_page(button, interaction, 1)

    @discord.ui.button(label="Refresh usage", row=2)
    async def refresh(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction, filter_by=self.filter_by)


class RetentionConfirmation(AdminQuotaView):
    def __init__(self, manager, admin_id, user_id, display_name, guild_id, item, restore=False):
        super().__init__(manager, admin_id, user_id, display_name, guild_id)
        self.item = item
        self.restore = restore
        name = discord.utils.escape_markdown(display_name)
        description = f"**{discord.utils.escape_markdown(item.title)}**\n\n"
        if restore:
            self.confirm.label = "Count this movie" if item.media_type == "movie" else "Count this season"
            if item.media_type == "tv" and item.season == -1:
                self.confirm.label = "Count whole show"
            description += f"Count this title against {name}'s quota again. Files stay in the library."
            if item.media_type == "tv" and item.season == -1:
                description += " This restores quota charges for all seasons covered by the whole-show exception."
        else:
            self.confirm.label = "Keep this movie"
            description += (
                f"Stop counting this download against {name}'s quota and keep the files. "
                "The bot will protect it from user deletion. Tags, request history, and monitoring stay unchanged."
            )
            if item.media_type == "tv":
                self.confirm.label = "Keep this season"
                description += (
                    "\n\nKeep this season covers its current and future episodes. "
                    "Keep whole show covers all this user's current and future seasons on this server."
                )
        if restore or item.media_type != "tv":
            self.remove_item(self.whole_show)
        self.embed = discord.Embed(
            title="Restore quota?" if restore else "Keep files and free quota?",
            description=description[:4096], color=discord.Color.blurple(),
        )

    async def apply(self, button, interaction, *, whole_series=False):
        if not await self.begin(button, interaction):
            return
        try:
            if self.restore:
                await self.manager.restore_retained(self.user_id, self.item, self.admin_id)
                notice = f"**{discord.utils.escape_markdown(self.item.title)}** counts against the user's quota again. Files remain in the library."
            else:
                await self.manager.retain(
                    self.user_id, self.item, self.admin_id, whole_series=whole_series
                )
                title = self.item.title
                if whole_series:
                    title = title.removesuffix(f" — Season {self.item.season}") + " (whole show)"
                notice = f"**{discord.utils.escape_markdown(title)}** kept in the library and removed from this user's quota."
        except QuotaError as error:
            notice = str(error)
        except Exception:
            logger.exception("Could not update retained quota for Seerr user %s", self.user_id)
            notice = "Could not confirm the quota change. Refresh the list before retrying."
        await self.show_list(interaction, notice=notice)

    @discord.ui.button(label="Keep this movie", style=discord.ButtonStyle.success)
    async def confirm(self, button, interaction):
        await self.apply(button, interaction)

    @discord.ui.button(label="Keep whole show", style=discord.ButtonStyle.primary)
    async def whole_show(self, button, interaction):
        await self.apply(button, interaction, whole_series=True)

    @discord.ui.button(label="Cancel")
    async def cancel(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction)
