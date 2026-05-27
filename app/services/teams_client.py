"""Microsoft Graph API client using MSAL for app-only (client credentials) auth."""
import asyncio
import re
import time
from typing import Any

import httpx
import msal
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]
_TIMEOUT = httpx.Timeout(30.0)

_token_cache: dict = {"access_token": None, "expires_at": 0}


def _get_access_token() -> str:
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    app = msal.ConfidentialClientApplication(
        client_id=settings.azure_client_id,
        client_credential=settings.azure_client_secret,
        authority=f"https://login.microsoftonline.com/{settings.azure_tenant_id}",
    )
    result = app.acquire_token_for_client(scopes=_SCOPE)
    if "access_token" not in result:
        raise RuntimeError(f"MSAL error: {result.get('error_description', result)}")

    _token_cache["access_token"] = result["access_token"]
    _token_cache["expires_at"] = time.time() + result.get("expires_in", 3600)
    return result["access_token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_access_token()}",
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_GRAPH}{path}", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def post(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}{path}", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json() if r.content else {}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def patch(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.patch(f"{_GRAPH}{path}", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json() if r.content else {}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def delete(path: str) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.delete(f"{_GRAPH}{path}", headers=_headers())
        r.raise_for_status()


async def paginate(path: str, params: dict | None = None) -> list[Any]:
    """Follow @odata.nextLink pagination and return all records."""
    results: list[Any] = []
    next_url: str | None = f"{_GRAPH}{path}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        while next_url:
            r = await c.get(next_url, headers=_headers(), params=params if next_url == f"{_GRAPH}{path}" else None)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")

    return results


async def post_team(payload: dict, poll_timeout: int = 60) -> dict:
    """
    POST /teams is async — Graph returns 202 + Location header.
    This function posts and polls the Location until the team is provisioned.
    Returns the team object with its id.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}/teams", headers=_headers(), json=payload)
        if r.status_code not in (200, 201, 202):
            r.raise_for_status()

        if r.status_code in (200, 201) and r.content:
            return r.json()

        # 202 — poll the Location or Content-Location header
        location = r.headers.get("Location") or r.headers.get("Content-Location", "")
        # Extract team ID from path like /teams('xxxxxxxx-...')
        team_id_match = re.search(r"teams\('([^']+)'\)", location)
        if not team_id_match:
            team_id_match = re.search(r"teams/([0-9a-f-]{36})", location)

        deadline = time.time() + poll_timeout
        while time.time() < deadline:
            await asyncio.sleep(3)
            if team_id_match:
                team_id = team_id_match.group(1)
                try:
                    rp = await c.get(f"{_GRAPH}/teams/{team_id}", headers=_headers())
                    if rp.status_code == 200:
                        return rp.json()
                except httpx.HTTPStatusError:
                    pass
            else:
                # Poll the operation URL directly
                rp = await c.get(f"{_GRAPH}{location}", headers=_headers())
                if rp.status_code == 200:
                    data = rp.json()
                    if data.get("status") == "succeeded":
                        target = data.get("targetResourceLocation", "")
                        tid_match = re.search(r"/teams/([0-9a-f-]{36})", target)
                        if tid_match:
                            rt = await c.get(f"{_GRAPH}/teams/{tid_match.group(1)}", headers=_headers())
                            if rt.status_code == 200:
                                return rt.json()

        raise TimeoutError(f"Team provisioning did not complete within {poll_timeout}s. Location: {location}")
