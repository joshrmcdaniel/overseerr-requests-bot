import os
import discord
from discord.ext import commands, tasks
from discord.commands import slash_command, Option
from discord.commands.context import ApplicationContext
import shared
from overseerrapi import OverseerrAPI
import traceback as tb
import logging
from overseerrapi.types import Requests, MediaSearchResult

from typing import Dict, Any

from views import SearchView, RequestsView

log = logging.getLogger(__name__)


class Overseerr(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self._bot = bot
        self.overseerr_client = OverseerrAPI(
            url=os.environ.get("OVERSEERR_URL"),
            api_key=os.environ.get("OVERSEERR_API_KEY"),
        )

    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Overseerr cog loading...")
        log.info("Starting Discord ID map task..")
        self.map_discord_ids.start()
        self.map_genre_ids.start()
        log.info("Discord ID map task started")
        log.info("Overseerr cog ready.")

    @tasks.loop(hours=1)
    async def map_discord_ids(self):
        log.debug("Updating discord id map...")
        discord_id_map = {}
        users = await self.overseerr_client.users()
        for user in users.results:
            user_full = await self.overseerr_client.user(user.id)
            discord_id_map[int(user_full.settings.discord_id)] = user_full.id

        self._discord_id_map = discord_id_map
        log.info("Updated discord user id map")
        log.trace("Id map: %s", discord_id_map)

    @tasks.loop(hours=168)
    async def map_genre_ids(self):
        movies = await self.overseerr_client.get_tv_genres()
        tvs = await self.overseerr_client.get_tv_genres()
        genre_id_map = {
            "movie": {x["id"]: x["name"] for x in movies},
            "tv": {x["id"]: x["name"] for x in tvs},
        }
        log.debug("Genre ID map retrieved")
        self._genre_id_map = genre_id_map

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
            return await ctx.respond(content="You are not allowed to use this command.")
        await ctx.respond(content=f"Searching for {query}...")
        results = await self.overseerr_client.search(query, page)
        view = self.get_search_view(results, query, user_id=ctx.user.id)
        await view._edit_embed()
        await ctx.edit(embed=view.embed, view=view, content=f"Results for: {query}")

    @_search.error
    async def _search_error(self, ctx: ApplicationContext, error):
        trace = tb.format_exception(error)
        log.error(error)
        log.debug(trace)
        await ctx.respond(content="An error occurred while searching..")

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
            default="pending",
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
        await ctx.respond("Fetching requests...")
        requests = await self.overseerr_client.get_all_requests(**params)
        view = self.get_request_view(params, requests, user_id=ctx.user.id)
        await view._edit_embed()
        await ctx.edit(embed=view.embed, view=view, content="")

    @_requests.error
    async def _requests_error(self, ctx: ApplicationContext, error):
        print(error)
        await ctx.respond("An error occurred while searching..")

    def get_request_view(
        self, params: Dict[str, Any], requests: Requests, user_id: int
    ) -> RequestsView:
        return RequestsView(
            user_id=user_id,
            overseerr_client=self.overseerr_client,
            discord_id_map=self._discord_id_map,
            genre_id_map=self._genre_id_map,
            requests=requests,
            params=params,
        )

    def get_search_view(
        self, results: MediaSearchResult, search_query: str, user_id: int
    ) -> SearchView:
        return SearchView(
            user_id=user_id,
            overseerr_client=self.overseerr_client,
            results=results,
            search_query=search_query,
            discord_id_map=self._discord_id_map,
            genre_id_map=self._genre_id_map,
        )


def setup(bot: discord.Bot):
    bot.add_cog(Overseerr(bot))
