import jsonobject

class MediaInfo(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    tmdb_id = jsonobject.IntegerProperty(name="tmdbId")
    tvdb_id = jsonobject.IntegerProperty(name="tvdbId")
    status = jsonobject.IntegerProperty(choices=[1, 2, 3, 4, 5], name="status")
    requests = jsonobject.DefaultProperty(name="requests")
    created_at = jsonobject.StringProperty(name="createdAt")
    updated_at = jsonobject.StringProperty(name="updatedAt")


class PersonResult(jsonobject.JsonObject):
    adult = jsonobject.BooleanProperty(name="adult")
    id = jsonobject.IntegerProperty(name="id")
    known_for = jsonobject.ListProperty(
        jsonobject.DefaultProperty(), name="knownFor"
    )  # parsed in return
    media_type = jsonobject.StringProperty(name="mediaType")
    profile_path = jsonobject.StringProperty(name="profilePath")


RELATED_VIDEO_TYPES = [
    "Clip",
    "Teaser",
    "Trailer",
    "Featurette",
    "Opening Credits",
    "Behind the Scenes",
    "Bloopers",
]


class RelatedVideo(jsonobject.JsonObject):
    url = jsonobject.StringProperty(name="url")
    key = jsonobject.StringProperty(name="key")
    name = jsonobject.StringProperty(name="name")
    size = jsonobject.IntegerProperty(name="size")
    type = jsonobject.StringProperty(name="type", choices=RELATED_VIDEO_TYPES)
    site = jsonobject.StringProperty(name="site", choices=["YouTube", "Vimeo", ""])


class ProductionCompany(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    logo_path = jsonobject.StringProperty(name="logoPath")
    origin_country = jsonobject.StringProperty(name="originCountry")
    name = jsonobject.StringProperty(name="name")


class ProductionCountry(jsonobject.JsonObject):
    iso_3166_1 = jsonobject.StringProperty(name="iso_3166_1")
    name = jsonobject.StringProperty(name="name")


class CreatedBy(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")
    gender = jsonobject.IntegerProperty(name="gender")
    profile_path = jsonobject.StringProperty(name="profilePath")


class ReleaseDate(jsonobject.JsonObject):
    certification = jsonobject.StringProperty(name="certification")
    descriptors = jsonobject.ListProperty(lambda: str, name="descriptors")
    iso_639_1 = jsonobject.StringProperty(name="iso_639_1")
    note = jsonobject.StringProperty(name="note")
    release_date = jsonobject.DateTimeProperty(name="release_date")
    type = jsonobject.IntegerProperty(name="type")


class Rating(jsonobject.JsonObject):
    iso_3166_1 = jsonobject.StringProperty(name="iso_3166_1")
    rating = jsonobject.StringProperty(name="rating")


class Release(jsonobject.JsonObject):
    iso_3166_1 = jsonobject.StringProperty(name="iso_3166_1")
    rating = jsonobject.StringProperty(name="rating")
    release_dates = jsonobject.ListProperty(lambda: ReleaseDate, name="release_dates")


class SpokenLanguage(jsonobject.JsonObject):
    iso_639_1 = jsonobject.StringProperty(name="iso_639_1")
    name = jsonobject.StringProperty(name="name")
    english_name = jsonobject.StringProperty(name="english_name")


class Cast(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    cast_id = jsonobject.IntegerProperty(name="castId")
    character = jsonobject.StringProperty(name="character")
    credit_id = jsonobject.StringProperty(name="creditId")
    gender = jsonobject.IntegerProperty(name="gender")
    name = jsonobject.StringProperty(name="name")
    order = jsonobject.IntegerProperty(name="order")
    profile_path = jsonobject.StringProperty(name="profilePath")


class Crew(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    credit_id = jsonobject.StringProperty(name="creditId")
    gender = jsonobject.IntegerProperty(name="gender")
    name = jsonobject.StringProperty(name="name")
    job = jsonobject.StringProperty(name="job")
    department = jsonobject.StringProperty(name="department")
    profile_path = jsonobject.StringProperty(name="profilePath")


class Credits(jsonobject.JsonObject):
    cast = jsonobject.ListProperty(lambda: Cast, name="cast")
    crew = jsonobject.ListProperty(lambda: Crew, name="crew")


class Collection(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")
    poster_path = jsonobject.StringProperty(name="posterPath")
    backdrop_path = jsonobject.StringProperty(name="backdropPath")


class ExternalIds(jsonobject.JsonObject):
    facebook_id = jsonobject.StringProperty(name="facebookId", exclude_if_none=True)
    freebase_id = jsonobject.StringProperty(name="freebaseId", exclude_if_none=True)
    freebase_mid = jsonobject.StringProperty(name="freebaseMid", exclude_if_none=True)
    imdb_id = jsonobject.StringProperty(name="imdbId", exclude_if_none=True)
    instagram_id = jsonobject.StringProperty(name="instagramId", exclude_if_none=True)
    tvdb_id = jsonobject.IntegerProperty(name="tvdbId", exclude_if_none=True)
    tvrage_id = jsonobject.IntegerProperty(name="tvrageId", exclude_if_none=True)
    twitter_id = jsonobject.StringProperty(name="twitterId", exclude_if_none=True)


class WatchProvider(jsonobject.JsonObject):
    iso_3166_1 = jsonobject.StringProperty(name="iso_3166_1")
    link = jsonobject.StringProperty(name="link")
    buy = jsonobject.ListProperty(lambda: jsonobject.JsonObject, name="buy")
    flatrate = jsonobject.ListProperty(lambda: jsonobject.JsonObject, name="flatrate")
