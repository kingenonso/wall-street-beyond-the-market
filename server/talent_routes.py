"""Proven Talent on the website (the talent and funds stage, Part 1).

Three kinds of visitor:
  a player     their own record, badges, what they share, invitations, and the firms' challenges;
  anybody      a record a player has chosen to share, at its unguessable address (no login);
  a firm       its own login (a separate pass and cookie, with no player powers): the talent board, records it may see,
               invitations and its challenges. Firms are approved by an administrator before they can do anything.

Never sent: the honesty checks or anything about them (a player held back is only told the board is waiting on a routine
check); how much money anybody has (the record is percentages and counts); a record to a firm that may not see it; a
player's contact details unless they accepted that firm's invitation and typed them in.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Query, Response, status
from fastapi import Path as FastPath
from fastapi import Request as HttpRequest
from psycopg import Connection
from psycopg.errors import CheckViolation, DeadlockDetected, UniqueViolation
from pydantic import EmailStr, Field

from server import emails, limits, security
from server.config import get_settings
from server.db import connection, get_connection
from server.main import _exchange_time, app, current_player
from server.schemas import Request
from simulation import challenges, firms, talent
from simulation.money import naira

KOBO = {"starting_cash", "cash", "value", "price", "cost", "answer", "fee"}


def _wire(value, key: str | None = None):
    if isinstance(value, dict):
        return {k: _wire(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(v, key) for v in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if key in KOBO and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def _refuse(error: Exception) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


def _act(conn: Connection, who: str, action, bucket: str = "talent", attempts: int = 30):
    limits.allow(bucket, who, attempts=attempts, per_seconds=60)
    try:
        # All of it or none of it: the locks the action takes hold until it is saved, so two requests at once take turns.
        with conn.transaction():
            return action(_exchange_time(conn))
    except (talent.TalentError, challenges.ChallengeError, firms.FirmError) as refused:
        raise _refuse(refused) from None
    except (DeadlockDetected, UniqueViolation, CheckViolation):
        raise HTTPException(status.HTTP_409_CONFLICT, "Somebody else changed this at the same moment. Please try again.") from None


# ---------------------------------------------------------------------------
# A player
# ---------------------------------------------------------------------------

def _page(conn: Connection, player: dict) -> dict:
    now = _exchange_time(conn)
    view = talent.own_view(conn, player["id"], now)
    view["invitations"] = firms.invitations_for_player(conn, player["id"])
    view["challenges"] = challenges.player_list(conn, player["id"], now)
    return _wire(view)


@app.get("/api/talent")
def talent_page(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    return _page(conn, player)


class ShareRequest(Request):
    on: bool


class SectionsRequest(Request):
    sections: list[str] = Field(max_length=len(talent.SECTIONS))


class BoardRequest(Request):
    on: bool
    headline: str = Field(default="", max_length=140)


class InvitationAnswer(Request):
    accept: bool
    contact: str = Field(default="", max_length=300)


@app.post("/api/talent/share")
def talent_share(body: ShareRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: talent.share(conn, player["id"], body.on, now))
    return _page(conn, player)


@app.post("/api/talent/new-link")
def talent_new_link(player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: talent.new_link(conn, player["id"], now), attempts=5)
    return _page(conn, player)


@app.post("/api/talent/sections")
def talent_sections(body: SectionsRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: talent.choose_sections(conn, player["id"], body.sections, now))
    return _page(conn, player)


@app.post("/api/talent/board")
def talent_board(body: BoardRequest, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: talent.set_board(conn, player["id"], body.on, body.headline, now))
    return _page(conn, player)


@app.post("/api/talent/invitations/{invitation_id}")
def talent_answer(body: InvitationAnswer, invitation_id: int = FastPath(ge=1, le=9_000_000_000_000_000_000),
                  player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: firms.answer(conn, player["id"], invitation_id, body.accept, body.contact, now))
    return _page(conn, player)


@app.post("/api/talent/firms/{firm_id}/block")
def talent_block(firm_id: UUID, player: dict = Depends(current_player), conn: Connection = Depends(get_connection)):
    if not conn.execute("SELECT 1 FROM talent_firms WHERE id = %s", (firm_id,)).fetchone():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no such firm.")
    _act(conn, str(player["id"]), lambda now: firms.block(conn, player["id"], firm_id, now))
    return _page(conn, player)


# Challenges ------------------------------------------------------------------

class JoinRequest(Request):
    seen_by_sponsor: bool = False


class SponsorRequest(Request):
    on: bool


class AnswerRequest(Request):
    amount_naira: int | None = Field(default=None, ge=-10_000_000_000_000, le=10_000_000_000_000, strict=True)
    ticker: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    reasons: str = Field(default="", max_length=1000)


class PaperTradeRequest(Request):
    ticker: str = Field(pattern="^[A-Z]{3}$")
    side: str = Field(pattern="^(buy|sell)$")
    quantity: int = Field(ge=1, le=1_000_000_000_000, strict=True)


def _cid():
    return FastPath(ge=1, le=9_000_000_000_000_000_000)


@app.post("/api/challenges/{challenge_id}/join")
def challenge_join(body: JoinRequest, challenge_id: int = _cid(), player: dict = Depends(current_player),
                   conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: challenges.join(conn, challenge_id, player["id"], body.seen_by_sponsor, now))
    return _page(conn, player)


@app.post("/api/challenges/{challenge_id}/sponsor")
def challenge_sponsor(body: SponsorRequest, challenge_id: int = _cid(), player: dict = Depends(current_player),
                      conn: Connection = Depends(get_connection)):
    _act(conn, str(player["id"]), lambda now: challenges.let_sponsor_see(conn, challenge_id, player["id"], body.on))
    return _page(conn, player)


@app.post("/api/challenges/{challenge_id}/answer")
def challenge_answer(body: AnswerRequest, challenge_id: int = _cid(), player: dict = Depends(current_player),
                     conn: Connection = Depends(get_connection)):
    amount = naira(body.amount_naira) if body.amount_naira is not None else None
    _act(conn, str(player["id"]), lambda now: challenges.answer(conn, challenge_id, player["id"], now, amount=amount, ticker=body.ticker,
                                                               reasons=body.reasons))
    return _page(conn, player)


@app.post("/api/challenges/{challenge_id}/trade")
def challenge_trade(body: PaperTradeRequest, challenge_id: int = _cid(), player: dict = Depends(current_player),
                    conn: Connection = Depends(get_connection)):
    done = _act(conn, str(player["id"]), lambda now: challenges.paper_trade(conn, challenge_id, player["id"], ticker=body.ticker,
                                                                           side=body.side, quantity=body.quantity, now=now), attempts=60)
    return {**_page(conn, player), "dealt": _wire(done)}


# ---------------------------------------------------------------------------
# Anybody: a shared record
# ---------------------------------------------------------------------------

@app.get("/api/talent/shared/{slug}")
def shared_record(request: HttpRequest, slug: str = FastPath(pattern="^[A-Za-z0-9_-]{20,40}$"), conn: Connection = Depends(get_connection)):
    limits.allow("talent-shared", limits.visitor(request), attempts=60, per_seconds=60)
    view = talent.public_view(conn, slug)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no shared record at this address. The player may have stopped sharing it.")
    return _wire(view)


# ---------------------------------------------------------------------------
# A firm
# ---------------------------------------------------------------------------

class FirmSignUp(Request):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    contact_name: str = Field(min_length=2, max_length=80)
    website: str = Field(default="", max_length=200)
    tagline: str = Field(default="", max_length=140)
    colour: str = Field(default="#2f6f9f", pattern="^#[0-9a-f]{6}$")


class FirmCode(Request):
    code: str = Field(pattern="^[0-9]{6}$")


class FirmLogin(Request):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class InviteRequest(Request):
    player_id: UUID
    message: str = Field(min_length=10, max_length=800)
    challenge_id: int | None = Field(default=None, ge=1, le=9_000_000_000_000_000_000)


class ChallengeRequest(Request):
    kind: str = Field(pattern="^(paper|valuation|weak_bank|forecast|live)$")
    title: str = Field(min_length=4, max_length=90)
    brief: str = Field(default="", max_length=1200)
    ticker: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    starting_cash_naira: int = Field(default=5_000_000_000, ge=1_000_000, le=100_000_000_000, strict=True)
    opens_at: datetime
    locks_at: datetime | None = None
    ends_at: datetime
    top_shown: int = Field(default=10, ge=1, le=50, strict=True)


def _firm_public(row: dict) -> dict:
    return _wire(firms.public(row))


def current_firm(session: str | None = Cookie(default=None, alias=security.FIRM_COOKIE), conn: Connection = Depends(get_connection)) -> dict:
    named = security.read_firm_token(session) if session else None
    row = conn.execute("SELECT * FROM talent_firms WHERE id = %s AND session_version = %s", named).fetchone() if named else None
    if row is None or row["status"] == "suspended":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in as a firm.")
    return row


def _approved_firm(firm: dict = Depends(current_firm)) -> dict:
    if firm["status"] != "approved":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your firm is waiting for an administrator's approval.")
    return firm


def _firm_session(response: Response, row: dict) -> None:
    settings = get_settings()
    response.set_cookie(key=security.FIRM_COOKIE, value=security.create_firm_token(str(row["id"]), row["session_version"]),
                        max_age=settings.session_days * 24 * 60 * 60, httponly=True, secure=settings.cookie_secure, samesite="lax")


@app.post("/api/firms/signup", status_code=status.HTTP_201_CREATED)
def firm_signup(body: FirmSignUp, request: HttpRequest, response: Response):
    limits.allow("firm-signup", limits.visitor(request), attempts=5, per_seconds=3600)
    try:
        key = emails.email_key(body.email)
    except emails.UnusableEmail as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    with limits.password_work:
        hashed = security.hash_password(body.password)
    with connection() as conn:
        try:
            row = firms.sign_up(conn, name=body.name, email=str(body.email).lower(), email_key=key, password_hash=hashed,
                                contact_name=body.contact_name, website=body.website, tagline=body.tagline, colour=body.colour,
                                now=_exchange_time(conn))
        except firms.FirmError as refused:
            raise _refuse(refused) from None
        except UniqueViolation:
            raise HTTPException(status.HTTP_409_CONFLICT, "A firm with that name or email has already signed up.") from None
        shown = _send_code(conn, row)
    _firm_session(response, row)
    return {**_firm_public(row), "code_shown_on_screen": shown}


def _send_code(conn: Connection, row: dict) -> str | None:
    """A code is sent to the firm's address; it proves the address before an administrator will approve the firm. With no
    email service connected (on a home computer), it is shown on the screen instead."""
    code = emails.new_code()
    firms.set_code(conn, row["id"], emails.hash_code(row["email_key"], code), emails.CODE_MINUTES)
    try:
        emails.send(row["email"], "Your Wall Street: Beyond the Market firm code",
                    f"Your code is {code}\n\nType it into the firms' page to confirm this address. It works for {emails.CODE_MINUTES} minutes.\n\n"
                    "If you did not sign a firm up, ignore this email.")
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "We could not send the email. Please ask for a new code in a moment.") from None
    return code if emails.shown_on_screen() else None


@app.post("/api/firms/confirm")
def firm_confirm(body: FirmCode, firm: dict = Depends(current_firm), conn: Connection = Depends(get_connection)):
    limits.allow("firm-confirm", str(firm["id"]), attempts=10, per_seconds=900)
    try:
        with conn.transaction():
            right = firms.confirm(conn, firm["id"], lambda stored: emails.code_matches(firm["email_key"], body.code, stored), _exchange_time(conn),
                                  emails.MAX_WRONG_GUESSES)
    except firms.FirmError as refused:
        raise _refuse(refused) from None
    if not right:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is not right.")
    return _firm_public(conn.execute("SELECT * FROM talent_firms WHERE id = %s", (firm["id"],)).fetchone())


@app.post("/api/firms/new-code")
def firm_new_code(firm: dict = Depends(current_firm), conn: Connection = Depends(get_connection)):
    limits.allow("firm-new-code", str(firm["id"]), attempts=3, per_seconds=900)
    if firm["email_confirmed_at"] is not None:
        return {**_firm_public(firm), "code_shown_on_screen": None}
    return {**_firm_public(firm), "code_shown_on_screen": _send_code(conn, firm)}


@app.post("/api/firms/login")
def firm_login(body: FirmLogin, request: HttpRequest, response: Response):
    limits.allow("firm-login", limits.visitor(request), attempts=20, per_seconds=300)
    limits.allow("firm-login-email", str(body.email).lower(), attempts=8, per_seconds=300)
    with connection() as conn:
        try:
            key = emails.email_key(body.email)
        except emails.UnusableEmail:
            key = ""
        row = conn.execute("SELECT * FROM talent_firms WHERE email_key = %s", (key,)).fetchone()
    with limits.password_work:
        correct = security.verify_password(body.password, row["password_hash"] if row else None)
    if not correct or row["status"] == "suspended":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    _firm_session(response, row)
    return _firm_public(row)


@app.post("/api/firms/logout", status_code=status.HTTP_204_NO_CONTENT)
def firm_logout(response: Response, session: str | None = Cookie(default=None, alias=security.FIRM_COOKIE),
                conn: Connection = Depends(get_connection)) -> None:
    named = security.read_firm_token(session) if session else None
    if named:
        conn.execute("UPDATE talent_firms SET session_version = session_version + 1 WHERE id = %s AND session_version = %s", named)
    response.delete_cookie(security.FIRM_COOKIE)


@app.get("/api/firms/me")
def firm_me(firm: dict = Depends(current_firm)):
    return _firm_public(firm)


@app.get("/api/firms/board")
def firm_board(build: str | None = Query(default=None, pattern="^[a-z_]{3,30}$"), least_level: int = Query(default=0, ge=0, le=100),
               badge: str | None = Query(default=None, pattern="^[a-z0-9_:-]{2,60}$"),
               sort: str = Query(default="versus_index", pattern="^(versus_index|risk|calls|badges|wins)$"),
               firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    limits.allow("firm-board", str(firm["id"]), attempts=60, per_seconds=60)
    return _wire({"players": firms.board(conn, firm["id"], build=build, least_level=least_level, badge=badge, sort=sort)})


@app.get("/api/firms/records/{player_id}")
def firm_record(player_id: UUID, firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    limits.allow("firm-record", str(firm["id"]), attempts=60, per_seconds=60)
    try:
        return _wire(firms.record_for_firm(conn, firm["id"], player_id))
    except firms.FirmError as refused:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(refused)) from None


@app.get("/api/firms/invitations")
def firm_invitations(firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    return _wire({"invitations": firms.invitations_for_firm(conn, firm["id"])})


@app.post("/api/firms/invitations", status_code=status.HTTP_201_CREATED)
def firm_invite(body: InviteRequest, firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    _act(conn, f"firm:{firm['id']}", lambda now: firms.invite(conn, firm["id"], body.player_id, body.message, now, body.challenge_id))
    return _wire({"invitations": firms.invitations_for_firm(conn, firm["id"])})


@app.get("/api/firms/challenges")
def firm_challenges(firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    return _wire({"challenges": challenges.firm_list(conn, firm["id"], _exchange_time(conn)), "kinds": challenges.KINDS,
                  "kind_words": challenges.KIND_WORDS})


@app.post("/api/firms/challenges", status_code=status.HTTP_201_CREATED)
def firm_new_challenge(body: ChallengeRequest, firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    for moment in (body.opens_at, body.locks_at, body.ends_at):
        if moment is not None and moment.tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Times must say their time zone.")
    _act(conn, f"firm:{firm['id']}", lambda now: challenges.create(
        conn, firm["id"], kind=body.kind, title=body.title, brief=body.brief, opens_at=body.opens_at, locks_at=body.locks_at,
        ends_at=body.ends_at, now=now, ticker=body.ticker, starting_cash=naira(body.starting_cash_naira), top_shown=body.top_shown), attempts=10)
    return firm_challenges(firm, conn)


@app.post("/api/firms/challenges/{challenge_id}/cancel")
def firm_cancel_challenge(challenge_id: int = _cid(), firm: dict = Depends(_approved_firm), conn: Connection = Depends(get_connection)):
    _act(conn, f"firm:{firm['id']}", lambda now: challenges.cancel(conn, firm["id"], challenge_id, now))
    return firm_challenges(firm, conn)
