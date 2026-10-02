"""Shared test setup. Tests run against a real PostgreSQL database kept only for testing."""

from __future__ import annotations

import os

import psycopg
import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@localhost:5433/wsbm_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-0123456789"
os.environ["COOKIE_SECURE"] = "false"
os.environ["WORLD_START"] = "2026-10-05T00:00:00+01:00"

from database.migrate import apply_migrations  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    apply_migrations(TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def _clean_tables():
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        conn.execute("TRUNCATE players")
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as test_client:
        yield test_client
