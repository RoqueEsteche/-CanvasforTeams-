"""Shared fixtures for the test suite."""
import os
import pytest

# Set required env vars before any app import so Settings loads cleanly.
os.environ.setdefault("CANVAS_ACCESS_TOKEN", "test-token")
os.environ.setdefault("CANVAS_BASE_URL", "https://canvas.example.com")
os.environ.setdefault("CANVAS_ACCOUNT_ID", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant")
os.environ.setdefault("AZURE_CLIENT_ID", "test-client")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-secret")
os.environ.setdefault("ENVIRONMENT", "development")


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the in-memory cache between tests to avoid state leakage."""
    from app.core import cache
    cache.clear_all()
    yield
    cache.clear_all()
