import logging
import sys
import asyncio
from aiohttp import ClientResponse, ClientResponseError
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
from ..types.load import load_error
from ..shared.wrappers import _request_with_type as request_with_type


__all__ = ["OverseerrAPI"]


class OverseerrAPI:
    def __init__(
        self,
        url: str,
        *,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        password: Optional[str] = None,
        log_level: str = "INFO",
        log_file: str | TextIO = sys.stderr,
    ) -> Self:
        setup_logging()
        self._url = url
        self._api_key = api_key
        self._me = None
        self._password: str = password
        self._email: str = email

        self._logger = logging.getLogger(__name__)
        ch = logging.StreamHandler(log_file)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s - %(levelname)s] %(message)s"
        )
        ch.setFormatter(formatter)
        ch.setLevel(log_level.upper())
        self._logger.addHandler(ch)
        self._logger.debug("Initialized OverseerrAPI")

        if email and password:
            asyncio.run(self._login(email, password))

    async def _login(self, email: Optional[str], password: Optional[str]) -> None:
        self._logger.debug("Logging in with email and password")
        if email is None:
            email = self._email
        if email is None:
            raise RuntimeError("No email specified.")
        if password is None:
            if self._password is None:
                raise RuntimeError("No password specified for authentication.")
            password = self._password

        login: ClientResponse = await post(
            self._url + "/auth/local",
            body={"email": email, "password": password},
            headers=self._headers,
            raw=True,
        )
        print(login)
        try:
            login.raise_for_status()
        except ClientResponseError as cre:
            login_err = load_error(login.json())
            self._logger.error("Error while logging in: %s", login_err.message)
            raise cre
        self.__cookies = login.cookies
        self._logger.debug("Successfully logged in")


    @request_with_type(overseerr_type=MediaSearchResult)
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
        return await get(
            self._url + "/search",
            params=params,
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=User)
    async def user(self, id: int) -> Union[User, ErrorResponse]:
        """
        Retrieve a user by ID

        :param id: The ID of the user to retrieve
        :type id: int
        :return: The user, or an error
        :rtype: Union[User, ErrorResponse]
        """
        return await get(
            self._url + f"/user/{id}", headers=self._headers, cookies=self._cookies
        )

    @request_with_type(overseerr_type=UserSearchResult)
    async def users(self) -> Union[UserSearchResult, ErrorResponse]:
        """
        Retrieve all users

        :return: All users, or an error
        :rtype: Union[UserSearchResult, ErrorResponse]
        """
        return await get(
            self._url + "/user", headers=self._headers, cookies=self._cookies
        )

    @request_with_type(overseerr_type=Request)
    async def get_request(self, id: int) -> Union[Request, ErrorResponse]:
        """
        Get a request by ID

        :param id: The ID of the request to retrieve
        :type id: int
        :return: The request, or an error
        :rtype: Union[Request, ErrorResponse]
        """
        return await get(
            self._url + f"/request/{id}", headers=self._headers, cookies=self._cookies
        )

    @request_with_type(overseerr_type=MovieDetails)
    async def get_movie(self, id: int) -> Union[MovieDetails, ErrorResponse]:
        """
        Get a movie by ID.

        :param id: The ID of the movie to retrieve. Use the TMDB ID.
        :type id: int
        :return: The movie, or an error
        :rtype: Union[MovieDetails, ErrorResponse]
        """
        return await get(
            self._url + f"/movie/{id}", headers=self._headers, cookies=self._cookies
        )

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
            self._url + f"/movie/{id}/recommendations",
            headers=self._headers,
            cookies=self._cookies,
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
        return await get(
            self._url + f"/tv/{id}", headers=self._headers, cookies=self._cookies
        )

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
        return await get(
            self._url + f"/tv/{id}/season/{season}",
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=TVSearchResponse)
    async def get_tv_recommendations(self, id: int):
        """
        Get TV show recommendations for a TV show by ID

        :param id: The ID of the TV show to retrieve recommendations for. Use the TMDB ID.
        :type id: int
        :return: The TV show recommendations, or an error
        :rtype: Union[TVSearchResponse, ErrorResponse]
        """
        return await get(
            self._url + f"/tv/{id}/recommendations",
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=Genre)
    async def _get_genre(self, media_type: MEDIA_TYPES) -> Union[List[Genre], ErrorResponse]:
        """
        Backing function for get_tv_genres and get_movie_genres. Don't use this directly.

        :param media_type: The media type to retrieve genres for. Either `"tv"` or `"movie"`
        :type media_type: str
        :return: The genres, or an error
        :rtype: Union[List[Genre], ErrorResponse]
        """
        if media_type not in MEDIA_TYPES:
            raise RuntimeError(f"Invalid media type {media_type}")
        return await get(
            self._url + f"/genres/{media_type}",
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=Genre)
    async def get_tv_genres(self) -> Union[Genre, ErrorResponse]:
        """
        Get all TV genres

        :return: TV genres, or an error
        :rtype: Union[Genre, ErrorResponse]
        """
        return await get(
            self._url + f"/genres/tv", headers=self._headers, cookies=self._cookies
        )

    @request_with_type(overseerr_type=Genre)
    async def get_movie_genres(self) -> Union[Genre, ErrorResponse]:
        """
        Get all movie genres

        :return: Movie genres, or an error
        :rtype: Union[Genre, ErrorResponse]
        """
        return await get(
            self._url + f"/genres/movie", headers=self._headers, cookies=self._cookies
        )

    @request_with_type(overseerr_type=Request)
    async def post_request(
        self, media_id: int, media_type: MediaTypes, user_id: Optional[int] = None, seasons: Union[List[int], Literal['all']] = "all"
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
        if media_type not in MEDIA_TYPES:
            raise RuntimeError(f"Invalid media type {media_type}")
        body = RequestBody(media_id=media_id, media_type=media_type)
        if media_type == "tv":
            body.seasons = seasons
        if user_id:
            body.user_id = user_id
        self._logger.debug("Request body: %s", body.to_json())
        return await post(
            self._url + "/request",
            body=body.to_json(),
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=Request)
    async def modify_request(
        self, id: int, status: Literal["approve", "decline"]
    ) -> Union[Request, ErrorResponse]:
        if status not in ["approve", "decline"]:
            raise RuntimeError(f"Invalid status {status}")
        return await post(
            self._url + f"/request/{id}/{status}", headers=self._headers_with_token
        )

    @request_with_type(overseerr_type=Request)
    async def deny_request(self, id: int) -> Union[Request, ErrorResponse]:
        return await post(
            self._url + f"/request/{id}/decline", headers=self._headers_with_token
        )

    @request_with_type(overseerr_type=Request)
    async def approve_request(self, id: int) -> Union[Request, ErrorResponse]:
        return await post(
            self._url + f"/request/{id}/approve", headers=self._headers_with_token
        )

    @request_with_type(overseerr_type=Requests)
    async def get_all_requests(
        self,
        *,
        take: int = 20,
        skip: int = 0,
        filter_by: RequestsFilterByOpts = 'pending',
        sort: RequestsSortOpts = 'added',
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
        if filter_by not in REQUESTS_FILTER_OPTS:
            raise RuntimeError(f"Invalid filter: {filter_by}")
        if sort not in REQUESTS_SORT_OPTS:
            raise RuntimeError(f"Invalid sort: `{sort}`")
        params = {
            "take": take,
            "skip": skip,
            "filter": filter_by,
            "sort": sort,
        }
        if requested_by is not None:
            params["requestedBy"] = requested_by
        return await get(
            self._url + "/request",
            params=params,
            headers=self._headers,
            cookies=self._cookies,
        )

    @request_with_type(overseerr_type=User)
    async def _get_me(self) -> Union[User, ErrorResponse]:
        return await get(
            self._url + "/auth/me", headers=self._headers, cookies=self._cookies
        )

    @property
    def _headers(self) -> Dict[str, str]:
        """
        Headers to send with every request. Don't use this directly.
        If user/pass
        :return: Overseerr headers
        :rtype: Dict[str, str]
        """
        return {"Content-Type": "application/json"}

    @property
    def _headers_with_token(self) -> Dict[str, str]:
        return dict(**self._headers, **{"X-Api-Key": self._api_key})

    @property
    def _cookies(self):
        return self.__cookies

    @property
    def me(self) -> User:
        if self._me is None:
            self._me = asyncio.run(self._get_me())
        return self._me


def setup_logging():
    logging.TRACE = 5
    logging.addLevelName(logging.TRACE, "TRACE")
    logging.Logger.trace = partialmethod(logging.Logger.log, logging.TRACE)
    logging.trace = partial(logging.log, logging.TRACE)
