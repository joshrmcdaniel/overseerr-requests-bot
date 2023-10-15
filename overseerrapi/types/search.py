import jsonobject


from .shared import PageInfo

from .user import User


class MediaSearchResult(jsonobject.JsonObject):
    page = jsonobject.IntegerProperty(name="page")
    total_results = jsonobject.IntegerProperty(name="totalResults")
    total_pages = jsonobject.IntegerProperty(name="totalPages")
    results = jsonobject.ListProperty(lambda: jsonobject.JsonObject, name="results")


class UserSearchResult(jsonobject.JsonObject):
    page_info = jsonobject.ObjectProperty(lambda: PageInfo, name="pageInfo")
    results = jsonobject.ListProperty(lambda: User, name="results")
