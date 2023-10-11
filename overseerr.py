import aiohttp
from typing import TypedDict
import os
import sys
import discord
from discord.ext import commands
from discord.commands import slash_command, Option
from discord.commands.context import ApplicationContext
from discord.ui.item import Item
import loguru
from typing import List, Self, Dict
import networking
import shared
import overseerr_types as OverseerrTypes

logger = loguru.logger
logger.remove()
logger.add(sys.stderr, level="TRACE")


class Overseerr(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self._url: str = os.environ.get("OVERSEERR_URL")
        self._token: str = os.environ.get("OVERSEERR_TOKEN")
        self._discord_id_map: Dict[int, int] = {}
        pass

    async def _setup_discord_id_map(self) -> Dict[int, int]:
        users = (await networking.get(f"{self._url}/user", headers=self._headers))['results']
        user_ids = map(lambda x: x["id"], users)
        for i in user_ids:
            user = await networking.get(f"{self._url}/user/{i}", headers=self._headers)
            discord_id = user["settings"]["discordId"]
            self._discord_id_map[int(discord_id)] = i

    @slash_command(
        name="search",
        default_permission=True,
        guild_ids=[int(os.environ.get("GUILD_ID"))],
    )
    async def _search(
        self,
        ctx: ApplicationContext,
        query: Option(str, "Media to search for.", required=True),
    ):
        """Searches for a movie or tv show"""
        params = {"query": query, "page": 1}
        data = await networking.get(
            f"{self._url}/search", params=params, headers=self._headers
        )
        with open("res2.json", "w") as f:
            import json

            json.dump(data, f)

        if isinstance(data, aiohttp.ClientResponseError):
            await ctx.respond(f"`Error occured during Overseerr request.`")
            return
        data: OverseerrTypes.Search = await self._parse_search(data)
        if data.total_results == 0:
            await ctx.respond(f"`No results found.`")
            return
        if self._discord_id_map == {}:
            await self._setup_discord_id_map()
        view = SearchView(search_results=data, discord_id_map=self._discord_id_map, headers=self._headers, url=self._url)
        await view._edit_embed()
        await ctx.respond(embed=view.embed, view=view)

    async def _parse_search(self, data: OverseerrTypes.Search) -> OverseerrTypes.Search:
        data = await shared.load_json(data, OverseerrTypes.Search)
        return data

    @property
    def _headers(self) -> dict:
        return {"X-Api-Key": self._token, "Content-Type": "application/json"}

async def _post_request(*, url: str, headers: Dict[str, str], media_id: int, media_type: str, user_id: int) -> None:
    logger.debug("Posting request")
    payload = {
        "mediaId": media_id,
        "mediaType": media_type,
        "profileId": user_id,
    }
    logger.trace("Body: {}", payload)

    await networking.post(f"{url}/request", body=payload, headers=headers)


class SearchView(discord.ui.View):
    def __init__(
        self,
        *items: Item,
        search_results: OverseerrTypes.Search,
        headers: Dict[str, str],
        discord_id_map: Dict[int, int],
        url: str,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        self._index: int = 0
        self._poster_base: str = "https://image.tmdb.org/t/p/w342"
        self._backdrop_base: str = "https://image.tmdb.org/t/p/w300"
        self._results: List[OverseerrTypes.SearchResult] = search_results.results
        self._result_length: int = search_results.total_results
        self._discord_id_map: Dict[int, int] = discord_id_map
        self._url: str = url
        self._headers: Dict[str, str] = headers
        self.embed: discord.Embed = discord.Embed(color=discord.Color.blurple())
        # Disable the left button if we're on the first page
        self.children[0].disabled = True

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def button_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index -= 1
        button.disabled = self._index <= 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label=">")
    async def button_callback2(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index += 1
        button.disabled = self._index >= self._result_length - 1
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.success, label="Request")
    async def button_callback3(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        user_id = self._discord_id_map[interaction.user.id]
        button.disabled = True
        self.embed.title = f"Sending requests for {self.embed.title}..."
        await interaction.response.edit_message(embed=self.embed, view=self)
        await _post_request(
            url=self._url,
            headers=self._headers,
            media_id=self._results[self._index].id,
            media_type=self._results[self._index].media_type,
            user_id=user_id
        )
        button.label = "Request Sent"
        if self._results[self._index].media_type == "movie":
            name =  self._results[self._index].title
        elif self._results[self._index].media_type == "tv":
            name = self._results[self._index].name
        else:
            name = "???"
        self.embed.title = f"Request for {name} Sent! 🎉"
        self.disable_all_items()
        self.stop()
        await interaction.followup.send(
            embed=self.embed, view=self,
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
        # Previous button
        self.children[0].disabled = self._index <= 0
        # Next button
        self.children[1].disabled = self._index >= self._result_length - 1

    async def _edit_embed(self) -> None:
        await self._update_buttons()
        self.embed.clear_fields()
        result = self._results[self._index]
        print(result)
        if result.media_type == "movie":
            self.embed.title = result.title
            self.embed.description = result.overview
            if result.backdrop_path:
                self.embed.set_image(url=self._backdrop_base + result["backdropPath"])
            if result.poster_path:
                self.embed.set_thumbnail(url=self._poster_base + result["posterPath"])
            self.embed.add_field(
                name="Released", value=result["releaseDate"], inline=True
            )
            self.embed.add_field(
                name="Language", value=result["originalLanguage"], inline=True
            )
            self.embed.add_field(
                name="Popularity", value=f'{int(result["popularity"])}%', inline=False
            )
            self.embed.add_field(
                name="Vote Average", value=f"{result['voteAverage']:.1f}", inline=True
            )
            self.embed.add_field(
                name="Vote Count", value=result["voteCount"], inline=True
            )
            self.embed.set_footer(text=f"{result['title']} | ID: {result['id']}")
        elif result.media_type == "tv":
            self.embed.description = result["overview"]
            self.embed.add_field(
                name=result["name"], value=result["overview"], inline=False
            )
        else:
            self.embed.title = result.name
            self.embed.set_thumbnail(url=self._backdrop_base + result.profile_path)
            self.embed.add_field(name="test", value="TODO", inline=False)


def setup(bot: commands.Bot):
    bot.add_cog(Overseerr(bot))
