"""The server. It checks every request and decides every outcome.

Stage 1: sign-up, login, logout, "who am I", and the world clock.
Stage 2: the player's cash and account history from the ledger, the companies
         and their filed reports, and closing each game quarter when it ends.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timezone

import psycopg
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi import Path as FastPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg_pool import PoolTimeout

from server import emails, limits, security
from server.config import get_settings
from server.db import close_pool, connection, get_connection
from server.schemas import (
    ClockResponse,
    CompaniesResponse,
    CompanyResponse,
    CompanySummary,
    ConfirmEmailRequest,
    EconomyQuarter,
    EconomyResponse,
    HouseholdGroup,
    LocationEffect,
    MoneyHolder,
    SpendingShare,
    Supplier,
    FiledReport,
    GameDateResponse,
    LoginRequest,
    Money,
    MovementResponse,
    Owner,
    PlayerResponse,
    ProfileIconRequest,
    SectorCompanies,
    SignUpPendingResponse,
    SignUpRequest,
    display_name_key,
    WorldStatusResponse,
    CommodityPrice, MacroQuarter, MoneyWatch, NewsItem, NewsResponse, PricesAndRates,
    Holding, OrderRequest, OrderResponse, PlacedOrderResponse, PriceLevel, PublicTrade, QuoteResponse,
)
from simulation import clock, exchange, ledger, moneywatch, news, news_kinds, players, quarters
from simulation import world_data as data
from simulation.ledger import NGN

log = logging.getLogger("wsbm.server")

QUARTER_CHECK_SECONDS = 30

# Whole numbers in a filed report that are not amounts and stay as plain numbers.
_NOT_AMOUNTS = {"annual_rate_bps", "maturity_period", "staff"}


def _close_due_quarters_once() -> None:
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        # The database's clock decides, so that servers whose own clocks disagree
        # can never close a quarter early.
        now = conn.execute("SELECT now()").fetchone()[0]
        quarters.close_due_quarters(conn, now)
        # Start the trading day and run each share's opening auction when the market opens.
        if conn.execute("SELECT to_regclass('market_instruments') IS NOT NULL AND EXISTS (SELECT 1 FROM world_state)").fetchone()[0]:
            exchange.open_market(conn, now)


async def _quarter_closer() -> None:
    """Runs for as long as the server is up: closes each game quarter when it ends."""
    while True:
        try:
            await asyncio.to_thread(_close_due_quarters_once)
        except Exception:  # keep trying; one failure must not stop the calendar
            log.exception("Closing the quarter failed. It will be tried again.")
        await asyncio.sleep(QUARTER_CHECK_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()  # Fail at start-up, not mid-request, if a setting is missing.
    closer = asyncio.create_task(_quarter_closer()) if settings.run_quarter_closer else None
    yield
    if closer:
        closer.cancel()
        with suppress(asyncio.CancelledError):
            await closer
    close_pool()


app = FastAPI(title="Wall Street: Beyond the Market", lifespan=lifespan)

MAX_BODY_BYTES = 16 * 1024      # nothing a player sends is anywhere near this size


@app.middleware("http")
async def refuse_oversized_requests(request: Request, call_next):
    length = request.headers.get("content-length", "0")
    if not length.isdigit() or int(length) > MAX_BODY_BYTES:
        return JSONResponse({"detail": "That request is too large."}, status_code=413)
    if request.method in ("POST", "PUT", "PATCH") and "content-length" not in request.headers:
        return JSONResponse({"detail": "That request is not complete."}, status_code=411)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, error: RequestValidationError):
    # Say what was wrong and where, but never send back what was typed:
    # it may be a password.
    problems = [
        {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")).removeprefix("Value error, "), "type": e.get("type")}
        for e in error.errors()
    ]
    return JSONResponse({"detail": problems}, status_code=422)


@app.exception_handler(PoolTimeout)
async def server_busy(_: Request, __: PoolTimeout):
    return JSONResponse(
        {"detail": "The server is busy. Please try again in a moment."},
        status_code=503, headers={"Retry-After": "5"},
    )


def _age_on(day: date, born: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def _player_response(conn: Connection, row: dict) -> PlayerResponse:
    account = ledger.player_account_id(conn, row["id"])
    cash = ledger.balance(conn, account) if account else 0
    return PlayerResponse(
        id=str(row["id"]),
        display_name=row["display_name"],
        reputation=row["reputation"],
        profile_icon=row["profile_icon"],
        cash=Money(amount_kobo=cash, currency=NGN),
    )


def _start_session(response: Response, row: dict) -> None:
    settings = get_settings()
    response.set_cookie(
        key=security.SESSION_COOKIE,
        value=security.create_session_token(str(row["id"]), row["session_version"]),
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,  # Page scripts cannot read it, which blocks a common way of stealing logins.
        secure=settings.cookie_secure,
        samesite="lax",
    )


def current_player(
    session: str | None = Cookie(default=None, alias=security.SESSION_COOKIE),
    conn: Connection = Depends(get_connection),
) -> dict:
    named = security.read_session_token(session) if session else None
    row = None
    if named:
        # The pass must carry the player's current version number. Logging out
        # raises the number, so a copied pass stops working at once.
        row = conn.execute(
            "SELECT * FROM players WHERE id = %s AND session_version = %s", named
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    return row


@app.get("/api/health")
def health(conn: Connection = Depends(get_connection)) -> dict:
    conn.execute("SELECT 1")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

_CODE_SENT = "We have sent a 6-digit code to that email address. Type it in to open your account."
_CODE_WRONG = "That code is not right, or it has expired. Check it, or ask for a new code."


@app.post("/api/auth/signup", response_model=SignUpPendingResponse, status_code=status.HTTP_202_ACCEPTED)
def sign_up(body: SignUpRequest, request: Request):
    """Step 1 of 2. Nothing is opened yet: a code is emailed, and the account and its
    starting cash only come into existence when that code is typed in (step 2)."""
    limits.allow("signup", limits.visitor(request), attempts=10, per_seconds=3600)
    settings = get_settings()
    today = datetime.now(clock.LAGOS).date()
    age = _age_on(today, body.date_of_birth)
    if age > 120:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please check your date of birth.")
    if body.date_of_birth > today or age < settings.minimum_age:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This game is for players aged {settings.minimum_age} and above.",
        )
    try:
        key = emails.email_key(body.email)
    except emails.UnusableEmail as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    limits.allow("signup-email", key, attempts=5, per_seconds=3600)

    # The slow password work is done before a database connection is taken,
    # so slow work never ties up the connections other players need.
    with limits.password_work:
        password_hash = security.hash_password(body.password)
    name_key = display_name_key(body.display_name)
    code = emails.new_code()

    with connection() as conn:
        name_taken = conn.execute(
            "SELECT 1 FROM players WHERE display_name_key = %s", (name_key,)
        ).fetchone()
        if name_taken:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "That display name, or one that looks just like it, is already in use."
            )
        already_a_player = conn.execute("SELECT 1 FROM players WHERE email_key = %s", (key,)).fetchone()
        if not already_a_player:
            with conn.transaction():
                conn.execute("DELETE FROM pending_signups WHERE expires_at < now()")
                # Asking again replaces the earlier request and its code.
                conn.execute(
                    "INSERT INTO pending_signups (email_key, email, display_name, display_name_key,"
                    "   password_hash, profile_icon, code_hash, expires_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s))"
                    " ON CONFLICT (email_key) DO UPDATE SET email = EXCLUDED.email,"
                    "   display_name = EXCLUDED.display_name, display_name_key = EXCLUDED.display_name_key,"
                    "   password_hash = EXCLUDED.password_hash, profile_icon = EXCLUDED.profile_icon,"
                    "   code_hash = EXCLUDED.code_hash, wrong_guesses = 0, expires_at = EXCLUDED.expires_at,"
                    "   created_at = now()",
                    (key, body.email.lower(), body.display_name, name_key, password_hash, body.profile_icon,
                     emails.hash_code(key, code), emails.CODE_MINUTES),
                )

    # The answer is the same whether or not the address already has an account, so
    # this form cannot be used to find out who plays. The owner of the address is
    # told by email instead.
    try:
        if already_a_player:
            emails.send_already_registered(body.email)
        else:
            emails.send_code(body.email, code)
    except Exception as error:
        log.exception("A confirmation email could not be sent.")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "We could not send the email. Please try again in a moment."
        ) from error

    on_screen = emails.shown_on_screen() and not already_a_player
    return SignUpPendingResponse(
        detail=_CODE_SENT, email=body.email, code_shown_on_screen=code if on_screen else None
    )


@app.post("/api/auth/confirm-email", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def confirm_email(body: ConfirmEmailRequest, request: Request, response: Response):
    """Step 2 of 2. The right code opens the account and pays the starting cash, once."""
    limits.allow("confirm", limits.visitor(request), attempts=30, per_seconds=900)
    try:
        key = emails.email_key(body.email)
    except emails.UnusableEmail as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _CODE_WRONG) from error

    with connection() as conn:
        row = None
        try:
            # All or nothing: the player, their ledger account and their starting cash
            # are created together, and are saved by the time this block ends.
            with conn.transaction():
                # Locking the request makes two identical confirmations take turns.
                pending = conn.execute(
                    "SELECT * FROM pending_signups WHERE email_key = %s AND expires_at > now() FOR UPDATE", (key,)
                ).fetchone()
                if pending and emails.code_matches(key, body.code, pending["code_hash"]):
                    row = conn.execute(
                        "INSERT INTO players (email, email_key, display_name, display_name_key, password_hash,"
                        "                     adult_confirmed_at, profile_icon)"
                        " VALUES (%s, %s, %s, %s, %s, now(), %s) RETURNING *",
                        (pending["email"], key, pending["display_name"], pending["display_name_key"],
                         pending["password_hash"], pending["profile_icon"]),
                    ).fetchone()
                    players.open_player_account(conn, row["id"])
                    conn.execute("DELETE FROM pending_signups WHERE email_key = %s", (key,))
                elif pending:
                    # A wrong guess is counted. After a few, the code is thrown away.
                    conn.execute(
                        "UPDATE pending_signups SET wrong_guesses = wrong_guesses + 1 WHERE email_key = %s", (key,)
                    )
                    conn.execute(
                        "DELETE FROM pending_signups WHERE email_key = %s AND wrong_guesses >= %s",
                        (key, emails.MAX_WRONG_GUESSES),
                    )
        except UniqueViolation as error:
            constraint = error.diag.constraint_name or ""
            if "display_name" in constraint:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Somebody took that display name while you were confirming. Please sign up again with another.",
                ) from error
            if "email" in constraint:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, _CODE_WRONG) from error
            raise
        except ledger.LedgerError as error:
            # The world does not exist yet, or the Treasury cannot pay the starting cash.
            log.error("Sign-up refused: %s", error)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "New accounts cannot be opened right now. Please try again later.",
            ) from error

        if row is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, _CODE_WRONG)
        _start_session(response, row)
        return _player_response(conn, row)


@app.post("/api/auth/login", response_model=PlayerResponse)
def log_in(body: LoginRequest, request: Request, response: Response):
    email = body.email.lower()
    limits.allow("login", limits.visitor(request), attempts=30, per_seconds=300)
    limits.allow("login-email", email, attempts=8, per_seconds=300)
    with connection() as conn:
        row = conn.execute("SELECT * FROM players WHERE lower(email) = %s", (email,)).fetchone()
    with limits.password_work:
        correct = security.verify_password(body.password, row["password_hash"] if row else None)
    if not correct:
        # One message for both a wrong email and a wrong password, so nobody can
        # use this form to find out which emails have accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")

    _start_session(response, row)
    with connection() as conn:
        return _player_response(conn, row)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    response: Response,
    session: str | None = Cookie(default=None, alias=security.SESSION_COOKIE),
    conn: Connection = Depends(get_connection),
) -> None:
    named = security.read_session_token(session) if session else None
    if named:
        # Cancel every pass issued so far, on every device, not just this browser's copy.
        conn.execute(
            "UPDATE players SET session_version = session_version + 1"
            " WHERE id = %s AND session_version = %s", named,
        )
    response.delete_cookie(security.SESSION_COOKIE)


@app.get("/api/me", response_model=PlayerResponse)
def me(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _player_response(conn, player)


@app.patch("/api/me/profile-icon", response_model=PlayerResponse)
def set_profile_icon(
    body: ProfileIconRequest,
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    row = conn.execute(
        "UPDATE players SET profile_icon = %s WHERE id = %s RETURNING *", (body.profile_icon, player["id"])
    ).fetchone()
    return _player_response(conn, row)


@app.get("/api/me/movements", response_model=list[MovementResponse])
def my_movements(
    limit: int = Query(default=20, ge=1, le=100),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    """The player's own account history: every naira in and out, newest first."""
    account = ledger.player_account_id(conn, player["id"])
    if account is None:
        return []
    rows = conn.execute(
        "SELECT t.created_at, t.kind, t.memo, e.amount, e.asset,"
        "  (SELECT CASE WHEN count(*) = 1 THEN min(a.name) ELSE 'Several accounts' END"
        "     FROM ledger_entries o JOIN ledger_accounts a ON a.id = o.account_id"
        "    WHERE o.transaction_id = t.id AND o.account_id <> e.account_id AND o.asset = e.asset) AS counterparty"
        " FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE e.account_id = %s AND e.asset = %s ORDER BY e.id DESC LIMIT %s",
        (account, NGN, limit),
    ).fetchall()
    return [
        MovementResponse(
            at=r["created_at"], kind=r["kind"], memo=r["memo"], counterparty=r["counterparty"],
            amount_kobo=r["amount"], currency=r["asset"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------

def _world(conn: Connection) -> dict | None:
    # Named columns only: the world's secret is never read into a request.
    return conn.execute(
        "SELECT world_start, last_closed_period, weeks_ahead, test_world FROM world_state"
    ).fetchone()


@app.get("/api/world/clock", response_model=ClockResponse)
def world_clock(conn: Connection = Depends(get_connection)):
    world = _world(conn)
    # The world remembers its own start. Before it is created, the setting is used.
    world_start = world["world_start"] if world else get_settings().world_start
    ahead = world["weeks_ahead"] if world else 0
    snap = clock.snapshot(datetime.now(timezone.utc), clock.effective_start(world_start, ahead))
    return ClockResponse(
        lagos_time=snap.lagos_time,
        market_state=snap.market_state.value,
        next_state=snap.next_state.value,
        next_change_at=snap.next_change_at,
        world_started=snap.world_started,
        test_weeks_ahead=ahead,
        game_date=GameDateResponse(**vars(snap.game_date)) if snap.game_date else None,
    )


@app.get("/api/world/status", response_model=WorldStatusResponse)
def world_status(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    world = _world(conn)
    last = world["last_closed_period"] if world else 0
    count = conn.execute("SELECT count(*) AS n FROM companies").fetchone()["n"]
    return WorldStatusResponse(
        companies=count,
        last_closed_period=last,
        last_closed_label=clock.period_label(last) if last else None,
    )


# ---------------------------------------------------------------------------
# Companies. Everything here is read from the REPORTED record: what each company
# filed. The true record is never sent to a player.
# ---------------------------------------------------------------------------

def _amounts_as_text(value, key: str | None = None):
    """Rewrite a filed report so every amount is kobo written as text."""
    if isinstance(value, dict):
        return {k: _amounts_as_text(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_amounts_as_text(v, key) for v in value]
    if isinstance(value, int) and not isinstance(value, bool) and key not in _NOT_AMOUNTS:
        return str(value)
    return value


def _location_effect(conn: Connection, company: dict) -> LocationEffect | None:
    """What a company's head-office location does to its running costs, in plain words."""
    place = conn.execute("SELECT * FROM locations WHERE name = %s", (company["headquarters"],)).fetchone()
    if place is None:
        return None
    where, cost = place["name"], company["location_cost_bps"]
    general = place["running_cost_bps"]
    reasons = []
    if general > 10_000:
        reasons.append(f"Rents and wages in {where} are about {(general - 10_000) / 100:.0f}% above the national average.")
    elif general < 10_000:
        reasons.append(f"Rents and wages in {where} are about {(10_000 - general) / 100:.0f}% below the national average.")
    else:
        reasons.append(f"Rents and wages in {where} are close to the national average.")
    fit = cost - general
    kind = company["sector_name"].lower()
    if fit < 0:
        reasons.append(f"{where} suits {kind}: that takes a further {-fit / 100:.0f}% off its running costs.")
    elif fit > 0:
        reasons.append(f"{where} is a hard place for {kind}: that adds {fit / 100:.0f}% to its running costs.")
    reasons.append(f"Half its staff work in {where}; the rest are spread across the country.")
    return LocationEffect(running_cost_bps=cost, reasons=reasons)


_MIN_PLAYERS_SHOWN = 20



@app.get("/api/economy", response_model=EconomyResponse)
def economy(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The published statistics of the economy: who earns, who spends, where money sits."""
    world = _world(conn)
    period = world["last_closed_period"] if world else 0
    money = ledger.amount_in_existence(conn) if world else 0

    now = {r["location"]: r for r in conn.execute(
        "SELECT h.*, l.population_bps, l.sort_order FROM household_results h JOIN locations l ON l.name = h.location"
        " WHERE h.period = %s", (period,)).fetchall()}
    before = {r["location"]: r for r in conn.execute(
        "SELECT * FROM household_results WHERE period = %s", (period - 1,)).fetchall()}

    def change(location: str, column: str) -> int | None:
        old = before.get(location, {}).get(column)
        # The opening quarter has no real "before" to compare with.
        if period < 2 or not old:
            return None
        return round((now[location][column] - old) * 10_000 / old)

    # A handful of players' balances would give each one away, so the players' line
    # appears only once there are enough of them. Until then they are part of "Other".
    enough_players = conn.execute("SELECT count(*) AS n FROM players").fetchone()["n"] >= _MIN_PLAYERS_SHOWN
    held = moneywatch.holders(conn)
    if not enough_players:
        # Counted with the other private investors, so that no line on the page is the players' money alone.
        held["Private investors"] += held.pop("Players")
    holders = [
        MoneyHolder(holder=name, amount_kobo=amount, share_bps=amount * 10_000 // money if money else 0)
        for name, amount in held.items()
    ]

    listed = sum(h.amount_kobo for h in holders)
    if money - listed > 0:
        holders.append(MoneyHolder(holder="Other", amount_kobo=money - listed, share_bps=(money - listed) * 10_000 // money))

    history = conn.execute(
        "SELECT h.period, sum(h.income)::bigint AS income, sum(h.spending)::bigint AS spending, sum(h.jobs)::bigint AS jobs,"
        "       (SELECT coalesce(sum(r.revenue), 0)::bigint FROM company_results r WHERE r.period = h.period) AS sales"
        " FROM household_results h WHERE h.period >= 1 AND h.period > %s GROUP BY h.period ORDER BY h.period",
        (period - 12,),
    ).fetchall()

    spending = conn.execute(
        "SELECT s.name, sum(r.sales_households)::bigint AS amount FROM company_results r"
        " JOIN companies c ON c.id = r.company_id JOIN sectors s ON s.code = c.sector"
        " WHERE r.period = %s GROUP BY s.name, s.sort_order ORDER BY amount DESC, s.sort_order", (period,),
    ).fetchall()
    spent = sum(r["amount"] for r in spending)

    prices, watch, macro_history = None, None, []
    state = conn.execute("SELECT * FROM economy_results WHERE period = %s", (period,)).fetchone() if period else None
    if state:
        earlier = conn.execute("SELECT * FROM economy_results WHERE period = %s", (period - 1,)).fetchone()
        names = (("Energy (oil, gas, fuel)", "energy_bps"), ("Farm produce", "agriculture_bps"),
                 ("Metals", "metals_bps"), ("Building materials", "materials_bps"))
        prices = PricesAndRates(
            inflation_bps=state["inflation_bps"], inflation_target_bps=data.INFLATION_TARGET_BPS,
            inflation_low_bps=data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS,
            inflation_high_bps=data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS,
            price_index_bps=state["price_index_bps"], wage_index_bps=state["wage_index_bps"],
            policy_rate_bps=state["next_policy_rate_bps"], previous_rate_bps=state["policy_rate_bps"],
            rate_reason=state["rate_reason"],
            household_loan_rate_bps=state["next_policy_rate_bps"] + data.HOUSEHOLD_LOAN_SPREAD_BPS,
            confidence_bps=state["confidence_bps"], demand_gap_bps=state["demand_gap_bps"],
            household_debt_kobo=sum(r["debt"] for r in now.values()),
            central_bank_lending_kobo=conn.execute(
                "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS total FROM company_debts"
                " WHERE kind = 'central_bank_loan'").fetchone()["total"],
            commodities=[
                CommodityPrice(
                    name=name, index_bps=state[column],
                    change_bps=round((state[column] - earlier[column]) * 10_000 / earlier[column]) if earlier else None,
                ) for name, column in names
            ],
        )
        macro_history = [
            MacroQuarter(period=r["period"], period_label=clock.period_label(r["period"]), inflation_bps=r["inflation_bps"],
                         policy_rate_bps=r["policy_rate_bps"], money_kobo=r["money"])
            for r in conn.execute("SELECT period, inflation_bps, policy_rate_bps, money FROM economy_results"
                                  " WHERE period >= 1 AND period > %s ORDER BY period", (period - 12,)).fetchall()
        ]
        reading = conn.execute("SELECT reading, reasons, action, money_growth_bps, output_growth_bps"
                               " FROM money_watch_results WHERE period = %s", (period,)).fetchone()
        if reading:
            watch = MoneyWatch(
                reading=reading["reading"], action=reading["action"],
                # What players hold between them stays private until there are enough of them.
                reasons=[r for r in reading["reasons"] if enough_players or not r.startswith("Players ")],
                money_growth_bps=reading["money_growth_bps"], output_growth_bps=reading["output_growth_bps"],
            )

    return EconomyResponse(
        prices=prices, macro_history=macro_history, money_watch=watch,
        period=period, period_label=clock.period_label(period) if period else None,
        money_in_existence_kobo=money,
        households=[
            HouseholdGroup(
                location=r["location"], population_bps=r["population_bps"], income_kobo=r["income"],
                wages_kobo=r["wages"], government_kobo=r["government"], pensions_kobo=r["pensions"],
                spending_kobo=r["spending"], savings_kobo=r["cash"], claims_kobo=r["claims"], debt_kobo=r["debt"],
                jobs=r["jobs"],
                income_change_bps=change(r["location"], "income"), jobs_change_bps=change(r["location"], "jobs"),
            )
            for r in sorted(now.values(), key=lambda r: r["sort_order"])
        ],
        money=holders,
        history=[
            EconomyQuarter(
                period=r["period"], period_label=clock.period_label(r["period"]), company_sales_kobo=r["sales"],
                household_income_kobo=r["income"], household_spending_kobo=r["spending"], jobs=r["jobs"],
            )
            for r in history
        ],
        household_spending=[
            SpendingShare(sector=r["name"], share_bps=r["amount"] * 10_000 // spent) for r in spending if spent
        ],
    )


# ---------------------------------------------------------------------------
# The news wire. A player is shown only what is dated up to the present game day:
# an event later in the running quarter is already decided, and stays unseen.
# ---------------------------------------------------------------------------

@app.get("/api/news", response_model=NewsResponse)
def read_news(
    outlet: str | None = Query(default=None, max_length=40),
    ticker: str | None = Query(default=None, pattern="^[A-Z]{2,5}$"),
    limit: int = Query(default=60, ge=1, le=120),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    world = _world(conn)
    papers = list(news_kinds.OUTLETS.values())
    if world is None:
        return NewsResponse(outlets=papers, items=[])
    code = next((key for key, name in news_kinds.OUTLETS.items() if outlet in (key, name)), None)
    if outlet and code is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no newspaper of that name.")
    today = clock.game_date(datetime.now(timezone.utc), clock.effective_start(world["world_start"], world["weeks_ahead"]))
    if today is None:
        return NewsResponse(outlets=papers, items=[])
    period_now = (today.year - 1) * clock.QUARTERS_PER_YEAR + today.quarter
    found = news.visible(conn, period_now, today.day_of_quarter, limit=limit, outlet=code, ticker=ticker)
    return NewsResponse(outlets=papers, items=[
        NewsItem(
            period=r["period"], period_label=clock.period_label(r["period"]), day=r["day"],
            outlet=news_kinds.OUTLETS[r["outlet"]], kind=r["kind"], story=r["story"], importance=r["importance"],
            headline=r["headline"], body=r["body"], tickers=r["tickers"], locations=r["locations"],
        ) for r in found
    ])


# ---------------------------------------------------------------------------
# The Broad Street Exchange. A player trades only from their own account, and
# sees of other people's orders only the totals waiting at each price.
# ---------------------------------------------------------------------------

def _trading_account(conn: Connection, player: dict):
    account = ledger.player_account_id(conn, player["id"])
    if account is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your account is not open yet.")
    return account


def _order_response(row: dict) -> OrderResponse:
    return OrderResponse(
        id=row["id"], ticker=row["ticker"], name=row["name"], side=row["side"], kind=row["kind"],
        limit_price_kobo=row["limit_price"], quantity=row["quantity"], remaining=row["remaining"],
        held_kobo=row["reserved"], value_traded_kobo=row["value_filled"], fees_paid_kobo=row["fees_paid"],
        status=row["status"], closed_reason=row["closed_reason"], placed_at=row["placed_at"], closed_at=row["closed_at"],
    )


def _exchange_time(conn: Connection) -> datetime:
    # The database's clock, so every server agrees on whether the market is open.
    return conn.execute("SELECT now() AS now").fetchone()["now"]


@app.get("/api/market/orders", response_model=list[OrderResponse])
def my_orders(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return [_order_response(row) for row in exchange.orders_of(conn, _trading_account(conn, player))]


@app.get("/api/market/holdings", response_model=list[Holding])
def my_holdings(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    holdings = []
    for row in exchange.holdings_of(conn, _trading_account(conn, player)):
        price = row["last_price"] or row["reference_price"]
        holdings.append(Holding(
            ticker=row["ticker"], name=row["name"], shares=row["shares"], held_for_orders=row["held_for_orders"],
            price_kobo=price, value_kobo=price * (row["shares"] + row["held_for_orders"]),
        ))
    return holdings


@app.post("/api/market/orders", response_model=PlacedOrderResponse, status_code=status.HTTP_201_CREATED)
def place_order(body: OrderRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    if (body.kind == "limit") != (body.limit_price_kobo is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Give a price for an order at your own price, and none for an order at the best price available.")
    account = _trading_account(conn, player)
    try:
        result = exchange.place_order(
            conn, account=account, ticker=body.ticker, side=body.side, kind=body.kind, quantity=body.quantity,
            limit_price=body.limit_price_kobo, now=_exchange_time(conn),
        )
    except exchange.ExchangeError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except exchange.EngineFailure:
        log.exception("The order-matching engine failed.")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The exchange cannot take orders at this moment. Nothing was changed. Please try again.") from None
    placed = next(row for row in exchange.orders_of(conn, account, limit=200) if row["id"] == result["order"]["id"])
    return PlacedOrderResponse(
        order=_order_response(placed),
        trades=[PublicTrade(price_kobo=t["price"], quantity=t["quantity"], in_auction=t["in_auction"], traded_at=t["traded_at"])
                for t in result["trades"]],
    )


@app.delete("/api/market/orders/{order_id}", response_model=OrderResponse)
def cancel_order(
    order_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    account = _trading_account(conn, player)
    try:
        exchange.cancel_order(conn, account=account, order_id=order_id, now=_exchange_time(conn))
    except exchange.ExchangeError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    except exchange.EngineFailure:
        log.exception("The order-matching engine failed.")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "The exchange cannot do that at this moment. Nothing was changed. Please try again.") from None
    return _order_response(next(row for row in exchange.orders_of(conn, account, limit=200) if row["id"] == order_id))


@app.get("/api/market/{ticker}", response_model=QuoteResponse)
def quote(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    found = exchange.quote(conn, ticker, _exchange_time(conn))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no share with that code on the exchange.")
    level = lambda row: PriceLevel(price_kobo=row["price"], quantity=row["quantity"], orders=row["orders"])  # noqa: E731
    return QuoteResponse(
        ticker=found["ticker"], name=found["name"], market_state=found["state"], last_price_kobo=found["last_price"],
        reference_price_kobo=found["reference_price"], lowest_today_kobo=found["lowest_today"],
        highest_today_kobo=found["highest_today"], fee_bps=data.EXCHANGE_FEE_BPS + data.STAMP_DUTY_BPS,
        bids=[level(row) for row in found["bids"]], offers=[level(row) for row in found["offers"]],
        trades=[PublicTrade(price_kobo=t["price"], quantity=t["quantity"], in_auction=t["in_auction"], traded_at=t["traded_at"])
                for t in found["trades"]],
    )


def _with_ebitda(figures: dict) -> dict:
    """Filings made before EBITDA was filed still show it: it is worked out from what they did file."""
    income = figures["income_statement"]
    if "ebitda" not in income:
        income["ebitda"] = income["operating_profit"] + income["depreciation"]
    return figures


@app.get("/api/companies", response_model=CompaniesResponse)
def list_companies(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    rows = conn.execute(
        "SELECT c.ticker, c.name, c.headquarters, s.code AS sector_code, s.name AS sector_name,"
        "       r.period, r.credit_rating, r.figures,"
        "       (prev.figures -> 'income_statement' ->> 'revenue')::bigint AS previous_revenue"
        " FROM companies c"
        " JOIN sectors s ON s.code = c.sector"
        " JOIN LATERAL (SELECT * FROM company_reports x WHERE x.company_id = c.id"
        "               ORDER BY x.period DESC, x.version DESC LIMIT 1) r ON true"
        " LEFT JOIN LATERAL (SELECT figures FROM company_reports y WHERE y.company_id = c.id"
        "                    AND y.period = r.period - 1 ORDER BY y.version DESC LIMIT 1) prev ON true"
        " ORDER BY s.sort_order, c.name"
    ).fetchall()

    sectors: dict[str, SectorCompanies] = {}
    for r in rows:
        income = r["figures"]["income_statement"]
        previous = r["previous_revenue"]
        change = None
        if previous and previous > 0:
            change = round((income["revenue"] - previous) * 10_000 / previous)
        sector = sectors.setdefault(
            r["sector_code"], SectorCompanies(code=r["sector_code"], name=r["sector_name"], companies=[])
        )
        sector.companies.append(
            CompanySummary(
                ticker=r["ticker"], name=r["name"], headquarters=r["headquarters"],
                period=r["period"], period_label=clock.period_label(r["period"]),
                credit_rating=r["credit_rating"],
                revenue_kobo=income["revenue"], net_profit_kobo=income["net_profit"],
                ebitda_kobo=income.get("ebitda", income["operating_profit"] + income["depreciation"]),
                total_assets_kobo=r["figures"]["balance_sheet"]["total_assets"],
                revenue_change_bps=change,
            )
        )
    return CompaniesResponse(sectors=list(sectors.values()))


@app.get("/api/companies/{ticker}", response_model=CompanyResponse)
def get_company(
    ticker: str,
    periods: int = Query(default=8, ge=1, le=40),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    company = None
    if len(ticker) == 3 and ticker.isascii() and ticker.isalpha():   # anything else cannot be a ticker
        company = conn.execute(
            "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector"
            " WHERE c.ticker = %s",
            (ticker.upper(),),
        ).fetchone()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no company with that ticker.")

    filed = conn.execute(
        "SELECT DISTINCT ON (period) period, version, figures, credit_rating, rating_reasons, filed_by, filed_at"
        " FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT %s",
        (company["id"], periods),
    ).fetchall()

    # The share register: who holds the shares, from the ledger.
    holders = conn.execute(
        "SELECT a.name, b.balance FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
        " WHERE b.asset = %s AND b.balance > 0 ORDER BY b.balance DESC, a.name",
        (company["share_asset"],),
    ).fetchall()
    in_issue = sum(h["balance"] for h in holders)

    return CompanyResponse(
        ticker=company["ticker"], name=company["name"], sector=company["sector_name"],
        headquarters=company["headquarters"], shares_in_issue=in_issue,
        location=_location_effect(conn, company),
        buys_from=[
            Supplier(sector=r["name"], share_bps=r["bps"])
            for r in conn.execute(
                "SELECT s.name, i.bps FROM sector_inputs i JOIN sectors s ON s.code = i.supplier"
                " WHERE i.buyer = %s ORDER BY i.bps DESC, s.name", (company["sector"],),
            ).fetchall()
        ],
        owners=[
            Owner(name=h["name"], shares=h["balance"], share_bps=h["balance"] * 10_000 // in_issue)
            for h in holders
        ],
        reports=[
            FiledReport(
                period=r["period"], period_label=clock.period_label(r["period"]), version=r["version"],
                amended=r["version"] > 1, filed_by=r["filed_by"], filed_at=r["filed_at"],
                credit_rating=r["credit_rating"], rating_reasons=r["rating_reasons"],
                figures=_amounts_as_text(_with_ebitda(r["figures"])),
            )
            for r in reversed(filed)
        ],
    )
