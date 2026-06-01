"""Microsoft Graph API client using MSAL for app-only (client credentials) auth."""
import asyncio
import re
import time
from typing import Any

import httpx
import msal
from fastapi import HTTPException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]
_TIMEOUT = httpx.Timeout(30.0)

_token_cache: dict = {"access_token": None, "expires_at": 0}
_sku_cache: dict[str, str] = {}

_TRANSIENT = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.RemoteProtocolError,
    httpx.ReadError,
)
_retry = retry(
    retry=retry_if_exception_type(_TRANSIENT),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=8),
    reraise=True,
)


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


def _raise(r: httpx.Response) -> None:
    if r.is_error:
        # Extract Graph API error details from the response body
        try:
            body = r.json()
            graph_err = body.get("error", {})
            graph_code = graph_err.get("code", "")
            graph_msg  = graph_err.get("message", "")
        except Exception:
            graph_code, graph_msg = "", r.text[:300]

        if r.status_code == 401:
            msg = "Azure AD: credenciales inválidas (401). Verificá AZURE_TENANT_ID, AZURE_CLIENT_ID y AZURE_CLIENT_SECRET."
        elif r.status_code == 403:
            msg = f"Azure AD: acceso denegado (403). La app necesita permisos 'User.ReadWrite.All' con admin consent en Azure Portal."
            if graph_msg:
                msg += f" Detalle: {graph_msg}"
        else:
            parts = [f"Microsoft Graph {r.status_code}"]
            if graph_code:
                parts.append(f"[{graph_code}]")
            if graph_msg:
                parts.append(graph_msg)
            msg = " ".join(parts)
        raise HTTPException(status_code=r.status_code, detail=msg)


import logging as _logging
_logger = _logging.getLogger(__name__)


async def get_sku_id(part_number: str) -> str | None:
    """Return the skuId for the given SKU part number, or None if not found."""
    part_number = part_number.strip().lower()
    if part_number in _sku_cache:
        return _sku_cache[part_number]

    skus = await paginate("/subscribedSkus")
    for sku in skus:
        if sku.get("skuPartNumber", "").strip().lower() == part_number:
            sku_id = sku.get("skuId")
            if sku_id:
                _sku_cache[part_number] = sku_id
                return sku_id

    # Log available SKUs to help diagnose misconfiguration
    available = [s.get("skuPartNumber") for s in skus]
    _logger.warning(
        "SKU '%s' no encontrado en este tenant. SKUs disponibles: %s",
        part_number, available,
    )
    return None


async def assign_license(user_id: str, sku_part_number: str) -> Any:
    """Assign a license to the user. Returns None silently if the SKU is not available."""
    sku_id = await get_sku_id(sku_part_number)
    if sku_id is None:
        return None
    return await post(f"/users/{user_id}/assignLicense", {"addLicenses": [{"skuId": sku_id}], "removeLicenses": []})


@_retry
async def get(path: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{_GRAPH}{path}", headers=_headers(), params=params)
        _raise(r)
        return r.json()


@_retry
async def post(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}{path}", headers=_headers(), json=payload)
        _raise(r)
        return r.json() if r.content else {}


@_retry
async def patch(path: str, payload: dict) -> Any:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.patch(f"{_GRAPH}{path}", headers=_headers(), json=payload)
        _raise(r)
        return r.json() if r.content else {}


@_retry
async def delete(path: str) -> None:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.delete(f"{_GRAPH}{path}", headers=_headers())
        _raise(r)


async def paginate(path: str, params: dict | None = None) -> list[Any]:
    """Follow @odata.nextLink pagination and return all records."""
    results: list[Any] = []
    next_url: str | None = f"{_GRAPH}{path}"

    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        while next_url:
            r = await c.get(next_url, headers=_headers(), params=params if next_url == f"{_GRAPH}{path}" else None)
            _raise(r)
            data = r.json()
            results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")

    return results


async def paginate_limited(path: str, params: dict | None = None,
                           max_records: int = 5000,
                           extra_headers: dict | None = None) -> list[Any]:
    """Follow @odata.nextLink but stop at max_records to avoid long waits."""
    results: list[Any] = []
    next_url: str | None = f"{_GRAPH}{path}"
    req_headers = {**_headers(), **(extra_headers or {})}

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as c:
        while next_url and len(results) < max_records:
            r = await c.get(
                next_url,
                headers=req_headers,
                params=params if next_url == f"{_GRAPH}{path}" else None,
            )
            _raise(r)
            data = r.json()
            results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")

    return results[:max_records]


async def search_users(query: str, select: str | None = None) -> list[Any]:
    """Search users using Graph $search (requires ConsistencyLevel: eventual)."""
    params: dict = {
        "$search": f'"displayName:{query}" OR "userPrincipalName:{query}" OR "mail:{query}"',
        "$top": 50,
        "$select": select or "id,displayName,userPrincipalName,mail,department,jobTitle,accountEnabled",
        "$orderby": "displayName",
    }
    return await paginate_limited(
        "/users", params,
        max_records=200,
        extra_headers={"ConsistencyLevel": "eventual"},
    )


async def create_team_via_group(
    display_name: str,
    mail_nickname: str,
    description: str,
    visibility: str,
    owner_ids: list[str],
    member_ids: list[str] | None = None,
    email: str | None = None,
    replication_wait: int = 20,
    provision_timeout: int = 60,
) -> dict:
    """Create a Microsoft Team using the reliable Group → Team flow.

    Workaround for POST /teams with templates, which fails on many tenants
    with 'Failed to execute Templates backend request'.

    Steps:
      1. POST /groups  — create M365 group with owners + members + optional email alias
      2. Wait for Azure AD replication (~20s)
      3. PUT /groups/{id}/team  — provision Teams on the group
    """
    owner_binds  = [f"{_GRAPH}/users/{uid}" for uid in owner_ids]
    member_binds = [f"{_GRAPH}/users/{uid}" for uid in (member_ids or [])]

    group_payload: dict[str, Any] = {
        "displayName":   display_name,
        "mailNickname":  mail_nickname,
        "description":   description or "",
        "groupTypes":    ["Unified"],
        "mailEnabled":   True,
        "securityEnabled": False,
        "visibility":    visibility,
        "owners@odata.bind":  owner_binds,
    }
    if member_binds:
        group_payload["members@odata.bind"] = member_binds
    if email:
        group_payload["mail"] = email

    long_client = httpx.AsyncClient(timeout=httpx.Timeout(90.0))
    async with long_client as c:
        # Step 1 — create the group
        rg = await c.post(f"{_GRAPH}/groups", headers=_headers(), json=group_payload)
        if rg.status_code not in (200, 201):
            try:
                err = rg.json().get("error", {})
                detail = err.get("message", rg.text[:300])
            except Exception:
                detail = rg.text[:300]
            raise RuntimeError(f"Group creation failed ({rg.status_code}): {detail}")

        group_id = rg.json()["id"]

        # Step 2 — wait for Azure AD replication
        await asyncio.sleep(replication_wait)

        # Step 3 — provision Teams, retry up to provision_timeout seconds
        team_payload = {
            "memberSettings":   {"allowCreateUpdateChannels": True},
            "messagingSettings": {"allowUserEditMessages": True, "allowUserDeleteMessages": True},
            "funSettings":      {"allowGiphy": False},
        }
        deadline = time.time() + provision_timeout
        last_err = ""
        while time.time() < deadline:
            rt = await c.put(
                f"{_GRAPH}/groups/{group_id}/team",
                headers=_headers(), json=team_payload,
            )
            if rt.status_code in (200, 201):
                return {**rt.json(), "id": rt.json().get("id", group_id)}
            try:
                last_err = rt.json().get("error", {}).get("message", rt.text[:200])
            except Exception:
                last_err = rt.text[:200]
            await asyncio.sleep(5)

        # If Teams provisioning failed, clean up the orphan group
        try:
            await c.delete(f"{_GRAPH}/groups/{group_id}", headers=_headers())
        except Exception:
            pass
        raise RuntimeError(
            f"Teams provisioning did not complete within {provision_timeout}s. "
            f"Group {group_id} was deleted. Last error: {last_err}"
        )


async def post_team(payload: dict, poll_timeout: int = 60) -> dict:
    """Legacy POST /teams wrapper — kept for backwards compatibility.
    Internally delegates to create_team_via_group when the template API fails.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(f"{_GRAPH}/teams", headers=_headers(), json=payload)
        if r.status_code in (200, 201) and r.content:
            return r.json()
        if r.status_code == 202:
            location = r.headers.get("Location") or r.headers.get("Content-Location", "")
            team_id_match = re.search(r"teams\('([^']+)'\)|teams/([0-9a-f-]{36})", location)
            deadline = time.time() + poll_timeout
            while time.time() < deadline:
                await asyncio.sleep(3)
                if team_id_match:
                    tid = team_id_match.group(1) or team_id_match.group(2)
                    rp = await c.get(f"{_GRAPH}/teams/{tid}", headers=_headers())
                    if rp.status_code == 200:
                        return rp.json()
            raise TimeoutError(f"Team provisioning timed out. Location: {location}")
        try:
            err = r.json().get("error", {})
            detail = err.get("message", r.text[:300])
        except Exception:
            detail = r.text[:300]
        raise RuntimeError(f"POST /teams failed ({r.status_code}): {detail}")
