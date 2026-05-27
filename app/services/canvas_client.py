"""HTTP client wrapper for the Canvas LMS REST API v1."""
import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_BASE = f"{settings.canvas_base_url.rstrip('/')}/api/v1"
_HEADERS = {"Authorization": f"Bearer {settings.canvas_access_token}"}
_TIMEOUT = httpx.Timeout(30.0)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=_BASE, headers=_HEADERS, timeout=_TIMEOUT)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def get(path: str, params: dict | None = None) -> Any:
    async with _client() as c:
        r = await c.get(path, params=params)
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def post(path: str, payload: dict) -> Any:
    async with _client() as c:
        r = await c.post(path, json=payload)
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def put(path: str, payload: dict) -> Any:
    async with _client() as c:
        r = await c.put(path, json=payload)
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def delete(path: str, params: dict | None = None) -> Any:
    async with _client() as c:
        r = await c.delete(path, params=params)
        r.raise_for_status()
        # Canvas returns 200 with body or 204 with no body
        return r.json() if r.content else {}


async def paginate(path: str, params: dict | None = None) -> list[Any]:
    """Follow Canvas Link-header pagination and return all records."""
    results: list[Any] = []
    params = dict(params or {})
    params.setdefault("per_page", 100)
    next_url: str | None = path

    async with _client() as c:
        while next_url:
            if next_url.startswith("http"):
                # Absolute URL returned by Canvas in Link header
                r = await c.get(next_url, params=params if next_url == path else None)
            else:
                r = await c.get(next_url, params=params)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
            link = r.headers.get("Link", "")
            next_url = _parse_next_link(link)

    return results


def _parse_next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        segments = part.strip().split(";")
        if len(segments) == 2 and 'rel="next"' in segments[1]:
            return segments[0].strip().strip("<>")
    return None
