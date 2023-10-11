import aiohttp
from typing import List, LiteralString, Union, Optional, TypeVar, Literal, Dict
import os
import loguru
import json
import urllib.parse
import shared
import sys
from overseerr_types import OverseerrErrorResult

M: TypeVar = TypeVar(
    "M", Literal["GET"], Literal["POST"], Literal["PUT"], Literal["DELETE"]
)

ENDPOINT = os.environ.get("OVERSEERR_URL")

logger = loguru.logger
logger.remove()
logger.add(sys.stderr, level="TRACE")
def _request(method: M):
    pass


async def get(
    url: str,
    *,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Union[Dict, OverseerrErrorResult]:
    if params:
        params = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()
        )
        url = f"{url}?{params}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            try:
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                try:
                    res = shared.load_json(await r.json(), OverseerrErrorResult)
                    return res
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {cre}")
                    raise e
            return await r.json()


async def post(
    url: str,
    *,
    body: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Union[Dict, OverseerrErrorResult]:
    body = json.dumps(body).encode('ascii')
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, data=body) as r:
            try:
                r.raise_for_status()
            except aiohttp.ClientResponseError as cre:
                try:
                    res = shared.load_json(await r.json(), OverseerrErrorResult)
                    return res
                except Exception as e:
                    logger.error(f"Error while requesting {url}: {cre}, {e}")
                    raise e from cre
            return await r.json()
