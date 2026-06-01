"""Tests for app/core/cache.py — TTL, invalidation y persistencia en disco."""
import json
import time
from pathlib import Path

import pytest

from app.core import cache


def test_set_and_get():
    cache.set("k1", {"value": 42}, ttl=60)
    assert cache.get("k1") == {"value": 42}


def test_expired_entry_returns_none():
    cache.set("k2", "data", ttl=1)
    time.sleep(1.1)
    assert cache.get("k2") is None


def test_missing_key_returns_none():
    assert cache.get("nonexistent") is None


def test_invalidate_by_prefix():
    cache.set("canvas:courses:a", [1, 2], ttl=60)
    cache.set("canvas:courses:b", [3, 4], ttl=60)
    cache.set("canvas:users:x", [5], ttl=60)
    cache.invalidate("canvas:courses")
    assert cache.get("canvas:courses:a") is None
    assert cache.get("canvas:courses:b") is None
    assert cache.get("canvas:users:x") == [5]


def test_clear_all_returns_count():
    cache.set("a", 1, ttl=60)
    cache.set("b", 2, ttl=60)
    n = cache.clear_all()
    assert n == 2
    assert cache.get("a") is None


def test_stats():
    cache.set("s1", "x", ttl=60)
    cache.set("s2", "y", ttl=1)
    time.sleep(1.1)
    s = cache.stats()
    assert s["valid"] == 1
    assert s["expired"] == 1
    assert s["total"] == 2


def test_save_and_load_from_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_BACKUP_FILE", tmp_path / "test_cache.json")
    cache.set("persist:k", {"hello": "world"}, ttl=120)
    cache.save_to_disk()
    cache.clear_all()
    assert cache.get("persist:k") is None
    restored = cache.load_from_disk()
    assert restored == 1
    assert cache.get("persist:k") == {"hello": "world"}


def test_expired_entries_not_restored(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_BACKUP_FILE", tmp_path / "test_cache.json")
    # Escribir un snapshot con una entrada ya expirada directamente en el archivo
    snapshot = {"old:key": [time.time() - 10, "stale"]}
    (tmp_path / "test_cache.json").write_text(json.dumps(snapshot), encoding="utf-8")
    restored = cache.load_from_disk()
    assert restored == 0
    assert cache.get("old:key") is None


def test_load_from_disk_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "_BACKUP_FILE", tmp_path / "no_file.json")
    assert cache.load_from_disk() == 0
