"""Sign-up, login, the player's profile and their starting cash."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest

from simulation import ledger, players
from simulation.money import naira
from tests.conftest import join, ADULT, TEST_DATABASE_URL


def years_ago(years: int, extra_days: int = 0) -> str:
    today = datetime.now(ZoneInfo("Africa/Lagos")).date()  # the server judges age by the Lagos date
    try:
        born = today.replace(year=today.year - years)
    except ValueError:  # 29 February
        born = today.replace(year=today.year - years, day=28)
    return date.fromordinal(born.toordinal() + extra_days).isoformat()


def test_sign_up_creates_a_player_with_the_starting_position(client):
    response = join(client, ADULT)
    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Ada"
    assert body["reputation"] == 50
    assert body["cash"] == {"amount_kobo": "50000000", "currency": "NGN"}  # ₦500,000, as kobo in text
    assert body["profile_icon"] == "female"
    assert "password" not in str(body).lower()


def test_sign_up_logs_the_player_in(client):
    join(client, ADULT)
    assert client.get("/api/me").json()["display_name"] == "Ada"


def test_password_is_never_stored_as_written(client):
    join(client, ADULT)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        stored = conn.execute("SELECT password_hash FROM players").fetchone()[0]
    assert ADULT["password"] not in stored
    assert stored.startswith("$argon2")


def test_date_of_birth_is_checked_but_not_kept(client):
    join(client, ADULT)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        columns = [d.name for d in conn.execute("SELECT * FROM players").description]
        confirmed = conn.execute("SELECT adult_confirmed_at FROM players").fetchone()[0]
    assert "date_of_birth" not in columns
    assert confirmed is not None


def test_under_18_cannot_sign_up(client):
    response = join(client, {**ADULT, "date_of_birth": years_ago(17)})
    assert response.status_code == 403
    assert "18" in response.json()["detail"]
    # One day short of the 18th birthday is still refused.
    almost = join(client, {**ADULT, "date_of_birth": years_ago(18, 1)})
    assert almost.status_code == 403


def test_exactly_18_today_can_sign_up(client):
    response = join(client, {**ADULT, "date_of_birth": years_ago(18)})
    assert response.status_code == 201


def test_a_birth_date_in_the_future_is_refused(client):
    response = join(client, {**ADULT, "date_of_birth": "2999-01-01"})
    assert response.status_code == 403


def test_email_cannot_be_used_twice_even_with_different_capitals(client, db):
    join(client, ADULT)
    again = join(client, {**ADULT, "email": "ada@example.com", "display_name": "Other"})
    # The answer does not say the address is taken (that would reveal who plays),
    # but no code is issued, so no second account can ever be opened.
    assert again.status_code == 202
    assert again.json()["code_shown_on_screen"] is None
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1


def test_display_name_cannot_be_used_twice(client):
    join(client, ADULT)
    again = join(
        client, {**ADULT, "email": "b@example.com", "display_name": "ADA"}
    )
    assert again.status_code == 409
    assert "display name" in again.json()["detail"]


def test_weak_or_malformed_details_are_refused(client):
    assert join(client, {**ADULT, "password": "short"}).status_code == 422
    assert join(client, {**ADULT, "email": "nope"}).status_code == 422
    assert join(client, {**ADULT, "display_name": "a"}).status_code == 422
    assert join(client, {**ADULT, "display_name": "<b>x</b>"}).status_code == 422


def test_login_with_the_right_password(client):
    join(client, ADULT)
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401

    response = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": ADULT["password"]}
    )
    assert response.status_code == 200
    assert client.get("/api/me").json()["display_name"] == "Ada"


def test_wrong_password_and_unknown_email_give_the_same_answer(client):
    join(client, ADULT)
    client.post("/api/auth/logout")
    wrong = client.post("/api/auth/login", json={"email": ADULT["email"], "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_profile_needs_a_login(client):
    assert client.get("/api/me").status_code == 401


def test_a_forged_session_is_rejected(client):
    client.cookies.set("wsbm_session", "not-a-real-token")
    assert client.get("/api/me").status_code == 401


def test_session_cookie_cannot_be_read_by_page_scripts(client):
    response = join(client, ADULT)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_world_clock_is_public_and_complete(client):
    response = client.get("/api/world/clock")
    assert response.status_code == 200
    body = response.json()
    assert body["market_state"] in {"opening_auction", "open", "closed"}
    assert body["lagos_time"].endswith("+01:00")
    assert set(body) == {
        "lagos_time", "market_state", "next_state", "next_change_at", "world_started", "game_date", "test_weeks_ahead",
    }


def test_health_check(client):
    assert client.get("/api/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Stage 2, item 5: starting cash is paid from a named source
# ---------------------------------------------------------------------------

def test_starting_cash_is_paid_by_the_treasury_not_created(client, db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    treasury_before = ledger.balance(db, treasury)
    money_before = ledger.amount_in_existence(db)

    body = join(client, ADULT).json()

    assert body["cash"]["amount_kobo"] == str(naira(500_000))
    assert ledger.balance(db, treasury) == treasury_before - naira(500_000)      # the Treasury paid
    assert ledger.amount_in_existence(db) == money_before                        # no new money appeared


def test_the_player_can_see_who_paid_them(client, player):
    movements = client.get("/api/me/movements").json()
    assert movements == [{
        "at": movements[0]["at"],
        "kind": "starting_grant",
        "memo": "Starting grant to a new professional",
        "counterparty": "Federal Government Treasury",
        "amount_kobo": "50000000",
        "currency": "NGN",
    }]


def test_the_old_stand_in_for_cash_is_gone(db):
    columns = [d.name for d in db.execute("SELECT * FROM players").description]
    assert "opening_cash_kobo" not in columns


def test_starting_cash_can_never_be_paid_twice(client, player, db):
    """Loophole question 3 (farming)."""
    players.open_player_account(db, player["id"])
    players.open_player_account(db, player["id"])
    assert client.get("/api/me").json()["cash"]["amount_kobo"] == str(naira(500_000))
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


def test_if_the_treasury_cannot_pay_no_half_made_account_is_left(client, db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    ledger.transfer(db, payer=treasury, receiver=ledger.account_id(db, "households:lagos"),
                    amount=ledger.balance(db, treasury) - naira(100), kind="test", memo="Test: Treasury emptied")

    response = join(client, ADULT)

    assert response.status_code == 503
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM ledger_accounts WHERE kind = 'player'").fetchone()[0] == 0
    assert "set-cookie" not in response.headers
    assert ledger.balance(db, treasury) == naira(100)


@pytest.mark.world("empty")
def test_sign_up_is_refused_cleanly_before_the_world_exists(client, db):
    response = join(client, ADULT)
    assert response.status_code == 503
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Profile pictures
# ---------------------------------------------------------------------------

def test_a_new_player_chooses_a_male_or_female_icon(client):
    assert join(client, {**ADULT, "profile_icon": "male"}).json()["profile_icon"] == "male"


def test_an_icon_must_be_chosen_and_must_be_one_of_the_two(client):
    without = {k: v for k, v in ADULT.items() if k != "profile_icon"}
    assert join(client, without).status_code == 422
    assert join(client, {**ADULT, "profile_icon": "dragon"}).status_code == 422


def test_a_player_can_change_their_icon(client, player):
    assert player["profile_icon"] == "female"
    response = client.patch("/api/me/profile-icon", json={"profile_icon": "male"})
    assert response.status_code == 200 and response.json()["profile_icon"] == "male"
    assert client.get("/api/me").json()["profile_icon"] == "male"
    assert client.patch("/api/me/profile-icon", json={"profile_icon": "<script>"}).status_code == 422


def test_changing_an_icon_needs_a_login(client):
    assert client.patch("/api/me/profile-icon", json={"profile_icon": "male"}).status_code == 401
