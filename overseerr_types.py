from typing import TypedDict, List, Union
import jsonobject


class OverseerrError(jsonobject.JsonObject):
    path = jsonobject.StringProperty(name="path")
    message = jsonobject.StringProperty(name="message")


class OverseerrErrorResult(jsonobject.JsonObject):
    message = jsonobject.StringProperty(name="message")
    errors = jsonobject.ListProperty(
        jsonobject.ObjectProperty(OverseerrError), name="errors"
    )


class MediaInfo(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    tmdb_id = jsonobject.IntegerProperty(name="tmdbId")
    tvdb_id = jsonobject.IntegerProperty(name="tvdbId")
    status = jsonobject.IntegerProperty(choices=[1, 2, 3, 4, 5], name="status")
    requests = jsonobject.DefaultProperty(name="requests")
    created_at = jsonobject.StringProperty(name="createdAt")
    updated_at = jsonobject.StringProperty(name="updatedAt")


class MovieResult(jsonobject.JsonObject):
    adult = jsonobject.BooleanProperty(name="adult")
    media_type = jsonobject.StringProperty(choices=["movie"], name="mediaType")
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    genre_ids = jsonobject.ListProperty(int, name="genreIds")
    id = jsonobject.IntegerProperty(name="id")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    original_title = jsonobject.StringProperty(name="originalTitle")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    poster_path = jsonobject.StringProperty(name="posterPath")
    release_date = jsonobject.StringProperty(name="releaseDate")
    title = jsonobject.StringProperty(name="title")
    video = jsonobject.BooleanProperty(name="video")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")
    media_info = jsonobject.ObjectProperty(
        jsonobject.ObjectProperty(MediaInfo), name="mediaInfo"
    )


class TvResult(jsonobject.JsonObject):
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    media_type = jsonobject.StringProperty(choices=["tv"], name="mediaType")
    first_air_date = jsonobject.StringProperty(name="firstAirDate")
    genre_ids = jsonobject.ListProperty(int, name="genreIds")
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    original_language = jsonobject.StringProperty(name="originalLanguage")
    original_name = jsonobject.StringProperty(name="originalName")
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    poster_path = jsonobject.StringProperty(name="posterPath")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")
    media_info = jsonobject.ObjectProperty(
        jsonobject.ObjectProperty(MediaInfo), name="mediaInfo"
    )


# Combine Tv Result and Movie Result into one
class MediaResult(jsonobject.JsonObject):
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    genre_ids = jsonobject.ListProperty(int, name="genreIds")
    id = jsonobject.IntegerProperty(name="id")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    poster_path = jsonobject.StringProperty(name="posterPath")
    release_date = jsonobject.StringProperty(name="releaseDate")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")

    # TV Specific
    first_air_date = jsonobject.StringProperty(name="firstAirDate")
    name = jsonobject.StringProperty(name="name")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    original_name = jsonobject.StringProperty(name="originalName")
    popularity = jsonobject.DecimalProperty(name="popularity")
    poster_path = jsonobject.StringProperty(name="posterPath")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")

    # Movie Specific
    adult = jsonobject.BooleanProperty(name="adult")
    original_title = jsonobject.StringProperty(name="originalTitle")
    video = jsonobject.BooleanProperty(name="video")
    title = jsonobject.StringProperty(name="title")


class PersonResult(jsonobject.JsonObject):
    adult = jsonobject.BooleanProperty(name="adult")
    id = jsonobject.IntegerProperty(name="id")
    known_for = jsonobject.ListProperty(
        jsonobject.ObjectProperty(MediaResult), name="knownFor"
    )
    media_type = jsonobject.StringProperty(name="mediaType")
    profile_path = jsonobject.StringProperty(name="profilePath")


class SearchResult(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    media_type = jsonobject.StringProperty(name="mediaType")
    popularity = jsonobject.DecimalProperty(name="popularity")
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    poster_path = jsonobject.StringProperty(name="posterPath")
    vote_count = jsonobject.IntegerProperty(name="voteCount")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    genre_ids = jsonobject.ListProperty(int, name="genreIds")
    overview = jsonobject.StringProperty(name="overview")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    media_info = jsonobject.ObjectProperty(MediaInfo, name="mediaInfo")
    adult = jsonobject.BooleanProperty(name="adult")
    original_title = jsonobject.StringProperty(name="originalTitle")
    release_date = jsonobject.StringProperty(name="releaseDate")
    title = jsonobject.StringProperty(name="title")
    video = jsonobject.BooleanProperty(name="video")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    first_air_date = jsonobject.StringProperty(name="firstAirDate")
    name = jsonobject.StringProperty(name="name")
    original_name = jsonobject.StringProperty(name="originalName")
    profile_path = jsonobject.StringProperty(name="profilePath")
    known_for = jsonobject.ListProperty(lambda: SearchResult, name="knownFor")


class Search(jsonobject.JsonObject):
    page = jsonobject.IntegerProperty(name="page")
    total_results = jsonobject.IntegerProperty(name="totalResults")
    total_pages = jsonobject.IntegerProperty(name="totalPages")
    results = jsonobject.ListProperty(
        jsonobject.ObjectProperty(SearchResult), name="results"
    )


class RequestMediaRequest(jsonobject.JsonObject):
    media_type = jsonobject.StringProperty(name="mediaType")
