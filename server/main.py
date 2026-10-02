"""The server. It checks every request and decides every outcome.

Stage 1 covers: sign-up, login, logout, "who am I", and the world clock.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response, status
from psycopg import Connection
from psycopg.errors import UniqueViolation

from server import security
from server.config import get_settings
from server.db import close_pool, get_connection
from server.schemas import (
    ClockResponse,
    GameDateResponse,
    LoginRequest,
    Money,
    PlayerResponse,
    SignUpRequest,
)
from simulation import clock


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()  # Fail at start-up, not mid-request, if a setting is missing.
    yield
    close_pool()


app = FastAPI(title="Wall Street: Beyond the Market", lifespan=lifespan)


def _age_on(day: date, born: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def _player_response(row: dict) -> PlayerResponse:
    return PlayerResponse(
        id=str(row["id"]),
        display_name=row["display_name"],
        reputation=row["reputation"],
        cash=Money(amount_kobo=row["opening_cash_kobo"], currency=row["currency"]),
    )


def _start_session(response: Response, player_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=security.SESSION_COOKIE,
        value=security.create_session_token(player_id),
        max_age=settings.session_days * 24 * 60 * 60,
        httponly=True,  # Page scripts cannot read it, which blocks a common way of stealing logins.
        secure=settings.cookie_secure,
        samesite="lax",
    )


def current_player(
    session: str | None = Cookie(default=None, alias=security.SESSION_COOKIE),
    conn: Connection = Depends(get_connection),
) -> dict:
    player_id = security.read_session_token(session) if session else None
    row = None
    if player_id:
        row = conn.execute("SELECT * FROM players WHERE id = %s", (player_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    return row


@app.get("/api/health")
def health(conn: Connection = Depends(get_connection)) -> dict:
    conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/auth/signup", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def sign_up(body: SignUpRequest, response: Response, conn: Connection = Depends(get_connection)):
    settings = get_settings()
    today = datetime.now(clock.LAGOS).date()
    if body.date_of_birth > today or _age_on(today, body.date_of_birth) < settings.minimum_age:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This game is for players aged {settings.minimum_age} and above.",
        )

    try:
        row = conn.execute(
            "INSERT INTO players (email, display_name, password_hash, adult_confirmed_at)"
            " VALUES (%s, %s, %s, now()) RETURNING *",
            (body.email.lower(), body.display_name, security.hash_password(body.password)),
        ).fetchone()
    except UniqueViolation as error:
        taken = "display name" if "display_name" in (error.diag.constraint_name or "") else "email"
        raise HTTPException(status.HTTP_409_CONFLICT, f"That {taken} is already in use.") from error

    _start_session(response, str(row["id"]))
    return _player_response(row)


@app.post("/api/auth/login", response_model=PlayerResponse)
def log_in(body: LoginRequest, response: Response, conn: Connection = Depends(get_connection)):
    row = conn.execute(
        "SELECT * FROM players WHERE lower(email) = %s", (body.email.lower(),)
    ).fetchone()
    if not security.verify_password(body.password, row["password_hash"] if row else None):
        # One message for both a wrong email and a wrong password, so nobody can
        # use this form to find out which emails have accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")

    _start_session(response, str(row["id"]))
    return _player_response(row)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(response: Response) -> None:
    response.delete_cookie(security.SESSION_COOKIE)


@app.get("/api/me", response_model=PlayerResponse)
def me(player: dict = Depends(current_player)):
    return _player_response(player)


@app.get("/api/world/clock", response_model=ClockResponse)
def world_clock():
    snap = clock.snapshot(datetime.now(timezone.utc), get_settings().world_start)
    return ClockResponse(
        lagos_time=snap.lagos_time,
        market_state=snap.market_state.value,
        next_state=snap.next_state.value,
        next_change_at=snap.next_change_at,
        world_started=snap.world_started,
        game_date=GameDateResponse(**vars(snap.game_date)) if snap.game_date else None,
    )
