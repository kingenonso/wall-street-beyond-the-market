"""Sign-up, login and the logged-in player's profile."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg

from tests.conftest import TEST_DATABASE_URL

ADULT = {
    "email": "Ada@Example.com",
    "display_name": "Ada",
    "password": "correct horse battery",
    "date_of_birth": "1998-04-12",
}


def years_ago(years: int, extra_days: int = 0) -> str:
    today = datetime.now(ZoneInfo("Africa/Lagos")).date()  # the server judges age by the Lagos date
    try:
        born = today.replace(year=today.year - years)
    except ValueError:  # 29 February
        born = today.replace(year=today.year - years, day=28)
    return date.fromordinal(born.toordinal() + extra_days).isoformat()


def test_sign_up_creates_a_player_with_the_starting_position(client):
    response = client.post("/api/auth/signup", json=ADULT)
    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Ada"
    assert body["reputation"] == 50
    assert body["cash"] == {"amount_kobo": 50_000_000, "currency": "NGN"}  # ₦500,000
    assert "password" not in str(body).lower()


def test_sign_up_logs_the_player_in(client):
    client.post("/api/auth/signup", json=ADULT)
    assert client.get("/api/me").json()["display_name"] == "Ada"


def test_password_is_never_stored_as_written(client):
    client.post("/api/auth/signup", json=ADULT)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        stored = conn.execute("SELECT password_hash FROM players").fetchone()[0]
    assert ADULT["password"] not in stored
    assert stored.startswith("$argon2")


def test_date_of_birth_is_checked_but_not_kept(client):
    client.post("/api/auth/signup", json=ADULT)
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        columns = [d.name for d in conn.execute("SELECT * FROM players").description]
        confirmed = conn.execute("SELECT adult_confirmed_at FROM players").fetchone()[0]
    assert "date_of_birth" not in columns
    assert confirmed is not None


def test_under_18_cannot_sign_up(client):
    response = client.post("/api/auth/signup", json={**ADULT, "date_of_birth": years_ago(17)})
    assert response.status_code == 403
    assert "18" in response.json()["detail"]
    # One day short of the 18th birthday is still refused.
    almost = client.post("/api/auth/signup", json={**ADULT, "date_of_birth": years_ago(18, 1)})
    assert almost.status_code == 403


def test_exactly_18_today_can_sign_up(client):
    response = client.post("/api/auth/signup", json={**ADULT, "date_of_birth": years_ago(18)})
    assert response.status_code == 201


def test_a_birth_date_in_the_future_is_refused(client):
    response = client.post("/api/auth/signup", json={**ADULT, "date_of_birth": "2999-01-01"})
    assert response.status_code == 403


def test_email_cannot_be_used_twice_even_with_different_capitals(client):
    client.post("/api/auth/signup", json=ADULT)
    again = client.post(
        "/api/auth/signup", json={**ADULT, "email": "ada@example.com", "display_name": "Other"}
    )
    assert again.status_code == 409
    assert "email" in again.json()["detail"]


def test_display_name_cannot_be_used_twice(client):
    client.post("/api/auth/signup", json=ADULT)
    again = client.post(
        "/api/auth/signup", json={**ADULT, "email": "b@example.com", "display_name": "ADA"}
    )
    assert again.status_code == 409
    assert "display name" in again.json()["detail"]


def test_weak_or_malformed_details_are_refused(client):
    assert client.post("/api/auth/signup", json={**ADULT, "password": "short"}).status_code == 422
    assert client.post("/api/auth/signup", json={**ADULT, "email": "nope"}).status_code == 422
    assert client.post("/api/auth/signup", json={**ADULT, "display_name": "a"}).status_code == 422
    assert client.post("/api/auth/signup", json={**ADULT, "display_name": "<b>x</b>"}).status_code == 422


def test_login_with_the_right_password(client):
    client.post("/api/auth/signup", json=ADULT)
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401

    response = client.post(
        "/api/auth/login", json={"email": "ada@example.com", "password": ADULT["password"]}
    )
    assert response.status_code == 200
    assert client.get("/api/me").json()["display_name"] == "Ada"


def test_wrong_password_and_unknown_email_give_the_same_answer(client):
    client.post("/api/auth/signup", json=ADULT)
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
    response = client.post("/api/auth/signup", json=ADULT)
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
        "lagos_time", "market_state", "next_state", "next_change_at", "world_started", "game_date",
    }


def test_health_check(client):
    assert client.get("/api/health").json() == {"status": "ok"}
