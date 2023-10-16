
import logging
from typing import Any, Awaitable, Union
from functools import wraps
from ..types import _load_type as load_type, ErrorResponse

logger = logging.getLogger(__name__)

__all__ = [
    "_request_with_type"
]

def _request_with_type(overseerr_type, raise_for_error=False):
    def _request(f: Awaitable) -> Union[ErrorResponse, overseerr_type]:
        @wraps(f)
        async def wrapper(*args, **kwargs):
            res = await f(*args, **kwargs)
            if isinstance(res, ErrorResponse):
                if raise_for_error:
                    raise RuntimeError(res.message)
                return res
            logger.debug("Loading type %s", overseerr_type.__name__)
            data = load_type(json_data=res, overseerr_type=overseerr_type)
            logger.debug("Loaded type %s", overseerr_type.__name__)
            logger.log(5, "Data: %s", data)
            return data

        return wrapper

    return _request
