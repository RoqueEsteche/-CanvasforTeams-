"""Tests for GET /canvas/courses — verifica caché y respuesta paginada."""
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.core import cache

client = TestClient(app)

_SAMPLE_COURSES = [
    {"id": 1, "name": "Matemáticas I", "course_code": "MAT1"},
    {"id": 2, "name": "Física General", "course_code": "FIS1"},
]


def test_list_courses_returns_data():
    with patch("app.routers.canvas.courses.canvas.paginate_limited", new=AsyncMock(return_value=_SAMPLE_COURSES)):
        resp = client.get("/canvas/courses")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "Matemáticas I"


def test_list_courses_uses_cache_on_second_call():
    call_count = 0

    async def fake_paginate(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _SAMPLE_COURSES

    with patch("app.routers.canvas.courses.canvas.paginate_limited", new=fake_paginate):
        client.get("/canvas/courses")
        client.get("/canvas/courses")

    # La segunda llamada debe leer del cache, no llamar a paginate_limited de nuevo
    assert call_count == 1


def test_list_courses_with_search_term():
    with patch("app.routers.canvas.courses.canvas.paginate_limited", new=AsyncMock(return_value=[_SAMPLE_COURSES[0]])):
        resp = client.get("/canvas/courses?search_term=mat")
    assert resp.status_code == 200
    assert resp.json()[0]["course_code"] == "MAT1"


def test_search_term_bypasses_default_cache():
    """search_term genera una cache key distinta de la llamada sin filtros."""
    calls = []

    async def fake_paginate(path, params, **kwargs):
        calls.append(params.get("search_term"))
        return _SAMPLE_COURSES

    with patch("app.routers.canvas.courses.canvas.paginate_limited", new=fake_paginate):
        client.get("/canvas/courses")
        client.get("/canvas/courses?search_term=fisica")

    assert len(calls) == 2  # Ambas rutas distintas → 2 llamadas reales
