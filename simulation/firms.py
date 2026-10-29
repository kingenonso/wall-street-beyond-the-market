"""Firms on Proven Talent (the talent and funds stage, Part 1): the talent board and invitations.

A firm is a real organisation that wants to find good players and sponsor challenges. It has its own login and no player
powers of any kind: it cannot trade, own, vote, message players in the game or touch the world. An administrator approves
each firm before it can do anything.

The board shows only players who chose to be on it, whose record is long enough to mean something, and who are not held
back by the honesty checks. A firm may also invite the best finishers of its own challenges who agreed to be seen by it.
An invitation is a short message. A player answers it or not; their contact details reach the firm only if they accept and
type them in themselves. A player can block a firm, and then it can never invite them again.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, talent

INVITES_PER_DAY = 30


class FirmError(Exception):
    """A request about a firm the rules do not allow. The words are for the firm or the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def public(firm: dict) -> dict:
    return {k: firm[k] for k in ("id", "name", "contact_name", "website", "tagline", "colour", "status", "created_at")}


def sign_up(conn: Connection, *, name: str, email: str, email_key: str, password_hash: str, contact_name: str, website: str,
            tagline: str, colour: str, now: datetime) -> dict:
    name, contact_name = " ".join(name.split()), " ".join(contact_name.split())
    if not 2 <= len(name) <= 80 or not 2 <= len(contact_name) <= 80:
        raise FirmError("Give the firm's name and a contact's name (2 to 80 characters each).")
    if website and not re.match(r"^https?://[^\s]{3,190}$", website):
        raise FirmError("A website must start with http:// or https://.")
    if not re.match(r"^#[0-9a-f]{6}$", colour or ""):
        colour = "#2f6f9f"
    if _one(conn, "SELECT 1 AS x FROM talent_firms WHERE name_key = %s OR email_key = %s", (name_key(name), email_key)):
        raise FirmError("A firm with that name or email has already signed up.")
    return _one(conn, "INSERT INTO talent_firms (name, name_key, email, email_key, password_hash, contact_name, website, tagline, colour,"
                      " created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (name, name_key(name), email, email_key, password_hash, contact_name, website, " ".join(tagline.split())[:140], colour, now))


def approve(conn: Connection, firm_id, now: datetime) -> None:
    conn.execute("UPDATE talent_firms SET status = 'approved', approved_at = coalesce(approved_at, %s) WHERE id = %s", (now, firm_id))


def suspend(conn: Connection, firm_id) -> None:
    """A suspended firm is logged out everywhere and its open challenges are called off."""
    conn.execute("UPDATE talent_firms SET status = 'suspended', session_version = session_version + 1 WHERE id = %s", (firm_id,))
    conn.execute("UPDATE talent_challenges SET status = 'cancelled' WHERE firm_id = %s AND status = 'open'", (firm_id,))


def _approved(conn: Connection, firm_id) -> dict:
    firm = _one(conn, "SELECT * FROM talent_firms WHERE id = %s", (firm_id,))
    if firm is None or firm["status"] != "approved":
        raise FirmError("This firm has not been approved yet. An administrator looks at every firm before it can use the board.")
    return firm


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------

def _on_board(conn: Connection) -> list[dict]:
    rows = _rows(conn, "SELECT s.player_id, s.headline, r.summary, r.worked_at, p.display_name, p.profile_icon FROM talent_settings s"
                       " JOIN talent_records r ON r.player_id = s.player_id JOIN players p ON p.id = s.player_id WHERE s.on_board"
                       " AND NOT EXISTS (SELECT 1 FROM talent_flags f WHERE f.player_id = s.player_id AND f.kind = 'linked'"
                       "                 AND f.cleared_at IS NULL)")
    return [r for r in rows if (r["summary"].get("days") or 0) >= talent.BOARD_MIN_DAYS]


def board(conn: Connection, firm_id, *, build: str | None = None, least_level: int = 0, badge: str | None = None,
          sort: str = "versus_index") -> list[dict]:
    _approved(conn, firm_id)
    blocked = {r["player_id"] for r in _rows(conn, "SELECT player_id FROM talent_firm_blocks WHERE firm_id = %s", (firm_id,))}
    out = []
    for r in _on_board(conn):
        if r["player_id"] in blocked:
            continue
        s = r["summary"]
        builds = s.get("builds") or []
        if build and not any(b["build"] == build and b["level"] >= least_level for b in builds):
            continue
        if not build and least_level and not any(b["level"] >= least_level for b in builds):
            continue
        if badge and badge not in (s.get("badges") or []):
            continue
        out.append({"player_id": r["player_id"], "name": r["display_name"], "icon": r["profile_icon"], "headline": r["headline"],
                    "builds": [{**b, "name": careers.BUILDS.get(b["build"], {}).get("name", b["build"])} for b in builds],
                    "days": s.get("days"), "total_bps": s.get("total_bps"), "versus_index_bps": s.get("versus_index_bps"),
                    "worst_fall_bps": s.get("worst_fall_bps"), "risk_ratio": s.get("risk_ratio"), "calls_right_bps": s.get("calls_right_bps"),
                    "proved": s.get("proved"), "wins": s.get("wins"), "badges": len(s.get("badges") or []), "worked_at": r["worked_at"]})
    keys = {"versus_index": lambda x: x["versus_index_bps"] if x["versus_index_bps"] is not None else -10**9,
            "risk": lambda x: x["risk_ratio"] if x["risk_ratio"] is not None else -10**9,
            "calls": lambda x: x["calls_right_bps"] if x["calls_right_bps"] is not None else -1,
            "badges": lambda x: x["badges"], "wins": lambda x: x["wins"] or 0}
    out.sort(key=keys.get(sort, keys["versus_index"]), reverse=True)
    return out[:100]


def may_see(conn: Connection, firm_id, player_id) -> bool:
    """A firm may see a record if the player is on the board, or finished among the best of the firm's own challenge and
    agreed to be seen by it."""
    if _one(conn, "SELECT 1 AS x FROM talent_firm_blocks WHERE firm_id = %s AND player_id = %s", (firm_id, player_id)):
        return False
    if any(r["player_id"] == player_id for r in _on_board(conn)):
        return True
    return bool(_one(conn, "SELECT 1 AS x FROM challenge_entries e JOIN talent_challenges c ON c.id = e.challenge_id WHERE c.firm_id = %s"
                           " AND e.player_id = %s AND c.status = 'scored' AND e.seen_by_sponsor AND e.place IS NOT NULL AND e.place <= c.top_shown",
                     (firm_id, player_id)))


def record_for_firm(conn: Connection, firm_id, player_id) -> dict:
    _approved(conn, firm_id)
    if not may_see(conn, firm_id, player_id):
        raise FirmError("That record is not open to this firm.")
    s = talent.settings(conn, player_id)
    view = talent._shown(conn, player_id, s["show"], s["headline"])
    view["invitations"] = _rows(conn, "SELECT id, status, sent_at, answered_at, contact FROM talent_invitations WHERE firm_id = %s"
                                      " AND player_id = %s ORDER BY id DESC", (firm_id, player_id))
    return view


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def invite(conn: Connection, firm_id, player_id, message: str, now: datetime, challenge_id: int | None = None) -> dict:
    _approved(conn, firm_id)
    conn.execute("SELECT 1 FROM talent_firms WHERE id = %s FOR UPDATE", (firm_id,))
    message = message.strip()
    if not 10 <= len(message) <= 800:
        raise FirmError("An invitation needs 10 to 800 characters.")
    if not may_see(conn, firm_id, player_id):
        raise FirmError("Only players on the board, or the best finishers of your own challenges who agreed to be seen, can be invited.")
    sent = _one(conn, "SELECT count(*) AS n FROM talent_invitations WHERE firm_id = %s AND sent_at > %s", (firm_id, now - timedelta(days=1)))["n"]
    if sent >= INVITES_PER_DAY:
        raise FirmError(f"A firm can send at most {INVITES_PER_DAY} invitations a day.")
    if _one(conn, "SELECT 1 AS x FROM talent_invitations WHERE firm_id = %s AND player_id = %s AND status = 'sent'", (firm_id, player_id)):
        raise FirmError("This player has not answered your last invitation yet.")
    if _one(conn, "SELECT 1 AS x FROM talent_invitations WHERE firm_id = %s AND player_id = %s AND status = 'declined' AND answered_at > %s",
            (firm_id, player_id, now - timedelta(days=30))):
        raise FirmError("This player declined an invitation from you in the last 30 days.")
    if challenge_id is not None and not _one(conn, "SELECT 1 AS x FROM talent_challenges WHERE id = %s AND firm_id = %s", (challenge_id, firm_id)):
        challenge_id = None
    row = _one(conn, "INSERT INTO talent_invitations (firm_id, player_id, challenge_id, message, sent_at) VALUES (%s, %s, %s, %s, %s) RETURNING *",
               (firm_id, player_id, challenge_id, message, now))
    return row


def answer(conn: Connection, player_id, invitation_id: int, accept: bool, contact: str, now: datetime) -> dict:
    inv = _one(conn, "SELECT * FROM talent_invitations WHERE id = %s AND player_id = %s FOR UPDATE", (invitation_id, player_id))
    if inv is None:
        raise FirmError("There is no such invitation.")
    if inv["status"] != "sent":
        raise FirmError("You have already answered this invitation.")
    contact = " ".join((contact or "").split())[:300]
    if accept and len(contact) < 5:
        raise FirmError("Type how the firm can reach you (an email address, for example). It is sent only to this firm.")
    conn.execute("UPDATE talent_invitations SET status = %s, contact = %s, answered_at = %s WHERE id = %s",
                 ("accepted" if accept else "declined", contact if accept else None, now, invitation_id))
    return _one(conn, "SELECT * FROM talent_invitations WHERE id = %s", (invitation_id,))


def block(conn: Connection, player_id, firm_id, now: datetime) -> None:
    conn.execute("INSERT INTO talent_firm_blocks (player_id, firm_id, at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (player_id, firm_id, now))
    conn.execute("UPDATE talent_invitations SET status = 'declined', answered_at = %s WHERE firm_id = %s AND player_id = %s AND status = 'sent'",
                 (now, firm_id, player_id))


def invitations_for_player(conn: Connection, player_id) -> list[dict]:
    return _rows(conn, "SELECT i.id, i.message, i.status, i.sent_at, i.answered_at, i.contact, f.id AS firm_id, f.name AS firm, f.website,"
                       " f.tagline, f.colour, c.title AS challenge FROM talent_invitations i JOIN talent_firms f ON f.id = i.firm_id"
                       " LEFT JOIN talent_challenges c ON c.id = i.challenge_id WHERE i.player_id = %s"
                       " AND NOT EXISTS (SELECT 1 FROM talent_firm_blocks b WHERE b.player_id = i.player_id AND b.firm_id = i.firm_id)"
                       " ORDER BY i.id DESC LIMIT 30", (player_id,))


def invitations_for_firm(conn: Connection, firm_id) -> list[dict]:
    return _rows(conn, "SELECT i.id, i.status, i.sent_at, i.answered_at, i.contact, i.message, p.display_name AS name, i.player_id"
                       " FROM talent_invitations i JOIN players p ON p.id = i.player_id WHERE i.firm_id = %s ORDER BY i.id DESC LIMIT 100",
                 (firm_id,))
