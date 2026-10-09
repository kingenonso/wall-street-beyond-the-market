"""Messages between players (quick fixes, October 2026).

A player writes to another by their display name. Either may block the other. A blocked player is
never told: what they write is taken as usual and simply never reaches the player who blocked them. A player can report a message sent to them; three
different players reporting the same sender within a week leave that sender able only to answer
people who wrote to them first, for that week.

Limits keep anyone from flooding others: so many messages an hour, so many new people a day, and no
more than three messages in a row to someone who has not answered yet.

Nothing here touches money. A player sees only messages they sent or received, and never who has
blocked or reported them.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import world_data as data


class MessageError(Exception):
    """A message or a block that cannot be done. The text is shown to the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _name_key(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name)
    return "".join(ch for ch in stripped if ch.isalnum()).lower()


def _clean(text: str) -> str:
    """Control characters out (new lines and tabs stay), spaces at the ends trimmed."""
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C").strip()


def find_player(conn: Connection, name: str) -> dict | None:
    key = _name_key(name or "")
    return _one(conn, "SELECT id, display_name FROM players WHERE display_name_key = %s", (key,)) if key else None


def _other(conn: Connection, me, name: str) -> dict:
    other = find_player(conn, name)
    if other is None:
        raise MessageError("There is no player of that name.")
    if other["id"] == me:
        raise MessageError("You cannot write to yourself.")
    return other


def _limited_by_reports(conn: Connection, me, now: datetime) -> bool:
    found = _one(conn, "SELECT count(DISTINCT r.reporter_id) AS n FROM message_reports r"
                       " JOIN player_messages m ON m.id = r.message_id WHERE m.sender_id = %s AND r.at > %s",
                 (me, now - timedelta(days=data.REPORT_WINDOW_DAYS)))
    return found["n"] >= data.REPORTS_TO_BE_LIMITED


def send(conn: Connection, me, to_name: str, body: str, now: datetime) -> dict:
    """Send one message. Returns it as the sender sees it."""
    text = _clean(body or "")
    if not text:
        raise MessageError("Write something first.")
    if len(text) > data.MESSAGE_MAX_CHARS:
        raise MessageError(f"A message may be at most {data.MESSAGE_MAX_CHARS} characters.")
    with conn.transaction():
        # One send at a time per player, so two at once cannot both slip under a limit.
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (me,))
        other = _other(conn, me, to_name)
        if _one(conn, "SELECT 1 FROM player_blocks WHERE blocker_id = %s AND blocked_id = %s", (me, other["id"])):
            raise MessageError("You have blocked this player. Unblock them first to write to them.")
        # A block by the other player is never revealed: the message is taken as usual, and simply never
        # reaches them. It counts towards every limit like any other.
        silenced = bool(_one(conn, "SELECT 1 FROM player_blocks WHERE blocker_id = %s AND blocked_id = %s", (other["id"], me)))
        sent_hour = _one(conn, "SELECT count(*) AS n FROM player_messages WHERE sender_id = %s AND sent_at > %s",
                         (me, now - timedelta(hours=1)))["n"]
        if sent_hour >= data.MESSAGES_PER_HOUR:
            raise MessageError(f"You have sent {data.MESSAGES_PER_HOUR} messages in the last hour. Please wait a little.")
        they_wrote = _one(conn, "SELECT max(id) AS last FROM player_messages WHERE sender_id = %s AND receiver_id = %s",
                          (other["id"], me))["last"]
        ever = _one(conn, "SELECT 1 FROM player_messages WHERE (sender_id = %s AND receiver_id = %s)"
                          " OR (sender_id = %s AND receiver_id = %s) LIMIT 1", (me, other["id"], other["id"], me))
        if they_wrote is None and _limited_by_reports(conn, me, now):
            raise MessageError("Several players have reported your messages this week. Until it passes you may only answer"
                               " players who wrote to you first.")
        if ever is None:
            started = _one(conn, """
                SELECT count(*) AS n FROM (
                    SELECT receiver_id, min(sent_at) AS first FROM player_messages WHERE sender_id = %s GROUP BY receiver_id
                ) f
                WHERE f.first > %s AND NOT EXISTS (
                    SELECT 1 FROM player_messages m WHERE m.sender_id = f.receiver_id AND m.receiver_id = %s AND m.sent_at <= f.first)
            """, (me, now - timedelta(days=1), me))["n"]
            if started >= data.NEW_PEOPLE_PER_DAY:
                raise MessageError(f"You have written to {data.NEW_PEOPLE_PER_DAY} new players today. Please try again tomorrow.")
        in_a_row = _one(conn, "SELECT count(*) AS n FROM player_messages WHERE sender_id = %s AND receiver_id = %s AND id > %s",
                        (me, other["id"], they_wrote or 0))["n"]
        if in_a_row >= data.UNANSWERED_IN_A_ROW:
            raise MessageError(f"{other['display_name']} has not answered your last {data.UNANSWERED_IN_A_ROW} messages."
                               " Please wait for an answer.")
        row = _one(conn, "INSERT INTO player_messages (sender_id, receiver_id, body, sent_at, hidden_for_receiver)"
                         " VALUES (%s, %s, %s, %s, %s) RETURNING id, body, sent_at", (me, other["id"], text, now, silenced))
        return {"id": row["id"], "mine": True, "body": row["body"], "sent_at": row["sent_at"], "read": False, "reported": False}


def unread_count(conn: Connection, me) -> int:
    return _one(conn, "SELECT count(*) AS n FROM player_messages m WHERE receiver_id = %s AND read_at IS NULL"
                      " AND NOT hidden_for_receiver"
                      " AND NOT EXISTS (SELECT 1 FROM player_blocks b WHERE b.blocker_id = %s AND b.blocked_id = m.sender_id)",
                (me, me))["n"]


def conversations(conn: Connection, me) -> dict:
    """Everyone the player has written to or heard from, newest first, and the players they have blocked."""
    rows = _rows(conn, """
        WITH mine AS (
            SELECT m.*, CASE WHEN m.sender_id = %(me)s THEN m.receiver_id ELSE m.sender_id END AS other_id
            FROM player_messages m
            WHERE (m.sender_id = %(me)s AND NOT m.hidden_for_sender) OR (m.receiver_id = %(me)s AND NOT m.hidden_for_receiver)
        ), latest AS (
            SELECT DISTINCT ON (other_id) other_id, id, body, sent_at, sender_id FROM mine ORDER BY other_id, id DESC
        )
        SELECT p.display_name AS name, l.body, l.sent_at, l.sender_id = %(me)s AS mine,
               (SELECT count(*) FROM mine u WHERE u.other_id = l.other_id AND u.receiver_id = %(me)s AND u.read_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM player_blocks b WHERE b.blocker_id = %(me)s AND b.blocked_id = u.other_id)) AS unread,
               EXISTS (SELECT 1 FROM player_blocks b WHERE b.blocker_id = %(me)s AND b.blocked_id = l.other_id) AS blocked
        FROM latest l JOIN players p ON p.id = l.other_id
        ORDER BY l.id DESC LIMIT 100
    """, {"me": me})
    blocked = [r["display_name"] for r in _rows(conn, "SELECT p.display_name FROM player_blocks b JOIN players p ON p.id = b.blocked_id"
                                                      " WHERE b.blocker_id = %s ORDER BY b.at DESC", (me,))]
    return {"conversations": [{**r, "preview": r.pop("body")[:120]} for r in rows], "blocked": blocked,
            "limits": {"max_chars": data.MESSAGE_MAX_CHARS, "per_hour": data.MESSAGES_PER_HOUR,
                       "new_people_per_day": data.NEW_PEOPLE_PER_DAY, "unanswered_in_a_row": data.UNANSWERED_IN_A_ROW}}


def thread(conn: Connection, me, name: str, now: datetime) -> dict:
    """The messages between the player and one other, oldest first (the last 200). Opening it marks
    the messages sent to the player as read."""
    other = _other(conn, me, name)
    with conn.transaction():
        rows = _rows(conn, """
            SELECT * FROM (
                SELECT m.id, m.sender_id = %(me)s AS mine, m.body, m.sent_at, m.read_at IS NOT NULL AS read,
                       EXISTS (SELECT 1 FROM message_reports r WHERE r.message_id = m.id AND r.reporter_id = %(me)s) AS reported
                FROM player_messages m
                WHERE (m.sender_id = %(me)s AND m.receiver_id = %(o)s AND NOT m.hidden_for_sender)
                   OR (m.sender_id = %(o)s AND m.receiver_id = %(me)s AND NOT m.hidden_for_receiver)
                ORDER BY m.id DESC LIMIT 200
            ) t ORDER BY id
        """, {"me": me, "o": other["id"]})
        # Only what was just shown is marked read: a message that arrives a moment later stays unread.
        shown = [m["id"] for m in rows if not m["mine"]]
        if shown:
            conn.execute("UPDATE player_messages SET read_at = %s WHERE sender_id = %s AND receiver_id = %s AND read_at IS NULL"
                         " AND id = ANY(%s)", (now, other["id"], me, shown))
    i_blocked = bool(_one(conn, "SELECT 1 FROM player_blocks WHERE blocker_id = %s AND blocked_id = %s", (me, other["id"])))
    # Whether the other player has blocked this one is never shown.
    return {"name": other["display_name"], "messages": rows, "blocked": i_blocked, "can_write": not i_blocked}


def block(conn: Connection, me, name: str, now: datetime) -> None:
    other = _other(conn, me, name)
    conn.execute("INSERT INTO player_blocks (blocker_id, blocked_id, at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                 (me, other["id"], now))


def unblock(conn: Connection, me, name: str) -> None:
    other = _other(conn, me, name)
    conn.execute("DELETE FROM player_blocks WHERE blocker_id = %s AND blocked_id = %s", (me, other["id"]))


def report(conn: Connection, me, message_id: int, reason: str | None, now: datetime, *, and_block: bool = False) -> None:
    """Report a message sent to the player. Only its receiver may report it, and only once."""
    with conn.transaction():
        message = _one(conn, "SELECT sender_id, receiver_id FROM player_messages WHERE id = %s", (message_id,))
        if message is None or message["receiver_id"] != me:
            raise MessageError("There is no such message sent to you.")
        words = _clean(reason or "")[:data.MESSAGE_REPORT_MAX_CHARS] or None
        done = conn.execute("INSERT INTO message_reports (message_id, reporter_id, reason, at) VALUES (%s, %s, %s, %s)"
                            " ON CONFLICT DO NOTHING", (message_id, me, words, now)).rowcount
        if not done:
            raise MessageError("You have already reported this message.")
        if and_block:
            conn.execute("INSERT INTO player_blocks (blocker_id, blocked_id, at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (me, message["sender_id"], now))


def hide_conversation(conn: Connection, me, name: str, now: datetime) -> None:
    """Clear a conversation from the player's own list. The other player keeps their copy."""
    with conn.transaction():
        other = _other(conn, me, name)
        conn.execute("UPDATE player_messages SET hidden_for_sender = true WHERE sender_id = %s AND receiver_id = %s", (me, other["id"]))
        conn.execute("UPDATE player_messages SET hidden_for_receiver = true WHERE sender_id = %s AND receiver_id = %s",
                     (other["id"], me))
