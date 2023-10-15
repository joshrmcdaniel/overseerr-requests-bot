import jsonobject


class PageInfo(jsonobject.JsonObject):
    pages = jsonobject.IntegerProperty(name="pages")
    page_size = jsonobject.IntegerProperty(name="pageSize")
    results = jsonobject.IntegerProperty(name="results")
    page = jsonobject.IntegerProperty(name="page")
