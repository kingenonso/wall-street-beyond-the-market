"""Stage 10, Part 2: investigations and the empire's press desk (Journalist 7; G1, G3, G4, G5, G8, G10, G13; A4).

Investigations, as files. A Financial Journalist opens a file on an empire, from a tip or a hunch, and searches for
documents a day at a time. If the empire is hiding something (money taken by one of its own and dressed up in the books,
or an unlawful pact), the documents point at it, one by one; if it is hiding nothing, the searches find nothing, and the
journalist cannot tell bad luck from innocence. With three documents and a second source, the exposé can run: the theft
is proved (a case opens, as after an audit) or the pact comes to light. It is the big prize: readers, a prize from the
paper, reputation and credibility. Nothing can be printed without the documents and the second source, so an exposé
cannot be made up.

The press desk, worked by the empire's Financial Journalist (or its head):
  * the press office answers other journalists' questions for the empire;
  * crisis statements: when something about the empire comes to light it has 24 hours to answer. Admitting what is true,
    quickly, limits the damage; denying it makes it worse; saying nothing costs the most. Denying what is false helps.
  * counter-investigation: who has been looking at the empire, from public traces only (questions asked, stories printed);
  * fact-checking for the members (in intel.py): a tip or rumour is checked before the Asset Manager trades on it;
  * leaks: a member can pass something about their own empire to a journalist; when it is printed the empire suffers a
    leak, and may hunt for the leaker. A hidden pact can also leak on its own (the "leak to the press" empire event);
  * spin, or refuse: the head may ask the journalist to answer a story with a misleading reply. Refusing keeps a clean
    name; going along helps the empire for now, but one in four such replies comes out each quarter, and then it costs
    both the empire and the journalist.

Nothing here ever sends what an empire holds, who leaked (except to a hunter who finds it), or whether a crisis is true.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, clock, intel, ledger, ripple, standing
from simulation import world_data as data
from simulation.money import BPS, naira

FIGURE = re.compile(r"\d")
STANCES = {"admit": "It is true, and here is what we are doing about it",
           "regret": "We regret what has happened and are looking into it",
           "deny": "It is not true"}


class PressError(Exception):
    """Something the rules of the press do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_rows(conn, "SELECT to_regclass('crises') IS NOT NULL AS ok")[0]["ok"])


def _now(conn: Connection, now: datetime) -> dict:
    return careers.world_now(conn, now)


def _roll(conn: Connection, *parts) -> int:
    return intel._roll(conn, "press", *parts)


def _words(text: str | None, least: int, most: int, what: str) -> str:
    text = " ".join((text or "").split())
    if not least <= len(text) <= most:
        raise PressError(f"{what} is between {least} and {most} characters.")
    if FIGURE.search(text) or "₦" in text or "%" in text:
        raise PressError(f"{what} is in words: a figure can be printed only from the record, so put none here.")
    return text


def _journalist(conn: Connection, player_id) -> dict:
    p = _one(conn, "SELECT id, display_name, build FROM players WHERE id = %s", (player_id,))
    if p is None or p["build"] != "journalist":
        raise PressError("Only a Financial Journalist can do this.")
    conn.execute("INSERT INTO journalist_profiles (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (player_id,))
    return p


def _level(conn: Connection, player_id) -> int:
    p = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    c = careers.career(conn, player_id, p["build"]) if p and p["build"] else None
    return c["level"] if c else 1


def empire_of(conn: Connection, player_id) -> dict | None:
    from simulation import newsroom
    return newsroom._seat_empire(conn, player_id)


def press_officer(conn: Connection, player_id) -> dict:
    """The empire this player speaks for: its head, or a Financial Journalist with a seat in it."""
    empire = empire_of(conn, player_id)
    if empire is None or empire["kind"] != "player":
        raise PressError("You do not speak for an empire.")
    if empire["head_player_id"] == player_id:
        return empire
    if _one(conn, "SELECT 1 AS x FROM empire_seats WHERE empire_id = %s AND player_id = %s AND build = 'journalist'", (empire["id"], player_id)):
        return empire
    raise PressError("The empire's head, or its Financial Journalist, speaks for it.")


def speaks_for(conn: Connection, player_id, empire_id) -> bool:
    try:
        return press_officer(conn, player_id)["id"] == empire_id
    except PressError:
        return False


def _log(conn: Connection, empire_id, words: str, now: datetime) -> None:
    conn.execute("INSERT INTO empire_events (empire_id, words, at) VALUES (%s, %s, %s)", (empire_id, words, now))


def _news(conn: Connection, *, period: int, day: int, kind: str, story: str, headline: str, body: str, author_id=None,
          tickers: list | None = None, importance: int = 50, facts: dict | None = None, follows=None) -> int:
    from simulation import newsroom
    row = _one(conn, "INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body, tickers, facts, author_id, follows)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
               (period, day, newsroom.PRESS, kind, story, importance, headline[:160], body, tickers or [], Jsonb(facts or {}), author_id, follows))
    return row["id"]


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------

def _wrongdoing(conn: Connection, empire_id) -> list[str]:
    """What the empire is hiding, oldest first: money taken and dressed up in the books, and unlawful pacts not yet public."""
    out = [f"book:{b['id']}" for b in _rows(conn, "SELECT id FROM empire_books WHERE empire_id = %s AND NOT genuine AND NOT found ORDER BY id",
                                            (empire_id,))]
    out += [f"pact:{p['id']}" for p in _rows(conn, "SELECT id FROM empire_pacts WHERE status = 'signed' AND exposed_at IS NULL AND NOT legal"
                                                   " AND %s IN (from_empire, to_empire) ORDER BY id", (empire_id,))]
    return out


def _charity_wrongdoing(conn: Connection, charity_id) -> list[str]:
    """Grants from a charity to people connected to those behind it, while it has not been exposed."""
    return [f"grant:{g['id']}" for g in _rows(conn, "SELECT g.id FROM charity_grants g JOIN charities c ON c.id = g.charity_id"
                                                      " WHERE g.charity_id = %s AND g.connected AND NOT c.exposed ORDER BY g.id", (charity_id,))]


def _still_hidden(conn: Connection, basis: str) -> bool:
    kind, key = basis.split(":")
    if kind == "grant":
        return bool(_one(conn, "SELECT 1 AS x FROM charity_grants g JOIN charities c ON c.id = g.charity_id WHERE g.id = %s AND NOT c.exposed",
                         (int(key),)))
    if kind == "book":
        return bool(_one(conn, "SELECT 1 AS x FROM empire_books WHERE id = %s AND NOT found", (int(key),)))
    return bool(_one(conn, "SELECT 1 AS x FROM empire_pacts WHERE id = %s AND exposed_at IS NULL AND status = 'signed'", (int(key),)))


def open_file(conn: Connection, player_id, empire_name: str | None, ref: str | None, now: datetime, *, charity_name: str | None = None) -> dict:
    _journalist(conn, player_id)
    w = _now(conn, now)
    if charity_name:
        return _open_charity_file(conn, player_id, charity_name, w, now)
    with conn.transaction():
        empire = _one(conn, "SELECT * FROM empires WHERE lower(name) = lower(%s) AND status = 'active' AND kind IN ('player', 'computer')",
                      ((empire_name or "").strip(),))
        if empire is None:
            raise PressError("There is no empire of that name.")
        mine = empire_of(conn, player_id)
        if mine and mine["id"] == empire["id"]:
            raise PressError("A journalist does not investigate the empire they sit in.")
        if _one(conn, "SELECT count(*) AS n FROM investigations WHERE journalist_id = %s AND status = 'open'", (player_id,))["n"] \
                >= data.INVESTIGATIONS_OPEN_MOST:
            raise PressError(f"At most {data.INVESTIGATIONS_OPEN_MOST} investigations at once. Publish or drop one first.")
        item = None
        if ref:
            try:
                item = intel.held(conn, player_id, ref)
            except intel.IntelError as e:
                raise PressError(str(e)) from None
            if empire["id"] not in (item["empire_id"], item["other_empire_id"]):
                raise PressError("That piece is not about this empire.")
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO investigations (journalist_id, target_kind, empire_id, from_item, opened_period, at, notes)"
                                 " VALUES (%s, 'empire', %s, %s, %s, %s, %s) RETURNING id",
                           (player_id, empire["id"], item["id"] if item else None, w["period"], now,
                            Jsonb([f"File opened on {empire['name']}" + (f", from: {item['words']}" if item else ".")])))
        except errors.UniqueViolation:
            raise PressError("You already have a file open on that empire.") from None
    return file_view(conn, player_id, row["id"], now)


def _open_charity_file(conn: Connection, player_id, charity_name: str, w: dict, now: datetime) -> dict:
    with conn.transaction():
        c = _one(conn, "SELECT * FROM charities WHERE lower(name) = lower(%s) AND status = 'open'", ((charity_name or "").strip(),))
        if c is None:
            raise PressError("There is no charity of that name.")
        mine = empire_of(conn, player_id)
        if c["trustee_id"] == player_id or c["founder_player"] == player_id or (mine and c["founder_empire"] == mine["id"]):
            raise PressError("A journalist does not investigate their own charity.")
        if _one(conn, "SELECT count(*) AS n FROM investigations WHERE journalist_id = %s AND status = 'open'", (player_id,))["n"] \
                >= data.INVESTIGATIONS_OPEN_MOST:
            raise PressError(f"At most {data.INVESTIGATIONS_OPEN_MOST} investigations at once. Publish or drop one first.")
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO investigations (journalist_id, target_kind, charity_id, opened_period, at, notes)"
                                 " VALUES (%s, 'charity', %s, %s, %s, %s) RETURNING id",
                           (player_id, c["id"], w["period"], now, Jsonb([f"File opened on the charity {c['name']}."])))
        except errors.UniqueViolation:
            raise PressError("You already have a file open on that charity.") from None
    return file_view(conn, player_id, row["id"], now)


def _file(conn: Connection, player_id, file_id: int, *, lock: bool = False) -> dict:
    f = _one(conn, "SELECT * FROM investigations WHERE id = %s AND journalist_id = %s" + (" FOR UPDATE" if lock else ""), (file_id, player_id))
    if f is None:
        raise PressError("You have no such investigation.")
    return f


DOCS = {
    "book": ("A payment in the books that matches nothing the empire received.",
             "The payee named for it cannot be found at any address.",
             "The same kind of payment, made again, in round sums."),
    "grant": ("A grant paid out to a named person rather than to the cause.",
              "The person who received it is close to those behind the charity.",
              "The same thing has happened more than once."),
    "pact": ("A meeting between people from {a} and {b}, kept off both diaries.",
             "{a} and {b} moved together in a way neither explained to its members.",
             "A draft of terms between {a} and {b}."),
}


def dig(conn: Connection, player_id, file_id: int, now: datetime) -> dict:
    """A day's search for documents. Something is found only if there is something to find."""
    _journalist(conn, player_id)
    with conn.transaction():
        f = _file(conn, player_id, file_id, lock=True)
        if f["status"] != "open":
            raise PressError("That file is closed.")
        today = intel.lagos_day(now)
        if f["last_dug"] == today:
            raise PressError("You have searched today. Search again tomorrow.")
        conn.execute("UPDATE investigations SET last_dug = %s WHERE id = %s", (today, file_id))
        notes = list(f["notes"])
        basis = f["basis"]
        if basis and not _still_hidden(conn, basis):
            basis = None                        # what it pointed at has come out some other way: the trail goes cold
            notes.append("What your documents pointed at is no longer hidden. The trail has gone cold.")
            conn.execute("UPDATE investigations SET basis = NULL, documents = 0, confirmed = false, notes = %s WHERE id = %s",
                         (Jsonb(notes), file_id))
            return file_view(conn, player_id, file_id, now)
        hidden = [basis] if basis else (_charity_wrongdoing(conn, f["charity_id"]) if f["target_kind"] == "charity"
                                         else _wrongdoing(conn, f["empire_id"]))
        chance = min(data.DIG_FINDS_BPS + data.DIG_FINDS_PER_LEVEL_BPS * _level(conn, player_id), data.DIG_FINDS_MOST_BPS)
        if f["from_item"]:
            item = _one(conn, "SELECT truth, basis FROM intel_items WHERE id = %s", (f["from_item"],))
            if item["truth"] == "true" and item["basis"] in hidden:
                hidden = [item["basis"]]
                chance += data.DIG_TIP_HELPS_BPS
        if not hidden or _roll(conn, "dig", file_id, today) >= chance or f["documents"] >= data.DOCUMENTS_NEEDED:
            notes.append(f"{clock.to_lagos(now):%d %b}: nothing new today." if f["documents"] < data.DOCUMENTS_NEEDED
                         else f"{clock.to_lagos(now):%d %b}: you have the documents you need.")
            conn.execute("UPDATE investigations SET notes = %s WHERE id = %s", (Jsonb(notes[-30:]), file_id))
            return file_view(conn, player_id, file_id, now)
        basis = basis or hidden[0]
        kind, key = basis.split(":")
        names = {"a": "", "b": ""}
        if kind == "pact":
            p = _one(conn, "SELECT from_empire, to_empire FROM empire_pacts WHERE id = %s", (int(key),))
            names = {"a": _one(conn, "SELECT name FROM empires WHERE id = %s", (p["from_empire"],))["name"],
                     "b": _one(conn, "SELECT name FROM empires WHERE id = %s", (p["to_empire"],))["name"]}
        notes.append(f"{clock.to_lagos(now):%d %b}: found a document. " + DOCS[kind][f["documents"]].format(**names))
        conn.execute("UPDATE investigations SET basis = %s, documents = documents + 1, notes = %s WHERE id = %s",
                     (basis, Jsonb(notes[-30:]), file_id))
    return file_view(conn, player_id, file_id, now)


def second_source(conn: Connection, player_id, file_id: int, now: datetime) -> dict:
    """Seek a second source to confirm what the documents show. Once a real day, once two documents are in hand. A piece of
    information the journalist holds that is about the same thing, and true, confirms it at once."""
    _journalist(conn, player_id)
    with conn.transaction():
        f = _file(conn, player_id, file_id, lock=True)
        if f["status"] != "open":
            raise PressError("That file is closed.")
        if f["confirmed"]:
            raise PressError("A second source has already confirmed it.")
        if f["documents"] < 2 or not f["basis"]:
            raise PressError("Find at least two documents before you look for a second source.")
        today = intel.lagos_day(now)
        if f["last_asked"] == today:
            raise PressError("You have looked for a second source today. Try again tomorrow.")
        conn.execute("UPDATE investigations SET last_asked = %s WHERE id = %s", (today, file_id))
        backed = _one(conn, "SELECT 1 AS x FROM intel_items i JOIN intel_holders h ON h.item_id = i.id AND h.player_id = %s"
                            " WHERE i.truth = 'true' AND i.basis = %s LIMIT 1", (player_id, f["basis"]))
        chance = min(data.SECOND_SOURCE_BPS + data.SECOND_SOURCE_PER_LEVEL_BPS * _level(conn, player_id), data.SECOND_SOURCE_MOST_BPS)
        found = bool(backed) or _roll(conn, "second", file_id, today) < chance
        notes = list(f["notes"])
        notes.append(f"{clock.to_lagos(now):%d %b}: " + ("a second source confirms it." if found else "no second source would talk today."))
        conn.execute("UPDATE investigations SET confirmed = %s, notes = %s WHERE id = %s", (found, Jsonb(notes[-30:]), file_id))
    return file_view(conn, player_id, file_id, now)


def drop_file(conn: Connection, player_id, file_id: int) -> None:
    with conn.transaction():
        f = _file(conn, player_id, file_id, lock=True)
        if f["status"] != "open":
            raise PressError("That file is closed.")
        conn.execute("UPDATE investigations SET status = 'dropped' WHERE id = %s", (file_id,))


def publish_expose(conn: Connection, player_id, file_id: int, now: datetime) -> dict:
    """Run the exposé. Three documents and a second source, about something still hidden."""
    from simulation import empires, newsroom
    author = _journalist(conn, player_id)
    w = _now(conn, now)
    period, day = w["period"], w["day"]
    with conn.transaction():
        f = _file(conn, player_id, file_id, lock=True)
        if f["status"] != "open":
            raise PressError("That file is closed.")
        if f["documents"] < data.DOCUMENTS_NEEDED or not f["confirmed"] or not f["basis"]:
            raise PressError(f"An exposé needs {data.DOCUMENTS_NEEDED} documents and a second source.")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('expose:' || %s))", (f["basis"],))
        if not _still_hidden(conn, f["basis"]):
            conn.execute("UPDATE investigations SET status = 'dropped' WHERE id = %s", (file_id,))
            raise PressError("What your documents show has already come out. Someone got there first.")
        empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (f["empire_id"],)) if f["empire_id"] else None
        kind, key = f["basis"].split(":")
        outlet = newsroom._outlet(conn, player_id)
        outlet_name = outlet["name"] if outlet else "an independent journalist"
        if kind == "grant":
            c = _one(conn, "SELECT * FROM charities WHERE id = %s FOR UPDATE", (f["charity_id"],))
            headline = f"Investigation: the charity {c['name']} paid its own"
            line = (f"An investigation by {author['display_name']} has found that the charity {c['name']} paid grants to people close to "
                    "those behind it, rather than to its cause. The documents, and a second source, confirm it.")
        elif kind == "book":
            headline = f"Investigation: money taken inside {empire['name']}"
            line = (f"An investigation by {author['display_name']} has found that money was taken from {empire['name']} by one of its own and "
                    "dressed up in the empire's books as an ordinary payment. The documents, and a second source, confirm it.")
        else:
            p = _one(conn, "SELECT * FROM empire_pacts WHERE id = %s", (int(key),))
            other = _one(conn, "SELECT name FROM empires WHERE id = %s", (p["to_empire"] if p["from_empire"] == empire["id"] else p["from_empire"],))
            headline = f"Investigation: the secret pact between {empire['name']} and {other['name']}"
            line = (f"An investigation by {author['display_name']} has found that {empire['name']} and {other['name']} signed an unlawful "
                    "pact and kept it hidden. The documents, and a second source, confirm it.")
        prof = newsroom.profile(conn, player_id)
        credibility = min(max(prof["credibility"] * BPS // 50, 5000), 15000)
        readers = max(newsroom._audience(conn, outlet, 0) * data.EXPOSE_IMPORTANCE // 100 * data.SCOOP_READERS_BPS // BPS * credibility // BPS
                      + prof["following"] * data.FOLLOWERS_READ_BPS // BPS, 1)
        story = _one(conn, "INSERT INTO stories (author_id, empire_id, outlet_company, status, headline, body, readers, scoop, period, day,"
                           " started_at, published_at, tone) VALUES (%s, %s, %s, 'published', %s, %s, %s, true, %s, %s, %s, %s, -1) RETURNING id",
                     (player_id, (empire_of(conn, player_id) or {}).get("id"), outlet["id"] if outlet else None, headline,
                      f"{line} By {author['display_name']}, {outlet_name}.", readers, period, day, f["at"], now))
        item_id = _news(conn, period=period, day=day, kind="player_story", story=f"story:{story['id']}", headline=headline,
                        body=f"{line} By {author['display_name']}, {outlet_name}.", author_id=player_id, importance=95,
                        facts={"story_id": story["id"], "author": author["display_name"], "outlet": outlet_name, "investigation": True})
        conn.execute("UPDATE stories SET news_item_id = %s WHERE id = %s", (item_id, story["id"]))
        conn.execute("UPDATE investigations SET status = 'published', story_id = %s WHERE id = %s", (story["id"], file_id))
        # What it shows comes to light.
        if kind == "grant":
            conn.execute("UPDATE charities SET exposed = true WHERE id = %s", (c["id"],))
            conn.execute("INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
                         (period, c["account_id"], f"Charity {c['name']}: exposed for paying grants to insiders"))
            if c["founder_empire"]:
                standing.change(conn, c["founder_empire"], -data.CHARITY_EXPOSED_REPUTATION, "Its charity was shown to pay its own", period, now)
                open_crisis(conn, c["founder_empire"], "report", f"charity:{c['id']}",
                            f"An investigation found that the charity {c['name']} paid grants to insiders.", "true", now)
            if c["founder_player"]:
                conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s",
                             (data.CHARITY_EXPOSED_REPUTATION, c["founder_player"]))
        elif kind == "book":
            book = _one(conn, "SELECT * FROM empire_books WHERE id = %s FOR UPDATE", (int(key),))
            audit = _one(conn, "INSERT INTO empire_audits (empire_id, kind, hired_by, period, from_period, to_period, examined, findings, reported, at)"
                               " VALUES (%s, 'report', %s, %s, %s, %s, 1, %s, %s, %s) RETURNING id",
                         (empire["id"], player_id, period, book["period"], book["period"], [book["id"]], [book["id"]], now))["id"]
            empires._prove(conn, empire, book, audit, now)
            standing.change(conn, empire["id"], -6, "An investigation exposed money taken inside the empire", period, now)
            open_crisis(conn, empire["id"], "theft", f"book:{book['id']}",
                        f"An investigation found money taken inside {empire['name']} by one of its own.", "true", now)
        else:
            empires.expose_pact(conn, _one(conn, "SELECT * FROM empire_pacts WHERE id = %s FOR UPDATE", (int(key),)), player_id, period, now,
                                how="An investigation uncovered")
        # The prize.
        payer = outlet or _one(conn, "SELECT c.* FROM companies c WHERE c.sector = 'media' AND c.listed AND c.status = 'trading'"
                                     " ORDER BY c.ticker LIMIT 1")
        paid = newsroom._pay(conn, payer, player_id, naira(data.EXPOSE_BONUS_NAIRA), f"for {author['display_name']}'s investigation", period) \
            if payer else 0
        conn.execute("UPDATE stories SET paid = %s WHERE id = %s", (paid, story["id"]))
        conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s", (data.EXPOSE_REPUTATION, player_id))
        conn.execute("UPDATE journalist_profiles SET readers = readers + %s, stories = stories + 1, scoops = scoops + 1,"
                     " credibility = least(credibility + %s, 100), following = following + %s WHERE player_id = %s",
                     (readers, data.EXPOSE_CREDIBILITY, readers * data.FOLLOW_SHARE_BPS // BPS, player_id))
        careers.add_experience(conn, player_id, "journalist", 150, now)
        from simulation import chronicle
        chronicle.write(conn, "personal", f"story:{story['id']}", "investigation", f"An exposé: {headline}",
                        f"{author['display_name']} published “{headline}” for {outlet_name}: {readers:,} readers.", period, day, now,
                        player_id=player_id)
        chronicle.write(conn, "world", f"expose:{story['id']}", "scandal", headline, line, period, day, now)
        ripple.link(conn, f"story:{story['id']}", f"investigation:{file_id}",
                    f"{author['display_name']}'s investigation of {empire['name'] if empire else c['name']}.", period, now, {})
    return {"story_id": story["id"], "headline": headline, "readers": readers, "paid": paid}


def file_view(conn: Connection, player_id, file_id: int, now: datetime) -> dict:
    f = _file(conn, player_id, file_id)
    target = (_one(conn, "SELECT name FROM empires WHERE id = %s", (f["empire_id"],)) if f["empire_id"] else
              _one(conn, "SELECT name FROM charities WHERE id = %s", (f["charity_id"],)))
    return {"id": f["id"], "empire": target["name"] if f["empire_id"] else None, "target": target["name"], "kind": f["target_kind"],
            "status": f["status"], "documents": f["documents"], "needed": data.DOCUMENTS_NEEDED,
            "confirmed": f["confirmed"], "notes": f["notes"], "opened": clock.period_label(f["opened_period"]),
            "dug_today": f["last_dug"] == intel.lagos_day(now), "asked_today": f["last_asked"] == intel.lagos_day(now),
            "can_publish": f["documents"] >= data.DOCUMENTS_NEEDED and f["confirmed"]}


def files(conn: Connection, player_id, now: datetime) -> list[dict]:
    return [file_view(conn, player_id, r["id"], now) for r in
            _rows(conn, "SELECT id FROM investigations WHERE journalist_id = %s ORDER BY status = 'open' DESC, id DESC LIMIT 10", (player_id,))]


# ---------------------------------------------------------------------------
# Crises
# ---------------------------------------------------------------------------

def open_crisis(conn: Connection, empire_id, kind: str, ref: str, words: str, truth: str, now: datetime) -> dict | None:
    """Something about the empire has come out: it has a day to answer. A computer-run empire answers at once, plainly."""
    if not ready(conn):
        return None
    empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (empire_id,))
    if empire is None or empire["kind"] not in ("player", "computer") or empire["status"] != "active":
        return None
    row = _one(conn, "INSERT INTO crises (empire_id, kind, ref, words, truth, opened_at, due_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (empire_id, ref) DO NOTHING RETURNING *",
               (empire_id, kind, ref, words[:400], truth, now, now + timedelta(hours=data.CRISIS_HOURS)))
    if row is None:
        return None
    if empire["kind"] == "computer" or empire["head_player_id"] is None:
        _settle_crisis(conn, row, "admit" if truth == "true" else "deny" if truth == "false" else "regret",
                       f"{empire['name']} said it is looking into the matter.", None, now)
    else:
        _log(conn, empire_id, f"Something has come out about the empire: {words} It must answer within a day.", now)
    return row


def _settle_crisis(conn: Connection, crisis: dict, stance: str | None, statement: str | None, by, now: datetime) -> int:
    w = _now(conn, now)
    change = data.CRISIS_OUTCOMES[(crisis["truth"], stance)]
    empire = _one(conn, "SELECT name FROM empires WHERE id = %s", (crisis["empire_id"],))
    conn.execute("UPDATE crises SET status = %s, stance = %s, statement = %s, answered_by = %s, answered_at = %s, change = %s WHERE id = %s",
                 ("answered" if stance else "silent", stance, statement, by, now if stance else None, change, crisis["id"]))
    why = {"admit": "Admitted what came out, quickly", "regret": "Said it regretted what came out",
           "deny": "Denied what came out", None: "Said nothing about what came out"}[stance]
    standing.change(conn, crisis["empire_id"], change, why, w["period"], now)
    if stance:
        _news(conn, period=w["period"], day=w["day"], kind="statement", story=f"crisis:{crisis['id']}",
              headline=f"Statement from {empire['name']}", body=f"{empire['name']}: {STANCES[stance]}. {statement or ''}".strip(),
              author_id=by, importance=45)
    return change


def answer_crisis(conn: Connection, player_id, crisis_id: int, stance: str, statement: str, now: datetime) -> dict:
    if stance not in STANCES:
        raise PressError("Admit it, express regret, or deny it.")
    statement = _words(statement, 10, 300, "A statement")
    with conn.transaction():
        empire = press_officer(conn, player_id)
        c = _one(conn, "SELECT * FROM crises WHERE id = %s AND empire_id = %s FOR UPDATE", (crisis_id, empire["id"]))
        if c is None:
            raise PressError("There is no such matter for your empire to answer.")
        if c["status"] != "open" or c["due_at"] <= now:
            raise PressError("That matter is closed.")
        _settle_crisis(conn, c, stance, statement, player_id, now)
        _log(conn, empire["id"], f"A statement was made for the empire: {STANCES[stance].lower()}.", now)
    return {"words": "The statement has gone out."}


def tick(conn: Connection, now: datetime) -> None:
    """Every few minutes: crises not answered in time count as silence."""
    if not ready(conn) or not _rows(conn, "SELECT 1 AS x FROM world_state"):
        return
    with conn.transaction():
        for c in _rows(conn, "SELECT * FROM crises WHERE status = 'open' AND due_at <= %s FOR UPDATE SKIP LOCKED", (now,)):
            _settle_crisis(conn, c, None, None, None, now)


# ---------------------------------------------------------------------------
# Who is looking at us (from public traces only)
# ---------------------------------------------------------------------------

def who_is_looking(conn: Connection, empire_id, now: datetime) -> list[dict]:
    """Journalists who have been looking at the empire, from what is public: questions put to it, and stories printed about it or
    the companies it has disclosed stakes in. Never anyone's private searches, files or tips."""
    w = _now(conn, now)
    since = w["period"] - data.TRACES_QUARTERS
    out: dict = {}
    for q in _rows(conn, "SELECT p.display_name AS who, i.question, i.asked_at FROM interviews i JOIN players p ON p.id = i.journalist_id"
                         " JOIN stories s ON s.id = i.story_id WHERE i.empire_id = %s AND i.asked_at > %s ORDER BY i.asked_at DESC",
                   (empire_id, now - timedelta(days=clock.REAL_DAYS_PER_QUARTER * data.TRACES_QUARTERS))):
        out.setdefault(q["who"], []).append(f"Asked: “{q['question']}”")
    tickers = [r["ticker"] for r in _rows(conn, "SELECT c.ticker FROM stake_disclosures s JOIN companies c ON c.id = s.company_id"
                                                " WHERE s.empire_id = %s AND s.bps > 0", (empire_id,))]
    for s in _rows(conn, """
            SELECT p.display_name AS who, s.headline FROM stories s JOIN players p ON p.id = s.author_id
            WHERE s.status = 'published' AND s.period >= %s AND (s.period < %s OR (s.period = %s AND s.day <= %s))
              AND ((s.lead->>'empire_id')::bigint = %s OR (s.lead->>'other_empire_id')::bigint = %s
                   OR s.facts @> %s::jsonb OR s.tickers && %s::text[]
                   OR s.id IN (SELECT story_id FROM investigations WHERE empire_id = %s AND status = 'published'))
            ORDER BY s.id DESC LIMIT 40""",
                   (since, w["period"], w["period"], w["day"], empire_id, empire_id, f'[{{"empire_id": {int(empire_id)}}}]', tickers, empire_id)):
        out.setdefault(s["who"], []).append(f"Wrote: “{s['headline']}”")
    return sorted(({"journalist": k, "traces": v[:8], "count": len(v)} for k, v in out.items()), key=lambda r: -r["count"])


# ---------------------------------------------------------------------------
# Leaks
# ---------------------------------------------------------------------------

def leak(conn: Connection, player_id, kind: str, to_name: str, now: datetime, *, ticker: str | None = None, pact_id: int | None = None) -> dict:
    """A member passes something about their own empire to a journalist: that it holds a company's shares, that it has a hidden
    pact, or what it plans to buy. Only what is so can be passed on. The record keeps who did it."""
    from simulation import empires
    w = _now(conn, now)
    with conn.transaction():
        seat = empires.seat_of(conn, player_id)
        if seat is None or seat.get("empire_status") != "active":
            raise PressError("You have no seat in an open empire.")
        empire = _one(conn, "SELECT * FROM empires WHERE id = %s", (seat["empire_id"],))
        if empire["head_player_id"] == player_id:
            raise PressError("The head speaks for the empire openly; there is nothing for them to leak.")
        to = _one(conn, "SELECT id, build, display_name FROM players WHERE lower(display_name) = lower(%s)", ((to_name or "").strip(),))
        if to is None or to["build"] != "journalist" or to["id"] == player_id:
            raise PressError("Pass it to a Financial Journalist, by name.")
        if _one(conn, "SELECT 1 AS x FROM empire_seats WHERE empire_id = %s AND player_id = %s", (empire["id"], to["id"])):
            raise PressError("That journalist sits in your own empire.")
        if _one(conn, "SELECT count(*) AS n FROM leaks WHERE member_id = %s AND period = %s", (player_id, w["period"]))["n"] >= data.LEAKS_A_QUARTER:
            raise PressError("You have passed something to the press this quarter already.")
        common = {"kind": "leak", "status": "lead", "truth": "true", "period": w["period"], "day": w["day"], "now": now,
                  "empire_id": empire["id"], "useful_until": now + timedelta(hours=data.LEAK_USEFUL_HOURS)}
        if kind == "holding":
            c = _one(conn, "SELECT id, name, share_asset FROM companies WHERE ticker = %s AND listed", ((ticker or "").upper(),))
            if c is None or ledger.balance(conn, empire["account_id"], c["share_asset"]) <= 0:
                raise PressError("Your empire holds no shares in that company.")
            item = intel.make(conn, **common, topic="company", company_id=c["id"], confidential=True, basis=f"holding:{empire['id']}",
                              words=f"From inside {empire['name']}: the empire holds shares in {c['name']}.")
        elif kind == "plan":
            task = _one(conn, "SELECT t.id, c.id AS company_id, c.name FROM empire_tasks t JOIN companies c ON c.id = t.company_id"
                              " WHERE t.empire_id = %s AND t.status = 'open'", (empire["id"],))
            if task is None:
                raise PressError("Your empire has no purchase in hand.")
            item = intel.make(conn, **common, topic="company", company_id=task["company_id"], confidential=True, basis=f"task:{task['id']}",
                              words=f"From inside {empire['name']}: the empire plans to buy into {task['name']}.")
        elif kind == "pact":
            p = _one(conn, "SELECT * FROM empire_pacts WHERE id = %s AND status = 'signed' AND exposed_at IS NULL AND %s IN (from_empire, to_empire)",
                     (pact_id, empire["id"]))
            if p is None:
                raise PressError("Your empire has no such hidden pact.")
            other_id = p["to_empire"] if p["from_empire"] == empire["id"] else p["from_empire"]
            other = _one(conn, "SELECT name FROM empires WHERE id = %s", (other_id,))
            item = intel.make(conn, **{**common, "empire_id": empire["id"]}, other_empire_id=other_id, topic="pact", basis=f"pact:{p['id']}",
                              words=f"From inside {empire['name']}: it has a private understanding with {other['name']}.")
        else:
            raise PressError("Pass on a holding, a plan, or a pact.")
        intel.hold(conn, item["id"], to["id"], "leaked", now, from_player=player_id)
        conn.execute("INSERT INTO leaks (empire_id, member_id, journalist_id, item_id, kind, period, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (empire["id"], player_id, to["id"], item["id"], kind, w["period"], now))
    return {"words": f"{to['display_name']} now has it. Your name is not on it, but a leak can be traced."}


def lead_printed(conn: Connection, story: dict, item: dict, unconfirmed: bool, now: datetime) -> None:
    """A story carrying a piece about an empire has run: a leak to the press, a crisis to answer, or (a pact) the pact comes out."""
    from simulation import empires
    w = _now(conn, now)
    leaked = _one(conn, "SELECT * FROM leaks WHERE item_id = %s FOR UPDATE", (item["id"],))
    if leaked:
        conn.execute("UPDATE leaks SET printed = true WHERE id = %s", (leaked["id"],))
        _log(conn, leaked["empire_id"], "A leak to the press: something from inside the empire has been printed.", now)
        if item["topic"] == "pact":
            pact = _one(conn, "SELECT * FROM empire_pacts WHERE id = %s FOR UPDATE", (int(item["basis"].split(":")[1]),))
            if pact and pact["exposed_at"] is None:
                empires.expose_pact(conn, pact, None, w["period"], now, how="A leak to the press revealed")
            return
        open_crisis(conn, leaked["empire_id"], "leak", f"leak:{leaked['id']}",
                    f"Something from inside the empire was printed: {item['words']}", "true", now)
        return
    for empire_id in {item["empire_id"], item["other_empire_id"]} - {None}:
        if item["topic"] in ("theft", "pact", "empire"):
            open_crisis(conn, empire_id, "report", f"story:{story['id']}", f"A report says: {item['words']}", item["truth"], now)


def leaks_of(conn: Connection, empire_id) -> list[dict]:
    """The empire's leaks that have been printed, and whether each has been hunted. Who leaked is never shown here."""
    out = []
    for r in _rows(conn, "SELECT l.id, l.kind, l.at, i.words, h.found FROM leaks l JOIN intel_items i ON i.id = l.item_id"
                         " LEFT JOIN leak_hunts h ON h.leak_id = l.id WHERE l.empire_id = %s AND l.printed ORDER BY l.id DESC LIMIT 20",
                   (empire_id,)):
        out.append({"id": r["id"], "words": r["words"], "at": r["at"],
                    "hunted": r["found"] is not None, "found": r["found"]})
    return out


def hunt(conn: Connection, player_id, leak_id: int, now: datetime) -> dict:
    """Trace who leaked: once for each leak. The result goes only to whoever hunts (the head or the empire's journalist)."""
    with conn.transaction():
        empire = press_officer(conn, player_id)
        lk = _one(conn, "SELECT * FROM leaks WHERE id = %s AND empire_id = %s AND printed FOR UPDATE", (leak_id, empire["id"]))
        if lk is None:
            raise PressError("There is no such leak from your empire.")
        if lk["member_id"] is None:
            raise PressError("This leak came from outside the empire's seats: there is nobody inside to trace.")
        if _one(conn, "SELECT 1 AS x FROM leak_hunts WHERE leak_id = %s", (leak_id,)):
            raise PressError("This leak has been hunted already.")
        low, high = data.LEAK_HUNT_RANGE_BPS
        chance = min(max(data.LEAK_HUNT_BPS + (_level(conn, player_id) - _level(conn, lk["member_id"])) * data.LEAK_HUNT_PER_LEVEL_BPS, low), high)
        found = _roll(conn, "hunt", leak_id) < chance
        conn.execute("INSERT INTO leak_hunts (leak_id, hunter_id, found, at) VALUES (%s, %s, %s, %s)", (leak_id, player_id, found, now))
        if not found:
            return {"found": False, "words": "The hunt found nothing you could prove."}
        name = _one(conn, "SELECT display_name FROM players WHERE id = %s", (lk["member_id"],))["display_name"]
        return {"found": True, "words": f"The leak came from {name}."}


def random_leaks(conn: Connection, period: int, now: datetime) -> int:
    """At the close: each hidden pact may leak to the press on its own (the "leak to the press" empire event)."""
    from simulation import empires
    if not ready(conn):
        return 0
    n = 0
    for p in _rows(conn, "SELECT p.* FROM empire_pacts p JOIN empires a ON a.id = p.from_empire JOIN empires b ON b.id = p.to_empire"
                         " WHERE p.status = 'signed' AND p.exposed_at IS NULL AND a.status = 'active' AND b.status = 'active'"
                         " AND (a.kind = 'player' OR b.kind = 'player') ORDER BY p.id"):
        if intel._roll(conn, "randomleak", p["id"], period) >= data.RANDOM_LEAK_BPS:
            continue
        names = [_one(conn, "SELECT name FROM empires WHERE id = %s", (e,))["name"] for e in (p["from_empire"], p["to_empire"])]
        item = intel.make(conn, kind="leak", topic="pact", truth="true", status="verified", basis=f"pact:{p['id']}", period=period + 1,
                          day=1, now=now, empire_id=p["from_empire"], other_empire_id=p["to_empire"], resolved=True,
                          words=f"Sources say {names[0]} and {names[1]} have a private understanding.")
        conn.execute("INSERT INTO leaks (empire_id, member_id, item_id, kind, period, printed, at) VALUES (%s, NULL, %s, 'random', %s, true, %s)",
                     (p["from_empire"], item["id"], period, now))
        _news(conn, period=period + 1, day=1, kind="leak", story=f"leak:pact:{p['id']}", headline=f"Leak: {names[0]} and {names[1]}",
              body=f"Sources say {names[0]} and {names[1]} have been working to a private understanding. Both have been asked to answer.",
              importance=70)
        empires.expose_pact(conn, p, None, period, now, how="A leak to the press revealed")
        n += 1
    return n


# ---------------------------------------------------------------------------
# Spin, or refuse; and an honest reply
# ---------------------------------------------------------------------------

def _about_empire(conn: Connection, story: dict, empire_id) -> bool:
    lead = story["lead"] or {}
    if empire_id in (lead.get("empire_id"), lead.get("other_empire_id")):
        return True
    if any(c.get("empire_id") == empire_id for c in story["facts"]):
        return True
    if _one(conn, "SELECT 1 AS x FROM investigations WHERE story_id = %s AND empire_id = %s", (story["id"], empire_id)):
        return True
    return bool(story["tickers"]) and bool(_one(conn, "SELECT 1 AS x FROM stake_disclosures s JOIN companies c ON c.id = s.company_id"
                                                      " WHERE s.empire_id = %s AND s.bps > 0 AND c.ticker = ANY(%s)", (empire_id, story["tickers"])))


def ask_spin(conn: Connection, head_id, story_id: int, now: datetime) -> dict:
    """The head asks the empire's journalist to answer a story with a reply that buries or twists it."""
    w = _now(conn, now)
    with conn.transaction():
        empire = _one(conn, "SELECT * FROM empires WHERE head_player_id = %s AND status = 'active' AND kind = 'player'", (head_id,))
        if empire is None:
            raise PressError("Only the head of an empire can ask this.")
        story = _one(conn, "SELECT * FROM stories WHERE id = %s AND status = 'published'", (story_id,))
        if story is None or not _about_empire(conn, story, empire["id"]):
            raise PressError("That is not a story about your empire.")
        j = _one(conn, "SELECT player_id FROM empire_seats WHERE empire_id = %s AND build = 'journalist' AND player_id IS NOT NULL"
                       " ORDER BY slot LIMIT 1", (empire["id"],))
        if j is None:
            raise PressError("Your empire has no Financial Journalist to ask.")
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO spin_requests (empire_id, head_id, journalist_id, story_id, period, at)"
                                 " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                           (empire["id"], head_id, j["player_id"], story_id, w["period"], now))
        except errors.UniqueViolation:
            raise PressError("You have already asked about that story.") from None
    return {"request_id": row["id"]}


def decide_spin(conn: Connection, player_id, request_id: int, comply: bool, words: str | None, now: datetime) -> dict:
    w = _now(conn, now)
    with conn.transaction():
        r = _one(conn, "SELECT * FROM spin_requests WHERE id = %s AND journalist_id = %s FOR UPDATE", (request_id, player_id))
        if r is None or r["status"] != "asked":
            raise PressError("There is no such request waiting for you.")
        if not comply:
            conn.execute("UPDATE spin_requests SET status = 'refused', decided_at = %s WHERE id = %s", (now, request_id))
            conn.execute("UPDATE players SET reputation = least(reputation + %s, 100) WHERE id = %s", (data.SPIN_REFUSED_REPUTATION, player_id))
            _log(conn, r["empire_id"], "The empire's journalist refused the head's request to spin a story.", now)
            return {"words": "You refused. Your name stays clean."}
        text = _words(words, 20, 300, "A reply")
        _one_reply_a_day(conn, r["story_id"], w)
        empire = _one(conn, "SELECT name FROM empires WHERE id = %s", (r["empire_id"],))
        story = _one(conn, "SELECT headline, news_item_id FROM stories WHERE id = %s", (r["story_id"],))
        author = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))
        item = _news(conn, period=w["period"], day=w["day"], kind="reply", story=f"story:{r['story_id']}",
                     headline=f"In reply: {story['headline']}", body=f"For {empire['name']}, {author['display_name']} writes: {text}",
                     author_id=player_id, importance=40, follows=story["news_item_id"])
        conn.execute("UPDATE spin_requests SET status = 'complied', reply_item = %s, decided_at = %s WHERE id = %s", (item, now, request_id))
        standing.change(conn, r["empire_id"], data.SPIN_REPUTATION, "A reply in the press helped its name", w["period"], now, press=True)
    return {"words": "Your reply has gone out."}


def _one_reply_a_day(conn: Connection, story_id: int, w: dict) -> None:
    if _one(conn, "SELECT 1 AS x FROM news_items WHERE kind = 'reply' AND story = %s AND period = %s AND day = %s",
            (f"story:{story_id}", w["period"], w["day"])):
        raise PressError("A reply to that story has gone out today. Reply tomorrow.")


def reply(conn: Connection, player_id, story_id: int, words: str, now: datetime) -> dict:
    """An honest right of reply to a story about the empire, from the press desk."""
    w = _now(conn, now)
    text = _words(words, 20, 300, "A reply")
    with conn.transaction():
        empire = press_officer(conn, player_id)
        story = _one(conn, "SELECT * FROM stories WHERE id = %s AND status = 'published'", (story_id,))
        if story is None or not _about_empire(conn, story, empire["id"]):
            raise PressError("That is not a story about your empire.")
        if _one(conn, "SELECT 1 AS x FROM news_items WHERE kind = 'reply' AND story = %s AND author_id = %s", (f"story:{story_id}", player_id)):
            raise PressError("You have already replied to that story.")
        _one_reply_a_day(conn, story_id, w)
        author = _one(conn, "SELECT display_name FROM players WHERE id = %s", (player_id,))
        _news(conn, period=w["period"], day=w["day"], kind="reply", story=f"story:{story_id}", headline=f"In reply: {story['headline']}",
              body=f"For {empire['name']}, {author['display_name']} writes: {text}", author_id=player_id, importance=40,
              follows=story["news_item_id"])
    return {"words": "Your reply has gone out."}


def raise_spin(conn: Connection, player_id, item_id: int, now: datetime) -> dict:
    """Any player may say a reply was spin. Upheld if the head asked for it and the journalist went along."""
    w = _now(conn, now)
    with conn.transaction():
        item = _one(conn, "SELECT * FROM news_items WHERE id = %s AND kind = 'reply'", (item_id,))
        if item is None:
            raise PressError("There is no such reply.")
        if item["author_id"] == player_id:
            raise PressError("You cannot raise your own reply.")
        if _one(conn, "SELECT 1 AS x FROM spin_raises WHERE item_id = %s AND player_id = %s", (item_id, player_id)):
            raise PressError("You have already raised this reply.")
        conn.execute("INSERT INTO spin_raises (item_id, player_id, at) VALUES (%s, %s, %s)", (item_id, player_id, now))
        r = _one(conn, "SELECT * FROM spin_requests WHERE reply_item = %s FOR UPDATE", (item_id,))
        if r is None:
            conn.execute("UPDATE players SET reputation = greatest(reputation - 1, 0) WHERE id = %s", (player_id,))
            return {"upheld": False, "words": "Not upheld: it was an honest reply. Raising it cost you a little reputation."}
        if r["exposed"]:
            return {"upheld": True, "words": "Upheld, but it had already come out."}
        _spin_out(conn, r, w["period"], now)
        conn.execute("UPDATE players SET reputation = least(reputation + 1, 100) WHERE id = %s", (player_id,))
        return {"upheld": True, "words": "Upheld: the reply was written to mislead, at the head's request."}


def _spin_out(conn: Connection, r: dict, period: int, now: datetime) -> None:
    conn.execute("UPDATE spin_requests SET exposed = true WHERE id = %s", (r["id"],))
    conn.execute("INSERT INTO journalist_profiles (player_id) VALUES (%s) ON CONFLICT DO NOTHING", (r["journalist_id"],))
    conn.execute("UPDATE players SET reputation = greatest(reputation - %s, 0) WHERE id = %s", (data.SPIN_EXPOSED_REPUTATION, r["journalist_id"]))
    conn.execute("UPDATE journalist_profiles SET credibility = greatest(credibility - %s, 0) WHERE player_id = %s",
                 (data.SPIN_EXPOSED_CREDIBILITY, r["journalist_id"]))
    standing.change(conn, r["empire_id"], -data.SPIN_EXPOSED_EMPIRE_REPUTATION, "A reply it put out was shown to be spin", period, now)
    empire = _one(conn, "SELECT name FROM empires WHERE id = %s", (r["empire_id"],))
    w = _now(conn, now)
    _news(conn, period=w["period"], day=w["day"], kind="spin_exposed", story=f"spin:{r['id']}",
          headline=f"{empire['name']}'s reply was spin", body=f"A reply put out for {empire['name']} was written to mislead, at its head's request.",
          importance=60, follows=r["reply_item"])
    _log(conn, r["empire_id"], "A reply the empire put out has been shown to be spin.", now)


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """At the close: spin that has not come out may come out; hidden pacts may leak on their own; open spin requests lapse."""
    if not ready(conn):
        return
    for r in _rows(conn, "SELECT * FROM spin_requests WHERE status = 'complied' AND NOT exposed ORDER BY id"):
        if intel._roll(conn, "spinout", r["id"], period) < data.SPIN_COMES_OUT_BPS:
            _spin_out(conn, r, period, now)
    conn.execute("UPDATE spin_requests SET status = 'lapsed' WHERE status = 'asked' AND period < %s", (period,))
    random_leaks(conn, period, now)


# ---------------------------------------------------------------------------
# The press desk, as the empire sees it
# ---------------------------------------------------------------------------

def desk(conn: Connection, player_id, now: datetime) -> dict:
    empire = press_officer(conn, player_id)
    crises = _rows(conn, "SELECT id, kind, words, opened_at, due_at, status, stance, statement, change FROM crises WHERE empire_id = %s"
                         " ORDER BY id DESC LIMIT 20", (empire["id"],))
    stories = []
    w = _now(conn, now)
    for s in _rows(conn, "SELECT * FROM stories WHERE status = 'published' AND (period < %s OR (period = %s AND day <= %s))"
                         " ORDER BY id DESC LIMIT 200", (w["period"], w["period"], w["day"])):
        if _about_empire(conn, s, empire["id"]):
            stories.append({"id": s["id"], "headline": s["headline"], "readers": s["readers"], "when": clock.period_label(s["period"]),
                            "asked": bool(_one(conn, "SELECT 1 AS x FROM spin_requests WHERE story_id = %s AND empire_id = %s",
                                               (s["id"], empire["id"])))})
        if len(stories) >= 15:
            break
    out = {"empire": empire["name"], "head": empire["head_player_id"] == player_id,
           "crises": [{**c, "stance_words": STANCES.get(c["stance"]) if c["stance"] else None} for c in crises],
           "stances": STANCES, "looking": who_is_looking(conn, empire["id"], now), "leaks": leaks_of(conn, empire["id"]),
           "stories": stories}
    if empire["head_player_id"] == player_id:
        out["requests"] = _rows(conn, "SELECT r.id, s.headline, r.status, r.at FROM spin_requests r JOIN stories s ON s.id = r.story_id"
                                      " WHERE r.empire_id = %s ORDER BY r.id DESC LIMIT 10", (empire["id"],))
    else:
        out["requests"] = _rows(conn, "SELECT r.id, s.headline, r.status, r.at FROM spin_requests r JOIN stories s ON s.id = r.story_id"
                                      " WHERE r.journalist_id = %s ORDER BY r.id DESC LIMIT 10", (player_id,))
    return out


# ---------------------------------------------------------------------------
# The fact-checking desk, and rumours planted by rivals
# ---------------------------------------------------------------------------

def fact_check(conn: Connection, player_id, member_name: str, ref: str, now: datetime) -> dict:
    """The empire's Financial Journalist checks a tip or rumour a member holds, before the member trades on it. The check is done
    at the journalist's own level and paid by them; the member sees the verdict."""
    _journalist(conn, player_id)
    empire = press_officer(conn, player_id)
    member = _one(conn, "SELECT p.id FROM players p JOIN empire_seats s ON s.player_id = p.id WHERE s.empire_id = %s"
                        " AND lower(p.display_name) = lower(%s)", (empire["id"], (member_name or "").strip()))
    if member is None:
        raise PressError("There is no member of your empire by that name.")
    try:
        got = intel.check(conn, member["id"], ref, now, checker=player_id)
    except intel.IntelError as e:
        raise PressError(str(e)) from None
    return got


def plant(conn: Connection, player_id, *, ticker: str | None, empire_name: str | None, tone: int, now: datetime) -> dict:
    """Start a rumour: that something good or bad is coming at a company, or that money is being taken at a rival empire. The rumour
    is yours to sell or pass on; whether it is true is for the world to decide. Who started it is kept (for the courts, Stage 11).
    Once a real day, from an empire's press desk."""
    _journalist(conn, player_id)
    mine = press_officer(conn, player_id)
    w = _now(conn, now)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('plant:' || %s))", (str(player_id),))
        if _one(conn, "SELECT 1 AS x FROM intel_items WHERE planted_by = %s AND found_at > %s", (player_id, now - timedelta(hours=24))):
            raise PressError("One rumour a day.")
        common = {"kind": "rumour", "status": "rumour", "period": w["period"], "day": w["day"], "now": now, "planted_by": player_id,
                  "useful_until": now + timedelta(hours=data.SOURCE_HINT_USEFUL_HOURS)}
        if ticker:
            if tone not in (1, -1):
                raise PressError("Say whether good or bad news is coming.")
            c = _one(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE ticker = %s AND listed", (ticker.upper(),))
            if c is None:
                raise PressError("There is no listed company with that ticker.")
            evs = intel.coming(conn, c, w["period"], w["day"])
            truth = "true" if evs and intel._effect_tone(evs) == tone else "false"
            item = intel.make(conn, **common, topic="company", company_id=c["id"], tone=tone, truth=truth,
                              basis=("event:" + ",".join(str(e["id"]) for e in evs)) if truth == "true" else "none",
                              resolves=(w["period"], min(e["day"] for e in evs) if truth == "true" else 90),
                              words=intel._company_words(c, tone, int(now.timestamp()), inside=False))
        else:
            e = _one(conn, "SELECT * FROM empires WHERE lower(name) = lower(%s) AND status = 'active' AND kind IN ('player', 'computer')",
                     ((empire_name or "").strip(),))
            if e is None or e["id"] == mine["id"]:
                raise PressError("Name a rival empire.")
            thefts = [b for b in intel._unfound_thefts(conn) if b["empire_id"] == e["id"]]
            item = intel.make(conn, **common, topic="theft", empire_id=e["id"], truth="true" if thefts else "false",
                              basis=f"book:{thefts[0]['id']}" if thefts else "none", resolves=None if thefts else (w["period"] + 1, 90),
                              words=f"Someone at {e['name']} may be taking the empire's money, dressed up as an ordinary payment.")
        intel.hold(conn, item["id"], player_id, "found", now)
    return intel.public(conn, item, now, with_words=True)
