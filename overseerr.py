import os
import sys
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
from discord.commands.context import ApplicationContext
from discord.ui.item import Item
import loguru
from typing import Self, Dict
import networking
import shared
import overseerr_types as OverseerrTypes

logger = loguru.logger
logger.remove()
logger.add(sys.stderr, level="TRACE")


class Overseerr(commands.Cog):
    _url: str = os.environ.get("OVERSEERR_URL")
    _headers: Dict[str, str] = {
        "X-Api-Key": os.environ.get("OVERSEERR_TOKEN"),
        "Content-Type": "application/json",
    }
    _discord_id_map: Dict[int, int] = {}

    def __init__(self, bot: commands.Cog):
        self._bot = bot

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
        results = await Overseerr.search(query, page)
        view = SearchView(results=results, search_query=query)
        await view._edit_embed()
        await ctx.respond(embed=view.embed, view=view)

    @staticmethod
    async def search(
        query, page=1
    ) -> OverseerrTypes.Search | OverseerrTypes.OverseerrErrorResult:
        params = {"query": query, "page": page}
        data = await networking.get(
            f"{Overseerr._url}/search", params=params, headers=Overseerr._headers
        )
        if isinstance(data, OverseerrTypes.OverseerrErrorResult):
            logger.error("Error occured during Overseerr request: {}", data)
        else:
            data = await shared.load_json(data, OverseerrTypes.Search)
        return data

    @staticmethod
    async def _setup_discord_id_map() -> Dict[int, int]:
        ids = {}
        users = (
            await networking.get(f"{Overseerr._url}/user", headers=Overseerr._headers)
        )["results"]
        user_ids = map(lambda x: x["id"], users)
        for i in user_ids:
            user = await networking.get(
                f"{Overseerr._url}/user/{i}", headers=Overseerr._headers
            )
            discord_id = user["settings"]["discordId"]
            ids[int(discord_id)] = i
        return ids

    @staticmethod
    async def post_request(*, media_id: int, media_type: str, discord_id: int) -> None:
        logger.debug("Posting request")
        if discord_id not in Overseerr._discord_id_map:
            logger.debug("User ID {} not in map", discord_id)
            Overseerr._discord_id_map = await Overseerr._setup_discord_id_map()
        user_id = Overseerr._discord_id_map[discord_id]
        payload = {
            "mediaId": media_id,
            "mediaType": media_type,
            "profileId": user_id,
        }
        logger.trace("Body: {}", payload)

        await networking.post(
            f"{Overseerr._url}/request", body=payload, headers=Overseerr._headers
        )


class SearchView(discord.ui.View):
    def __init__(
        self,
        search_query: str,
        results: OverseerrTypes.Search,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        self._index: int = 0
        self._poster_base: str = "https://image.tmdb.org/t/p/w342"
        self._backdrop_base: str = "https://image.tmdb.org/t/p/w300"
        self._query: str = search_query
        self._results: OverseerrTypes.Search = results
        self._result_length: int = self._results.total_results
        self.embed: discord.Embed = discord.Embed(color=discord.Color.blurple())
        # Disable the left button if we're on the first page
        self.children[0].disabled = True

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index -= 1
        button.disabled = self._results.page == 1 and self._index <= 0
        if self._index == 0 and self._results.page > self._results.total_pages:
            self._results = await Overseerr.search(self._query, self._results.page - 1)
            self._index = 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label=">")
    async def button_callback2(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index += 1
        button.disabled = (
            self._results.total_pages == self._results.page
            and self._index * self._results.page >= self._result_length - 1
        )
        if self._index == 20 and self._results.page < self._results.total_pages:
            self._results = await Overseerr.search(self._query, self._results.page + 1)
            self._index = 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.success, label="Request")
    async def button_callback3(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        button.disabled = True
        self.embed.title = f"Sending requests for {self.embed.title}..."
        await interaction.response.edit_message(embed=self.embed, view=self)
        await Overseerr.post_request(
            media_id=self._results.results[self._index].id,
            media_type=self._results.results[self._index].media_type,
            discord_id=interaction.user.id,
        )
        button.label = "Request Sent"
        if self._results.results[self._index].media_type == "movie":
            name = self._results.results[self._index].title
        elif self._results.results[self._index].media_type == "tv":
            name = self._results.results[self._index].name
        else:
            name = "???"
        self.embed.title = f"Request for {name} Sent! 🎉"
        self.disable_all_items()
        self.stop()
        await interaction.followup.send(
            embed=self.embed,
            view=self,
        )

    @discord.ui.button(style=discord.ButtonStyle.danger, label="Cancel")
    async def button_callback4(
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
        await self._update_buttons()
        self.embed.clear_fields()
        result: OverseerrTypes.PersonResult | OverseerrTypes.MovieResult | OverseerrTypes.TvResult = self._results.results[
            self._index
        ]
        result_number = (self._index + 1) + (self._results.page - 1) * 20
        print(result)
        if result.media_type == "movie":
            self.embed.title = result.title
            self.embed.description = result.overview
            if result.backdrop_path:
                self.embed.set_image(url=self._backdrop_base + result["backdropPath"])
            if result.poster_path:
                self.embed.set_thumbnail(url=self._poster_base + result["posterPath"])
            self.embed.add_field(
                name="Released", value=result.release_date, inline=True
            )
            self.embed.add_field(
                name="Language", value=result.original_language, inline=True
            )
            self.embed.add_field(
                name="Popularity", value=f"{int(result.popularity)}%", inline=False
            )
            self.embed.add_field(
                name="Vote Average", value=f"{result.vote_average}", inline=True
            )
            self.embed.add_field(
                name="Vote Count", value=result.vote_count, inline=True
            )
        elif result.media_type == "tv":
            self.embed.description = result["overview"]
            self.embed.add_field(
                name=result["name"], value=result["overview"], inline=False
            )
        else:
            self.embed.title = result.name
            self.embed.set_thumbnail(url=self._backdrop_base + result.profile_path)
            self.embed.add_field(name="test", value="TODO", inline=False)
        self.embed.set_footer(
            text=f"Result {result_number} out of {self._result_length}\n\n{result.title} | ID: {result['id']}"
        )


def setup(bot: commands.Bot):
    bot.add_cog(Overseerr(bot))
