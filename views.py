from discord.ui.item import Item
import discord
from typing import Self, Dict, TypedDict, Union
import shared
from overseerrapi import OverseerrAPI
from overseerrapi.types import (
    MediaSearchResult,
    Genres,
    TvResult,
    MovieResult,
    PersonResult,
    Requests,
    Request,
    PageInfo,
    MediaInfo,
    TVDetails,
    MovieDetails,
)

import logging

logger = logging.getLogger(__name__)


class GenreIDMap(TypedDict):
    movie: Genres
    tv: Genres


class OverseerrView(discord.ui.View):
    def __init__(
        self,
        overseerr_client: OverseerrAPI,
        user_id: int,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(*items, timeout=timeout, disable_on_timeout=disable_on_timeout)
        self.cmd_by_user_id: int = user_id
        self.overseerr_client: OverseerrAPI = overseerr_client
        self._embed: discord.Embed = discord.Embed(color=discord.Color.blurple())
        self._index: int = 0
        self._genre_id_map: GenreIDMap = {}
        self.interaction_check = self.check_interaction

    def clear_embed(self) -> None:
        self._embed = discord.Embed(color=discord.Color.blurple())

    def _movie_embed(self, result: Union[MovieResult, MovieDetails]) -> None:
        self._embed = discord.Embed(color=discord.Color.blurple())
        self.embed.title = result.title
        self.embed.add_field(name="Released", value=result.release_date, inline=True)

    def _tv_embed(self, result: Union[TVDetails, TvResult]) -> None:
        self._embed = discord.Embed(color=discord.Color.blurple())
        self.embed.title = result.name
        self.embed.add_field(name="Released", value=result.first_air_date, inline=True)

    def _person_embed(self, result: PersonResult) -> None:
        self.embed.title = result.name
        if result.profile_path:
            self.embed.set_thumbnail(url=self.poster_base + result.profile_path)

    def media_common_embed(
        self, result: Union[MovieResult, MovieDetails, TVDetails, TvResult]
    ) -> discord.Embed:
        self.clear_embed()
        if isinstance(result, PersonResult):
            self._person_embed(result)
            return

        if isinstance(result, (TvResult, MovieResult)):
            genre_str = ", ".join(
                self._genre_id_map[result.media_type][i] for i in result.genre_ids
            )
        else:
            genre_str = ", ".join(genre.name for genre in result.genres)

        if result.backdrop_path:
            self.embed.set_image(url=self.backdrop_base + result.backdrop_path)
        if result.poster_path:
            self.embed.set_thumbnail(url=self.poster_base + result.poster_path)
        if isinstance(result, (MovieResult, MovieDetails)):
            self._movie_embed(result)
        elif isinstance(result, (TvResult, TVDetails)):
            self._tv_embed(result)
        self.embed.description = result.overview
        if result.backdrop_path:
            self.embed.set_image(url=self.backdrop_base + result.backdrop_path)
        if result.poster_path:
            self.embed.set_thumbnail(url=self.poster_base + result.poster_path)

        self.embed.add_field(
            name="Language", value=result.original_language, inline=True
        )
        self.embed.add_field(name="Genres", value=genre_str, inline=True)
        self.embed.add_field(
            name="Popularity", value=f"{result.popularity:.2f}%", inline=False
        )
        self.embed.add_field(
            name="Vote Average",
            value=f"{result.vote_average:.2f}",
            inline=True,
        )
        self.embed.add_field(name="Vote Count", value=result.vote_count, inline=True)

        self.embed.set_footer(
            text=f"Result {self.result_number} out of {self.result_count}\n\n{self.embed.title} | ID: {result.id}"
        )

    @property
    def poster_base(self) -> str:
        return "https://image.tmdb.org/t/p/w342"

    @property
    def backdrop_base(self) -> str:
        return "https://image.tmdb.org/t/p/w300"

    @property
    def embed(self) -> discord.Embed:
        return self._embed

    @property
    def genre_id_map(self) -> GenreIDMap:
        return self._genre_id_map

    async def setup_genre_id_map(self) -> None:
        if self._genre_id_map == {}:
            logger.debug("Genre ID map is empty, setting it")
            self._genre_id_map = {
                "movie": {
                    x["id"]: x["name"]
                    for x in await self.overseerr_client.get_movie_genres()
                },
                "tv": {
                    x["id"]: x["name"]
                    for x in await self.overseerr_client.get_tv_genres()
                },
            }
            logger.debug("Genre ID map set")
        return self._genre_id_map

    async def check_interaction(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.cmd_by_user_id

    @property
    def result_number(self):
        raise NotImplementedError

    @property
    def result_count(self):
        raise NotImplementedError


class SearchView(OverseerrView):
    def __init__(
        self,
        search_query: str,
        user_id: int,
        results: MediaSearchResult,
        overseerr_client: OverseerrAPI,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(
            overseerr_client,
            user_id=user_id,
            *items,
            timeout=timeout,
            disable_on_timeout=disable_on_timeout,
        )
        self._index: int = 0
        self._query: str = search_query
        self._results: MediaSearchResult = results
        self._genre_id_map: GenreIDMap = {}
        self._discord_id_map: Dict[int, int] = {}

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index -= 1
        button.disabled = self.previous_button_disabled
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label=">")
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index += 1
        button.disabled = self.next_button_disabled
        if self._needs_next_page:
            self._results = await self._get_page(self._results.page + 1)
        await self._paginate(interaction)

    @property
    def _needs_next_page(self) -> bool:
        return self._index == 20 and self._results.page > self._results.total_pages

    @property
    def _needs_previous_page(self) -> bool:
        return self._index == 0 and 1 < self._results.page < self._results.total_pages

    async def _get_page(self, page: int) -> MediaSearchResult:
        self._index = 0
        res = await self.overseerr_client.search(self._query, page=page)
        logger.trace("Returing page data: {}", res)

    @property
    def previous_button_disabled(self) -> bool:
        return self._results.page == 1 and self._index <= 0

    @property
    def next_button_disabled(self) -> bool:
        return (
            self._results.total_pages == self._results.page
            and self._index * self._results.page >= self.result_count - 1
        )

    @property
    async def results(self):
        if self._needs_previous_page:
            await setattr(
                self, "_results", await self._get_page(self._results.page - 1)
            )
            self._results = await self._get_page(self._results.page - 1)
        if self._needs_next_page:
            self._results = await setattr(
                self, "_results", self._get_page(self._results.page + 1)
            )
        return self._results

    @property
    def result(self) -> Union[MovieResult, TVDetails, PersonResult]:
        return self._results.results[self._index]

    @property
    def result_count(self) -> int:
        return self._results.total_results

    @results.setter
    async def results(self, value):
        self._results = value

    @discord.ui.button(style=discord.ButtonStyle.success, label="Request")
    async def request(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        button.disabled = True
        self.embed.title = f"Sending requests for {self.embed.title}..."
        if self._discord_id_map == {}:
            users = await self.overseerr_client.users()
            for user in users.results:
                user_full = await self.overseerr_client.user(user.id)
                self._discord_id_map[int(user_full.settings.discord_id)] = user_full.id
        user_id = self._discord_id_map.get(interaction.user.id, None)
        if user_id is None:
            interaction.response.send_message("You are not registered with Overseerr.")
            self.disable_all_items()
            self.stop()
            return
        await interaction.response.edit_message(embed=self.embed, view=self)
        await self.overseerr_client.post_request(
            media_id=self.result.id,
            media_type=self.result.media_type,
            user_id=user_id,
        )
        self.embed.title = f"Request for {self.embed.title} Sent! 🎉"
        self.disable_all_items()
        self.clear_items()
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
        self.children[0].disabled = self.previous_button_disabled
        # Next button
        self.children[1].disabled = self.next_button_disabled
        # Request button
        if self.result.media_type == "person":
            self.children[2].disabled = True
        else:
            status = self.result.media_info.status
            status_map = {
                1: "Request",
                2: "Pending",
                3: "Processing",
                4: "Partiallly Available",
                5: "Available",
            }
            self.children[2].disabled = status != 1
            self.children[2].label = status_map.get(status, "Request")

    async def _edit_embed(self) -> None:
        if self._results.results == []:
            self.embed.title = "No Results Found"
            self.embed.description = f"No results found for {self._query}"
            self.embed.set_image(
                url="https://www.shutterstock.com/image-vector/emoticon-showing-screw-loose-sign-600w-195080234.jpg"
            )
            self.clear_items()
            self.stop()
            return

        self.clear_embed()
        await self._update_buttons()
        if self._genre_id_map == {}:
            await self.setup_genre_id_map()

        self.media_common_embed(self.result)

    @property
    def result_number(self):
        return (self._index + 1) + (self._results.page - 1) * 20


class RequestsView(OverseerrView):
    def __init__(
        self,
        requests: Requests,
        overseerr_client: OverseerrAPI,
        user_id: int,
        params,
        *items: Item,
        timeout: float | None = 180,
        disable_on_timeout: bool = False,
    ) -> Self:
        super().__init__(
            overseerr_client=overseerr_client,
            user_id=user_id,
            *items,
            timeout=timeout,
            disable_on_timeout=disable_on_timeout,
        )
        self._index: int = 0
        self._requests: Requests = requests
        self._requests_length: int = (
            requests.page_info.pages * requests.page_info.page_size
        )
        self._discord_id_map: Dict[int, int] = {}
        self._params = params

    @discord.ui.button(label="<", style=discord.ButtonStyle.primary)
    async def previous(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index -= 1
        button.disabled = self.result_number <= 1
        if self._index < 0 and self.page_info.page > self.page_info.pages:
            self._requests = await self.get_results_page(-1)
            self._index = 0
        await self._paginate(interaction)

    @discord.ui.button(style=discord.ButtonStyle.primary, label=">")
    async def next(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self._index += 1
        button.disabled = self.disable_next_button()
        if self.result_number > self.page_info.results:
            self._requests = await self.get_results_page(1)
            self._index = 0
        await self._paginate(interaction)

    def disable_next_button(self) -> bool:
        return self.result_number == self.page_info.results

    async def get_results_page(self, page: int) -> MediaSearchResult:
        self._params["skip"] = self.page_info.page * (self._params["take"] + page)
        return await self.overseerr_client.get_all_requests(**self._params)

    @discord.ui.button(style=discord.ButtonStyle.success, label="Approve")
    async def approve(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        button.disabled = True
        resp = await self.overseerr_client.approve_request(self.request.id)
        logger.debug(
            "Sent approval request for {}, (ID: {})", self.embed.title, self.request.id
        )
        logger.trace(resp)
        self.embed.title = f"Request for {self.embed.title} Approved! 🎉"
        self.disable_all_items()
        self.stop()
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(style=discord.ButtonStyle.danger, label="Deny")
    async def cancel(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ) -> None:
        self.disable_all_items()
        self.stop()
        await self.overseerr_client.deny_request(self.request.id)
        await interaction.response.edit_message(view=self)

    async def _paginate(self, interaction: discord.Interaction) -> None:
        await self._edit_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def _update_buttons(self) -> None:
        """
        Done for embed time check
        """
        # Previous button
        self.children[0].disabled = self.page_info.page == 1 and self._index <= 0
        # Next button
        self.children[1].disabled = self.result_number == self.page_info.results

    async def _edit_embed(self) -> None:
        if self._genre_id_map == {}:
            await self.setup_genre_id_map()
        if self.page_info.results == 0:
            self.embed.title = "No requests"
            self.embed.description = f"No current requests. You are caught up."
            self.clear_items()
            self.stop()
            return
        await self._update_buttons()
        if self.genre_id_map == {}:
            await self.setup_genre_id_map()

        media_type = self.request.media.media_type
        result: Union[MovieDetails, TVDetails] = await self.get_request_info(
            self.request.media
        )
        self.media_common_embed(result)

    async def get_request_info(
        self, media: MediaInfo
    ) -> Union[TVDetails, MovieDetails]:
        if media.media_type == "movie":
            return await self.overseerr_client.get_movie(media.tmdb_id)
        elif media.media_type == "tv":
            return await self.overseerr_client.get_tv(media.tmdb_id)

    @property
    def page_info(self) -> PageInfo:
        return self._requests.page_info

    @property
    def result_number(self) -> int:
        """Returns index adjusted for pagination. Index starts at 1"""
        return (self._index + 1) + (self.page_info.page - 1) * 20

    @property
    def result_count(self) -> int:
        return self.page_info.results

    @property
    def request(self) -> Request:
        return self._requests.results[self._index]
