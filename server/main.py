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
    Holding, OrderRequest, OrderResponse, PlacedOrderResponse, PriceLevel, PublicTrade, QuoteResponse, WhyResponse,
    AnalysisResponse, IndexPoint, MarketResponse, MarketShare, NpvYear, PortfolioHolding, PortfolioResponse,
    Shareholder, TradingDay, WatchedShare, WatchRequest,
    BellMover, ClosingBell, ClosingBellResponse, CompanyFactsResponse, Industry, IndustryCompany, IndustryPlace, LargeOrder,
    NetWorthDay, NextResults, ProfitPerShare, ReportQuarter, ResultsReportResponse, TickerResponse, TickerShare,
    BondHolding, BondRow, BondsResponse, BondTradeRequest, BondTradeResponse, ConvertRequest, CorporateResponse, CreditSpread,
    AcceptRequest, AccountantDeskResponse, AllocationSlice, AssetDeskResponse, BankInfo, BuildInfo, BuildRequest, CareerEvent,
    CareerInfo, CareerResponse, ExtraSavingRequest, FundRequest, HandInRequest, InterestPaid, JobInfo, ObjectiveOffer, ObjectiveRow, ObjectivesResponse,
    Opening, OtherBuild, PayInfo, Payslip, PensionFund, PlayerBank, RetirementEntry, RetirementInfo, ReviewStanding, Skill,
    StatementQuarter, TickerRequest, WatchRow,
    CurvePoint, GrantResponse, GrantStep, IntegrationQuarter, IntegrationRow, Notice, OfferRow, OwnershipRow, SharesRequest,
    TakeoverRow, VoteRequest, VoteRow, WaitingSwap,
)
from simulation import clock, exchange, investors, ledger, moneywatch, news, news_kinds, players, quarters
from simulation import bonds, careers, closingbell, corporate, desks, grants, insight, marketview, objectives
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
            # The computer-run investors look at the market and renew their orders.
            investors.act(conn, now)
            # After 22:00 the Closing Bell goes out, once for each trading day.
            closingbell.ring(conn, now)


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
    mine = careers.career(conn, row["id"]) if row.get("build") else None
    job = careers.current_job(conn, row["id"]) if mine else None
    return PlayerResponse(
        id=str(row["id"]),
        display_name=row["display_name"],
        reputation=row["reputation"],
        profile_icon=row["profile_icon"],
        cash=Money(amount_kobo=cash, currency=NGN),
        build=mine and mine["build"],
        build_name=mine and careers.BUILDS[mine["build"]]["name"],
        accent=mine and careers.BUILDS[mine["build"]]["accent"],
        level=mine and mine["level"],
        employer=job and job["name"],
        empire=_empire_badge(conn, row["id"]),
    )


def _empire_badge(conn: Connection, player_id):
    from server.schemas import EmpireBadge
    from simulation import empires
    seen = empires.badge(conn, player_id, _exchange_time(conn))
    return seen and EmpireBadge(**seen)


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
        closing_rush=clock.in_closing_rush(snap.lagos_time),
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


@app.get("/api/market", response_model=MarketResponse)
def market(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The whole market: every share's price and today's move, and the BSX 50 index."""
    seen = marketview.overview(conn, _exchange_time(conn))
    return MarketResponse(
        market_state=seen["state"], paused_until=seen["paused_until"], index=seen["index"] / 100,
        index_change_bps=seen["index_change_bps"], market_value_kobo=seen["market_value"], volume=seen["volume"],
        trades=seen["trades"],
        shares=[MarketShare(
            ticker=s["ticker"], name=s["name"], sector=s["sector"], price_kobo=s["price"], traded=s["last_price"] is not None,
            change_bps=s["change_bps"], volume=s["volume"], market_value_kobo=s["market_value"], credit_rating=s["rating"],
        ) for s in seen["shares"]],
        index_history=[IndexPoint(session_date=p["session_date"], level=p["level"] / 100) for p in seen["index_history"]],
    )


@app.get("/api/market/portfolio", response_model=PortfolioResponse)
def my_portfolio(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    account, now = _trading_account(conn, player), _exchange_time(conn)
    mine = marketview.portfolio(conn, account, now)
    # Bonds and bills, and what the exchange holds for applications and takeover acceptances, are part of what a player is worth.
    mine["bonds_value"] = sum(h["value"] for h in bonds.holdings_of(conn, account, now))
    held_cash, offered = corporate.held_by_account(conn).get(account, (0, 0))
    mine["total"] += mine["bonds_value"] + held_cash + offered
    bill = next((b for b in bonds.curve(conn)["points"] if b["quarters"] == 1), None)
    days = [NetWorthDay(session_date=d["session_date"], total_kobo=d["total"]) for d in mine["net_worth_days"]
            if d["session_date"] < mine["today"]]
    days.append(NetWorthDay(session_date=mine["today"], total_kobo=mine["total"]))
    return PortfolioResponse(
        advice=insight.personal_advice(conn, mine, bill_yield_bps=bill["yield_bps"] if bill else None), net_worth=days,
        bonds_value_kobo=mine["bonds_value"], held_for_offers_kobo=held_cash, offered_to_bidders_kobo=offered,
        cash_kobo=mine["cash"], held_for_orders_kobo=mine["held_for_orders"], shares_value_kobo=mine["shares_value"],
        total_kobo=mine["total"], dividends_kobo=mine["dividends"], realised_kobo=mine["realised"],
        holdings=[PortfolioHolding(
            ticker=h["ticker"], name=h["name"], shares=h["shares"], held_for_orders=h["held_for_orders"],
            price_kobo=h["price"], change_bps=h["change_bps"], value_kobo=h["value"], cost_kobo=h["cost"],
            gain_kobo=h["gain"], dividends_kobo=h["dividends"],
        ) for h in mine["holdings"]],
    )


def _watched(conn: Connection, player: dict) -> list[WatchedShare]:
    return [WatchedShare(
        ticker=w["ticker"], name=w["name"], price_kobo=w["price"], change_bps=w["change_bps"],
        alert_above_kobo=w["alert_above"], alert_below_kobo=w["alert_below"], reached=w["reached"],
    ) for w in marketview.watchlist(conn, player["id"], _exchange_time(conn))]


@app.get("/api/market/watchlist", response_model=list[WatchedShare])
def my_watchlist(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _watched(conn, player)


@app.put("/api/market/watchlist/{ticker}", response_model=list[WatchedShare])
def watch_a_share(
    body: WatchRequest,
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    limits.allow("watchlist", str(player["id"]), attempts=60, per_seconds=60)
    try:
        marketview.watch(conn, player["id"], ticker, body.alert_above_kobo, body.alert_below_kobo)
    except marketview.WatchlistError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _watched(conn, player)


@app.delete("/api/market/watchlist/{ticker}", response_model=list[WatchedShare])
def stop_watching_a_share(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    limits.allow("watchlist", str(player["id"]), attempts=60, per_seconds=60)
    marketview.unwatch(conn, player["id"], ticker)
    return _watched(conn, player)


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
        raise HTTPException(422,
                            "Give a price for an order at your own price, and none for an order at the best price available.")
    account = _trading_account(conn, player)
    try:
        # A player may not deal with the empire they sit in, or the pension fund they manage.
        from simulation import empires
        company = conn.execute("SELECT id FROM companies WHERE ticker = %s", (body.ticker,)).fetchone()
        if company:
            try:
                empires.own_order_allowed(conn, account, company["id"], body.side)
            except empires.EmpireError as refused:
                raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
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


def _notice(row: dict, ticker: str | None) -> Notice:
    return Notice(ticker=ticker, kind=row["kind"], title=row["title"], body=row["body"], posted_at=row["posted_at"],
                  period_label=clock.period_label(row["period"]))


@app.get("/api/market/ticker", response_model=TickerResponse)
def price_ticker(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every share's price and today's move, for the strip across the top of every screen."""
    now = _exchange_time(conn)
    seen = marketview.overview(conn, now, with_history=False)
    return TickerResponse(
        market_state=seen["state"], closing_rush=clock.in_closing_rush(now), index=seen["index"] / 100,
        index_change_bps=seen["index_change_bps"],
        shares=[TickerShare(ticker=s["ticker"], price_kobo=s["price"], change_bps=s["change_bps"],
                            traded_today=s["volume"] > 0) for s in seen["shares"]],
    )


@app.get("/api/market/closing-bell", response_model=ClosingBellResponse)
def closing_bell(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """The Closing Rush as it stands, and the latest Closing Bell broadcast."""
    rush = closingbell.rush(conn, _exchange_time(conn))
    rung = closingbell.latest(conn)
    bell = None
    if rung:
        c = rung["content"]
        mover = lambda m: BellMover(ticker=m["ticker"], name=m["name"], close_kobo=m["close"], change_bps=m["change_bps"]) if m else None  # noqa: E731
        bell = ClosingBell(
            session_date=rung["session_date"], rung_at=rung["rung_at"], index=c["index"] / 100,
            index_change_bps=c["index_change_bps"], lines=c["lines"], stories=c["stories"], advisory=c["advisory"],
            next=c["next"], winner=mover(c["winner"]), loser=mover(c["loser"]), risers=c["risers"], fallers=c["fallers"])
    return ClosingBellResponse(
        in_rush=rush["in_rush"], fee_bps=rush["fee_bps"], usual_fee_bps=rush["usual_fee_bps"], bell=bell,
        large_orders=[LargeOrder(ticker=o["ticker"], name=o["name"], side=o["side"], quantity=o["quantity"],
                                 value_kobo=o["value"], shown_at=o["shown_at"]) for o in rush["large_orders"]])


@app.get("/api/market/industries", response_model=list[Industry])
def industries(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Every industry: today's move, how fast its sales are growing, and its companies ranked by their share of it."""
    return [Industry(
        code=s["code"], name=s["name"], market_value_kobo=s["market_value"], change_bps=s["change_bps"], sales_kobo=s["sales"],
        sales_growth_bps=s["sales_growth_bps"],
        companies=[IndustryCompany(
            ticker=c["ticker"], name=c["name"], rank=c["rank"], share_bps=c["share_bps"], sales_kobo=c["sales"],
            sales_growth_bps=c["sales_growth_bps"], price_kobo=c["price"], change_bps=c["change_bps"],
            market_value_kobo=c["market_value"]) for c in s["companies"]],
    ) for s in insight.industries(conn, _exchange_time(conn))]


@app.get("/api/market/{ticker}/facts", response_model=CompanyFactsResponse)
def company_facts(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    found = insight.facts(conn, ticker, _exchange_time(conn))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no company with that code.")
    return CompanyFactsResponse(
        ticker=found["ticker"], name=found["name"], filing_label=clock.period_label(found["period"]),
        profit_per_share=[ProfitPerShare(period=p["period"], label=p["label"], kobo_per_share=p["eps"] / 100,
                                         net_profit_kobo=p["net_profit"]) for p in found["profit_per_share"]],
        yearly_profit_per_share_kobo=found["yearly_profit_per_share"] / 100, compared_with=found["compared_with"],
        sales_change_bps=found["sales_change_bps"], profit_change_bps=found["profit_change_bps"],
        sales_before_kobo=found["sales_before"], profit_before_kobo=found["profit_before"], cash_kobo=found["cash"],
        cash_change_quarter_kobo=found["cash_change_quarter"], cash_change_year_kobo=found["cash_change_year"],
        cash_in_three_months_kobo=found["cash_in_three_months"], cash_outlook=found["cash_outlook"],
        year_high_kobo=found["year_high"], year_low_kobo=found["year_low"],
        next_results=NextResults(**found["next_results"]) if found["next_results"] else None,
        industry=IndustryPlace(**found["industry"]),
        control=corporate.control(conn, conn.execute("SELECT id FROM companies WHERE ticker = %s", (ticker,)).fetchone()["id"])["summary"],
        notices=[_notice(n, ticker) for n in conn.execute(
            "SELECT n.* FROM market_notices n JOIN companies c ON c.id = n.company_id WHERE c.ticker = %s ORDER BY n.id DESC LIMIT 8",
            (ticker,)).fetchall()],
    )


@app.get("/api/market/{ticker}/results", response_model=ResultsReportResponse)
def results_report(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    period: int | None = Query(default=None, ge=0, le=100_000),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    """One quarter's results in words, built only from what the company filed."""
    found = insight.results_report(conn, ticker, period)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That company has filed no report for that quarter.")
    return ResultsReportResponse(
        ticker=found["ticker"], name=found["name"], period=found["period"], label=found["label"], title=found["title"],
        paragraphs=found["paragraphs"], available=[ReportQuarter(**q) for q in found["available"]])


@app.get("/api/market/{ticker}/why", response_model=WhyResponse)
def why_the_price_moved(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    found = exchange.why(conn, ticker, _exchange_time(conn))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no share with that code on the exchange.")
    return WhyResponse(
        ticker=found["ticker"], name=found["name"], summary=found["summary"], move_bps=found["move_bps"],
        reference_price_kobo=found["reference_price"], last_price_kobo=found["last_price"],
        bought_in_a_hurry=found["bought_in_a_hurry"], sold_in_a_hurry=found["sold_in_a_hurry"], reasons=found["reasons"],
        valuation_label=clock.period_label(found["valuation_period"]) if found["valuation_period"] else None,
        valuation_reasons=found["valuation_reasons"],
    )


@app.get("/api/market/{ticker}/history", response_model=list[TradingDay])
def price_history(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    days = marketview.history(conn, ticker)
    if days is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no share with that code on the exchange.")
    return [TradingDay(session_date=d["session_date"], open_kobo=d["open"], close_kobo=d["close"], high_kobo=d["high"],
                       low_kobo=d["low"], volume=d["volume"]) for d in days]


@app.get("/api/market/{ticker}/analysis", response_model=AnalysisResponse)
def investor_analysis(
    ticker: str = FastPath(pattern="^[A-Z]{3}$"),
    _: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    found = marketview.analysis(conn, ticker, _exchange_time(conn))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no share with that code on the exchange.")
    ratio = lambda hundredths: None if hundredths is None else hundredths / 100          # noqa: E731
    return AnalysisResponse(
        ticker=found["ticker"], name=found["name"], filing_label=clock.period_label(found["period"]) if found["period"] else "Opening balance sheet",
        price_kobo=found["price"], shares_in_issue=found["shares_in_issue"], market_value_kobo=found["market_value"],
        yearly_profit_kobo=found["yearly_profit"], yearly_sales_kobo=found["yearly_sales"],
        yearly_dividends_kobo=found["yearly_dividends"], owners_funds_kobo=found["owners_funds"],
        book_per_share_kobo=found["book_per_share"], price_to_profit=ratio(found["price_to_profit"]),
        price_to_sales=ratio(found["price_to_sales"]), price_to_owners_funds=ratio(found["price_to_owners_funds"]),
        market_price_to_profit=ratio(found["market_price_to_profit"]), dividend_yield_bps=found["dividend_yield_bps"],
        npv_per_share_kobo=found["npv_per_share"], npv_total_kobo=found["npv_total"], npv_method=found["npv_method"],
        npv_gap_bps=found["npv_gap_bps"], growth_bps=found["growth_bps"], discount_bps=found["discount_bps"],
        long_run_bps=found["long_run_bps"],
        schedule=[NpvYear(label=y["label"], profit_kobo=y["profit"], value_today_kobo=y["value_today"]) for y in found["schedule"]],
        verdict=found["verdict"], reasons=found["reasons"], risks=found["risks"],
        shareholders=[Shareholder(**h) for h in found["shareholders"]],
    )


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

    # The share register: who holds the shares, by kind of owner. No single player's holding is
    # ever listed, and shares the exchange holds for a sell order still count as their seller's.
    holders = marketview.shareholders(conn, company["id"], company["share_asset"])
    in_issue = sum(h["shares"] for h in holders)

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
            Owner(name=h["holder"], shares=h["shares"], share_bps=h["share_bps"])
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


# ---------------------------------------------------------------------------
# Bonds and Government bills. A player trades with the bond desk (the pension funds),
# from their own account only, at the desk's prices.
# ---------------------------------------------------------------------------

def _bond_row(b: dict) -> dict:
    return dict(
        code=b["code"], name=b["name"], kind=b["kind"], kind_label=b["kind_label"], issuer=b["issuer"], ticker=b["ticker"],
        rating=b["rating"], pays=b["pays"], face_kobo=b["face"], maturity_label=b["maturity_label"], quarters_left=b["quarters_left"],
        yield_bps=b["yield_bps"], distressed=b["distressed"], conversion_shares=b["conversion_shares"], project=b["project"],
        green=b["green"], outstanding=b["outstanding"], fair_kobo=b["fair"], ask_kobo=b["ask"], bid_kobo=b["bid"],
        on_offer=b.get("on_offer"))


@app.get("/api/bonds", response_model=BondsResponse)
def bond_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    now = _exchange_time(conn)
    account = _trading_account(conn, player)
    curve = bonds.curve(conn)
    swaps = conn.execute(
        "SELECT v.id, b.asset, b.name, v.units, v.units * b.conversion_shares AS shares FROM bond_conversions v"
        " JOIN bonds b ON b.id = v.bond_id WHERE v.account_id = %s AND v.status = 'waiting' ORDER BY v.id", (account,)).fetchall()
    return BondsResponse(
        desk_open=clock.market_state(now) is clock.MarketState.OPEN, policy_rate_bps=curve["policy_rate_bps"],
        curve=[CurvePoint(**p) for p in curve["points"]], spreads=[CreditSpread(**p) for p in curve["spreads"]],
        bonds=[BondRow(**_bond_row(b)) for b in bonds.listing(conn, now)],
        holdings=[BondHolding(**_bond_row(h), units=h["units"], held_for_swap=h["held_for_swap"], value_kobo=h["value"],
                              cost_kobo=h["cost"], gain_kobo=h["gain"]) for h in bonds.holdings_of(conn, account, now)],
        income_kobo=bonds.income_of(conn, account),
        swaps=[WaitingSwap(id=r["id"], code=r["asset"][4:], name=r["name"], units=r["units"], shares=r["shares"]) for r in swaps],
    )


@app.post("/api/bonds/trade", response_model=BondTradeResponse, status_code=status.HTTP_201_CREATED)
def trade_a_bond(body: BondTradeRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    try:
        done = bonds.trade(conn, account=_trading_account(conn, player), code=body.code, side=body.side, units=body.units,
                           now=_exchange_time(conn))
    except bonds.BondError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return BondTradeResponse(code=done["code"], name=done["name"], side=done["side"], units=done["units"],
                             price_kobo=done["price"], value_kobo=done["value"], fair_kobo=done["fair"])


@app.post("/api/bonds/swaps", response_model=WaitingSwap, status_code=status.HTTP_201_CREATED)
def swap_bonds_for_shares(body: ConvertRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Ask for convertible bonds to be swapped for shares when the quarter closes."""
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    try:
        done = bonds.ask_to_convert(conn, account=_trading_account(conn, player), code=body.code, units=body.units,
                                    now=_exchange_time(conn))
    except bonds.BondError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    name = conn.execute("SELECT name FROM bonds WHERE asset = %s", (f"BND-{body.code}",)).fetchone()["name"]
    return WaitingSwap(id=done["id"], code=body.code, name=name, units=done["units"], shares=done["shares"])


@app.delete("/api/bonds/swaps/{swap_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_a_swap(
    swap_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
) -> None:
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    try:
        bonds.cancel_conversion(conn, account=_trading_account(conn, player), request_id=swap_id, now=_exchange_time(conn))
    except bonds.BondError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None


# ---------------------------------------------------------------------------
# Share offers, votes and takeovers: what a shareholder can act on.
# ---------------------------------------------------------------------------

def _corporate(conn: Connection, player: dict) -> CorporateResponse:
    account = _trading_account(conn, player)
    world = _world(conn)
    period = world["last_closed_period"] if world else 0
    seen = corporate.board(conn, account, period)
    closes = lambda row: f"when {clock.period_label(row['closes_period'])} closes"            # noqa: E731
    return CorporateResponse(
        offers=[OfferRow(
            id=o["id"], ticker=o["ticker"], name=o["name"], kind=o["kind"], price_kobo=o["price"], shares=o["shares"],
            rights_new=o["rights_new"], rights_held=o["rights_held"], reason=o["reason"], status=o["status"], closes_label=closes(o),
            needs_vote=o["vote_id"] is not None, outcome=o["outcome"], asked=o["asked"] or 0, held_kobo=o["held"] or 0,
            allotted=o["allotted"]) for o in seen["offers"]],
        votes=[VoteRow(
            id=v["id"], ticker=v["ticker"], name=v["name"], subject=v["subject"], question=v["question"], explanation=v["explanation"],
            board=v["board"], status=v["status"], closes_label=closes(v), my_choice=v["choice"], my_shares=v["my_shares"],
            votes_for=v["votes_for"], votes_against=v["votes_against"], tally=v["tally"]) for v in seen["votes"]],
        takeovers=[TakeoverRow(
            id=t["id"], bidder=t["bidder"], bidder_ticker=t["bidder_ticker"], target=t["target"], ticker=t["ticker"],
            price_kobo=t["price"], market_price_kobo=t["market_price"], premium_bps=t["premium_bps"], shares_sought=t["shares_sought"],
            hostile=t["hostile"], status=t["status"], closes_label=closes(t), needs_vote=t["vote_id"] is not None,
            outcome=t["outcome"], offered=t["offered"] or 0, free=t["free"]) for t in seen["takeovers"]],
        integrations=[IntegrationRow(
            bidder=i["bidder"], target=i["target"], ticker=i["ticker"], planned_saving_bps=i["planned_saving_bps"], quarters=i["quarters"],
            done=[IntegrationQuarter(label=clock.period_label(q["period"]), cost_bps=q["cost_bps"], notes=q["notes"])
                  for q in (i["quarters_done"] or [])]) for i in seen["integrations"]],
        notices=[_notice(n, n["ticker"]) for n in seen["notices"]],
    )


@app.get("/api/corporate", response_model=CorporateResponse)
def corporate_board(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _corporate(conn, player)


def _act(conn: Connection, player: dict, action) -> CorporateResponse:
    limits.allow("order", str(player["id"]), attempts=60, per_seconds=60)
    try:
        action(_trading_account(conn, player), _exchange_time(conn))
    except corporate.CorporateError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _corporate(conn, player)


@app.put("/api/corporate/offers/{offer_id}", response_model=CorporateResponse)
def apply_for_new_shares(
    body: SharesRequest,
    offer_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    return _act(conn, player, lambda account, now: corporate.apply_for_shares(
        conn, account=account, offer_id=offer_id, shares=body.shares, now=now))


@app.put("/api/corporate/votes/{vote_id}", response_model=CorporateResponse)
def cast_a_vote(
    body: VoteRequest,
    vote_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    return _act(conn, player, lambda account, now: corporate.cast_vote(conn, account=account, vote_id=vote_id, choice=body.choice, now=now))


@app.put("/api/corporate/takeovers/{takeover_id}", response_model=CorporateResponse)
def answer_a_takeover_offer(
    body: SharesRequest,
    takeover_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    return _act(conn, player, lambda account, now: corporate.tender(
        conn, account=account, takeover_id=takeover_id, shares=body.shares, now=now))


@app.get("/api/corporate/ownership", response_model=list[OwnershipRow])
def who_owns_what(_: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return [OwnershipRow(**row) for row in corporate.ownership(conn)]


# ---------------------------------------------------------------------------
# The starting grant, paid in parts.
# ---------------------------------------------------------------------------

@app.post("/api/me/grant", response_model=GrantResponse)
def my_grant(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    """Where the player stands with their starting grant. Any part that has fallen due is paid."""
    limits.allow("grant", str(player["id"]), attempts=30, per_seconds=60)
    seen = grants.review(conn, player["id"], _exchange_time(conn))
    return GrantResponse(received_kobo=seen["received"], total_kobo=seen["total"], next_payment_at=seen["next_payment_at"],
                         steps=[GrantStep(**s) for s in seen["steps"]])


# ---------------------------------------------------------------------------
# Stage 5. A player's working life: build, employer, bank, pay, retirement savings.
# ---------------------------------------------------------------------------

def _career(conn: Connection, player: dict) -> CareerResponse:
    seen = careers.profile(conn, player["id"], _exchange_time(conn))
    label = clock.period_label
    money = lambda row, *keys: {f"{k}_kobo": row[k] for k in keys}                 # noqa: E731
    pay = seen["pay"]
    savings = seen["retirement"]
    return CareerResponse(
        build=seen["build"], builds=[BuildInfo(**b) for b in seen["builds"]], later_builds=seen["later_builds"],
        reputation=seen["reputation"], can_change_build_at=seen["can_change_build_at"],
        career=seen["career"] and CareerInfo(**{**seen["career"], "review": seen["career"]["review"] and ReviewStanding(**seen["career"]["review"]),
                                               "other_builds": [OtherBuild(**o) for o in seen["career"]["other_builds"]]}),
        job=seen["job"] and JobInfo(ticker=seen["job"]["ticker"], name=seen["job"]["name"], headquarters=seen["job"]["headquarters"],
                                    since=seen["job"]["since"], can_move=seen["job"]["can_move"], owed_kobo=seen["job"]["owed"]),
        bank=seen["bank"] and BankInfo(**seen["bank"]),
        pay=pay and PayInfo(**money(pay, "gross", "pension_yours", "pension_employer", "tax", "living_costs", "take_home", "at_next_level",
                                    "extra_saving", "employer_match"),
                            worked_this_quarter=pay["worked_this_quarter"]),
        payslips=[Payslip(period_label=label(p["period"]), employer=p["employer"], level=p["level"], days_worked=p["days_worked"],
                          worked=p["worked"], note=p["note"],
                          **money(p, "gross", "pension_yours", "pension_employer", "tax", "living_costs", "take_home", "paid", "owed"))
                  for p in seen["payslips"]],
        interest=[InterestPaid(period_label=label(i["period"]), bank=i["bank"], lowest_balance_kobo=i["lowest_balance"],
                               rate_bps=i["rate_bps"], amount_kobo=i["amount"]) for i in seen["interest"]],
        retirement=savings and RetirementInfo(
            fund=savings["fund"], value_kobo=savings["value"], can_change=savings["can_change"],
            funds=[PensionFund(code=f["code"], name=f["name"], who_for=f["for"], shares_bps=f["shares_bps"], bonds_bps=f["bonds_bps"],
                               cash_bps=f["cash_bps"], last_return_bps=f["last_return_bps"], good=f["good"], bad=f["bad"],
                               best_bps=f["best_bps"], worst_bps=f["worst_bps"], year_bps=f["year_bps"],
                               year_after_prices_bps=f["year_after_prices_bps"]) for f in savings["funds"]],
            entries=[RetirementEntry(period_label=label(e["period"]), fund=e["fund"],
                                     **money(e, "opening", "growth", "paid_in_by_you", "paid_in_by_employer", "closing", "paid_out"))
                     for e in savings["entries"]],
            extra_bps=savings["extra_bps"], most_extra_bps=savings["most_extra_bps"], match_most_bps=savings["match_most_bps"],
            sound_finances=savings["sound_finances"], retired=savings["retired"], can_retire=savings["can_retire"],
            retirement_level=savings["retirement_level"], quarters_to_go=savings["quarters_to_go"],
            retires_label=savings["retires_label"], early_withdrawal_used=savings["early_withdrawal_used"],
            managed_by=savings["managed_by"] and savings["managed_by"]["name"], leaving_fund=savings["leaving_fund"]),
        events=[CareerEvent(**e) for e in seen["events"]], next_pay_day=seen["next_pay_day"],
    )


def _career_step(conn: Connection, player: dict, action) -> CareerResponse:
    limits.allow("career", str(player["id"]), attempts=30, per_seconds=60)
    try:
        action(_exchange_time(conn))
    except careers.CareerError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None
    return _career(conn, player)


@app.get("/api/career", response_model=CareerResponse)
def my_career(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career(conn, player)


@app.put("/api/career/build", response_model=CareerResponse)
def choose_my_build(body: BuildRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.choose_build(conn, player["id"], body.build, now))


@app.get("/api/career/employers", response_model=list[Opening])
def employers_hiring(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return [Opening(ticker=o["ticker"], name=o["name"], sector=o["sector"], headquarters=o["headquarters"], rating=o["rating"],
                    places_left=o["places_left"], behind_on_bills=o["behind_on_bills"], gross_kobo=o["gross"],
                    take_home_kobo=o["take_home"], yours=o["yours"])
            for o in careers.openings(conn, player["id"], _exchange_time(conn))]


@app.put("/api/career/job", response_model=CareerResponse)
def take_a_job(body: TickerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.take_job(conn, player["id"], body.ticker, now))


@app.delete("/api/career/job", response_model=CareerResponse)
def leave_my_job(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.leave_job(conn, player["id"], now))


@app.get("/api/career/banks", response_model=list[PlayerBank])
def the_six_banks(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return [PlayerBank(**b) for b in careers.banks(conn, player["id"], _exchange_time(conn))]


@app.put("/api/career/bank", response_model=CareerResponse)
def choose_my_bank(body: TickerRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.choose_bank(conn, player["id"], body.ticker, now))


@app.put("/api/career/retirement", response_model=CareerResponse)
def choose_my_fund(body: FundRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.choose_fund(conn, player["id"], body.fund, now))


@app.put("/api/career/extra-saving", response_model=CareerResponse)
def choose_my_extra_saving(body: ExtraSavingRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.set_extra_saving(conn, player["id"], body.extra_bps, now))


@app.post("/api/career/retirement/pension", response_model=CareerResponse)
def begin_my_pension(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _career_step(conn, player, lambda now: careers.retire(conn, player["id"], now))


# ---------------------------------------------------------------------------
# Professional objectives. The server sets the terms, judges the result and has the payer pay.
# A player sees only their own work, and never an answer before it has been judged.
# ---------------------------------------------------------------------------

def _terms_as_text(value):
    """Amounts of money inside an objective's terms travel as text, like every other amount."""
    if isinstance(value, dict):
        return {k: (str(v) if k == "kobo" and isinstance(v, int) else _terms_as_text(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_terms_as_text(v) for v in value]
    return value


def _objective(row: dict) -> ObjectiveRow:
    return ObjectiveRow(
        id=row["id"], template=row["template"], module=row["module"], title=row["title"], kind=row["kind"], idea=row["idea"],
        terms=_terms_as_text(row["terms"]), reward_kobo=row["reward"], experience=row["experience"], payer=row["payer"],
        accepted_at=row["accepted_at"], state=row["state"], progress=row["progress"], submission=row["submission"],
        submitted_at=row["submitted_at"], result=row["result"], judged_at=row["judged_at"], paid_kobo=row["paid"],
        can_hand_in=row["can_hand_in"], setting=row["setting"], setting_name=row["setting_name"], track=row["track"])


@app.get("/api/objectives", response_model=ObjectivesResponse)
def my_objectives(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("objective-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = objectives.board(conn, player["id"], _exchange_time(conn))
    return ObjectivesResponse(
        ready=seen["ready"], why=seen["why"], active=[_objective(o) for o in seen["active"]],
        offers=[ObjectiveOffer(**{**{k: v for k, v in o.items() if k != "reward"}, "reward_kobo": o["reward"]}) for o in seen["offers"]],
        finished=[_objective(o) for o in seen["finished"]], skills=[Skill(**s) for s in seen["skills"]],
        coverage=seen["coverage"], limit=seen["limit"], tracks=seen["tracks"], weekend=seen["weekend"], settings=seen["settings"],
        in_empire=seen.get("in_empire", False), empire_work=seen.get("empire_work", {}))


def _objective_step(player: dict, action) -> ObjectiveRow:
    limits.allow("objective", str(player["id"]), attempts=30, per_seconds=60)
    try:
        return _objective(action())
    except objectives.ObjectiveError as refused:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refused)) from None


@app.post("/api/objectives", response_model=ObjectiveRow, status_code=status.HTTP_201_CREATED)
def take_on_work(body: AcceptRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _objective_step(player, lambda: objectives.accept(conn, player["id"], body.template, _exchange_time(conn)))


@app.post("/api/objectives/{objective_id}/hand-in", response_model=ObjectiveRow)
def hand_work_in(
    body: HandInRequest,
    objective_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    return _objective_step(player, lambda: objectives.submit(conn, player["id"], objective_id, body.answers, _exchange_time(conn)))


@app.delete("/api/objectives/{objective_id}", response_model=ObjectiveRow)
def give_work_up(
    objective_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    return _objective_step(player, lambda: objectives.withdraw(conn, player["id"], objective_id, _exchange_time(conn)))


# ---------------------------------------------------------------------------
# The build screens' own figures.
# ---------------------------------------------------------------------------

@app.get("/api/desk/asset-manager", response_model=AssetDeskResponse)
def asset_manager_desk(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = desks.asset_desk(conn, player["id"], _trading_account(conn, player), _exchange_time(conn))
    piece = lambda a: AllocationSlice(label=a["label"], group=a["group"], value_kobo=a["value"], share_bps=a["share_bps"])   # noqa: E731
    return AssetDeskResponse(
        total_kobo=seen["total"], cash_kobo=seen["cash"], shares_kobo=seen["shares"], bonds_kobo=seen["bonds"],
        change_today_bps=seen["change_today_bps"], change_year_bps=seen["change_year_bps"],
        index_change_year_bps=seen["index_change_year_bps"], allocation=[piece(a) for a in seen["allocation"]],
        sectors=[piece(a) for a in seen["sectors"]], largest_bps=seen["largest_bps"], companies_held=seen["companies_held"],
        industries_held=seen["industries_held"], retirement_kobo=seen["retirement"])


@app.get("/api/desk/accountant", response_model=AccountantDeskResponse)
def accountant_desk(
    ticker: str | None = Query(default=None, pattern="^[A-Z]{3}$"),
    player: dict = Depends(current_player),
    conn: Connection = Depends(get_connection),
):
    limits.allow("desk-read", str(player["id"]), attempts=90, per_seconds=60)
    seen = desks.accountant_desk(conn, player["id"], ticker, _exchange_time(conn))
    if seen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no company with that code.")
    return AccountantDeskResponse(
        ticker=seen["ticker"], name=seen["name"], sector=seen["sector"], is_employer=seen["is_employer"],
        quarters=[StatementQuarter(period=q["period"], period_label=q["period_label"], credit_rating=q["credit_rating"],
                                   income_statement=q["income_statement"], cash_flow=q["cash_flow"], balance_sheet=q["balance_sheet"],
                                   notes=q["notes"], ratios=q["ratios"], tax_owed_kobo=q["tax_owed"], staff=q["staff"])
                  for q in seen["quarters"]],
        companies=seen["companies"],
        watch=[WatchRow(ticker=w["ticker"], name=w["name"], credit_rating=w["credit_rating"], unpaid_bills_kobo=w["unpaid"],
                        overdue_debt_kobo=w["overdue"], cash_kobo=w["cash"]) for w in seen["watch"]],
        tax_rate_bps=seen["tax_rate_bps"])


# Stage 6: empires, the War Room and pension funds run by players.
from server import empire_routes  # noqa: E402,F401  (importing it adds its routes to the application)
from server import rank_routes  # noqa: E402,F401
from server import firm_routes  # noqa: E402,F401
