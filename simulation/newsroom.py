"""Stage 10, Part 1: the newsroom (Journalist 1, 2, 3, 5, 6; G13; A10; the path of a story).

A Financial Journalist writes a story from confirmed facts (newsroom_facts.py): they choose the facts, check each
one against the record, may ask a company or the head of an empire for comment, may add a line of their own view
in words, and publish. The story appears on the wire under their name, for the media house they work for or as an
independent.

What follows from it:
  * readers, from how big the news is, how early it is, the paper's audience and the author's following;
  * a scoop, if it is first with a confirmed fact before the wire: a bonus and reputation;
  * pay that rises with reach; an independent is paid a fee by the paper that picks the story up;
  * a true, widely read story nudges how the computer-run investors value the companies it names, a little,
    fading over five trading days (at most 2%, one nudge per company per day);
  * the author and their empire may not trade those companies from the first draft until two trading days after
    publication;
  * an author who sits in an empire must declare the empire's interest in any company they write about. Hiding it
    is an offence other players can expose; the verdict is all that is ever shown, never the holding.
  * if a fact it used is later changed in the record (a company restates its accounts), the story must be corrected
    within a day. A correction costs reputation; a late one costs more, and readers.
Honest error is never a crime here: only facts on the record can be printed, so a story cannot be made up.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, clock, exchange, ledger, newsroom_facts, ripple, standing
from simulation import world_data as data
from simulation.money import BPS, naira


class NewsroomError(Exception):
    """Something the newsroom's rules do not allow. The words are for the player."""


ANGLES = {
    "straight": "Just the facts",
    "what_it_means": "What it means",
    "who_wins": "Who wins, who loses",
}
PRESS = "press"                        # the outlet code for players' stories on the wire
FIGURE = re.compile(r"\d")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _money(kobo: int) -> str:
    return newsroom_facts.money(kobo)


# ---------------------------------------------------------------------------
# Who is writing
# ---------------------------------------------------------------------------

def _journalist(conn: Connection, player_id) -> dict:
    player = _one(conn, "SELECT id, display_name, build, reputation FROM players WHERE id = %s", (player_id,))
    if player is None or player["build"] != "journalist":
        raise NewsroomError("Only a Financial Journalist can write and publish stories.")
    conn.execute("INSERT INTO journalist_profiles (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
    return player


def profile(conn: Connection, player_id) -> dict:
    row = _one(conn, "SELECT * FROM journalist_profiles WHERE player_id = %s", (player_id,))
    if row is None:
        return {"following": 0, "readers": 0, "stories": 0, "scoops": 0, "corrections": 0, "credibility": 50}
    return {k: row[k] for k in ("following", "readers", "stories", "scoops", "corrections", "credibility")}


def _seat_empire(conn: Connection, player_id) -> dict | None:
    return _one(conn, "SELECT e.* FROM empire_seats s JOIN empires e ON e.id = s.empire_id WHERE s.player_id = %s AND e.status = 'active'",
                (player_id,)) or _one(conn, "SELECT * FROM empires WHERE head_player_id = %s AND status = 'active'", (player_id,))


def _outlet(conn: Connection, player_id) -> dict | None:
    """The media house the journalist works for, if any."""
    job = careers.current_job(conn, player_id)
    if not job:
        return None
    company = _one(conn, "SELECT * FROM companies WHERE id = %s", (job["company_id"],))
    return company if company and company["sector"] == "media" else None


def _audience(conn: Connection, outlet: dict | None, following: int) -> int:
    """How many people a story could reach: a media house's audience, or an independent's own following."""
    if outlet is None:
        return data.INDEPENDENT_AUDIENCE + following
    staff = _one(conn, "SELECT staff FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1", (outlet["id"],))
    return (staff["staff"] if staff else 1000) * data.AUDIENCE_PER_STAFF + following


def _now(conn: Connection, now: datetime) -> dict:
    return careers.world_now(conn, now)


def _session_close(day, extra_days: int) -> datetime:
    """The close (22:00 Lagos) of the trading day `extra_days` after `day`."""
    return datetime(day.year, day.month, day.day, clock.MARKET_CLOSE.hour, tzinfo=clock.LAGOS) + timedelta(days=extra_days)


# ---------------------------------------------------------------------------
# Trading around one's own story is not allowed
# ---------------------------------------------------------------------------

def check_trade(conn: Connection, account, company_id, now: datetime) -> None:
    """Raise if this account may not trade this company now, because of a story its owner (or its journalist) is writing
    or has just published."""
    if company_id is None or not _rows(conn, "SELECT to_regclass('story_blocks') IS NOT NULL AS ok")[0]["ok"]:
        return
    found = _one(conn, "SELECT b.until FROM story_blocks b WHERE b.account_id = %s AND b.company_id = %s AND b.since <= %s"
                       " AND (b.until IS NULL OR b.until > %s) LIMIT 1", (account, company_id, now, now))
    if found:
        when = "until the story is published or dropped" if found["until"] is None else \
            f"until {clock.to_lagos(found['until']):%d %B %H:%M} Lagos time"
        raise exchange.ExchangeError(
            f"No trading in this company {when}: a story about it is being written or has just been published by you or your empire's "
            "journalist. (A journalist and their empire may not trade around their own story.)")


def _block(conn: Connection, story: dict, tickers: list[str], now: datetime) -> None:
    accounts = [ledger.player_account_id(conn, story["author_id"])]
    if story["empire_id"]:
        empire = _one(conn, "SELECT account_id FROM empires WHERE id = %s", (story["empire_id"],))
        accounts.append(empire["account_id"])
    for ticker in tickers:
        company = _one(conn, "SELECT id FROM companies WHERE ticker = %s", (ticker,))
        if company is None:
            continue
        for account in accounts:
            conn.execute("INSERT INTO story_blocks (story_id, account_id, company_id, since) VALUES (%s, %s, %s, %s)"
                         " ON CONFLICT DO NOTHING", (story["id"], account, company["id"], now))


# ---------------------------------------------------------------------------
# Writing a story
# ---------------------------------------------------------------------------

def _draft(conn: Connection, player_id, *, lock: bool = False) -> dict | None:
    return _one(conn, "SELECT * FROM stories WHERE author_id = %s AND status = 'draft'" + (" FOR UPDATE" if lock else ""), (player_id,))


def start(conn: Connection, player_id, now: datetime) -> dict:
    """Open a new draft (one at a time)."""
    _journalist(conn, player_id)
    if _draft(conn, player_id):
        raise NewsroomError("You already have a story in hand. Publish it or drop it first.")
    empire = _seat_empire(conn, player_id)
    outlet = _outlet(conn, player_id)
    row = _one(conn, "INSERT INTO stories (author_id, empire_id, outlet_company, started_at) VALUES (%s, %s, %s, %s) RETURNING *",
               (player_id, empire["id"] if empire else None, outlet["id"] if outlet else None, now))
    return view(conn, player_id, now)


def add_fact(conn: Connection, player_id, fact_id: str, now: datetime) -> dict:
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("Start a story first.")
        card = newsroom_facts.find(conn, fact_id, now)
        if card is None:
            raise NewsroomError("That is not a confirmed fact on the record today.")
        chosen = list(story["facts"])
        if any(c["id"] == fact_id for c in chosen):
            return view(conn, player_id, now)
        if len(chosen) >= data.STORY_MOST_FACTS:
            raise NewsroomError(f"A story may use at most {data.STORY_MOST_FACTS} facts: keep it to the point.")
        chosen.append({k: card[k] for k in ("id", "kind", "title", "line", "figures", "tone", "tickers", "empire_id",
                                            "importance", "wire_kinds", "source", "ripple", "scoopable", "record", "period", "day")})
        tickers = sorted({t for c in chosen for t in c["tickers"]})
        conn.execute("UPDATE stories SET facts = %s, tickers = %s WHERE id = %s", (Jsonb(chosen), tickers, story["id"]))
        _block(conn, story, card["tickers"], now)
    return view(conn, player_id, now)


def remove_fact(conn: Connection, player_id, fact_id: str, now: datetime) -> dict:
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("You have no story in hand.")
        chosen = [c for c in story["facts"] if c["id"] != fact_id]
        checked = [c for c in story["checked"] if c != fact_id]
        conn.execute("UPDATE stories SET facts = %s, checked = %s, tickers = %s WHERE id = %s",
                     (Jsonb(chosen), Jsonb(checked), sorted({t for c in chosen for t in c["tickers"]}), story["id"]))
    return view(conn, player_id, now)


def check_fact(conn: Connection, player_id, fact_id: str, now: datetime) -> dict:
    """Check a chosen fact against the record (the path of a story: no fact goes to print unchecked)."""
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("You have no story in hand.")
        card = next((c for c in story["facts"] if c["id"] == fact_id), None)
        if card is None:
            raise NewsroomError("That fact is not in your story.")
        now_card = newsroom_facts.find(conn, fact_id, now)
        if now_card is None or not newsroom_facts.still_true(conn, card) or now_card["line"] != card["line"]:
            # The record has changed since it was chosen: take the record's version.
            if now_card is None:
                raise NewsroomError("That fact is no longer on the record as it was. Take it out of the story.")
            chosen = [now_card if c["id"] == fact_id else c for c in story["facts"]]
            conn.execute("UPDATE stories SET facts = %s WHERE id = %s", (Jsonb(chosen), story["id"]))
            words = f"The record has changed since you chose it. It now says: {now_card['line']} Your story uses the record's version."
        else:
            words = f"Checked against {card['record']}: it stands."
        checked = sorted(set(story["checked"]) | {fact_id})
        conn.execute("UPDATE stories SET checked = %s WHERE id = %s", (Jsonb(checked), story["id"]))
    return {**view(conn, player_id, now), "words": words}


def set_words(conn: Connection, player_id, angle: str, comment: str, declared: bool, now: datetime) -> dict:
    if angle not in ANGLES:
        raise NewsroomError("Choose how the story is told: " + ", ".join(ANGLES.values()) + ".")
    comment = " ".join((comment or "").split())
    if len(comment) > data.STORY_COMMENT_MOST:
        raise NewsroomError(f"Your own view is at most {data.STORY_COMMENT_MOST} characters.")
    if FIGURE.search(comment) or "₦" in comment or "%" in comment:
        raise NewsroomError("Your own view is in words only: every figure in a story must come from the record, so put none here.")
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("You have no story in hand.")
        conn.execute("UPDATE stories SET angle = %s, comment = %s, declared = %s WHERE id = %s",
                     (angle, comment, bool(declared), story["id"]))
    return view(conn, player_id, now)


def drop(conn: Connection, player_id, now: datetime) -> None:
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("You have no story in hand.")
        conn.execute("UPDATE stories SET status = 'withdrawn' WHERE id = %s", (story["id"],))
        conn.execute("UPDATE story_blocks SET until = %s WHERE story_id = %s AND until IS NULL", (now, story["id"]))
        conn.execute("UPDATE interviews SET status = 'lapsed' WHERE story_id = %s AND status = 'asked'", (story["id"],))


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------

def _company_answer(conn: Connection, company: dict, story_id: int) -> tuple[str, str]:
    """A computer-run company answers from its own record, or declines. Never a figure that is not filed."""
    report = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1",
                  (company["id"],))
    rating = report["credit_rating"] if report else "BBB"
    weak = newsroom_facts.RATING_ORDER.index(rating) >= newsroom_facts.RATING_ORDER.index("BB")
    pick = (story_id + sum(map(ord, company["ticker"]))) % 3
    if weak and pick != 0:
        return "declined", f"{company['name']} declined to comment."
    lines = (f"A spokesperson for {company['name']} said the company's filed accounts speak for themselves.",
             f"{company['name']} said it would say more when it next files its results.",
             f"A spokesperson for {company['name']} said the company is focused on its customers and its plans.")
    return "answered", lines[pick]


def ask(conn: Connection, player_id, *, ticker: str | None, empire_name: str | None, question: str, now: datetime) -> dict:
    question = " ".join((question or "").split())
    if not 10 <= len(question) <= 300:
        raise NewsroomError("A question is between 10 and 300 characters.")
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("Start a story first: an interview belongs to a story.")
        due = now + timedelta(hours=data.INTERVIEW_HOURS)
        if ticker:
            company = _one(conn, "SELECT * FROM companies WHERE ticker = %s AND listed", (ticker,))
            if company is None:
                raise NewsroomError("There is no listed company with that ticker.")
            status, answer = _company_answer(conn, company, story["id"])
            try:
                conn.execute("INSERT INTO interviews (story_id, journalist_id, company_id, question, answer, status, asked_at, due_at, answered_at)"
                             " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                             (story["id"], player_id, company["id"], question, answer, status, now, due, now))
            except Exception as e:
                raise NewsroomError("You have already asked them for this story.") from e
        else:
            empire = _one(conn, "SELECT * FROM empires WHERE lower(name) = lower(%s) AND status = 'active'", (empire_name or "",))
            if empire is None:
                raise NewsroomError("There is no empire of that name.")
            if empire["id"] == story["empire_id"]:
                raise NewsroomError("You cannot interview your own empire for your own story.")
            if empire["kind"] == "computer" or empire["head_player_id"] is None:
                status, answer, answered = "declined", f"{empire['name']} declined to comment.", now
            else:
                status, answer, answered = "asked", None, None
            if _one(conn, "SELECT 1 AS x FROM interviews WHERE story_id = %s AND empire_id = %s", (story["id"], empire["id"])):
                raise NewsroomError("You have already asked them for this story.")
            conn.execute("INSERT INTO interviews (story_id, journalist_id, empire_id, question, answer, status, asked_at, due_at, answered_at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                         (story["id"], player_id, empire["id"], question, answer, status, now, due, answered))
    return view(conn, player_id, now)


def to_answer(conn: Connection, player_id, now: datetime) -> list[dict]:
    """Questions from journalists waiting on this player, as the head of an empire."""
    return _rows(conn, "SELECT i.id, i.question, i.due_at, e.name AS empire, p.display_name AS journalist FROM interviews i"
                       " JOIN empires e ON e.id = i.empire_id JOIN players p ON p.id = i.journalist_id"
                       " WHERE e.head_player_id = %s AND i.status = 'asked' AND i.due_at > %s ORDER BY i.due_at",
                 (player_id, now))


def answer(conn: Connection, player_id, interview_id: int, words: str | None, now: datetime) -> None:
    """The head answers a journalist's question, or declines (no words). On the record either way."""
    words = " ".join((words or "").split())
    if len(words) > 300:
        raise NewsroomError("An answer is at most 300 characters.")
    with conn.transaction():
        row = _one(conn, "SELECT i.*, e.head_player_id, e.name AS empire FROM interviews i JOIN empires e ON e.id = i.empire_id"
                         " WHERE i.id = %s FOR UPDATE OF i", (interview_id,))
        if row is None or row["head_player_id"] != player_id:
            raise NewsroomError("That question is not yours to answer.")
        if row["status"] != "asked" or row["due_at"] <= now:
            raise NewsroomError("That question is closed.")
        if words:
            conn.execute("UPDATE interviews SET status = 'answered', answer = %s, answered_at = %s WHERE id = %s",
                         (f"{row['empire']} said: “{words}”", now, interview_id))
            standing.change(conn, row["empire_id"], 1, "Answered a journalist's question on the record", _now(conn, now)["period"], now)
        else:
            conn.execute("UPDATE interviews SET status = 'declined', answer = %s, answered_at = %s WHERE id = %s",
                         (f"{row['empire']} declined to comment.", now, interview_id))


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

def _scoop(conn: Connection, card: dict, period: int, day: int, story_id: int) -> bool:
    """First with a confirmed fact: nothing on the wire carries it yet, and no player published it first."""
    if not card.get("scoopable") or not card.get("wire_kinds"):
        return False
    tickers = card.get("tickers") or []
    on_wire = _one(conn, "SELECT 1 AS x FROM news_items WHERE kind = ANY(%s) AND author_id IS NULL AND (period, day) <= (%s, %s)"
                         " AND period >= %s AND (cardinality(%s::text[]) = 0 OR tickers && %s::text[]) LIMIT 1",
                   (card["wire_kinds"], period, day, card.get("period", period), tickers, tickers))
    if on_wire:
        return False
    earlier = _one(conn, "SELECT 1 AS x FROM stories WHERE status = 'published' AND id <> %s AND facts @> %s::jsonb LIMIT 1",
                   (story_id, json.dumps([{"id": card["id"]}])))
    return earlier is None


def _write(story: dict, author: str, outlet_name: str, interviews: list[dict], declaration: str | None) -> tuple[str, str]:
    facts = story["facts"]
    main = max(facts, key=lambda c: c["importance"])
    others = [c for c in facts if c is not main]
    if story["angle"] == "what_it_means":
        headline = f"{main['title']}: what it means"
    elif story["angle"] == "who_wins":
        headline = f"{main['title']}: who wins, who loses"
    else:
        headline = main["title"]
    parts = [main["line"]]
    parts += [c["line"] for c in others]
    for i in interviews:
        if i["status"] in ("answered", "declined"):
            parts.append(i["answer"])
        elif i["status"] == "lapsed":
            parts.append(f"{i['who']} had not answered by the deadline.")
        else:
            parts.append(f"{i['who']} had not yet answered when this story went to press.")
    if story["comment"]:
        parts.append(f"{author}'s view: {story['comment']}")
    if declaration:
        parts.append(declaration)
    parts.append(f"By {author}, {outlet_name}.")
    return headline[:160], " ".join(parts)


def _empire_holds(conn: Connection, empire: dict, tickers: list[str]) -> bool:
    for t in tickers:
        c = _one(conn, "SELECT id, share_asset FROM companies WHERE ticker = %s", (t,))
        if c is None:
            continue
        if ledger.balance(conn, empire["account_id"], c["share_asset"]) > 0:
            return True
        if _one(conn, "SELECT 1 AS x FROM derivative_positions p JOIN derivative_series s ON s.id = p.series_id"
                      " WHERE p.account = %s AND p.status = 'open' AND s.underlying = %s LIMIT 1", (empire["account_id"], t)):
            return True
        if _one(conn, "SELECT 1 AS x FROM short_positions WHERE borrower = %s AND company_id = %s AND status = 'open' LIMIT 1",
                (empire["account_id"], c["id"])):
            return True
        for inst in _rows(conn, "SELECT asset FROM instruments WHERE company_id = %s", (c["id"],)):
            if ledger.balance(conn, empire["account_id"], inst["asset"]) > 0:
                return True
    return False


def _pay(conn: Connection, payer: dict, player_id, amount: int, why: str, period: int) -> int:
    if amount <= 0:
        return 0
    return ledger.pay_up_to(conn, payer=payer["account_id"], receiver=ledger.player_account_id(conn, player_id), wanted=amount,
                            kind="professional_fee", memo=f"{payer['name']}: {why}", period=period)


def publish(conn: Connection, player_id, now: datetime) -> dict:
    author = _journalist(conn, player_id)
    w = _now(conn, now)
    period, day = w["period"], w["day"]
    with conn.transaction():
        story = _draft(conn, player_id, lock=True)
        if story is None:
            raise NewsroomError("You have no story in hand.")
        if not story["facts"]:
            raise NewsroomError("A story needs at least one confirmed fact.")
        unchecked = [c["title"] for c in story["facts"] if c["id"] not in story["checked"]]
        if unchecked:
            raise NewsroomError("Check every fact against the record before it goes to print: " + "; ".join(unchecked) + ".")
        for c in story["facts"]:
            if not newsroom_facts.still_true(conn, c):
                raise NewsroomError(f"The record has changed for “{c['title']}”. Check it again.")
        today = _one(conn, "SELECT count(*) AS n FROM stories WHERE author_id = %s AND status = 'published' AND period = %s AND day = %s",
                     (player_id, period, day))["n"]
        if today >= data.STORIES_A_DAY:
            raise NewsroomError(f"At most {data.STORIES_A_DAY} stories a game day.")
        # Lapse any interview whose deadline has passed.
        conn.execute("UPDATE interviews SET status = 'lapsed' WHERE story_id = %s AND status = 'asked' AND due_at <= %s", (story["id"], now))
        interviews = _rows(conn, "SELECT i.*, coalesce(c.name, e.name) AS who FROM interviews i LEFT JOIN companies c ON c.id = i.company_id"
                                 " LEFT JOIN empires e ON e.id = i.empire_id WHERE i.story_id = %s ORDER BY i.id", (story["id"],))
        empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (story["empire_id"],)) if story["empire_id"] else None
        held = bool(empire) and _empire_holds(conn, empire, story["tickers"])
        declaration = None
        if empire and story["declared"]:
            declaration = (f"Declared interest: {author['display_name']} sits in {empire['name']}, which "
                           f"{'has a position in' if held else 'holds no position in'} the companies named.")
        outlet = _one(conn, "SELECT * FROM companies WHERE id = %s", (story["outlet_company"],)) if story["outlet_company"] else None
        prof = profile(conn, player_id)
        outlet_name = outlet["name"] if outlet else "an independent journalist"
        headline, body = _write(story, author["display_name"], outlet_name, interviews, declaration)

        # Readers: how big the news is, how early, the audience, and the author's name.
        scoop = any(_scoop(conn, c, period, day, story["id"]) for c in story["facts"])
        importance = max(c["importance"] for c in story["facts"])
        late = all(not c.get("scoopable") or _one(conn, "SELECT 1 AS x FROM news_items WHERE kind = ANY(%s) AND author_id IS NULL"
                                                         " AND (period, day) <= (%s, %s) AND period >= %s AND tickers && %s::text[] LIMIT 1",
                                                         (c.get("wire_kinds") or ["-"], period, day, c.get("period", period),
                                                          c.get("tickers") or ["-"])) for c in story["facts"])
        freshness = data.SCOOP_READERS_BPS if scoop else data.OLD_NEWS_READERS_BPS if late else BPS
        credibility = min(max(prof["credibility"] * BPS // 50, 5000), 15000)
        answered = sum(1 for i in interviews if i["status"] == "answered")
        readers = (_audience(conn, outlet, 0) * importance // 100 * freshness // BPS * credibility // BPS
                   + prof["following"] * data.FOLLOWERS_READ_BPS // BPS)
        readers = readers * (BPS + answered * data.INTERVIEW_READERS_BPS) // BPS
        readers = max(readers, 1)

        item = _one(conn, "INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body, tickers, facts, author_id)"
                          " VALUES (%s, %s, %s, 'player_story', %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (period, day, PRESS, f"story:{story['id']}", min(40 + readers // 5000, 95), headline, body, story["tickers"],
                     Jsonb({"story_id": story["id"], "author": author["display_name"], "outlet": outlet_name,
                            "facts": [c["id"] for c in story["facts"]]}), player_id))
        # Pay: a scoop bonus from the employer; an independent is paid by the paper that picks the story up.
        paid = 0
        if outlet is None:
            buyer = _one(conn, "SELECT c.* FROM companies c JOIN company_results r ON r.company_id = c.id AND r.period ="
                               " (SELECT max(period) FROM company_results WHERE company_id = c.id)"
                               " WHERE c.sector = 'media' AND c.listed AND c.status = 'trading' ORDER BY r.staff DESC LIMIT 1")
            if buyer:
                fee = min(readers * data.FREELANCE_KOBO_PER_READER, naira(data.FREELANCE_MOST_NAIRA))
                fee += naira(data.SCOOP_BONUS_NAIRA) if scoop else 0
                paid = _pay(conn, buyer, player_id, fee, f"for a story by {author['display_name']}", period)
        elif scoop:
            paid = _pay(conn, outlet, player_id, naira(data.SCOOP_BONUS_NAIRA), f"scoop bonus to {author['display_name']}", period)
        conn.execute("UPDATE stories SET status = 'published', headline = %s, body = %s, readers = %s, scoop = %s, paid = %s,"
                     " news_item_id = %s, period = %s, day = %s, published_at = %s,"
                     " tone = %s WHERE id = %s",
                     (headline, body, readers, scoop, paid, item["id"], period, day, now,
                      max(min(sum(c["tone"] for c in story["facts"]), 1), -1), story["id"]))
        conn.execute("UPDATE journalist_profiles SET readers = readers + %s, stories = stories + 1, scoops = scoops + %s,"
                     " following = following + %s WHERE player_id = %s",
                     (readers, 1 if scoop else 0, readers * data.FOLLOW_SHARE_BPS // BPS, player_id))
        if scoop:
            conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s", (data.SCOOP_REPUTATION, player_id))
        # No trading around it until two trading days after publication.
        session, _ = exchange.session_of(now)
        conn.execute("UPDATE story_blocks SET until = %s WHERE story_id = %s AND until IS NULL",
                     (_session_close(session, data.STORY_BLOCK_TRADING_DAYS), story["id"]))
        # Declared interest, kept for the record (the holding itself is never shown).
        if empire:
            conn.execute("INSERT INTO story_interests (story_id, empire_id, held, declared) VALUES (%s, %s, %s, %s)",
                         (story["id"], empire["id"], held, bool(story["declared"])))
        # A true, widely read story nudges the investors' view of the companies it is about.
        nudges = _nudge(conn, story, readers, session, now)
        # Empires that refused or let a question lapse.
        for i in interviews:
            if i["empire_id"] and i["status"] == "lapsed":
                standing.change(conn, i["empire_id"], -1, "Did not answer a journalist's question by the deadline", period, now)
        # The Ripple: the story was caused by its facts, and caused its nudges.
        for c in story["facts"]:
            ripple.link(conn, f"story:{story['id']}", c["ripple"], f"{author['display_name']}'s story “{headline}” reported: {c['line']}",
                        period, now, c["figures"])
        for n in nudges:
            ripple.link(conn, f"nudge:{n['ticker']}:{session}", f"story:{story['id']}",
                        f"{readers:,} readers read “{headline}”, and investors marked {n['ticker']} {'up' if n['bps'] > 0 else 'down'} "
                        f"{n['bps'] / 100:.2f}% for a few days.", period, now, {"readers": f"{readers:,}", "nudge": f"{n['bps'] / 100:.2f}%"})
        from simulation import chronicle
        if scoop or readers >= data.WIDELY_READ:
            chronicle.write(conn, "personal", f"story:{story['id']}", "scoop" if scoop else "story",
                            ("A scoop: " if scoop else "A widely read story: ") + headline,
                            f"{author['display_name']} published “{headline}” for {outlet_name}: {readers:,} readers.",
                            period, day, now, player_id=player_id)
    return {"story_id": story["id"], "news_item_id": item["id"], "headline": headline, "readers": readers, "scoop": scoop,
            "paid": paid, "nudges": nudges}


def _nudge(conn: Connection, story: dict, readers: int, session, now: datetime) -> list[dict]:
    if readers < data.WIDELY_READ or len(story["tickers"]) > data.NUDGE_MOST_COMPANIES:
        return []
    out = []
    for ticker in story["tickers"]:
        tone = sum(c["tone"] for c in story["facts"] if ticker in c["tickers"])
        if tone == 0:
            continue
        bps = (1 if tone > 0 else -1) * min(data.NUDGE_MOST_BPS, readers // data.READERS_PER_NUDGE_BPS)
        if bps == 0:
            continue
        company = _one(conn, "SELECT id FROM companies WHERE ticker = %s", (ticker,))
        made = _one(conn, "INSERT INTO story_nudges (company_id, story_id, bps, session_date, days, at) VALUES (%s, %s, %s, %s, %s, %s)"
                          " ON CONFLICT (company_id, session_date) DO NOTHING RETURNING id",
                    (company["id"], story["id"], bps, session, data.NUDGE_DAYS, now))
        if made:
            out.append({"ticker": ticker, "bps": bps})
    return out


def nudges_today(conn: Connection, session, *, lag_days: int = 0) -> dict:
    """What players' stories add to how investors value each company on a trading day: each nudge in full on its first day,
    fading to nothing over its days. `lag_days`: an investor who reads the news late sees it that many days later."""
    if not _rows(conn, "SELECT to_regclass('story_nudges') IS NOT NULL AS ok")[0]["ok"]:
        return {}
    seen = session - timedelta(days=lag_days)
    out: dict = {}
    for n in _rows(conn, "SELECT company_id, bps, session_date, days FROM story_nudges WHERE session_date <= %s AND session_date > %s",
                   (seen, seen - timedelta(days=data.NUDGE_DAYS))):
        gone = (seen - n["session_date"]).days
        if 0 <= gone < n["days"]:
            out[n["company_id"]] = out.get(n["company_id"], 0) + n["bps"] * (n["days"] - gone) // n["days"]
    return {k: max(min(v, data.NUDGE_MOST_BPS), -data.NUDGE_MOST_BPS) for k, v in out.items()}


# ---------------------------------------------------------------------------
# Corrections, deadlines and exposing an undeclared interest
# ---------------------------------------------------------------------------

def tick(conn: Connection, now: datetime) -> None:
    """Run every few minutes: questions that ran out of time lapse; a story whose facts the record has changed must be
    corrected within a day, and a late correction costs more."""
    if not _rows(conn, "SELECT to_regclass('stories') IS NOT NULL AS ok")[0]["ok"]:
        return
    with conn.transaction():
        conn.execute("UPDATE interviews SET status = 'lapsed' WHERE status = 'asked' AND due_at <= %s", (now,))
        for s in _rows(conn, "SELECT * FROM stories WHERE status = 'published' AND NOT correction_due AND published_at > %s",
                       (now - timedelta(days=data.CORRECTION_WATCH_DAYS),)):
            if any(not newsroom_facts.still_true(conn, c) for c in s["facts"]):
                conn.execute("UPDATE stories SET correction_due = true, correct_by = %s WHERE id = %s",
                             (now + timedelta(hours=data.CORRECTION_HOURS), s["id"]))
        period = _now(conn, now)["period"]
        for s in _rows(conn, "SELECT * FROM stories WHERE correction_due AND correction_id IS NULL AND NOT correction_late AND correct_by <= %s"
                             " FOR UPDATE", (now,)):
            conn.execute("UPDATE stories SET correction_late = true WHERE id = %s", (s["id"],))
            _cost(conn, s["author_id"], data.LATE_CORRECTION_REPUTATION, late=True, period=period, now=now)


def _cost(conn: Connection, player_id, points: int, *, late: bool, period: int, now: datetime) -> None:
    conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s", (points, player_id))
    conn.execute("UPDATE journalist_profiles SET credibility = greatest(credibility - %s, 0),"
                 " following = following * %s / 10000 WHERE player_id = %s",
                 (points, BPS - (data.LATE_CORRECTION_FOLLOWING_BPS if late else 0), player_id))
    prof = profile(conn, player_id)
    if late and prof["credibility"] < data.DISMISS_BELOW_CREDIBILITY and careers.current_job(conn, player_id):
        careers._leave(conn, player_id, now, "dismissed: repeated reckless reporting cost the paper its readers' trust")


def to_correct(conn: Connection, player_id) -> list[dict]:
    return _rows(conn, "SELECT id, headline, correct_by, correction_late FROM stories WHERE author_id = %s AND correction_due"
                       " AND correction_id IS NULL ORDER BY id", (player_id,))


def correct(conn: Connection, player_id, story_id: int, now: datetime) -> dict:
    """Publish the correction: the record as it now stands, linked to the story it corrects."""
    w = _now(conn, now)
    with conn.transaction():
        s = _one(conn, "SELECT * FROM stories WHERE id = %s AND author_id = %s FOR UPDATE", (story_id, player_id))
        if s is None or not s["correction_due"] or s["correction_id"]:
            raise NewsroomError("That story has nothing to correct.")
        fixed = []
        for c in s["facts"]:
            if not newsroom_facts.still_true(conn, c):
                now_card = newsroom_facts.find(conn, c["id"], now)
                fixed.append(now_card["line"] if now_card else f"“{c['title']}” no longer stands in the record.")
        body = (f"Correction to “{s['headline']}”: the record has changed since it was published. It now says: " + " ".join(fixed)
                + " The story has been corrected.")
        item = _one(conn, "INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body, tickers, facts, author_id, follows)"
                          " VALUES (%s, %s, %s, 'correction', %s, 30, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (w["period"], w["day"], PRESS, f"story:{s['id']}", f"Correction: {s['headline']}"[:160], body, s["tickers"],
                     Jsonb({"story_id": s["id"], "correction": True}), player_id, s["news_item_id"]))
        conn.execute("UPDATE stories SET correction_id = %s WHERE id = %s", (item["id"], s["id"]))
        conn.execute("UPDATE journalist_profiles SET corrections = corrections + 1 WHERE player_id = %s", (player_id,))
        if not s["correction_late"]:
            _cost(conn, player_id, data.CORRECTION_REPUTATION, late=False, period=w["period"], now=now)
    return {"news_item_id": item["id"]}


def expose(conn: Connection, player_id, story_id: int, now: datetime) -> dict:
    """Any player may say a story hid its author's interest. Only the verdict is shown, never the holding."""
    w = _now(conn, now)
    with conn.transaction():
        s = _one(conn, "SELECT * FROM stories WHERE id = %s AND status = 'published'", (story_id,))
        if s is None:
            raise NewsroomError("There is no such published story.")
        if s["author_id"] == player_id:
            raise NewsroomError("You cannot expose your own story.")
        if _one(conn, "SELECT 1 AS x FROM interest_exposures WHERE story_id = %s AND by_player = %s", (story_id, player_id)):
            raise NewsroomError("You have already raised this story.")
        interest = _one(conn, "SELECT * FROM story_interests WHERE story_id = %s", (story_id,))
        upheld = bool(interest and interest["held"] and not interest["declared"])
        already = _one(conn, "SELECT 1 AS x FROM interest_exposures WHERE story_id = %s AND upheld", (story_id,))
        conn.execute("INSERT INTO interest_exposures (story_id, by_player, upheld, at) VALUES (%s, %s, %s, %s)",
                     (story_id, player_id, upheld, now))
        if upheld and not already:
            conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s", (data.UNDECLARED_REPUTATION, s["author_id"]))
            conn.execute("UPDATE journalist_profiles SET credibility = greatest(credibility - %s, 0) WHERE player_id = %s",
                         (data.UNDECLARED_CREDIBILITY, s["author_id"]))
            conn.execute("UPDATE players SET reputation = least(reputation + 1, 100) WHERE id = %s", (player_id,))
            standing.change(conn, interest["empire_id"], -data.UNDECLARED_EMPIRE_REPUTATION,
                            "Its journalist hid the empire's interest in a story", w["period"], now)
            words = "Upheld: the author's empire had an interest in the companies named and did not declare it. Their reputation has fallen."
        elif upheld:
            words = "Upheld, but another player raised it first."
        else:
            conn.execute("UPDATE players SET reputation = greatest(reputation - 1, 0) WHERE id = %s", (player_id,))
            words = "Not upheld: there was no undeclared interest. Raising it cost you a little reputation."
    return {"upheld": upheld, "words": words}


# ---------------------------------------------------------------------------
# What a journalist sees
# ---------------------------------------------------------------------------

def view(conn: Connection, player_id, now: datetime) -> dict:
    story = _draft(conn, player_id)
    out: dict = {"profile": profile(conn, player_id), "angles": ANGLES, "to_correct": [
        {"id": s["id"], "headline": s["headline"], "correct_by": s["correct_by"], "late": s["correction_late"]}
        for s in to_correct(conn, player_id)]}
    empire = _seat_empire(conn, player_id)
    outlet = _outlet(conn, player_id)
    out["writing_for"] = outlet["name"] if outlet else "Independent"
    from simulation import clients
    out["editors"] = clients.view(conn, player_id)
    out["empire"] = empire["name"] if empire else None
    if story:
        interviews = _rows(conn, "SELECT i.id, i.question, i.answer, i.status, i.due_at, coalesce(c.name, e.name) AS who FROM interviews i"
                                 " LEFT JOIN companies c ON c.id = i.company_id LEFT JOIN empires e ON e.id = i.empire_id"
                                 " WHERE i.story_id = %s ORDER BY i.id", (story["id"],))
        out["draft"] = {
            "id": story["id"], "facts": [{k: c[k] for k in ("id", "title", "line", "tickers", "record")} | {"checked": c["id"] in story["checked"]}
                                         for c in story["facts"]],
            "angle": story["angle"], "comment": story["comment"], "declared": story["declared"], "tickers": story["tickers"],
            "interviews": interviews,
        }
    else:
        out["draft"] = None
    out["published"] = _rows(conn, "SELECT id, headline, readers, scoop, period, day, correction_due, correction_id IS NOT NULL AS corrected"
                                   " FROM stories WHERE author_id = %s AND status = 'published' ORDER BY id DESC LIMIT 20", (player_id,))
    return out


def public_stories(conn: Connection, period_now: int, day_now: int, *, author_id=None, limit: int = 40) -> list[dict]:
    """Players' published stories, as anyone may read them."""
    cond = "s.status = 'published' AND (s.period < %s OR (s.period = %s AND s.day <= %s))"
    params: list = [period_now, period_now, day_now]
    if author_id:
        cond += " AND s.author_id = %s"
        params.append(author_id)
    params.append(limit)
    return _rows(conn, f"""
        SELECT s.id, s.headline, s.body, s.readers, s.scoop, s.period, s.day, s.tickers, p.display_name AS author,
               coalesce(c.name, 'Independent') AS outlet, s.correction_id IS NOT NULL AS corrected, s.news_item_id
        FROM stories s JOIN players p ON p.id = s.author_id LEFT JOIN companies c ON c.id = s.outlet_company
        WHERE {cond} ORDER BY s.period DESC, s.day DESC, s.id DESC LIMIT %s""", params)
