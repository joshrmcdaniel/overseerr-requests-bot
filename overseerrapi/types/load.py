from jsonobject import JsonArray, JsonObject
from typing import Union, TypeVar, List, Dict


T = TypeVar("T", JsonArray, JsonObject)
J = TypeVar("J", List[Dict], Dict)


def load_json(*, json_data: J, overseerr_type: T) -> Union[JsonArray, JsonObject]:
    return overseerr_type(json_data)
