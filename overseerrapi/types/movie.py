import jsonobject

from . import (
    MediaInfo,
    Release,
    Genre,
    RelatedVideo,
    ProductionCompany,
    ProductionCountry,
    SpokenLanguage,
    Credits,
    Collection,
    ExternalIds,
    WatchProvider,
)


class MovieResult(jsonobject.JsonObject):
    adult = jsonobject.BooleanProperty(name="adult")
    media_type = jsonobject.StringProperty(
        choices=["movie"], name="mediaType", required=True
    )
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    genre_ids = jsonobject.ListProperty(jsonobject.IntegerProperty(), name="genreIds")
    id = jsonobject.IntegerProperty(name="id")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    original_title = jsonobject.StringProperty(name="originalTitle")
    origin_country = jsonobject.ListProperty(
        jsonobject.StringProperty(), name="originCountry"
    )
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    poster_path = jsonobject.StringProperty(name="posterPath")
    release_date = jsonobject.DateProperty(name="releaseDate")
    title = jsonobject.StringProperty(name="title")
    video = jsonobject.BooleanProperty(name="video")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")
    media_info = jsonobject.ObjectProperty(lambda: MediaInfo, name="mediaInfo")


class MovieDetailReleases(jsonobject.JsonObject):
    results = jsonobject.ListProperty(lambda: Release, name="results")


class MovieDetails(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id", required=True)
    imdb_id = jsonobject.StringProperty(name="imdbId")
    adult = jsonobject.BooleanProperty(name="adult")
    backdrop_path = jsonobject.StringProperty(name="backdropPath")
    poster_path = jsonobject.StringProperty(name="posterPath")
    budget = jsonobject.IntegerProperty(name="budget")
    genres = jsonobject.ListProperty(lambda: Genre, name="genres")
    homepage = jsonobject.StringProperty(name="homepage")
    related_videos = jsonobject.ListProperty(lambda: RelatedVideo, name="relatedVideos")
    original_language = jsonobject.StringProperty(name="originalLanguage")
    original_title = jsonobject.StringProperty(name="originalTitle")
    overview = jsonobject.StringProperty(name="overview")
    popularity = jsonobject.DecimalProperty(name="popularity")
    production_companies = jsonobject.ListProperty(
        lambda: ProductionCompany, name="productionCompanies"
    )
    production_countries = jsonobject.ListProperty(
        lambda: ProductionCountry, name="productionCountries"
    )
    release_date = jsonobject.DateProperty(name="releaseDate")
    releases = jsonobject.ObjectProperty(lambda: MovieDetailReleases, name="releases")
    revenue = jsonobject.IntegerProperty(name="revenue")
    runtime = jsonobject.IntegerProperty(name="runtime")
    spoken_languages = jsonobject.ListProperty(
        lambda: SpokenLanguage, name="spokenLanguages"
    )
    status = jsonobject.StringProperty(name="status")
    tagline = jsonobject.StringProperty(name="tagline")
    title = jsonobject.StringProperty(name="title")
    video = jsonobject.BooleanProperty(name="video")
    vote_average = jsonobject.DecimalProperty(name="voteAverage")
    vote_count = jsonobject.IntegerProperty(name="voteCount")
    credits = jsonobject.ObjectProperty(lambda: Credits, name="credits")
    collection = jsonobject.ObjectProperty(lambda: Collection, name="collection")
    external_ids = jsonobject.ObjectProperty(lambda: ExternalIds, name="externalIds")
    media_info = jsonobject.ObjectProperty(lambda: MediaInfo, name="mediaInfo")
    watch_providers = jsonobject.ListProperty(
        lambda: WatchProvider, name="watchProviders"
    )
