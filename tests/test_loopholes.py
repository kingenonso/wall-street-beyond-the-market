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
from tests.conftest import ADULT, after_quarters, join

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
    response = join(client, {**ADULT, **extra})
    assert response.status_code == 422                       # fields the server did not ask for are refused
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0


def test_a_profile_change_cannot_carry_other_changes(client, player):
    response = client.patch("/api/me/profile-icon", json={"profile_icon": "male", "reputation": 100})
    assert response.status_code == 422
    assert client.get("/api/me").json()["reputation"] == 50


def _token(player_id, *, key=SECRET, algorithm="HS256", expires_in=timedelta(days=1)):
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": player_id, "ver": 0, "iat": now, "exp": now + expires_in}, key, algorithm=algorithm)


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
    """Every request that changes anything is on this list. There is none that pays money
    directly, edits a company or closes a quarter. Since Stage 4 a player can place and cancel
    orders on the exchange; those are attacked in test_market.py. Stage 4 Part B added the bond
    desk, share offers, votes and takeover offers (attacked in test_bonds.py and test_corporate.py)
    and collecting the starting grant's later parts (test_grants.py). Stage 5 added choosing a
    build, a bank, an employer and a retirement fund (test_careers.py), and taking on, handing in
    and giving up professional work (test_objectives.py). Stage 6 added empires and pension funds run
    by players (test_empires.py, test_savings.py, test_empire_api.py): every one of those requests acts
    on the empire or fund the server knows the player belongs to, and moves money only through the ledger.
    Stage 7 added resignation letters, counter-offers and the vote for a head (test_leaving.py), rank cases
    and reports of marking (test_mastery.py, test_rank_api.py). The private equity stage, part 1, added the firm: duties,
    requests, votes, papers, borrowing, budgets, contracts, poaching, tasks, events and cover (test_firm.py, test_firm_api.py),
    buying into another empire's stake offer, and hiring a bookkeeper (test_firm_review.py): each acts on the player's own seat and moves money only through the ledger."""
    from server.main import app

    writes = sorted(
        (method, route.path) for route in app.routes if hasattr(route, "methods")
        for method in route.methods if method not in ("GET", "HEAD", "OPTIONS")
    )
    assert writes == [
        ("DELETE", "/api/bonds/swaps/{swap_id}"),
        ("DELETE", "/api/bookkeeping/{engagement_id}"),
        ("DELETE", "/api/career/job"),
        ("DELETE", "/api/empire/application"),
        ("DELETE", "/api/empire/founding"),
        ("DELETE", "/api/empire/members/{member_id}"),
        ("DELETE", "/api/empire/orders/{order_id}"),
        ("DELETE", "/api/empire/resignation"),
        ("DELETE", "/api/empire/resignations/{resignation_id}"),
        ("DELETE", "/api/firm/apprentices"),
        ("DELETE", "/api/firm/approaches/{offer_id}"),
        ("DELETE", "/api/firm/votes/{resolution_id}"),
        ("DELETE", "/api/market/orders/{order_id}"),
        ("DELETE", "/api/market/watchlist/{ticker}"),
        ("DELETE", "/api/objectives/{objective_id}"),
        ("DELETE", "/api/pension-fund/orders/{order_id}"),
        ("DELETE", "/api/pension-fund/savings"),
        ("PATCH", "/api/me/profile-icon"),
        ("POST", "/api/auth/confirm-email"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
        ("POST", "/api/auth/signup"),
        ("POST", "/api/bonds/swaps"),
        ("POST", "/api/bonds/trade"),
        ("POST", "/api/bookkeeping"),
        ("POST", "/api/bookkeeping/{engagement_id}/open"),
        ("POST", "/api/bookkeeping/{engagement_id}/report"),
        ("POST", "/api/career/retirement/pension"),
        ("POST", "/api/empire/ai-audit"),
        ("POST", "/api/empire/audits"),
        ("POST", "/api/empire/bonds"),
        ("POST", "/api/empire/bonuses"),
        ("POST", "/api/empire/capital"),
        ("POST", "/api/empire/expenses"),
        ("POST", "/api/empire/head-votes"),
        ("POST", "/api/empire/investigations"),
        ("POST", "/api/empire/messages"),
        ("POST", "/api/empire/opening"),
        ("POST", "/api/empire/orders"),
        ("POST", "/api/empire/pacts"),
        ("POST", "/api/empire/reports"),
        ("POST", "/api/empire/resignation"),
        ("POST", "/api/empire/resignation/acceptance"),
        ("POST", "/api/empire/steps/{step_id}/approve"),
        ("POST", "/api/empire/steps/{step_id}/take"),
        ("POST", "/api/empire/tasks"),
        ("POST", "/api/empires"),
        ("POST", "/api/empires/{empire_id}/applications"),
        ("POST", "/api/firm/apprentices"),
        ("POST", "/api/firm/approaches"),
        ("POST", "/api/firm/bonus-pool"),
        ("POST", "/api/firm/contracts"),
        ("POST", "/api/firm/cover"),
        ("POST", "/api/firm/debts/{debt_id}/repayment"),
        ("POST", "/api/firm/duties/{duty_id}/hand-in"),
        ("POST", "/api/firm/duties/{duty_id}/open"),
        ("POST", "/api/firm/events/{happening_id}"),
        ("POST", "/api/firm/raisings"),
        ("POST", "/api/firm/requests/{approval_id}/overrule"),
        ("POST", "/api/firm/tasks"),
        ("POST", "/api/firm/training"),
        ("POST", "/api/firm/votes"),
        ("POST", "/api/market/orders"),
        ("POST", "/api/me/grant"),
        ("POST", "/api/objectives"),
        ("POST", "/api/objectives/{objective_id}/hand-in"),
        ("POST", "/api/pension-fund/ai-audit"),
        ("POST", "/api/pension-fund/bonds"),
        ("POST", "/api/pension-fund/costs"),
        ("POST", "/api/pension-fund/orders"),
        ("POST", "/api/pension-funds"),
        ("POST", "/api/ranks/cases"),
        ("POST", "/api/ranks/cases/{case_id}/hand-in"),
        ("POST", "/api/reports"),
        ("POST", "/api/stake-offers/{offer_id}"),
        ("PUT", "/api/bookkeeping/{engagement_id}/rating"),
        ("PUT", "/api/career/bank"),
        ("PUT", "/api/career/build"),
        ("PUT", "/api/career/extra-saving"),
        ("PUT", "/api/career/job"),
        ("PUT", "/api/career/retirement"),
        ("PUT", "/api/corporate/offers/{offer_id}"),
        ("PUT", "/api/corporate/takeovers/{takeover_id}"),
        ("PUT", "/api/corporate/votes/{vote_id}"),
        ("PUT", "/api/empire/applications/{application_id}"),
        ("PUT", "/api/empire/audits/{audit_id}"),
        ("PUT", "/api/empire/cases/{case_id}"),
        ("PUT", "/api/empire/limits"),
        ("PUT", "/api/empire/pacts/{pact_id}"),
        ("PUT", "/api/empire/resignations/{resignation_id}/offer"),
        ("PUT", "/api/empire/staff"),
        ("PUT", "/api/firm/approaches/{offer_id}"),
        ("PUT", "/api/firm/approaches/{offer_id}/match"),
        ("PUT", "/api/firm/budgets"),
        ("PUT", "/api/firm/contracts/{contract_id}"),
        ("PUT", "/api/firm/contracts/{contract_id}/offer"),
        ("PUT", "/api/firm/duties/{duty_id}/given-to"),
        ("PUT", "/api/firm/freeze"),
        ("PUT", "/api/firm/papers/{document_id}"),
        ("PUT", "/api/firm/requests/{approval_id}"),
        ("PUT", "/api/firm/rival"),
        ("PUT", "/api/firm/shortlists/{approval_id}"),
        ("PUT", "/api/firm/steps/{step_id}/defence"),
        ("PUT", "/api/firm/steps/{step_id}/given-to"),
        ("PUT", "/api/firm/strategy"),
        ("PUT", "/api/firm/tasks/{task_id}/priority"),
        ("PUT", "/api/firm/titles"),
        ("PUT", "/api/firm/trade-limit"),
        ("PUT", "/api/firm/votes/{resolution_id}"),
        ("PUT", "/api/market/watchlist/{ticker}"),
        ("PUT", "/api/pension-fund/fee"),
        ("PUT", "/api/pension-funds/{fund_id}/savings"),
    ]
    for method, path in [("post", "/api/companies"), ("put", "/api/companies/IKB"), ("delete", "/api/companies/IKB"),
                         ("post", "/api/me/movements"), ("post", "/api/world/clock"), ("delete", "/api/me")]:
        assert getattr(client, method)(path).status_code == 405


# --- 2. Money from nothing ---

def test_signing_up_many_players_creates_no_money(client, db):
    money_before = ledger.amount_in_existence(db)
    for n in range(5):
        join(client, {**ADULT, "email": f"p{n}@example.com", "display_name": f"Player {n}"})
    assert ledger.amount_in_existence(db) == money_before
    assert db.execute("SELECT sum(balance) FROM ledger_balances WHERE asset = 'NGN'").fetchone()[0] == 0
    paid = db.execute("SELECT count(*), sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id WHERE t.kind = 'starting_grant' AND e.amount > 0").fetchone()
    assert paid == (5, 5 * naira(100_000))


# --- 3. Farming: can a reward be collected again and again? ---

def test_signing_up_again_with_the_same_details_pays_nothing_more(client, db):
    join(client, ADULT)
    for variant in (ADULT, {**ADULT, "email": "ADA@EXAMPLE.COM"}, {**ADULT, "email": "other@example.com"}):
        assert join(client, variant).status_code == 409
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


def test_logging_in_repeatedly_pays_nothing(client, player, db):
    for _ in range(3):
        client.post("/api/auth/login", json={"email": ADULT["email"], "password": ADULT["password"]})
    assert client.get("/api/me").json()["cash"]["amount_kobo"] == str(naira(100_000))


# --- 4. Timing: two requests at the same instant ---

def test_the_same_sign_up_sent_many_times_at_once_makes_one_player(client, db):
    barrier = threading.Barrier(6)
    statuses: list[int] = []

    def sign_up():
        barrier.wait()
        statuses.append(join(client, ADULT).status_code)

    threads = [threading.Thread(target=sign_up) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert statuses.count(201) == 1 and len(statuses) == 6     # one succeeds; the rest are turned away
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM ledger_accounts WHERE kind = 'player'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


# --- 5. Permissions ---

def test_a_player_sees_only_their_own_account_history(client, db):
    join(client, ADULT)
    client.post("/api/auth/logout")
    join(client, {**ADULT, "email": "bisi@example.com", "display_name": "Bisi"})

    movements = client.get("/api/me/movements").json()
    assert len(movements) == 1                                # Bisi's own grant only
    # There is no way to ask for someone else's: the request names no player.
    assert client.get("/api/me/movements?player_id=anything&account_id=anything").json() == movements


def test_one_player_cannot_change_another_players_profile(client, db):
    join(client, ADULT)
    client.post("/api/auth/logout")
    join(client, {**ADULT, "email": "bisi@example.com", "display_name": "Bisi", "profile_icon": "male"})
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
    hidden = [str(ledger.balance(db, ledger.account_id(db, code))) for code in (ledger.TREASURY, "households:lagos")]
    hidden.append(str(ledger.amount_in_existence(db)))
    pages = "".join(client.get(p).text for p in ("/api/me", "/api/me/movements", "/api/world/status", "/api/companies", "/api/companies/IKB"))
    for figure in hidden:
        assert figure not in pages


def test_error_messages_do_not_describe_the_inside_of_the_game(client, db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    ledger.transfer(db, payer=treasury, receiver=ledger.account_id(db, "households:lagos"), amount=ledger.balance(db, treasury), kind="test", memo="Test: Treasury emptied")
    detail = join(client, ADULT).json()["detail"]
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

    honest = client.get("/api/world/clock").json()["world_started"]
    monkeypatch.setenv("WORLD_START", "2099-01-01T00:00:00+01:00")
    get_settings.cache_clear()
    try:
        assert client.get("/api/world/clock").json()["world_started"] is honest    # the world keeps the start it was made with
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Found by the independent reviewer (a second AI told to break Stage 1 and
# Stage 2). Each test below is one of its attacks, now proven to fail.
# ---------------------------------------------------------------------------

def test_a_correctly_signed_pass_still_works_so_the_tests_above_mean_something(client, player):
    client.cookies.set(security.SESSION_COOKIE, _token(player["id"]))
    assert client.get("/api/me").status_code == 200


def test_a_login_pass_with_no_expiry_date_is_refused(client, player):
    forever = jwt.encode({"sub": player["id"], "ver": 0, "iat": datetime.now(timezone.utc)}, SECRET, algorithm="HS256")
    client.cookies.set(security.SESSION_COOKIE, forever)
    assert client.get("/api/me").status_code == 401


def test_a_copied_login_pass_stops_working_after_logout(client, player):
    copied = client.cookies.get(security.SESSION_COOKIE)
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(security.SESSION_COOKIE, copied)
    assert client.get("/api/me").status_code == 401
    # Logging in again gives a fresh pass that works.
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"email": ADULT["email"], "password": ADULT["password"]}).status_code == 200
    assert client.get("/api/me").status_code == 200


@pytest.mark.parametrize("key", ["change-me-to-a-long-random-string-of-at-least-32-characters", "a" * 40])
def test_the_server_will_not_start_with_the_example_secret_key(monkeypatch, key):
    from server.config import get_settings
    monkeypatch.setenv("SECRET_KEY", key)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            get_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@pytest.fixture
def limited(monkeypatch):
    from server import limits
    from server.config import get_settings
    monkeypatch.setenv("RATE_LIMITS", "true")
    get_settings.cache_clear()
    limits.forget_all()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    limits.forget_all()


def test_password_guessing_is_cut_off(client, player, limited):
    wrong = {"email": ADULT["email"], "password": "a wrong guess"}
    codes = [client.post("/api/auth/login", json=wrong).status_code for _ in range(12)]
    assert codes[:8] == [401] * 8 and codes[8:] == [429] * 4
    # Even the right password must now wait: the guesser gets no signal.
    assert client.post("/api/auth/login", json={"email": ADULT["email"], "password": ADULT["password"]}).status_code == 429


def test_one_visitor_cannot_open_accounts_without_limit(client, db, limited):
    codes = []
    for n in range(13):
        details = {**ADULT, "email": f"bot{n}@example.com", "display_name": f"Bot number {n}"}
        codes.append(join(client, details).status_code)
    assert codes == [201] * 10 + [429] * 3
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 10


@pytest.mark.parametrize("lookalike", ["ada", "A da", "Ada_", "A-d-a", "Ádá", "Ａｄａ"])
def test_a_display_name_that_looks_like_another_players_is_refused(client, player, lookalike):
    response = join(client, {**ADULT, "email": "other@example.com", "display_name": lookalike})
    assert response.status_code == 409, response.text


@pytest.mark.parametrize("name", [
    "Аda",                      # the first letter is Cyrillic, not English
    "Central Bank of Nigeria", "Prize pool", "Company management", "admin", "Federal Government Treasury",
])
def test_a_display_name_cannot_imitate_the_game_or_use_lookalike_alphabets(client, db, name):
    assert join(client, {**ADULT, "display_name": name}).status_code == 422
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0


def test_nigerian_names_with_accents_and_under_dots_are_welcome(client):
    response = join(client, {**ADULT, "display_name": "Ọláyínká Asset Mgmt"})
    assert response.status_code == 201, response.text


def test_a_rejected_request_does_not_repeat_back_what_was_typed(client):
    response = join(client, {**ADULT, "password": "s3cret-pw", "date_of_birth": "nonsense"})
    assert response.status_code == 422
    assert "s3cret-pw" not in response.text and "nonsense" not in response.text


def test_an_oversized_request_is_refused_before_it_is_read(client):
    response = client.post("/api/auth/login", json={"email": "a@example.com", "password": "x" * 100_000})
    assert response.status_code == 413


def test_an_impossible_date_of_birth_is_refused(client, db):
    assert join(client, {**ADULT, "date_of_birth": "0001-01-01"}).status_code == 400
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0


@pytest.mark.parametrize("ticker", ["%00", "ZZ", "ABCD", "A%00B", "ÀBC"])
def test_a_nonsense_ticker_is_simply_not_found(client, player, ticker):
    assert client.get(f"/api/companies/{ticker}").status_code == 404


def test_the_starting_grant_cannot_be_paid_twice_by_spelling_the_player_differently(client, player, db):
    from simulation import players
    players.open_player_account(db, player["id"].upper())
    players.open_player_account(db, player["id"])
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0] == 1


def test_the_database_itself_refuses_a_second_starting_grant(client, player, db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    account = ledger.player_account_id(db, player["id"])
    with pytest.raises(Exception) as refused:
        ledger.transfer(db, payer=treasury, receiver=account, amount=naira(100_000), kind="starting_grant",
                        memo="A second grant", reference=str(account), idempotency_key="some-other-key")
    assert refused.value.diag.constraint_name == "ledger_one_starting_grant"
    assert ledger.balance(db, account) == naira(100_000)


def test_new_money_cannot_be_issued_for_a_made_up_reason(db):
    central_bank = ledger.account_id(db, ledger.CENTRAL_BANK)
    prize_pool = ledger.account_id(db, ledger.PRIZE_POOL)
    before = ledger.amount_in_existence(db, ledger.NGN)
    with pytest.raises(Exception) as refused:
        ledger.transfer(db, payer=central_bank, receiver=prize_pool, amount=naira(1_000_000), kind="gift", memo="Free money")
    assert refused.value.diag.constraint_name == "ledger_issuance_reason"
    assert ledger.amount_in_existence(db, ledger.NGN) == before


def test_new_shares_cannot_be_issued_for_a_made_up_reason(db):
    company = ledger.account_id(db, "company:IKB")
    prize_pool = ledger.account_id(db, ledger.PRIZE_POOL)
    with pytest.raises(Exception) as refused:
        ledger.transfer(db, payer=company, receiver=prize_pool, amount=1_000, asset="SHR-IKB", kind="gift", memo="Free shares")
    assert refused.value.diag.constraint_name == "ledger_issuance_reason"


def test_a_lookalike_currency_cannot_be_created(db):
    prize_pool = ledger.account_id(db, ledger.PRIZE_POOL)
    for code in ("NGN ", "ngn", "NGN2", "SHR-IKBX"):
        with pytest.raises(Exception):
            db.execute("INSERT INTO assets (code, kind, name, unit, issuer_account_id) VALUES (%s, 'currency', 'Fake', 'kobo', %s)", (code, prize_pool))


def test_an_account_cannot_pay_itself_by_spelling_its_id_differently(db):
    public = ledger.account_id(db, "households:lagos")
    with pytest.raises(ledger.LedgerError):
        ledger.transfer(db, payer=public, receiver=str(public).upper(), amount=naira(1), kind="customer_revenue", memo="To myself")
    with pytest.raises(ledger.LedgerError):
        ledger.post(db, kind="customer_revenue", memo="To myself", legs=[
            ledger.Leg(public, -naira(1)), ledger.Leg(str(public).upper(), naira(1)),
        ])


@pytest.mark.world("eight")
@pytest.mark.parametrize("statement", [
    "UPDATE world_state SET last_closed_period = 0",            # rewind the calendar
    "UPDATE world_state SET last_closed_period = 50",           # skip ahead
    "UPDATE world_state SET world_start = now()",               # restart the world
    "DELETE FROM world_state",
    "TRUNCATE world_state",
])
def test_the_calendar_cannot_be_rewound_skipped_or_restarted(db, statement):
    with pytest.raises(Exception) as refused:
        db.execute(statement)
    assert refused.value.diag.constraint_name == "world_is_permanent"
    assert db.execute("SELECT last_closed_period FROM world_state").fetchone()[0] == 8


@pytest.mark.world("eight")
@pytest.mark.parametrize("period, version, rating", [
    (8, 7, "AAA"),      # jumps the queue of versions
    (8, 1, "AAA"),      # pretends to be the original filing
    (999, 1, "AAA"),    # a quarter that has not happened
    (8, 2, "ZZZ"),      # a rating that does not exist
])
def test_a_filing_out_of_order_or_for_a_future_quarter_is_refused(db, period, version, rating):
    from psycopg.types.json import Jsonb
    company = db.execute("SELECT id FROM companies WHERE ticker = 'IKB'").fetchone()[0]
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'Somebody')",
            (company, period, version, Jsonb({}), rating, Jsonb([])),
        )


@pytest.mark.world("eight")
def test_a_filing_cannot_be_backdated(db):
    from psycopg.types.json import Jsonb
    company = db.execute("SELECT id FROM companies WHERE ticker = 'IKB'").fetchone()[0]
    filed_at = db.execute(
        "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by, filed_at)"
        " VALUES (%s, 8, 2, %s, 'A', %s, 'Somebody', '2020-01-01') RETURNING filed_at",
        (company, Jsonb({}), Jsonb([])),
    ).fetchone()[0]
    assert filed_at.year >= 2026


@pytest.mark.world("eight")
def test_the_whole_ledger_is_re_added_and_agrees_after_eight_quarters(db):
    assert ledger.audit(db) == []


def test_a_quarter_will_not_close_if_the_ledger_has_been_tampered_with(db):
    """Somebody with direct access to the database switches the rules off and edits a
    balance. A player cannot do this; the check is there in case anyone ever does."""
    from simulation import quarters
    from tests.conftest import after_quarters
    db.execute("SET session_replication_role = replica")
    db.execute("UPDATE ledger_balances SET balance = balance + 100 WHERE account_id = %s",
               (ledger.account_id(db, ledger.PRIZE_POOL),))
    db.execute("INSERT INTO ledger_balances (account_id, asset, balance) VALUES (%s, 'NGN', 100) ON CONFLICT DO NOTHING",
               (ledger.account_id(db, ledger.PRIZE_POOL),))
    db.execute("SET session_replication_role = origin")
    assert ledger.audit(db) != []
    with pytest.raises(ledger.LedgerError):
        quarters.close_due_quarters(db, after_quarters(1))
    assert db.execute("SELECT last_closed_period FROM world_state").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# One real, confirmed email address per account, and so one starting grant.
# ---------------------------------------------------------------------------

def _grants(db):
    return db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'starting_grant'").fetchone()[0]


def _ask(client, **changes):
    return client.post("/api/auth/signup", json={**ADULT, **changes})


def test_asking_to_sign_up_opens_nothing_and_pays_nothing(client, db):
    answer = _ask(client)
    assert answer.status_code == 202
    assert "set-cookie" not in answer.headers                 # not logged in
    assert client.get("/api/me").status_code == 401
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM ledger_accounts WHERE kind = 'player'").fetchone()[0] == 0
    assert _grants(db) == 0


def test_the_right_code_opens_the_account_and_pays_the_grant_once(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    confirm = {"email": ADULT["email"], "code": code}
    assert client.post("/api/auth/confirm-email", json=confirm).status_code == 201
    assert client.get("/api/me").json()["cash"]["amount_kobo"] == str(naira(100_000))
    # The same code cannot be used a second time.
    assert client.post("/api/auth/confirm-email", json=confirm).status_code == 400
    assert _grants(db) == 1


@pytest.mark.parametrize("alias", [
    "ada@example.com", "ADA@EXAMPLE.COM", "ada+second@example.com", "Ada+anything.at.all@Example.com",
])
def test_another_spelling_of_the_same_mailbox_cannot_open_a_second_account(client, player, db, alias):
    answer = _ask(client, email=alias, display_name="Somebody Else")
    assert answer.status_code == 202
    assert answer.json()["code_shown_on_screen"] is None      # no code is issued at all
    assert db.execute("SELECT count(*) FROM pending_signups").fetchone()[0] == 0
    for guess in ("000000", "123456"):
        assert client.post("/api/auth/confirm-email", json={"email": alias, "code": guess}).status_code == 400
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1
    assert _grants(db) == 1


@pytest.mark.parametrize("alias", ["a.d.a@gmail.com", "ada+bonus@gmail.com", "A.DA@googlemail.com", "ad.a+x@googlemail.com"])
def test_gmail_dots_and_plus_tags_are_the_same_mailbox(client, db, alias):
    assert join(client, {**ADULT, "email": "ada@gmail.com"}).status_code == 201
    client.cookies.clear()
    assert join(client, {**ADULT, "email": alias, "display_name": "Somebody Else"}).status_code == 202
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1
    assert _grants(db) == 1


def test_the_answer_does_not_reveal_whether_an_email_already_has_an_account(client, player, monkeypatch):
    """With a real email service the two answers are identical, word for word."""
    from server import emails
    sent = []
    monkeypatch.setattr(emails, "shown_on_screen", lambda: False)
    monkeypatch.setattr(emails, "send", lambda to, subject, body: sent.append((to, subject)))
    taken = _ask(client, display_name="Somebody Else")
    fresh = _ask(client, email="new@example.com", display_name="Somebody Else")
    assert taken.status_code == fresh.status_code == 202
    assert {**taken.json(), "email": ""} == {**fresh.json(), "email": ""}
    # The owner of the address is told by email instead.
    assert sent[0][1] == "You already have an account"
    assert sent[1][1] == "Your Wall Street: Beyond the Market code"


def test_with_a_real_email_service_the_code_never_appears_in_the_answer(client, monkeypatch):
    from server import emails
    sent = []
    monkeypatch.setattr(emails, "shown_on_screen", lambda: False)
    monkeypatch.setattr(emails, "send", lambda to, subject, body: sent.append(body))
    answer = _ask(client)
    assert answer.json()["code_shown_on_screen"] is None
    code = sent[0].split("Your code is ")[1][:6]
    assert code not in answer.text
    assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": code}).status_code == 201


def test_a_code_cannot_be_guessed(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": wrong}).status_code == 400
    # After five wrong guesses the code is thrown away: even the right one no longer works.
    assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": code}).status_code == 400
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 0
    assert _grants(db) == 0


def test_a_code_stops_working_after_fifteen_minutes(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    db.execute("UPDATE pending_signups SET expires_at = now() - interval '1 second'")
    assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": code}).status_code == 400
    assert _grants(db) == 0


def test_asking_for_a_new_code_cancels_the_old_one(client, db):
    old = _ask(client).json()["code_shown_on_screen"]
    new = _ask(client).json()["code_shown_on_screen"]
    if old != new:
        assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": old}).status_code == 400
    assert client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": new}).status_code == 201
    assert _grants(db) == 1


def test_a_code_sent_to_one_address_does_not_work_for_another(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    _ask(client, email="bisi@example.com", display_name="Bisi")
    assert client.post("/api/auth/confirm-email", json={"email": "bisi@example.com", "code": code}).status_code in (400, 201)
    # (201 only if the two random codes happened to be equal.) Either way, one grant per mailbox:
    assert _grants(db) <= 1


def test_the_same_code_sent_many_times_at_once_opens_one_account(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    statuses = []

    def confirm():
        statuses.append(client.post("/api/auth/confirm-email", json={"email": ADULT["email"], "code": code}).status_code)

    threads = [threading.Thread(target=confirm) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [201] + [400] * 7
    assert db.execute("SELECT count(*) FROM players").fetchone()[0] == 1
    assert _grants(db) == 1


def test_the_code_is_not_kept_in_the_database_as_written(client, db):
    code = _ask(client).json()["code_shown_on_screen"]
    stored = db.execute("SELECT * FROM pending_signups").fetchone()
    assert code not in [str(value) for value in stored]
    assert ADULT["password"] not in str(stored)


@pytest.mark.parametrize("email", ["bot@mailinator.com", "x@yopmail.com", "y@10minutemail.com"])
def test_a_throwaway_mailbox_is_refused(client, db, email):
    assert _ask(client, email=email).status_code == 400
    assert db.execute("SELECT count(*) FROM pending_signups").fetchone()[0] == 0


def test_codes_cannot_be_requested_for_one_address_without_limit(client, limited):
    codes = [_ask(client).status_code for _ in range(7)]
    assert codes == [202] * 5 + [429] * 2


def test_a_real_website_will_not_start_without_an_email_service(monkeypatch):
    from server.config import get_settings
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            get_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_the_database_itself_allows_one_player_per_mailbox(client, player, db):
    with pytest.raises(Exception) as refused:
        db.execute(
            "INSERT INTO players (email, email_key, display_name, display_name_key, password_hash, adult_confirmed_at)"
            " VALUES ('Ada+2@example.com', 'ada@example.com', 'Copy', 'copy', 'x', now())"
        )
    assert refused.value.diag.constraint_name == "players_email_key_unique"


# ---------------------------------------------------------------------------
# Good and bad quarters: can a player know next quarter in advance?
# (Second independent review, 2 October 2026.)
# ---------------------------------------------------------------------------

def test_a_world_cannot_be_created_with_a_short_guessable_secret(db):
    from simulation import genesis
    from tests.conftest import WORLD_START
    with psycopg_connect_empty() as empty:
        for weak in ("", "7", "password", "a" * 31):
            if weak == "":
                continue                                       # empty means "choose a random one"
            with pytest.raises(ValueError):
                genesis.create_world(empty, WORLD_START, weak)
        assert empty.execute("SELECT count(*) FROM world_state").fetchone()[0] == 0


def psycopg_connect_empty():
    """A connection to a database that has the tables but no world yet."""
    import psycopg
    from tests.conftest import _TEMPLATES, _admin, _recreate, _url
    name = "wsbm_test_no_world"
    with _admin() as admin:
        _recreate(admin, name, _TEMPLATES["empty"])
    return psycopg.connect(_url(name), autocommit=True)


def test_a_world_made_without_a_chosen_secret_gets_a_long_random_one():
    from simulation import genesis
    from tests.conftest import WORLD_START
    seeds = []
    for _ in range(2):
        with psycopg_connect_empty() as empty:
            genesis.create_world(empty, WORLD_START)
            seeds.append(empty.execute("SELECT fortune_seed FROM world_state").fetchone()[0])
    assert all(len(seed) >= 32 for seed in seeds) and seeds[0] != seeds[1]


def test_the_database_refuses_a_world_with_a_short_secret(db):
    with psycopg_connect_empty() as empty:
        with pytest.raises(Exception) as refused:
            empty.execute("INSERT INTO world_state (world_start, company_tax_bps, fortune_seed) VALUES (now(), 3000, 'short')")
        assert refused.value.diag.constraint_name == "world_secret_is_long"


def test_a_world_from_before_fortunes_existed_is_given_a_secret_when_it_is_upgraded():
    """Without this, an older world's fortunes could be worked out from the game's code alone."""
    import psycopg
    from pathlib import Path
    from tests.conftest import _admin, _recreate, _url
    name = "wsbm_test_no_world"
    with _admin() as admin:
        _recreate(admin, name)
    migrations = sorted(Path("database/migrations").glob("*.sql"))
    with psycopg.connect(_url(name), autocommit=True) as old:
        for path in migrations[:4]:
            old.execute(path.read_text())
        old.execute("INSERT INTO world_state (world_start, company_tax_bps) VALUES (now(), 3000)")
        old.execute(migrations[4].read_text())
        assert len(old.execute("SELECT fortune_seed FROM world_state").fetchone()[0]) >= 32


def test_quarters_cannot_be_closed_for_a_world_with_no_secret(db):
    from simulation import quarters
    with pytest.raises(ledger.LedgerError):
        quarters._close_period(db, 1, 3000, "", after_quarters(1))


def test_fortune_can_never_make_sales_negative(db, monkeypatch):
    from simulation import quarters
    from simulation import world_data
    from tests.conftest import after_quarters
    monkeypatch.setattr(world_data, "SECTOR_VOLATILITY_BPS", 30_000)        # absurd on purpose
    assert quarters.close_due_quarters(db, after_quarters(6)) == [1, 2, 3, 4, 5, 6]
    assert db.execute("SELECT count(*) FROM company_results WHERE revenue < 0").fetchone()[0] == 0
    assert ledger.audit(db) == []


# ---------------------------------------------------------------------------
# The fast-forward: for testing only. Can it be used on a live world?
# ---------------------------------------------------------------------------

def test_a_test_world_can_be_moved_ahead_and_its_quarters_close_as_normal(db, client):
    from simulation import fast_forward
    from tests.conftest import WORLD_START
    now = WORLD_START + timedelta(hours=1)                       # the world has only just opened
    assert fast_forward.fast_forward(db, 3, now) == [1, 2, 3]
    assert db.execute("SELECT last_closed_period, weeks_ahead FROM world_state").fetchone() == (3, 3)
    assert db.execute("SELECT count(*) FROM company_results WHERE period = 3").fetchone()[0] == 50
    assert ledger.audit(db) == []
    assert client.get("/api/world/clock").json()["test_weeks_ahead"] == 3
    # Moving ahead again carries on from there.
    assert fast_forward.fast_forward(db, 1, now) == [4]


def _live_world():
    """A world created the way a real website creates one."""
    from simulation import genesis
    from tests.conftest import WORLD_START
    live = psycopg_connect_empty()
    genesis.create_world(live, WORLD_START, test_world=False)
    return live


def test_a_live_world_cannot_be_fast_forwarded_by_anyone():
    from simulation import fast_forward
    from tests.conftest import WORLD_START
    with _live_world() as live:
        with pytest.raises(fast_forward.NotATestWorld):
            fast_forward.fast_forward(live, 1, WORLD_START + timedelta(hours=1))
        # Not even by writing to the database directly.
        with pytest.raises(Exception) as refused:
            live.execute("UPDATE world_state SET weeks_ahead = 5")
        assert refused.value.diag.constraint_name == "live_calendar_is_fixed"
        with pytest.raises(Exception) as refused:
            live.execute("UPDATE world_state SET test_world = true")
        assert refused.value.diag.constraint_name == "world_is_permanent"
        assert live.execute("SELECT last_closed_period, weeks_ahead, test_world FROM world_state").fetchone() == (0, 0, False)


def test_time_can_never_be_moved_back_even_on_a_test_world(db):
    from simulation import fast_forward
    from tests.conftest import WORLD_START
    fast_forward.fast_forward(db, 2, WORLD_START + timedelta(hours=1))
    with pytest.raises(Exception) as refused:
        db.execute("UPDATE world_state SET weeks_ahead = 0")
    assert refused.value.diag.constraint_name == "live_calendar_is_fixed"


@pytest.mark.parametrize("amount", [0, -1, 41, 10**9, 1.5, "3", True, None])
def test_the_fast_forward_refuses_a_silly_amount(db, amount):
    from simulation import fast_forward
    from tests.conftest import WORLD_START
    with pytest.raises(ValueError):
        fast_forward.fast_forward(db, amount, WORLD_START + timedelta(hours=1))
    assert db.execute("SELECT weeks_ahead FROM world_state").fetchone()[0] == 0


def test_there_is_no_request_a_player_can_send_to_move_time(client, player):
    from server.main import app
    assert not [r.path for r in app.routes if "fast" in r.path or "forward" in r.path]
    assert client.post("/api/world/clock", json={"weeks_ahead": 5}).status_code == 405
