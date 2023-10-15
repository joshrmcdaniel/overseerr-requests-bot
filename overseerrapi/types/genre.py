import jsonobject


class Genre(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id")
    name = jsonobject.StringProperty(name="name")


class Genres(jsonobject.JsonArray):
    item_type = Genre
