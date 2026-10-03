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

# The order-matching engine is a separate small program (Rust). Build it once if it is not there.
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

_ENGINE = Path(__file__).resolve().parent.parent / "engine"
if not (_ENGINE / "target" / "release" / "bsx-engine").is_file() and not os.environ.get("BSX_ENGINE"):
    subprocess.run(["cargo", "build", "--release"], cwd=_ENGINE, check=True)

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
            genesis.create_world(conn, WORLD_START, fortune_seed="a-fixed-secret-so-that-every-test-run-repeats", test_world=True)

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


def money_accounted_for(db) -> int:
    """All the naira that should exist, counted without looking at anybody's balance:
    the opening money, plus what banks still owe the Central Bank on its loans to them.
    (Stage 3 Part B: the Central Bank's lending to banks is the one way new money appears;
    it goes out of existence again when a bank repays.)"""
    opening = db.execute(
        "SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'opening_balance' AND e.asset = 'NGN' AND e.amount > 0").fetchone()[0]
    lent = db.execute(
        "SELECT coalesce(sum(principal_outstanding), 0) FROM company_debts WHERE kind = 'central_bank_loan'").fetchone()[0]
    return int(opening + lent)


def government_budget(db, period: int) -> int:
    """What the Government had to spend in one quarter, from the records: what it collected, plus
    what it borrowed to spend by selling new bonds, less what its borrowing cost it (interest on its
    bonds, and the difference between what a bill or bond was sold for and what it was repaid at)."""
    from simulation import economy, ledger
    treasury = ledger.account_id(db, ledger.TREASURY)
    collected = ledger.received_in_period(db, treasury, period, kinds=economy.GOVERNMENT_INCOME)
    one = lambda sql, params: int(db.execute(sql, params).fetchone()[0])          # noqa: E731
    borrowed = one("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                   " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0 AND t.period = %s AND t.kind = 'bond_issue'"
                   " AND t.memo LIKE '%%new bonds sold'", (treasury, period))
    coupons = one("SELECT coalesce(-sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                  " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount < 0 AND t.period = %s AND t.kind = 'bond_coupon'", (treasury, period))
    discount, replaced = 0, 0
    for bond_id, kind in db.execute("SELECT id, kind FROM bonds WHERE issuer = 'government' AND redeemed_period = %s", (period,)).fetchall():
        repaid = one("SELECT coalesce(-sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                     " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount < 0 AND t.kind = 'bond_redemption' AND t.reference = %s",
                     (treasury, f"bond:{bond_id}"))
        sold = one("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                   " WHERE e.account_id = %s AND e.asset = 'NGN' AND e.amount > 0 AND t.kind = 'bond_issue' AND t.reference = %s",
                   (treasury, f"bond:{bond_id}"))
        discount += max(repaid - sold, 0)
        if kind != "bill":
            replaced += min(repaid, sold)                 # borrowed again to replace bonds repaid: not for spending
    return max(collected + max(borrowed - replaced, 0) - coupons - discount, 0)
