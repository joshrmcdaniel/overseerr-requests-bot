import jsonobject


from .genre import Genre
from .media import (
    MediaInfo,
    Rating,
    CreatedBy,
    ProductionCompany,
    ProductionCountry,
    SpokenLanguage,
    Credits,
    ExternalIds,
)


class TvResult(jsonobject.JsonObject):
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    media_type = jsonobject.StringProperty(
        choices=["tv"], name="mediaType", required=True
    )
    first_air_date = jsonobject.StringProperty(name="firstAirDate")
    genre_ids = jsonobject.ListProperty(jsonobject.IntegerProperty(), name="genreIds")
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
    media_info = jsonobject.ObjectProperty(lambda: MediaInfo, name="mediaInfo")


class TVEpisode(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")
    air_date = jsonobject.DateProperty(name="airDate")
    episode_number = jsonobject.IntegerProperty(name="episodeNumber")
    overview = jsonobject.StringProperty(name="overview")
    production_code = jsonobject.StringProperty(name="productionCode")
    show_id = jsonobject.IntegerProperty(name="showId")
    season_number = jsonobject.IntegerProperty(name="seasonNumber")
    still_path = jsonobject.StringProperty(name="stillPath")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")


class TVSeason(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    air_date = jsonobject.DateProperty(name="airDate")
    episode_count = jsonobject.IntegerProperty(name="episodeCount")
    name = jsonobject.StringProperty(name="name")
    overview = jsonobject.StringProperty(name="overview")
    poster_path = jsonobject.StringProperty(name="posterPath")
    season_number = jsonobject.IntegerProperty(name="seasonNumber")
    episodes = jsonobject.ListProperty(lambda: TVEpisode, name="episodes")


class Keywords(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")


class TVDetails(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id", required=True)
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    poster_path = jsonobject.StringProperty(name="posterPath")
    content_ratings = jsonobject.ObjectProperty(lambda: Rating, name="contentRatings")
    created_by = jsonobject.ListProperty(lambda: CreatedBy, name="createdBy")
    episode_run_time = jsonobject.ListProperty(
        jsonobject.IntegerProperty(), name="episodeRunTime"
    )
    first_air_date = jsonobject.DateProperty(name="firstAirDate")
    genres = jsonobject.ListProperty(lambda: Genre, name="genres")
    homepage = jsonobject.StringProperty(name="homepage")
    in_production = jsonobject.BooleanProperty(name="inProduction")
    languages = jsonobject.ListProperty(jsonobject.StringProperty(), name="languages")
    last_air_date = jsonobject.DateProperty(name="lastAirDate")
    last_episode_to_air = jsonobject.ObjectProperty(
        lambda: TVEpisode, name="lastEpisodeToAir"
    )
    name = jsonobject.StringProperty(name="name")
    next_episode_to_air = jsonobject.ObjectProperty(
        lambda: TVEpisode, name="nextEpisodeToAir"
    )
    networks = jsonobject.ListProperty(lambda: ProductionCompany, name="networks")
    number_of_episodes = jsonobject.IntegerProperty(name="numberOfEpisodes")
    number_of_seasons = jsonobject.IntegerProperty(name="numberOfSeasons")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    original_language = jsonobject.StringProperty(name="originalLanguage")
    original_name = jsonobject.StringProperty(name="originalName")
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    production_companies = jsonobject.ListProperty(
        lambda: ProductionCompany, name="productionCompanies"
    )
    production_countries = jsonobject.ListProperty(
        lambda: ProductionCountry, name="productionCountries"
    )
    spoken_languages = jsonobject.ListProperty(
        lambda: SpokenLanguage, name="spokenLanguages"
    )
    seasons = jsonobject.ListProperty(lambda: TVSeason, name="seasons")
    credits = jsonobject.ObjectProperty(lambda: Credits, name="credits")
    external_ids = jsonobject.ObjectProperty(lambda: ExternalIds, name="externalIds")
    media_info = jsonobject.ObjectProperty(lambda: MediaInfo, name="mediaInfo")
    keywords = jsonobject.ListProperty(lambda: Keywords, name="keywords")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")


class TVSearchResponse(jsonobject.JsonObject):
    page = jsonobject.IntegerProperty(name="page")
    total_results = jsonobject.IntegerProperty(name="totalResults")
    total_pages = jsonobject.IntegerProperty(name="totalPages")
    results = jsonobject.ListProperty(lambda: TvResult, name="results")
