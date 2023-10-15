import os
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
from discord.commands.context import ApplicationContext
from discord.ui.item import Item
from typing import Self, Dict, List, TypedDict
import shared
from overseerrapi import OverseerrAPI
from overseerrapi.types import (
    MediaSearchResult,
    Genres,
    TvResult,
    MovieResult,
    PersonResult,
)

logger = shared.get_logger()


class GenreIDMap(TypedDict):
    movie: Genres
    tv: Genres


class Overseerr(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self._bot = bot
        self._overseerr_client = OverseerrAPI(
            url=os.environ.get("OVERSEERR_URL"),
            api_key=os.environ.get("OVERSEERR_API_KEY"),
        )

    @slash_command(
        name="search",
        default_permission=True,
        guild_ids=[int(os.environ.get("GUILD_ID"))],
    )
    async def _search(
        self,
        ctx: ApplicationContext,
        query: Option(str, "Media to search for.", required=True),
        page: Option(
            int, "Media to search for.", min_value=1, required=False, default=1
        ),
    ):
        """Searches for a movie or tv show"""
        results = await self._overseerr_client.search(query, page)
        view = SearchView(
            overseerr_client=self._overseerr_client, results=results, search_query=query
        )
        await view._edit_embed()
        await ctx.respond(embed=view.embed, view=view)


class SearchView(discord.ui.View):
    def __init__(
        self,
        search_query: str,
        results: MediaSearchResult,
        overseerr_client: OverseerrAPI,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        self._overseerr_client: OverseerrAPI = overseerr_client
        self._index: int = 0
        self._poster_base: str = "https://image.tmdb.org/t/p/w342"
        self._backdrop_base: str = "https://image.tmdb.org/t/p/w300"
        self._query: str = search_query
        self._results: MediaSearchResult = results
        self._result_length: int = self._results.total_results
        self._genre_id_map: GenreIDMap = {}
        self.embed: discord.Embed = discord.Embed(color=discord.Color.blurple())
        self._discord_id_map: Dict[int, int] = {}

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index -= 1
        button.disabled = self._results.page == 1 and self._index <= 0
        if self._index == 0 and self._results.page > self._results.total_pages:
            self._results = await self._overseerr_client.search(
                self._query, self._results.page - 1
            )
            self._index = 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label=">")
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index += 1
        button.disabled = (
            self._results.total_pages == self._results.page
            and self._index * self._results.page >= self._result_length - 1
        )
        if self._index == 20 and self._results.page < self._results.total_pages:
            self._results = await self._overseerr_client.search(
                self._query, self._results.page + 1
            )
            self._index = 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.success, label="Request")
    async def request(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        button.disabled = True
        self.embed.title = f"Sending requests for {self.embed.title}..."
        if self._discord_id_map == {}:
            users = self._overseerr_client.users()
            for user in users:
                user_full = await self._overseerr_client.user(user.id)
                self._discord_id_map[int(user_full.settings.discord_id)] = user_full.id
        user_id = self._discord_id_map.get(interaction.user.id, None)
        if user_id is None:
            interaction.response.send_message(
                "You are not registered with Overseerr. Please register at https://overseerr.mydomain.com"
            )
            self.disable_all_items()
            self.stop()
            return
        await interaction.response.edit_message(embed=self.embed, view=self)
        await self._overseerr_client.post_request(
            media_id=self._results.results[self._index].id,
            media_type=self._results.results[self._index].media_type,
            discord_id=interaction.user.id,
        )
        button.label = "Request Sent"
        media_type = self._results.results[self._index].media_type
        if media_type == "movie":
            name = self._results.results[self._index].title
        elif media_type == "tv":
            name = self._results.results[self._index].name
        else:
            name = "???"
        self.embed.title = f"Request for {name} Sent! 🎉"
        self.disable_all_items()
        self.stop()
        await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.danger, label="Cancel")
    async def cancel(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self.disable_all_items()
        self.stop()
        await interaction.response.edit_message(view=self)

    async def _paginate(self, interaction: discord.Interaction) -> None:
        await self._edit_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def _update_buttons(self) -> None:
        """
        Done for embed time check
        """
        # Previous button
        self.children[0].disabled = self._results.page == 1 and self._index <= 0
        # Next button
        self.children[1].disabled = (
            self._results.total_pages == self._results.page
            and self._index * self._results.page >= self._result_length - 1
        )

    async def _edit_embed(self) -> None:
        if self._results.total_results == 0:
            self.embed.title = "No Results Found"
            self.embed.description = f"No results found for {self._query}"
            self.clear_items()
            self.stop()
            return
        await self._update_buttons()
        if self._genre_id_map == {}:
            logger.debug("Genre ID map is empty, setting it")
            self._genre_id_map = {
                "movie": {
                    x["id"]: x["name"]
                    for x in await self._overseerr_client.get_movie_genres()
                },
                "tv": {
                    x["id"]: x["name"]
                    for x in await self._overseerr_client.get_tv_genres()
                },
            }
            logger.debug("Genre ID map set")
        self.embed.clear_fields()
        self.embed.remove_author()
        self.embed.remove_footer()
        self.embed.remove_image()
        self.embed.remove_thumbnail()

        result: TvResult | MovieResult | PersonResult = self._results.results[
            self._index
        ]
        result_number = (self._index + 1) + (self._results.page - 1) * 20

        if result.media_type == "movie":
            result: MovieResult
            title = result.title
            release_date = result.release_date
        elif result.media_type == "tv":
            result: TvResult
            title = result.name
            release_date = result.first_air_date
        else:
            result: PersonResult
            title = result.name
        self.embed.title = title
        if result.media_type == "person":
            self.embed.set_thumbnail(url=self._backdrop_base + result.profile_path)
        else:
            logger.trace("Result: {}", result)
            logger.trace("Result keys: {}", result.keys())
            lang = result.original_language.upper()
            if result.backdrop_path:
                self.embed.set_image(url=self._backdrop_base + result.backdrop_path)
            if result.poster_path:
                self.embed.set_thumbnail(url=self._poster_base + result.poster_path)

            self.embed.description = result.overview
            self.embed.add_field(name="Released", value=release_date, inline=True)
            self.embed.add_field(name="Language", value=lang, inline=True)

            genre_map = self._genre_id_map[result.media_type]
            genre_str = ", ".join(genre_map[i] for i in result.genre_ids)

            self.embed.add_field(
                name="Genre",
                value=genre_str,
                inline=True,
            )
            self.embed.add_field(
                name="Popularity", value=f"{result.popularity:.2f}%", inline=False
            )
            self.embed.add_field(
                name="Vote Average",
                value=f"{result.vote_average:.2f}",
                inline=True,
            )
            self.embed.add_field(
                name="Vote Count", value=result.vote_count, inline=True
            )

        self.embed.set_footer(
            text=f"Result {result_number} out of {self._result_length}\n\n{title} | ID: {result.id}"
        )


def setup(bot: discord.Bot):
    bot.add_cog(Overseerr(bot))
