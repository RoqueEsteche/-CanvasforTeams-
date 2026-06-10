"""In-memory TTL cache with optional JSON disk persistence.

Reduces latency and external API calls for read-heavy endpoints.
All cache entries expire after their configured TTL (seconds).
Write operations (create/update/delete) must call invalidate().
Call load_from_disk() on startup and save_to_disk() on shutdown to survive restarts.
"""
import json
import logging
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STORE: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_BACKUP_FILE = Path(tempfile.gettempdir()) / "usil_canvas_cache.json"

# Límites de caché
MAX_CACHE_ENTRIES = 1000
MAX_CACHE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


def _cleanup_expired() -> None:
    """Remover entradas expiradas."""
    now = time.time()
    for k in list(_STORE):
        if _STORE[k][0] <= now:
            del _STORE[k]


def _get_cache_size() -> int:
    """Obtener tamaño aproximado del caché en bytes."""
    return sum(sys.getsizeof(k) + sys.getsizeof(v[1]) for k, v in _STORE.items())


def _evict_if_needed() -> None:
    """Aplicar LRU eviction si se exceden límites."""
    if len(_STORE) > MAX_CACHE_ENTRIES:
        logger.info("Caché exceede límite de entradas, removiendo 10%")
        entries_to_remove = len(_STORE) // 10
        for _ in range(entries_to_remove):
            _STORE.popitem(last=False)

    if _get_cache_size() > MAX_CACHE_SIZE_BYTES:
        logger.info("Caché exceede límite de tamaño, removiendo 20%")
        entries_to_remove = len(_STORE) // 5
        for _ in range(entries_to_remove):
            _STORE.popitem(last=False)


def get(key: str) -> Any | None:
    entry = _STORE.get(key)
    if entry and time.time() < entry[0]:
        _STORE.move_to_end(key)  # Marcar como accedido recientemente (LRU)
        return entry[1]
    return None


def set(key: str, value: Any, ttl: int = 180) -> None:
    _cleanup_expired()
    _STORE[key] = (time.time() + ttl, value)
    _STORE.move_to_end(key)
    _evict_if_needed()


def invalidate(prefix: str) -> None:
    """Remove all keys starting with prefix (e.g. 'canvas:users')."""
    for k in list(_STORE):
        if k.startswith(prefix):
            del _STORE[k]


def patch_list(prefix: str, item_id: Any, item_data: dict | None, id_field: str = "id", action: str = "update") -> None:
    """
    Optimistically patches all cached lists starting with `prefix`.
    action: 'create', 'update', or 'delete'.
    """
    for k, (ts, value) in _STORE.items():
        if k.startswith(prefix) and isinstance(value, list):
            if action == "delete":
                _STORE[k] = (ts, [v for v in value if str(v.get(id_field, "")) != str(item_id)])
            elif action == "update" and item_data is not None:
                new_list = []
                for v in value:
                    if str(v.get(id_field, "")) == str(item_id):
                        v.update(item_data)
                    new_list.append(v)
                _STORE[k] = (ts, new_list)
            elif action == "create" and item_data is not None:
                # Insert at the top of the cached list
                _STORE[k] = (ts, [item_data] + value)


def clear_all() -> int:
    n = len(_STORE)
    _STORE.clear()
    return n


def stats() -> dict:
    now = time.time()
    valid = sum(1 for ts, _ in _STORE.values() if now < ts)
    return {"total": len(_STORE), "valid": valid, "expired": len(_STORE) - valid}


def save_to_disk() -> None:
    """Persist valid (non-expired) cache entries to disk."""
    now = time.time()
    snapshot = {k: [ts, v] for k, (ts, v) in _STORE.items() if ts > now}
    try:
        _BACKUP_FILE.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        logger.debug("Cache guardado en disco: %d entradas", len(snapshot))
    except Exception as exc:
        logger.warning("No se pudo guardar cache en disco: %s", exc)


def load_from_disk() -> int:
    """Restore valid cache entries saved by a previous run. Returns count restored."""
    if not _BACKUP_FILE.exists():
        return 0
    try:
        snapshot: dict = json.loads(_BACKUP_FILE.read_text(encoding="utf-8"))
        now = time.time()
        restored = 0
        for k, payload in snapshot.items():
            ts, v = payload[0], payload[1]
            if ts > now:
                _STORE[k] = (ts, v)
                restored += 1
        logger.info("Cache restaurado desde disco: %d entradas válidas", restored)
        return restored
    except Exception as exc:
        logger.warning("No se pudo restaurar cache desde disco: %s", exc)
        return 0
