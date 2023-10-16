import aiohttp
import aiohttp.client_exceptions
from ..types import ErrorResponse, _load_type
from typing import List, Optional, TypeVar, Dict
import json
import urllib.parse
import logging


logger = logging.getLogger(__name__)

R = TypeVar("R", Dict, List[Dict], ErrorResponse)

__all__ = ["get", "post"]

async def get(
    url: str,
    *,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    logger.debug("Sending GET requests to {}", url)
    # logger.trace("Parameters: {}", params)
    if params:
        params = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            try:
                resp = await r.json()
                logger.debug("Received response {} from {}", r.status, url)
                logger.log(5, "Response: {}", resp)
                r.raise_for_status()

            except aiohttp.client_exceptions.ClientConnectionError as cce:
                logger.error(f"Error while requesting {url}: {cce}")
                logging.fatal(cce)

            except aiohttp.client_exceptions.ClientResponseError as cre:
                try:
                    res = _load_type(json_data=resp, overseerr_type=ErrorResponse)
                    return res
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {cre}")
                    raise e
            return resp


async def post(
    url: str,
    *,
    body: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> R:
    body = json.dumps(body).encode("ascii")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, data=body) as r:
            try:
                resp = await r.json()
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                try:
                    return _load_type(resp, ErrorResponse)
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {e}")
                    raise e from cre
            return resp
