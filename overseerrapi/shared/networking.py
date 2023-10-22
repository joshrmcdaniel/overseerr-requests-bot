import aiohttp
import aiohttp.client_exceptions
from ..types import ErrorResponse
from ..types.load import load_error
from typing import List, Optional, TypeVar, Dict, Union, Any
import json
import urllib.parse
import logging

from json import JSONDecoder

logger = logging.getLogger(__name__)

R = TypeVar("R", Dict, List[Dict], ErrorResponse)

__all__ = ["get", "post", "put"]


def empty_string_to_none(values: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(values, list):
        for i, v in enumerate(values):
            if not v:
                values[i] = None
    elif isinstance(values, dict):
        for k in values:
            if not values[k]:
                values[k] = None
    return values


DECODER = JSONDecoder(object_hook=empty_string_to_none).decode


async def get(
    url: str,
    *,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    logger.debug("Sending GET requests to %s", url)
    logger.trace("Parameters: %s", params)
    if params:
        params = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            try:
                resp = await r.json(loads=DECODER)
                logger.debug("Received response %d from %s", r.status, url)
                logger.log(5, "Response: %s", resp)
                r.raise_for_status()

            except aiohttp.client_exceptions.ClientConnectionError as cce:
                logger.error(f"Error while requesting %s: %s", url, cce)
                logger.fatal(cce)

            except aiohttp.client_exceptions.ClientResponseError as cre:
                try:
                    return load_error(resp)
                except Exception as e:
                    logger.error(f"Error while requesting %s: %s", url, cre)
                    raise e
            return resp


async def post(
    url: str,
    *,
    body: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    if body:
        body = json.dumps(body).encode("ascii")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, data=body) as r:
            try:
                resp = await r.json(loads=DECODER)
                logger.debug("Received response %d from %s", r.status, url)
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                logger.error(f"Error while requesting %s: %s", url, cre)
                try:
                    return load_error(resp)
                except Exception as e:
                    logger.error("Error while loading error response: %s", e)
                    raise e from cre
            return resp


async def put(
    url: str,
    *,
    body: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    if body:
        body = json.dumps(body).encode("ascii")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.put(url, data=body) as r:
            try:
                resp = await r.json(loads=DECODER)
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                logger.error(f"Error while requesting %s: %s", url, cre)
                try:
                    return load_error(resp)
                except Exception as e:
                    logger.error("Error while loading error response: %s", e)
                    raise e from cre
            return resp
