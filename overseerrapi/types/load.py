from jsonobject import JsonArray, JsonObject
from typing import Union, TypeVar, List, Dict

from .error import ErrorResponse


T = TypeVar("T", bound=[JsonArray, JsonObject])
J = TypeVar("J", List[Dict], Dict)


def load_json(*, json_data: J, overseerr_type: T) -> T:
    if isinstance(json_data, list):
        return [overseerr_type.wrap(i) for i in json_data]
    return overseerr_type(json_data)


def load_error(json_data: J) -> ErrorResponse:
    return load_json(json_data=json_data, overseerr_type=ErrorResponse)
