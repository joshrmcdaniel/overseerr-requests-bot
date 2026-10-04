"""Administrator controls for retaining downloads outside a user's quota."""

import logging

import discord

from .api import QuotaError
from .models import format_size
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

    async def show_list(self, interaction, *, retained=False, notice=None):
        view = self.next_view(AdminRetentionList, retained)
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


class AdminQuotaActionsView(AdminQuotaView):
    @discord.ui.button(label="Keep downloads", style=discord.ButtonStyle.primary)
    async def keep(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction)

    @discord.ui.button(label="Restore quota")
    async def restore(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction, retained=True)


class AdminRetentionList(AdminQuotaView):
    PAGE_SIZE = 5

    def __init__(self, manager, admin_id, user_id, display_name, guild_id, retained=False):
        super().__init__(manager, admin_id, user_id, display_name, guild_id)
        self.retained = retained
        self.page = 0
        self.snapshot = None
        self.items = []
        self.selector = discord.ui.Select(
            placeholder="Choose a download", row=0,
            options=[discord.SelectOption(label="No downloads", value="none")], disabled=True,
        )
        self.selector.callback = self.select_item
        self.add_item(self.selector)

    async def load(self):
        self.snapshot = await self.manager.snapshot(self.user_id)
        self.items = self.snapshot.retained_items if self.retained else self.snapshot.items
        self.render()

    def render(self):
        last_page = max(0, (len(self.items) - 1) // self.PAGE_SIZE)
        self.page = min(self.page, last_page)
        title = "Kept downloads" if self.retained else "Keep downloads and free quota"
        self.embed = quota_summary_embed(self.snapshot, title=f"{title} — {self.display_name}")
        page_items = self.items[self.page * self.PAGE_SIZE:(self.page + 1) * self.PAGE_SIZE]
        options = []
        for item in page_items:
            server = item.server_name if self.retained else item.server.name
            detail = f"{format_size(item.size)} · {server}"
            self.embed.add_field(name=item.title[:256], value=detail[:1024], inline=False)
            options.append(discord.SelectOption(label=item.title[:100], value=item.key, description=detail[:100]))
        if not page_items:
            self.embed.add_field(
                name="Downloads",
                value="No retained quota exceptions." if self.retained else "No downloaded items count against this user.",
            )
        self.selector.options = options or [discord.SelectOption(label="No downloads", value="none")]
        self.selector.placeholder = "Choose an item to restore to quota" if self.retained else "Choose a download to keep"
        self.selector.disabled = not options
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= last_page
        self.refresh.disabled = False
        self.toggle.disabled = False
        self.toggle.label = "Back to quota items" if self.retained else "View kept downloads"
        self.embed.set_footer(text=f"Page {self.page + 1} of {last_page + 1} · Files stay in the library.")

    async def select_item(self, interaction):
        if not await self.begin(self.selector, interaction):
            return
        selected = next((item for item in self.items if item.key == self.selector.values[0]), None)
        if selected is None:
            await self.show_list(interaction, retained=self.retained, notice="Refresh the list and try again.")
            return
        view = self.next_view(RetentionConfirmation, selected, self.retained)
        await interaction.edit_original_response(content=None, embed=view.embed, view=view)
        self.stop()

    async def change_page(self, button, interaction, change):
        if not await self.begin(button, interaction):
            return
        self.page = max(0, self.page + change)
        self.render()
        await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(label="Previous", row=1)
    async def previous(self, button, interaction):
        await self.change_page(button, interaction, -1)

    @discord.ui.button(label="Next", row=1)
    async def next(self, button, interaction):
        await self.change_page(button, interaction, 1)

    @discord.ui.button(label="Refresh usage", row=1)
    async def refresh(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction, retained=self.retained)

    @discord.ui.button(label="View kept downloads", row=2)
    async def toggle(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction, retained=not self.retained)


class RetentionConfirmation(AdminQuotaView):
    def __init__(self, manager, admin_id, user_id, display_name, guild_id, item, restore=False):
        super().__init__(manager, admin_id, user_id, display_name, guild_id)
        self.item = item
        self.restore = restore
        name = discord.utils.escape_markdown(display_name)
        description = f"**{discord.utils.escape_markdown(item.title)}**\n\n"
        if restore:
            self.confirm.label = "Restore to quota"
            description += f"Count this title against {name}'s quota again. Files stay in the library."
        else:
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
                notice = "This title counts against the user's quota again. Files remain in the library."
            else:
                await self.manager.retain(
                    self.user_id, self.item, self.admin_id, whole_series=whole_series
                )
                notice = "Files kept in the library and removed from this user's quota."
        except QuotaError as error:
            notice = str(error)
        except Exception:
            logger.exception("Could not update retained quota for Seerr user %s", self.user_id)
            notice = "Could not confirm the quota change. Refresh the list before retrying."
        await self.show_list(interaction, retained=self.restore, notice=notice)

    @discord.ui.button(label="Keep files and free quota", style=discord.ButtonStyle.success)
    async def confirm(self, button, interaction):
        await self.apply(button, interaction)

    @discord.ui.button(label="Keep whole show", style=discord.ButtonStyle.primary)
    async def whole_show(self, button, interaction):
        await self.apply(button, interaction, whole_series=True)

    @discord.ui.button(label="Cancel")
    async def cancel(self, button, interaction):
        if await self.begin(button, interaction):
            await self.show_list(interaction, retained=self.restore)
