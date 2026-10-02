"""The loophole check (design document, section 19).

Players may commit crimes against each other inside the game. Nobody may cheat
the game itself. Each test here is one attempt to cheat the game, and proves it
fails. They are grouped by the ten questions every feature must pass.

More loophole tests sit beside the features they attack:
  test_ledger.py     money from nothing, double spending, repeated rewards
  test_quarters.py   closing a quarter early, twice, or from two servers at once
  test_accounts.py   starting cash paid twice, half-made accounts
  test_companies_api.py   hidden information, bad numbers, permissions
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from server import security
from simulation import ledger
from simulation.money import naira
from tests.conftest import ADULT

SECRET = "test-only-secret-key-that-is-long-enough-0123456789"


# --- 1. Forgery: can a browser send a made-up request and have it accepted? ---

@pytest.mark.parametrize("extra", [
    {"cash": {"amount_kobo": "99999999999", "currency": "NGN"}},
    {"opening_cash_kobo": 99_999_999_999},
    {"reputation": 100},
    {"id": "00000000-0000-0000-0000-000000000001"},
    {"adult_confirmed_at": "2000-01-01T00:00:00Z"},
    {"level": 80},
])
def test_sign_up_cannot_set_its_own_cash_reputation_or_identity(client, db, extra):
    response = client.post("/api/auth/signup", json={**ADULT, **extra})
    assert response.status_code == 422                       # fields the server did not ask for are refused
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0


def test_a_profile_change_cannot_carry_other_changes(client, player):
    response = client.patch("/api/me/profile-icon", json={"profile_icon": "male", "reputation": 100})
    assert response.status_code == 422
    assert client.get("/api/me").json()["reputation"] == 50


def _token(player_id, *, key=SECRET, algorithm="HS256", expires_in=timedelta(days=1)):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": player_id, "iat": now, "exp": now + expires_in}, key, algorithm=algorithm)


def test_a_login_pass_signed_with_the_wrong_key_is_refused(client, player):
    client.cookies.set(security.SESSION_COOKIE, _token(player["id"], key="an-attacker-made-up-this-key-0123456789abcdef"))
    assert client.get("/api/me").status_code == 401


def test_an_unsigned_login_pass_is_refused(client, player):
    unsigned = jwt.encode({"sub": player["id"]}, key=None, algorithm="none")
    client.cookies.set(security.SESSION_COOKIE, unsigned)
    assert client.get("/api/me").status_code == 401


def test_an_expired_login_pass_is_refused(client, player):
    client.cookies.set(security.SESSION_COOKIE, _token(player["id"], expires_in=timedelta(seconds=-5)))
    assert client.get("/api/me").status_code == 401


def test_a_login_pass_for_a_player_who_does_not_exist_is_refused(client):
    client.cookies.set(security.SESSION_COOKIE, _token("00000000-0000-0000-0000-000000000000"))
    assert client.get("/api/me").status_code == 401
    client.cookies.set(security.SESSION_COOKIE, _token("not-even-an-id"))
    assert client.get("/api/me").status_code == 401


def test_the_website_has_no_way_to_move_money_or_change_records(client, player):
    """There is simply no request that pays money, edits a company or closes a quarter."""
    from server.main import app

    writes = sorted(
        (method, route.path) for route in app.routes if hasattr(route, "methods")
        for method in route.methods if method not in ("GET", "HEAD", "OPTIONS")
    )
    assert writes == [
        ("PATCH", "/api/me/profile-icon"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/signup"),
    ]
    for method, path in [("post", "/api/companies"), ("put", "/api/companies/IKB"), ("delete", "/api/companies/IKB"),
                         ("post", "/api/me/movements"), ("post", "/api/world/clock"), ("delete", "/api/me")]:
        assert getattr(client, method)(path).status_code == 405


# --- 2. Money from nothing ---

def test_signing_up_many_players_creates_no_money(client, db):
    money_before = ledger.amount_in_existence(db)
    for n in range(5):
        client.post("/api/auth/signup", json={**ADULT, "email": f"p{n}@example.com", "display_name": f"Player {n}"})
    assert ledger.amount_in_existence(db) == money_before
    assert db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = 'NGN'").fetchone()[0] == 0
    paid = db.execute("SELECT count(*), sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id WHERE t.kind = 'starting_grant' AND e.amount > 0").fetchone()
    assert paid == (5, 5 * naira(500_000))


# --- 3. Farming: can a reward be collected again and again? ---

def test_signing_up_again_with_the_same_details_pays_nothing_more(client, db):
    client.post("/api/auth/signup", json=ADULT)
    for variant in (ADULT, {**ADULT, "email": "ADA@EXAMPLE.COM"}, {**ADULT, "email": "other@example.com"}):
        assert client.post("/api/auth/signup", json=variant).status_code == 409
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


def test_logging_in_repeatedly_pays_nothing(client, player, db):
    for _ in range(3):
        client.post("/api/auth/login", json={"email": ADULT["email"], "password": ADULT["password"]})
    assert client.get("/api/me").json()["cash"]["amount_kobo"] == str(naira(500_000))


# --- 4. Timing: two requests at the same instant ---

def test_the_same_sign_up_sent_many_times_at_once_makes_one_player(client, db):
    barrier = threading.Barrier(6)
    statuses: list[int] = []

    def sign_up():
        barrier.wait()
        statuses.append(client.post("/api/auth/signup", json=ADULT).status_code)

    threads = [threading.Thread(target=sign_up) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(statuses) == [201, 409, 409, 409, 409, 409]
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM ledger_accounts WHERE kind = 'player'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


# --- 5. Permissions ---

def test_a_player_sees_only_their_own_account_history(client, db):
    client.post("/api/auth/signup", json=ADULT)
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={**ADULT, "email": "bisi@example.com", "display_name": "Bisi"})

    movements = client.get("/api/me/movements").json()
    assert len(movements) == 1                                # Bisi's own grant only
    # There is no way to ask for someone else's: the request names no player.
    assert client.get("/api/me/movements?player_id=anything&account_id=anything").json() == movements


def test_one_player_cannot_change_another_players_profile(client, db):
    client.post("/api/auth/signup", json=ADULT)
    client.post("/api/auth/logout")
    client.post("/api/auth/signup", json={**ADULT, "email": "bisi@example.com", "display_name": "Bisi", "profile_icon": "male"})
    client.patch("/api/me/profile-icon", json={"profile_icon": "male"})
    icons = dict(db.execute("SELECT display_name, profile_icon FROM players").fetchall())
    assert icons == {"Ada": "female", "Bisi": "male"}         # Ada's was not touched


# --- 6. Hidden information ---

def test_responses_never_carry_passwords_or_email_addresses(client, player):
    for path in ("/api/me", "/api/me/movements", "/api/world/status", "/api/world/clock"):
        text = client.get(path).text.lower()
        assert "password" not in text and "argon2" not in text and "@example.com" not in text


@pytest.mark.world("eight")
def test_no_request_reveals_the_treasury_or_any_other_accounts_balance(client, player, db):
    hidden = [str(ledger.balance(db, ledger.account_id(db, code))) for code in (ledger.TREASURY, ledger.PUBLIC)]
    hidden.append(str(ledger.amount_in_existence(db)))
    pages = "".join(client.get(p).text for p in ("/api/me", "/api/me/movements", "/api/world/status", "/api/companies", "/api/companies/IKB"))
    for figure in hidden:
        assert figure not in pages


def test_error_messages_do_not_describe_the_inside_of_the_game(client, db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    ledger.transfer(db, payer=treasury, receiver=ledger.account_id(db, ledger.PUBLIC), amount=ledger.balance(db, treasury), kind="test", memo="Test: Treasury emptied")
    detail = client.post("/api/auth/signup", json=ADULT).json()["detail"]
    assert detail == "New accounts cannot be opened right now. Please try again later."


# --- 7. Bad numbers ---

@pytest.mark.parametrize("limit", ["0", "-5", "101", "1e9", "abc"])
def test_a_silly_history_length_is_refused(client, player, limit):
    assert client.get(f"/api/me/movements?limit={limit}").status_code == 422


# --- 10. The clock ---

def test_the_clock_cannot_be_told_what_time_it_is(client):
    honest = client.get("/api/world/clock").json()
    lied = client.get("/api/world/clock?now=2099-01-01T00:00:00Z&world_start=2000-01-01T00:00:00Z",
                      headers={"Date": "Fri, 01 Jan 2099 00:00:00 GMT"}).json()
    assert lied["world_started"] == honest["world_started"]
    assert lied["lagos_time"][:16] == honest["lagos_time"][:16]


def test_changing_the_setting_does_not_move_a_world_that_already_exists(client, db, monkeypatch):
    """The world remembers its own start. Editing the setting later cannot fast-forward it."""
    from server.config import get_settings

    monkeypatch.setenv("WORLD_START", "2020-01-01T00:00:00+01:00")
    get_settings.cache_clear()
    try:
        assert client.get("/api/world/clock").json()["world_started"] is False     # still 5 October 2026
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
