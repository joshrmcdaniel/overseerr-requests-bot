from typing import Dict, List, Any, Union
import jsonobject


async def load_json(
    data: Union[List[Any], Dict[str, Any]], json_type: jsonobject.JsonObject
) -> jsonobject.JsonObject:
    return json_type(data)
