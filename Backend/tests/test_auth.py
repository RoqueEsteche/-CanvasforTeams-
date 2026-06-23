"""Tests for app/services/auth.py — session token create/validate."""
import time

import pytest
from fastapi import HTTPException

from app.services import auth as auth_service


def test_create_and_validate_token():
    user = {"sub": "abc123", "name": "Test User", "email": "test@example.com"}
    token = auth_service.create_session_token(user)
    assert "." in token
    payload = auth_service.validate_session_token(token)
    assert payload["sub"] == "abc123"
    assert payload["name"] == "Test User"
    assert payload["email"] == "test@example.com"


def test_token_contains_expiry():
    user = {"sub": "u1", "name": "U", "email": "u@e.com"}
    token = auth_service.create_session_token(user)
    payload = auth_service.validate_session_token(token)
    # Token válido por 8 horas — la exp debe estar en el futuro
    assert payload["exp"] > int(time.time())
    assert payload["exp"] <= int(time.time()) + 60 * 60 * 8 + 5


def test_tampered_signature_raises_401():
    user = {"sub": "u2", "name": "U", "email": "u@e.com"}
    token = auth_service.create_session_token(user)
    parts = token.split(".")
    bad_token = parts[0] + ".invalidsignature"
    with pytest.raises(HTTPException) as exc_info:
        auth_service.validate_session_token(bad_token)
    assert exc_info.value.status_code == 401


def test_malformed_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        auth_service.validate_session_token("notavalidtoken")
    assert exc_info.value.status_code == 401


def test_expired_token_raises_401(monkeypatch):
    user = {"sub": "u3", "name": "U", "email": "u@e.com"}
    token = auth_service.create_session_token(user)
    # Avanzar el tiempo más allá de la expiración
    monkeypatch.setattr(time, "time", lambda: time.time() + 60 * 60 * 9)
    with pytest.raises(HTTPException) as exc_info:
        auth_service.validate_session_token(token)
    assert exc_info.value.status_code == 401


def test_different_users_get_different_tokens():
    u1 = {"sub": "a", "name": "A", "email": "a@e.com"}
    u2 = {"sub": "b", "name": "B", "email": "b@e.com"}
    assert auth_service.create_session_token(u1) != auth_service.create_session_token(u2)
