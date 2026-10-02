"""Shared test setup.

Tests run against a real PostgreSQL database kept only for testing. Every test
starts from an exact, known world, made by copying a prepared template:

  empty   the tables exist but the world has not been created
  fresh   the world has just been created (this is the default)
  eight   eight game quarters have been closed

A test picks a template with `@pytest.mark.world("eight")`.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres@localhost:5433/wsbm_test"
)
WORLD_START = datetime.fromisoformat("2026-10-05T00:00:00+01:00")

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SECRET_KEY"] = "test-only-secret-key-that-is-long-enough-0123456789"
os.environ["COOKIE_SECURE"] = "false"
os.environ["WORLD_START"] = WORLD_START.isoformat()
os.environ["RATE_LIMITS"] = "false"            # switched on only by the tests that are about them
os.environ["RUN_QUARTER_CLOSER"] = "false"     # tests close quarters themselves, at chosen times

from database.migrate import apply_migrations  # noqa: E402
from simulation import genesis, quarters  # noqa: E402

_TEST_DB = psycopg.conninfo.conninfo_to_dict(TEST_DATABASE_URL)["dbname"]
_TEMPLATES = {name: f"{_TEST_DB}_template_{name}" for name in ("empty", "fresh", "eight")}


def _url(dbname: str) -> str:
    return make_conninfo(TEST_DATABASE_URL, dbname=dbname)


def _admin():
    return psycopg.connect(_url("postgres"), autocommit=True)


def _recreate(conn, name: str, template: str | None = None) -> None:
    conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    conn.execute(f'CREATE DATABASE "{name}"' + (f' TEMPLATE "{template}"' if template else ""))


def after_quarters(count: int) -> datetime:
    """A moment just after `count` game quarters have ended."""
    return WORLD_START + timedelta(weeks=count, hours=1)


@pytest.fixture(scope="session", autouse=True)
def _templates():
    with _admin() as admin:
        _recreate(admin, _TEMPLATES["empty"])
        apply_migrations(_url(_TEMPLATES["empty"]))

        _recreate(admin, _TEMPLATES["fresh"], _TEMPLATES["empty"])
        with psycopg.connect(_url(_TEMPLATES["fresh"]), autocommit=True) as conn:
            genesis.create_world(conn, WORLD_START, fortune_seed="a-fixed-seed-so-tests-repeat")

        _recreate(admin, _TEMPLATES["eight"], _TEMPLATES["fresh"])
        with psycopg.connect(_url(_TEMPLATES["eight"]), autocommit=True) as conn:
            assert quarters.close_due_quarters(conn, after_quarters(8)) == list(range(1, 9))
    yield
    with _admin() as admin:
        for name in (_TEST_DB, *_TEMPLATES.values()):
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def _world(request, _templates):
    marker = request.node.get_closest_marker("world")
    template = _TEMPLATES[marker.args[0] if marker else "fresh"]
    with _admin() as admin:
        _recreate(admin, _TEST_DB, template)
    yield


@pytest.fixture
def db():
    """A direct connection to the test database."""
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture
def connect():
    """Opens extra connections, for tests where two things happen at the same moment."""
    opened = []

    def _connect():
        conn = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
        opened.append(conn)
        return conn

    yield _connect
    for conn in opened:
        conn.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as test_client:
        yield test_client


ADULT = {
    "email": "Ada@Example.com",
    "display_name": "Ada",
    "password": "correct horse battery",
    "date_of_birth": "1998-04-12",
    "profile_icon": "female",
}


def join(client, details):
    """Sign up and type in the emailed code, as a new player would.

    Returns the server's last answer: the finished sign-up if it got that far,
    otherwise the answer that stopped it.
    """
    asked = client.post("/api/auth/signup", json=details)
    code = asked.json().get("code_shown_on_screen") if asked.status_code == 202 else None
    if code is None:
        return asked
    return client.post("/api/auth/confirm-email", json={"email": details["email"], "code": code})


@pytest.fixture
def player(client):
    """A signed-up, logged-in player. Returns what the server said about them."""
    response = join(client, ADULT)
    assert response.status_code == 201, response.text
    return response.json()
