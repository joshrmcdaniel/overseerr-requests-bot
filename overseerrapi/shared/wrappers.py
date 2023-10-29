import logging
from typing import Any, Awaitable, Union
from functools import wraps
from ..types import _load_type as load_type, ErrorResponse

logger = logging.getLogger(__name__)

__all__ = ["_request_with_type"]


def _request_with_type(overseerr_type, raise_for_error=False):
    """
    Generic request wrapper for overseerr types. This will load the response into the given type provided in `overseerr_type`.
    This is intended for internal use only.

    :param overseerr_type: The type to load the response into.
    :param raise_for_error: Whether or not to raise an exception if the response is an error.
    :return: The loaded type.
    :rtype: Union[ErrorResponse, overseerr_type]

    """

    def _request(f: Awaitable) -> Union[ErrorResponse, overseerr_type]:
        @wraps(f)
        async def wrapper(*args, **kwargs):
            res = await f(*args, **kwargs)
            print(type(res))
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
