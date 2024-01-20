import jsonobject


from .shared import PageInfo
from .tv import TvResult, TVDetails
from .movie import MovieResult, MovieDetails
from .user import User


class MediaResult(jsonobject.JsonObject):
    _type = (MovieResult, MovieDetails,TvResult, TVDetails)
    def __init__(self, *args, **kwargs):
        super(jsonobject.JsonObject, self).__init__(*args, **kwargs)


class MediaSearchResult(jsonobject.JsonObject):
    page = jsonobject.IntegerProperty(name="page")
    total_results = jsonobject.IntegerProperty(name="totalResults")
    total_pages = jsonobject.IntegerProperty(name="totalPages")
    results = jsonobject.ListProperty(lambda: MediaResult, name="results")


class UserSearchResult(jsonobject.JsonObject):
    page_info = jsonobject.ObjectProperty(lambda: PageInfo, name="pageInfo")
    results = jsonobject.ListProperty(lambda: User, name="results")
