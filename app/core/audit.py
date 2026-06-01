"""In-memory audit log for all mutation operations.

Stores the last MAX_ENTRIES actions with timestamp, user, action type,
resource type, and brief detail. Exposed via GET /audit/recent.
"""
import time
from collections import deque
from typing import Any

MAX_ENTRIES = 500

_LOG: deque[dict] = deque(maxlen=MAX_ENTRIES)


def log(
    action: str,          # "create" | "update" | "delete" | "import" | "login"
    resource: str,        # "canvas_user" | "teams_team" | "ingreso" | ...
    user: str = "system",
    detail: Any = None,
    status: str = "ok",   # "ok" | "error"
) -> None:
    _LOG.append({
        "ts":       int(time.time()),
        "user":     user,
        "action":   action,
        "resource": resource,
        "status":   status,
        "detail":   str(detail)[:200] if detail else None,
    })


def recent(limit: int = 50) -> list[dict]:
    entries = list(_LOG)
    return list(reversed(entries[-limit:]))


def summary() -> dict:
    entries = list(_LOG)
    return {
        "total": len(entries),
        "by_action":   _count(entries, "action"),
        "by_resource": _count(entries, "resource"),
        "by_status":   _count(entries, "status"),
    }


def _count(entries: list[dict], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for e in entries:
        v = e.get(key, "unknown")
        result[v] = result.get(v, 0) + 1
    return result
