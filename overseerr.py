import os
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
from discord.commands.context import ApplicationContext
import shared
from overseerrapi import OverseerrAPI
import traceback as tb
import logging

from views import SearchView, RequestsView

log = logging.getLogger(__name__)


class Overseerr(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self._bot = bot
        self.overseerr_client = OverseerrAPI(
            url=os.environ.get("OVERSEERR_URL"),
            api_key=os.environ.get("OVERSEERR_API_KEY"),
        )
        log.info("Overseerr cog ready.")

    @slash_command(
        name="search",
        default_permission=True,
        guild_ids=[int(os.environ.get("GUILD_ID"))],
    )
    async def _search(
        self,
        ctx: ApplicationContext,
        query: Option(str, "Media to search for.", name="media_title", required=True),
        page: Option(
            int,
            "Media to search for.",
            name="page_number",
            min_value=1,
            required=False,
            default=1,
        ),
    ):
        """Searches for a movie or tv show"""
        requester_role = await shared.get_role(ctx.guild, "Requester")
        if requester_role not in ctx.author.roles:
            return await ctx.respond("You are not allowed to use this command.")
        results = await self.overseerr_client.search(query, page)
        view = SearchView(
            user_id=ctx.user.id,
            overseerr_client=self.overseerr_client,
            results=results,
            search_query=query,
        )
        await view._edit_embed()
        await ctx.respond(embed=view.embed, view=view)

    @_search.error
    async def _search_error(self, ctx: ApplicationContext, error):
        trace = tb.format_exception(error)
        log.error(error)
        log.debug(trace)
        await ctx.respond("An error occurred while searching..")

    @slash_command(
        name="requests",
        default_permission=False,
        guild_ids=[int(os.environ.get("GUILD_ID"))],
    )
    async def _requests(
        self,
        ctx: ApplicationContext,
        size: Option(
            int,
            "Amount of results to show per page.",
            name="page_size",
            required=False,
            default=20,
        ),
        skip: Option(
            int,
            "Amount of results to skip; offset to start at.",
            name="offset",
            required=False,
            default=0,
        ),
        filter: Option(
            str,
            "Filter requests by status.",
            required=False,
            name="request_type",
            choices=[
                "all",
                "approved",
                "available",
                "pending",
                "processing",
                "unavailable",
                "failed",
            ],
            default="all",
        ),
        sort: Option(
            str,
            "Sort requests by a field.",
            required=False,
            name="sort_by",
            choices=["added", "modified"],
            default="added",
        ),
    ):
        """View your requests"""
        approver_role = await shared.get_role(ctx.guild, "Approver")
        if approver_role not in ctx.author.roles:
            return await ctx.respond("You are not allowed to use this command.")
        params = {
            "take": size,
            "skip": skip,
            "filter_by": filter,
            "sort": sort,
        }
        requests = await self.overseerr_client.get_all_requests(**params)
        view = RequestsView(
            user_id=ctx.user.id,
            overseerr_client=self.overseerr_client,
            requests=requests,
            params=params,
        )
        await view._edit_embed()
        await ctx.respond(embed=view.embed, view=view)

    @_requests.error
    async def _requests_error(self, ctx: ApplicationContext, error):
        print(error)
        await ctx.respond("An error occurred while searching..")


def setup(bot: discord.Bot):
    bot.add_cog(Overseerr(bot))
