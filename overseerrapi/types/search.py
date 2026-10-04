import jsonobject


from .shared import PageInfo
from .tv import TvResult
from .movie import MovieResult
from .media import PersonResult
from .user import User


class MediaResultProperty(jsonobject.ObjectProperty):
    def __init__(self, **kwargs):
        super().__init__(jsonobject.JsonObject, **kwargs)

    def wrap(self, obj):
        result_types = {
            "movie": MovieResult,
            "tv": TvResult,
            "person": PersonResult,
        }
        media_type = obj.get("mediaType")
        if media_type not in result_types:
            raise ValueError(f"Unknown search result media type: {media_type!r}")
        return result_types[media_type].wrap(obj)


class MediaSearchResult(jsonobject.JsonObject):
    page = jsonobject.IntegerProperty(name="page")
    total_results = jsonobject.IntegerProperty(name="totalResults")
    total_pages = jsonobject.IntegerProperty(name="totalPages")
    results = jsonobject.ListProperty(MediaResultProperty(), name="results")


class UserSearchResult(jsonobject.JsonObject):
    page_info = jsonobject.ObjectProperty(lambda: PageInfo, name="pageInfo")
    results = jsonobject.ListProperty(lambda: User, name="results")
