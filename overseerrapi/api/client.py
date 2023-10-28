import logging
import sys
import jsonobject
from functools import partial, partialmethod
from typing import (
    Dict,
    TextIO,
    Union,
    Optional,
    Self,
    Literal,
    List,
)
from ..shared.networking import get, post, put
from ..types import *
from ..shared.wrappers import _request_with_type as request_with_type


__all__ = ["OverseerrAPI"]


class OverseerrAPI:
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        log_level: str = "INFO",
        log_file: str | TextIO = sys.stderr,
    ) -> Self:
        setup_logging()
        self._url = url
        self._api_key = api_key
        self._logger = logging.getLogger(__name__)
        ch = logging.StreamHandler(log_file)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s - %(levelname)s] %(message)s"
        )
        ch.setFormatter(formatter)
        ch.setLevel(log_level.upper())
        self._logger.addHandler(ch)
        self._logger.debug("Initialized OverseerrAPI")
        self._logger.trace("TEST")

    async def search(
        self, query: str, page: int = 1
    ) -> Union[MediaSearchResult, ErrorResponse]:
        """
        Search for a movie, tv, or person by name.

        :param query: A movie, tv, or person name to search for
        :type query: str
        :param page: The page of results to return
        :return:  Results of the search, or an error
        :rtype: Union[MediaSearchResult, ErrorResponse]
        """
        self._logger.debug("Searching for %s on page %d", query, page)
        params = {"query": query, "page": 1}
        res = await get(self._url + "/search", params=params, headers=self._headers)
        if isinstance(res, ErrorResponse):
            self._logger.error("Error while searching for %s: %s", query, res.error)
            raise Exception(res.error)
        # results key is unknown until runtime
        results = res.pop("results")
        res = _load_type(json_data=res, overseerr_type=MediaSearchResult)
        res.results = []
        if isinstance(res, MediaSearchResult):
            # it is certain that the results key will be a list of MovieResult, TvResult, or PersonResult
            # if the result is a MediaSearchResult
            res_map = {"person": PersonResult, "movie": MovieResult, "tv": TvResult}
            if results:
                for result in results:
                    self._logger.debug("Found result %s", result)
                    typed_json = _load_type(
                        overseerr_type=res_map[result["mediaType"]], json_data=result
                    )
                    res.results.append(typed_json)

        return res

    @request_with_type(overseerr_type=User)
    async def user(self, id: int) -> Union[User, ErrorResponse]:
        """
        Retrieve a user by ID

        :param id: The ID of the user to retrieve
        :type id: int
        :return: The user, or an error
        :rtype: Union[User, ErrorResponse]
        """
        return await get(self._url + f"/user/{id}", headers=self._headers)

    @request_with_type(overseerr_type=UserSearchResult)
    async def users(self) -> Union[UserSearchResult, ErrorResponse]:
        """
        Retrieve all users

        :return: All users, or an error
        :rtype: Union[UserSearchResult, ErrorResponse]
        """
        return await get(self._url + "/user", headers=self._headers)

    @request_with_type(overseerr_type=Request)
    async def get_request(self, id: int) -> Union[Request, ErrorResponse]:
        """
        Get a request by ID

        :param id: The ID of the request to retrieve
        :type id: int
        :return: The request, or an error
        :rtype: Union[Request, ErrorResponse]
        """
        return await get(self._url + f"/request/{id}", headers=self._headers)

    @request_with_type(overseerr_type=MovieDetails)
    async def get_movie(self, id: int) -> Union[MovieDetails, ErrorResponse]:
        """
        Get a movie by ID.

        :param id: The ID of the movie to retrieve. Use the TMDB ID.
        :type id: int
        :return: The movie, or an error
        :rtype: Union[MovieDetails, ErrorResponse]
        """
        return await get(self._url + f"/movie/{id}", headers=self._headers)

    @request_with_type(overseerr_type=MovieSearchResult)
    async def get_movie_recommendations(
        self, id: int
    ) -> Union[MovieSearchResult, ErrorResponse]:
        """
        Get movie recommendations for a movie by ID

        :param id: The ID of the movie to retrieve recommendations for. Use the TMDB ID.
        :type id: int
        :return: The movie recommendations, or an error
        :rtype: Union[MovieSearchResult, ErrorResponse]
        """
        return await get(
            self._url + f"/movie/{id}/recommendations", headers=self._headers
        )

    @request_with_type(overseerr_type=TVDetails)
    async def get_tv(self, id: int) -> Union[TVDetails, ErrorResponse]:
        """
        Get a TV show by ID.

        :param id: The ID of the TV show to retrieve. Use the TMDB ID.
        :type id: int
        :return: The TV show, or an error
        :rtype: Union[TVDetails, ErrorResponse]
        """
        return await get(self._url + f"/tv/{id}", headers=self._headers)

    @request_with_type(overseerr_type=TVDetails)
    async def get_tv_season(
        self, id: int, season: int
    ) -> Union[TVSeason, ErrorResponse]:
        """
        Get a TV season by ID.

        :param id: The ID of the TV show to retrieve. Use the TMDB ID.
        :type id: int
        :param season: The season number to retrieve
        :type season: int
        :return: The TV season, or an error
        :rtype: Union[TVSeason, ErrorResponse]
        """
        return await get(self._url + f"/tv/{id}/season/{season}", headers=self._headers)

    @request_with_type(overseerr_type=TVSearchResponse)
    async def get_tv_recommendations(self, id: int):
        """
        Get TV show recommendations for a TV show by ID

        :param id: The ID of the TV show to retrieve recommendations for. Use the TMDB ID.
        :type id: int
        :return: The TV show recommendations, or an error
        :rtype: Union[TVSearchResponse, ErrorResponse]
        """
        return await get(self._url + f"/tv/{id}/recommendations", headers=self._headers)

    @request_with_type(overseerr_type=Genre)
    async def _get_genre(self, media_type: str) -> Union[List[Genre], ErrorResponse]:
        """
        Backing function for get_tv_genres and get_movie_genres. Don't use this directly.

        :param media_type: The media type to retrieve genres for. Either `"tv"` or `"movie"`
        :type media_type: str
        :return: The genres, or an error
        :rtype: Union[List[Genre], ErrorResponse]
        """
        if media_type not in ["tv", "movie"]:
            raise RuntimeError(f"Invalid media type {media_type}")
        return await get(self._url + f"/genres/{media_type}", headers=self._headers)

    @request_with_type(overseerr_type=Genre)
    async def get_tv_genres(self) -> Union[Genre, ErrorResponse]:
        """
        Get all TV genres

        :return: TV genres, or an error
        :rtype: Union[Genre, ErrorResponse]
        """
        return await get(self._url + f"/genres/tv", headers=self._headers)

    @request_with_type(overseerr_type=Genre)
    async def get_movie_genres(self) -> Union[Genre, ErrorResponse]:
        """
        Get all movie genres

        :return: Movie genres, or an error
        :rtype: Union[Genre, ErrorResponse]
        """
        return await get(self._url + f"/genres/movie", headers=self._headers)

    @request_with_type(overseerr_type=Request)
    async def post_request(
        self, media_id: int, media_type: str, user_id: int
    ) -> Union[Request, ErrorResponse]:
        """
        Add a request for a movie or TV show

        :param media_id: The ID of the movie or TV show to request
        :type media_id: int
        :param media_type: The type of media to request. Either `"movie"` or `"tv"`
        :type media_type: str
        :param user_id: The ID of the user to request the media for
        :type user_id: int
        :return: The request, or an error
        :rtype: Union[Request, ErrorResponse]
        """
        if media_type not in ["movie", "tv"]:
            raise RuntimeError(f"Invalid media type {media_type}")

        body = RequestBody(media_id=media_id, media_type=media_type, user_id=user_id)
        return await post(
            self._url + "/request", body=body.to_json(), headers=self._headers
        )

    @request_with_type(overseerr_type=Request)
    async def modify_request(
        self, id: int, status: Literal["approve", "decline"]
    ) -> Union[Request, ErrorResponse]:
        if status not in ["approve", "decline"]:
            raise RuntimeError(f"Invalid status {status}")
        return await post(self._url + f"/request/{id}/{status}", headers=self._headers)

    @request_with_type(overseerr_type=Request)
    async def deny_request(self, id: int) -> Union[Request, ErrorResponse]:
        return await post(self._url + f"/request/{id}/decline", headers=self._headers)

    @request_with_type(overseerr_type=Request)
    async def approve_request(self, id: int) -> Union[Request, ErrorResponse]:
        return await post(self._url + f"/request/{id}/approve", headers=self._headers)

    @request_with_type(overseerr_type=Requests)
    async def get_all_requests(
        self,
        *,
        take: int = 20,
        skip: int = 0,
        filter_by: str = "all",
        sort: str = "added",
        requested_by: Optional[int] = None,
    ) -> Union[Requests, ErrorResponse]:
        """
        Get all requests

        :param take: The number of results to return
        :type take: int
        :param skip: The number of results to skip
        :type skip: int
        :param filter_by: The type of requests to return. Must be one of: "all", "approved", "available", "pending", "processing", "unavailable", "failed"
        :type filter_by: str
        :param sort: The field to sort by. Must be `"added"` or `"modified"`
        :type sort: str
        :param requested_by: The ID of the user to return requests for
        :type requested_by: Optional[int]
        :return: The requests, or an error
        :rtype: Union[Requests, ErrorResponse]
        """
        filter_by_options = [
            "all",
            "approved",
            "available",
            "pending",
            "processing",
            "unavailable",
            "failed",
        ]
        sort_options = ["added", "modified"]
        if filter_by not in filter_by_options:
            raise RuntimeError(f"Invalid filter: {filter_by}")
        if sort not in sort_options:
            raise RuntimeError(f"Invalid sort: `{sort}`")
        params = {
            "take": take,
            "skip": skip,
            "filter": filter_by,
            "sort": sort,
        }
        if requested_by is not None:
            params["requestedBy"] = requested_by
        return await get(self._url + "/request", params=params, headers=self._headers)

    @property
    def _headers(self) -> Dict[str, str]:
        """
        Headers to send with every request. Don't use this directly.

        :return: Overseerr headers
        :rtype: Dict[str, str]
        """
        return {"X-Api-Key": self._api_key, "Content-Type": "application/json"}


def setup_logging():
    logging.TRACE = 5
    logging.addLevelName(logging.TRACE, "TRACE")
    logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
    logging.trace = partial(logging.log, logging.TRACE)
