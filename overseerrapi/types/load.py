from jsonobject import JsonArray, JsonObject
from typing import Union, TypeVar, List, Dict


T = TypeVar("T", bound=[JsonArray, JsonObject])
J = TypeVar("J", List[Dict], Dict)


def load_json(*, json_data: J, overseerr_type: T) -> T:
    if isinstance(json_data, list):
        return [overseerr_type.wrap(i) for i in json_data]
    return overseerr_type(json_data)
