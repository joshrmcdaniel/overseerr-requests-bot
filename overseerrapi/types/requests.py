from typing import Literal, get_args

import jsonobject


from .media import MediaInfo
from .shared import PageInfo
from .user import User


RequestsSortOpts = Literal[
    "added",
    "modified"
]
REQUESTS_SORT_OPTS = get_args(RequestsSortOpts)


RequestsFilterByOpts = Literal[
    "all",
    "approved",
    "available",
    "pending",
    "processing",
    "unavailable",
    "failed"
]

REQUESTS_FILTER_OPTS = get_args(RequestsFilterByOpts)

class RequestBody(jsonobject.JsonObject):
    media_id = jsonobject.IntegerProperty(name="mediaId", required=True)
    media_type = jsonobject.StringProperty(name="mediaType", required=True)
    user_id = jsonobject.IntegerProperty(name="userId")
    tvdb_id = jsonobject.IntegerProperty(name="tvdbId", exclude_if_none=True)
    seasons = jsonobject.DefaultProperty(name="seasons", exclude_if_none=True)
    is_4k = jsonobject.BooleanProperty(name="is4k", exclude_if_none=True)
    server_id = jsonobject.IntegerProperty(name="serverId", exclude_if_none=True)
    profile_id = jsonobject.IntegerProperty(name="profileId", exclude_if_none=True)
    root_folder = jsonobject.StringProperty(name="rootFolder", exclude_if_none=True)
    language_profile_id = jsonobject.IntegerProperty(
        name="languageProfileId", exclude_if_none=True
    )
    media_type = jsonobject.StringProperty(name="mediaType", required=True)


class Request(jsonobject.JsonObject):
    id = jsonobject.IntegerProperty(name="id", required=True)
    status = jsonobject.IntegerProperty(
        choices=[1, 2, 3, 4], name="status", required=True
    )
    media = jsonobject.ObjectProperty(lambda: MediaInfo, name="media")
    created_at = jsonobject.DateTimeProperty(name="createdAt", required=True)
    updated_at = jsonobject.DateTimeProperty(name="updatedAt", required=True)
    requested_by = jsonobject.ObjectProperty(
        lambda: User, name="requestedBy", required=True
    )
    modified_by = jsonobject.ObjectProperty(lambda: User, name="modifiedBy")
    is_4k = jsonobject.BooleanProperty(name="is4k")
    server_id = jsonobject.IntegerProperty(name="serverId")
    profile_id = jsonobject.IntegerProperty(name="profileId")
    root_folder = jsonobject.StringProperty(name="rootFolder")


class RequestCount(jsonobject.JsonObject):
    total = jsonobject.IntegerProperty(name="total", required=True)
    movie = jsonobject.IntegerProperty(name="movie", required=True)
    tv = jsonobject.IntegerProperty(name="tv", required=True)
    pending = jsonobject.IntegerProperty(name="pending", required=True)
    approved = jsonobject.IntegerProperty(name="approved", required=True)
    declined = jsonobject.IntegerProperty(name="declined", required=True)
    processing = jsonobject.IntegerProperty(name="processing", required=True)
    available = jsonobject.IntegerProperty(name="available", required=True)


class Requests(jsonobject.JsonObject):
    page_info = jsonobject.ObjectProperty(
        lambda: PageInfo, name="pageInfo", required=True
    )
    results = jsonobject.ListProperty(lambda: Request, name="results", required=True)
