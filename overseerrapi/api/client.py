import logging
import sys
from typing import Dict, TextIO
from ..shared.networking import get, post
from ..types import *


class OverseerrAPI:
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        log_level: str = "INFO",
        log_file: str | TextIO = sys.stderr,
    ):
        self._url = url
        self._api_key = api_key
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(log_level)
        self._logger.addHandler(logging.StreamHandler(log_file))

    async def search(self, query: str, page: int = 1) -> MediaSearchResult:
        self._logger.debug("Searching for %s on page %d", query, page)
        params = {"query": query, "page": 1}
        res = await get(self._url + "/search", params=params, headers=self._headers)
        if isinstance(res, ErrorResponse):
            self._logger.error("Error while searching for %s: %s", query, res.error)
            raise Exception(res.error)
        results = res.pop("results")
        res = _load_type(json_data=res, overseerr_type=MediaSearchResult)
        res.results = []
        if isinstance(res, MediaSearchResult):
            res_map = {"person": PersonResult, "movie": MovieResult, "tv": TvResult}
            for result in results:
                self._logger.debug("Found result %s", result)
                typed_json = _load_type(
                    overseerr_type=res_map[result["mediaType"]], json_data=result
                )
                res.results.append(typed_json)

        return res

    async def user(self, id: int) -> User:
        res = await get(self._url + f"/user/{id}", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=User)

    async def users(self):
        res = await get(self._url + "/user", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=UserSearchResult)

    async def list_requests(self) -> Requests:
        res = await get(self._url + "/request", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=Requests)

    async def get_request(self, id: int) -> Request:
        res = await get(self._url + f"/request/{id}", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=Request)

    async def get_movie(self, id: int):
        res = await get(self._url + f"/movie/{id}", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=MovieDetails)

    async def get_movie_recommendations(self, id: int):
        res = await get(
            self._url + f"/movie/{id}/recommendations", headers=self._headers
        )
        return _load_type(json_data=res, overseerr_type=MovieDetails)

    async def get_tv(self, id: int):
        res = await get(self._url + f"/tv/{id}", headers=self._headers)
        with open("tv.json", "w") as f:
            import json

            json.dump(res, f, indent=4)
        return _load_type(json_data=res, overseerr_type=TVDetails)

    async def get_tv_season(self, id: int, season: int):
        res = await get(self._url + f"/tv/{id}/season/{season}", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=TVSeason)

    async def get_tv_recommendations(self, id: int):
        pass

    async def _get_genre(self, media_type: str):
        if media_type not in ["tv", "movie"]:
            raise RuntimeError(f"Invalid media type {media_type}")
        res = await get(self._url + f"/genres/{media_type}", headers=self._headers)
        return _load_type(json_data=res, overseerr_type=Genres)

    async def get_tv_genres(self) -> Genres:
        return await self._get_genre("tv")

    async def get_movie_genres(self) -> Genres:
        return await self._get_genre("movie")

    async def post_request(self, media_id: int, media_type: str, user_id: int):
        body = RequestBody(media_id=media_id, media_type=media_type, user_id=user_id)
        res = await post(
            self._url + "/request", body=body.to_dict(), headers=self._headers
        )
        return _load_type(json_data=res, overseerr_type=Request)

    @property
    def _headers(self) -> Dict[str, str]:
        return {"X-Api-Key": self._api_key}
