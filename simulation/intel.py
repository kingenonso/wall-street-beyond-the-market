"""Stage 10, Part 2: information as a thing in the world (design M29, M31; Journalist 4).

The Intelligence Market. Every piece of information has a record: where it came from and how reliable that source is,
who found it and when, whether it is a rumour, a lead or verified, which companies or empires it concerns, and when it
stops being useful. Who held it, and since when, is kept for good, so "who knew what, when" can be rebuilt. Whether a
piece is true, and what it was drawn from, is known only to the server: a player learns it by checking, by a second
source, or by watching what happens.

  * The Sealed Tip: once each real day every player receives one sealed piece, drawn from something really
    developing and matched to their build. About a third are about something real and still to come, a third are false,
    a third are true but already public. A tip stops being useful four hours after it is opened. About one in ten comes
    from someone inside a company: trading on those while they are useful is dealing on confidential information, kept
    for the courts (Stage 11). Extra tips can never be bought.
  * A holder may check a piece (a fee; right 70% of the time, more for a senior player), sell copies of it on the market,
    give or leak it to a Financial Journalist, trade on it, or ignore it.
  * Sources: a Financial Journalist builds contacts inside companies and in the ministries over two quarters. A source's
    hint is true about 80% of the time; one can be asked once a real day. Printing a source's hint before it is borne out,
    or selling it, may burn the source.
  * Different builds see different pieces of the public record laid out for their work (the desk feed); nobody gets
    hidden data just by asking.

Nothing here is ever sent with its truth, its basis, who planted it, or when it will be settled.
"""

from __future__ import annotations

import contextvars
import secrets
from datetime import datetime, timedelta

from psycopg import Connection, errors
from psycopg.rows import dict_row

from simulation import careers, clock, events, ledger
from simulation import world_data as data
from simulation.money import naira


class IntelError(Exception):
    """Something the rules of the Intelligence Market do not allow. The words are for the player."""


BUILD_WORDS = {"journalist": "Financial Journalist", "lawyer": "Legal Counsel", "accountant": "Accountant",
               "asset_manager": "Asset Manager", "risk_manager": "Risk Manager", "investment_banker": "Investment Banker"}
VERDICTS = {"holds": "It checks out.", "fails": "It does not check out.", "nothing_new": "Nothing new: it is already public."}
STATUS_WORDS = {"rumour": "a rumour", "lead": "a lead", "verified": "verified", "disproved": "disproved"}
GOOD_WORDS = ("good news is coming", "something good is coming", "a lift is coming")
BAD_WORDS = ("trouble is coming", "bad news is coming", "a blow is coming")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_rows(conn, "SELECT to_regclass('intel_items') IS NOT NULL AS ok")[0]["ok"])


def _seed(conn: Connection) -> str:
    return _one(conn, "SELECT fortune_seed FROM world_state")["fortune_seed"]


def _roll(conn: Connection, *parts) -> int:
    from simulation import private
    return private.roll(_seed(conn), "intel", *parts)


def _now(conn: Connection, now: datetime) -> dict:
    return careers.world_now(conn, now)


def lagos_day(now: datetime):
    return clock.to_lagos(now).date()


def _player(conn: Connection, player_id) -> dict:
    p = _one(conn, "SELECT id, display_name, build, reputation FROM players WHERE id = %s", (player_id,))
    if p is None:
        raise IntelError("There is no such player.")
    return p


def _level(conn: Connection, player_id, build: str | None) -> int:
    c = careers.career(conn, player_id, build) if build else None
    return c["level"] if c else 1


# ---------------------------------------------------------------------------
# Making and holding pieces
# ---------------------------------------------------------------------------

def make(conn: Connection, *, kind: str, topic: str, words: str, truth: str, period: int, day: int, now: datetime,
         company_id=None, empire_id=None, other_empire_id=None, city: str | None = None, tone: int = 0, status: str = "rumour",
         basis: str | None = None, planted_by=None, resolves: tuple[int, int] | None = None, confidential: bool = False,
         source_id=None, reliability_bps: int | None = None, found_by=None, useful_until: datetime | None = None,
         resolved: bool = False) -> dict:
    return _one(conn, """
        INSERT INTO intel_items (ref, kind, topic, company_id, empire_id, other_empire_id, city, tone, words, status, truth, basis,
                                 planted_by, resolves_period, resolves_day, confidential, source_id, reliability_bps, found_by,
                                 period, day, found_at, useful_until, resolved_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (secrets.token_urlsafe(9), kind, topic, company_id, empire_id, other_empire_id, city, tone, words[:400], status, truth,
                 basis, planted_by, resolves[0] if resolves else None, resolves[1] if resolves else None, confidential, source_id,
                 reliability_bps, found_by, period, day, now, useful_until, now if resolved else None))


def hold(conn: Connection, item_id: int, player_id, how: str, now: datetime, from_player=None) -> bool:
    row = _one(conn, "INSERT INTO intel_holders (item_id, player_id, how, from_player, at) VALUES (%s, %s, %s, %s, %s)"
                     " ON CONFLICT DO NOTHING RETURNING item_id", (item_id, player_id, how, from_player, now))
    return row is not None


def _item(conn: Connection, ref: str, *, lock: bool = False) -> dict | None:
    return _one(conn, "SELECT * FROM intel_items WHERE ref = %s" + (" FOR UPDATE" if lock else ""), (ref,))


def held(conn: Connection, player_id, ref: str, *, lock: bool = False) -> dict:
    """A piece this player holds, or an error. Nobody can see or use a piece they do not hold."""
    item = _item(conn, ref, lock=lock)
    if item is None or not _one(conn, "SELECT 1 AS x FROM intel_holders WHERE item_id = %s AND player_id = %s", (item["id"], player_id)):
        raise IntelError("You do not hold that piece of information.")
    tip = _one(conn, "SELECT opened_at FROM sealed_tips WHERE item_id = %s AND player_id = %s", (item["id"], player_id))
    if tip and tip["opened_at"] is None:
        raise IntelError("Open your tip first.")
    return item


def useful(item: dict, now: datetime) -> bool:
    return item["status"] != "disproved" and (item["useful_until"] is None or item["useful_until"] > now)


def _about(conn: Connection, item: dict) -> dict:
    out: dict = {"topic": item["topic"]}
    if item["company_id"]:
        c = _one(conn, "SELECT name, ticker FROM companies WHERE id = %s", (item["company_id"],))
        out["company"], out["ticker"] = c["name"], c["ticker"]
    for key, col in (("empire", "empire_id"), ("other_empire", "other_empire_id")):
        if item[col]:
            out[key] = _one(conn, "SELECT name FROM empires WHERE id = %s", (item[col],))["name"]
    if item["city"]:
        out["city"] = item["city"]
    return out


def public(conn: Connection, item: dict, now: datetime, *, with_words: bool) -> dict:
    """A piece as a player may see it: never its truth, its basis, who planted it, or when it will be settled."""
    holders = _one(conn, "SELECT count(*) AS n FROM intel_holders WHERE item_id = %s", (item["id"],))["n"]
    about = _about(conn, item) if with_words or item["topic"] not in ("pact", "theft") else {"topic": item["topic"]}
    out = {"ref": item["ref"], "kind": item["kind"], "about": about, "status": item["status"],
           "status_words": STATUS_WORDS[item["status"]], "confidential": item["confidential"], "reliability_bps": item["reliability_bps"],
           "found": clock.period_label(item["period"]) + f", day {item['day']}", "useful_until": item["useful_until"],
           "useful": useful(item, now), "holders": holders}
    if with_words:
        out["words"] = item["words"]
        out["tone"] = item["tone"]
    return out


# ---------------------------------------------------------------------------
# What is really developing
# ---------------------------------------------------------------------------

def _listed(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE listed AND status = 'trading' ORDER BY ticker")


def _effect_tone(evs: list[dict]) -> int:
    """Good or bad for the company, all things together."""
    score = 0
    for e in evs:
        score += e["sales_bps"] - e["cost_bps"] - e["damage_bps"]
    return 1 if score > 0 else -1 if score < 0 else 0


def coming(conn: Connection, company: dict, period: int, day: int) -> list[dict]:
    """The events still to come this quarter that will reach this company (hidden until their day)."""
    return [e for e in events.load(conn, period) if e["day"] > day and events.touches(e, company)]


def _past(conn: Connection, company: dict, period: int, day: int) -> list[dict]:
    return [e for e in events.load(conn, period) if e["day"] <= day and events.touches(e, company)]


def _company_words(company: dict, tone: int, n: int, *, inside: bool) -> str:
    phrase = (GOOD_WORDS if tone > 0 else BAD_WORDS)[n % 3]
    lead = f"From someone inside {company['name']}" if inside else f"Word around {company['name']}"
    return f"{lead}: {phrase} before the quarter is out."


def _hidden_pacts(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT p.* FROM empire_pacts p JOIN empires a ON a.id = p.from_empire JOIN empires b ON b.id = p.to_empire"
                       " WHERE p.status = 'signed' AND p.exposed_at IS NULL AND a.status = 'active' AND b.status = 'active' ORDER BY p.id")


def _unfound_thefts(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT b.id, b.empire_id FROM empire_books b JOIN empires e ON e.id = b.empire_id"
                       " WHERE NOT b.genuine AND NOT b.found AND e.status = 'active' ORDER BY b.id")


def _empires(conn: Connection) -> list[dict]:
    return _rows(conn, "SELECT id, name FROM empires WHERE status = 'active' AND kind IN ('player', 'computer') ORDER BY id")


def _tip_topic(build: str, r: int) -> str:
    if build == "journalist":
        return "company" if r < 5000 else "pact" if r < 7500 else "theft"
    if build == "lawyer":
        return "pact" if r < 6000 else "company"
    return "company"


def draw(conn: Connection, player: dict, period: int, day: int, now: datetime, key: str) -> dict:
    """Draw one piece of information for a player from what is really developing in the world. `key` makes it the player's own."""
    r = _roll(conn, "kind", key)
    worth = "true" if r < data.TIP_VALUABLE_BPS else "false" if r < data.TIP_VALUABLE_BPS + data.TIP_FALSE_BPS else "worthless"
    topic = _tip_topic(player["build"] or "", _roll(conn, "topic", key))
    pick = _roll(conn, "pick", key)
    common = {"kind": "tip", "period": period, "day": day, "now": now}
    empires_now = _empires(conn)
    if topic == "pact":
        pacts = _hidden_pacts(conn)
        if worth == "true" and pacts:
            p = pacts[pick % len(pacts)]
            names = [_one(conn, "SELECT name FROM empires WHERE id = %s", (e,))["name"] for e in (p["from_empire"], p["to_empire"])]
            return make(conn, **common, topic="pact", truth="true", basis=f"pact:{p['id']}", empire_id=p["from_empire"],
                        other_empire_id=p["to_empire"], words=f"{names[0]} and {names[1]} are said to have a private understanding.")
        if worth == "false" and len(empires_now) >= 2:
            linked = {(p["from_empire"], p["to_empire"]) for p in _rows(conn, "SELECT from_empire, to_empire FROM empire_pacts WHERE status = 'signed'")}
            pairs = [(a, b) for i, a in enumerate(empires_now) for b in empires_now[i + 1:]
                     if (a["id"], b["id"]) not in linked and (b["id"], a["id"]) not in linked]
            if pairs:
                a, b = pairs[pick % len(pairs)]
                return make(conn, **common, topic="pact", truth="false", basis="none", empire_id=a["id"], other_empire_id=b["id"],
                            words=f"{a['name']} and {b['name']} are said to have a private understanding.")
        if worth == "worthless":
            old = _one(conn, "SELECT * FROM empire_pacts WHERE exposed_at IS NOT NULL ORDER BY exposed_at DESC LIMIT 1")
            if old:
                names = [_one(conn, "SELECT name FROM empires WHERE id = %s", (e,))["name"] for e in (old["from_empire"], old["to_empire"])]
                return make(conn, **common, topic="pact", truth="worthless", basis=f"pact:{old['id']}", status="verified", resolved=True,
                            empire_id=old["from_empire"], other_empire_id=old["to_empire"],
                            words=f"{names[0]} and {names[1]} had an understanding between them.")
        topic = "company"
    if topic == "theft":
        thefts = _unfound_thefts(conn)
        if worth == "true" and thefts:
            b = thefts[pick % len(thefts)]
            name = _one(conn, "SELECT name FROM empires WHERE id = %s", (b["empire_id"],))["name"]
            return make(conn, **common, topic="theft", truth="true", basis=f"book:{b['id']}", empire_id=b["empire_id"],
                        words=f"Someone at {name} may be taking the empire's money, dressed up as an ordinary payment.")
        if worth == "false":
            clean = [e for e in empires_now if not any(t["empire_id"] == e["id"] for t in thefts)]
            if clean:
                e = clean[pick % len(clean)]
                return make(conn, **common, topic="theft", truth="false", basis="none", empire_id=e["id"],
                            words=f"Someone at {e['name']} may be taking the empire's money, dressed up as an ordinary payment.")
        if worth == "worthless":
            case = _one(conn, "SELECT c.empire_id, e.name FROM empire_cases c JOIN empires e ON e.id = c.empire_id ORDER BY c.id DESC LIMIT 1")
            if case:
                return make(conn, **common, topic="theft", truth="worthless", basis="case", status="verified", resolved=True,
                            empire_id=case["empire_id"], words=f"An audit at {case['name']} found money taken from the empire.")
        topic = "company"
    companies = _listed(conn)
    if worth == "true":
        live = [(c, coming(conn, c, period, day)) for c in companies]
        live = [(c, evs) for c, evs in live if evs and _effect_tone(evs) != 0]
        if live:
            c, evs = live[pick % len(live)]
            tone = _effect_tone(evs)
            inside = any(events.BY_NAME[e["kind"]].scope == "company" for e in evs) and \
                _roll(conn, "inside", key) < data.TIP_CONFIDENTIAL_BPS
            first = min(e["day"] for e in evs)
            return make(conn, **common, topic="company", truth="true", basis="event:" + ",".join(str(e["id"]) for e in evs),
                        company_id=c["id"], tone=tone, confidential=inside, resolves=(period, first),
                        words=_company_words(c, tone, pick, inside=inside))
        worth = "worthless"            # nothing real is still to come this quarter: the tip is about what is already known
    if worth == "false":
        quiet = [c for c in companies if not coming(conn, c, period, day)]
        if quiet:
            c = quiet[pick % len(quiet)]
            tone = 1 if _roll(conn, "tone", key) < 5000 else -1
            return make(conn, **common, topic="company", truth="false", basis="none", company_id=c["id"], tone=tone,
                        resolves=(period, 90), words=_company_words(c, tone, pick, inside=False))
    # True, but already public: last few days' news.
    seen = [(c, _past(conn, c, period, day)) for c in companies]
    seen = [(c, evs) for c, evs in seen if evs and _effect_tone(evs) != 0] or [(companies[pick % len(companies)], [])]
    c, evs = seen[pick % len(seen)]
    tone = _effect_tone(evs) if evs else 0
    words = (f"{c['name']} has had {'good' if tone > 0 else 'bad'} news this quarter." if tone else
             f"{c['name']} is going about its business as usual.")
    return make(conn, **common, topic="company", truth="worthless", basis="public", company_id=c["id"], tone=tone,
                status="verified", resolved=True, words=words)


# ---------------------------------------------------------------------------
# The Sealed Tip
# ---------------------------------------------------------------------------

def _tip_row(conn: Connection, player_id, now: datetime) -> dict | None:
    return _one(conn, "SELECT * FROM sealed_tips WHERE player_id = %s AND tip_day = %s", (player_id, lagos_day(now)))


def sealed_tip(conn: Connection, player_id, now: datetime) -> dict:
    """Today's Sealed Tip: given once each real day, matched to the player's build. Sealed until opened."""
    player = _player(conn, player_id)
    if not player["build"]:
        raise IntelError("Choose a build first: your tip is matched to the work you do.")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('tip:' || %s))", (str(player_id),))
        row = _tip_row(conn, player_id, now)
        if row is None:
            w = _now(conn, now)
            item = draw(conn, player, w["period"], w["day"], now, f"{player_id}:{lagos_day(now)}")
            conn.execute("INSERT INTO sealed_tips (player_id, tip_day, item_id) VALUES (%s, %s, %s)", (player_id, lagos_day(now), item["id"]))
            row = _tip_row(conn, player_id, now)
    item = _one(conn, "SELECT * FROM intel_items WHERE id = %s", (row["item_id"],))
    if row["opened_at"] is None:
        return {"opened": False, "for": BUILD_WORDS.get(player["build"], player["build"]),
                "words": "A sealed tip for today. Once opened, it is useful for four hours."}
    return {"opened": True, **public(conn, item, now, with_words=True), **_verdict(conn, item["id"], player_id)}


def open_tip(conn: Connection, player_id, now: datetime) -> dict:
    sealed_tip(conn, player_id, now)
    with conn.transaction():
        row = _one(conn, "SELECT * FROM sealed_tips WHERE player_id = %s AND tip_day = %s FOR UPDATE", (player_id, lagos_day(now)))
        if row["opened_at"] is None:
            conn.execute("UPDATE sealed_tips SET opened_at = %s WHERE player_id = %s AND tip_day = %s", (now, player_id, row["tip_day"]))
            conn.execute("UPDATE intel_items SET useful_until = coalesce(useful_until, %s) WHERE id = %s",
                         (now + timedelta(hours=data.TIP_USEFUL_HOURS), row["item_id"]))
            hold(conn, row["item_id"], player_id, "tip", now)
    return sealed_tip(conn, player_id, now)


# ---------------------------------------------------------------------------
# Checking, giving, selling
# ---------------------------------------------------------------------------

def _verdict(conn: Connection, item_id: int, player_id) -> dict:
    v = _one(conn, "SELECT verdict FROM intel_checks WHERE item_id = %s AND player_id = %s", (item_id, player_id))
    return {"check": VERDICTS[v["verdict"]] if v else None}


def check(conn: Connection, player_id, ref: str, now: datetime, *, checker=None) -> dict:
    """Check a piece: a fee, and a verdict that is right most of the time (more often for a senior player). `checker`: an
    empire's journalist checking for a member (the fact-checking desk) uses their own level and pays from their own account."""
    checker = checker or player_id
    with conn.transaction():
        item = held(conn, player_id, ref, lock=True)
        if _one(conn, "SELECT 1 AS x FROM intel_checks WHERE item_id = %s AND player_id = %s", (item["id"], player_id)):
            raise IntelError("This piece has already been checked for you.")
        if item["planted_by"] is not None and item["planted_by"] in (player_id, checker):
            raise IntelError("You started this rumour: there is nothing in it for you to check.")
        who = _player(conn, checker)
        w = _now(conn, now)
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, checker), receiver=ledger.account_id(conn, ledger.TREASURY),
                            amount=naira(data.CHECK_FEE_NAIRA), kind="intel_check", memo="Checking a piece of information", period=w["period"])
        except ledger.InsufficientFunds:
            raise IntelError(f"A check costs ₦{data.CHECK_FEE_NAIRA:,}, and there is not the cash for it.") from None
        right = min(data.CHECK_RIGHT_BPS + data.CHECK_RIGHT_PER_LEVEL_BPS * _level(conn, checker, who["build"]), data.CHECK_RIGHT_MOST_BPS)
        if item["resolved_at"] is not None:
            truth = "holds" if item["status"] == "verified" and item["truth"] != "worthless" else \
                "nothing_new" if item["truth"] == "worthless" else "fails"
        elif item["truth"] == "unknown":
            # A forecast, or a rumour somebody started: nobody can know yet. The check is a coin toss.
            truth = "holds" if _roll(conn, "check-unknown", item["id"], player_id) < 5000 else "fails"
        else:
            truth = {"true": "holds", "false": "fails", "worthless": "nothing_new"}[item["truth"]]
        if item["truth"] != "unknown" and item["resolved_at"] is None and _roll(conn, "check", item["id"], player_id) >= right:
            truth = {"holds": "fails", "fails": "holds", "nothing_new": "holds"}[truth]
        conn.execute("INSERT INTO intel_checks (item_id, player_id, verdict, by_player, at) VALUES (%s, %s, %s, %s, %s)",
                     (item["id"], player_id, truth, checker if checker != player_id else None, now))
    return {"verdict": truth, "words": VERDICTS[truth]}


def give(conn: Connection, player_id, ref: str, to_name: str, now: datetime) -> dict:
    """Give (or leak) a piece to a Financial Journalist. They hold it from now; the record keeps who gave it."""
    with conn.transaction():
        item = held(conn, player_id, ref)
        if not useful(item, now):
            raise IntelError("That piece is no longer useful.")
        to = _one(conn, "SELECT id, build, display_name FROM players WHERE lower(display_name) = lower(%s)", ((to_name or "").strip(),))
        if to is None or to["id"] == player_id:
            raise IntelError("There is no other player of that name.")
        if to["build"] != "journalist":
            raise IntelError("Information is given to a Financial Journalist, who can check it and print it.")
        if not hold(conn, item["id"], to["id"], "given", now, from_player=player_id):
            raise IntelError(f"{to['display_name']} already holds it.")
        if item["source_id"]:
            _maybe_burn(conn, item, "give", now)
    return {"words": f"{to['display_name']} now holds it."}


def offer(conn: Connection, player_id, ref: str, price: int, now: datetime) -> dict:
    """Offer copies of a piece on the Intelligence Market. Buyers see what it is about, its status and its source's reliability;
    only a buyer reads the words."""
    if not naira(data.INTEL_PRICE_LEAST_NAIRA) <= price <= naira(data.INTEL_PRICE_MOST_NAIRA):
        raise IntelError(f"A price is between ₦{data.INTEL_PRICE_LEAST_NAIRA:,} and ₦{data.INTEL_PRICE_MOST_NAIRA:,}.")
    with conn.transaction():
        item = held(conn, player_id, ref)
        if not useful(item, now):
            raise IntelError("That piece is no longer useful, so it cannot be sold.")
        if _one(conn, "SELECT count(*) AS n FROM intel_listings WHERE seller = %s AND status = 'open'", (player_id,))["n"] >= data.INTEL_LISTINGS_MOST:
            raise IntelError(f"At most {data.INTEL_LISTINGS_MOST} pieces on the market at once.")
        try:
            with conn.transaction():
                row = _one(conn, "INSERT INTO intel_listings (item_id, seller, price, at) VALUES (%s, %s, %s, %s) RETURNING id",
                           (item["id"], player_id, price, now))
        except errors.UniqueViolation:
            raise IntelError("You are already offering that piece.") from None
        if item["source_id"]:
            _maybe_burn(conn, item, "sale", now)
    return {"listing_id": row["id"]}


def withdraw(conn: Connection, player_id, listing_id: int) -> None:
    with conn.transaction():
        row = _one(conn, "SELECT * FROM intel_listings WHERE id = %s AND seller = %s AND status = 'open' FOR UPDATE", (listing_id, player_id))
        if row is None:
            raise IntelError("You have no such offer open.")
        conn.execute("UPDATE intel_listings SET status = 'withdrawn' WHERE id = %s", (listing_id,))


def market(conn: Connection, viewer, now: datetime) -> list[dict]:
    """What is offered: what each piece is about and how good it looks, never its words (until bought)."""
    out = []
    for row in _rows(conn, "SELECT l.*, p.display_name AS seller_name FROM intel_listings l JOIN players p ON p.id = l.seller"
                           " WHERE l.status = 'open' ORDER BY l.id DESC LIMIT 100"):
        item = _one(conn, "SELECT * FROM intel_items WHERE id = %s", (row["item_id"],))
        if not useful(item, now):
            continue
        mine = viewer and _one(conn, "SELECT 1 AS x FROM intel_holders WHERE item_id = %s AND player_id = %s", (item["id"], viewer))
        out.append({"listing_id": row["id"], "price": row["price"], "seller": row["seller_name"], "sold": row["sold"],
                    "yours": row["seller"] == viewer, "held": bool(mine), **public(conn, item, now, with_words=bool(mine))})
    return out


def buy(conn: Connection, player_id, listing_id: int, now: datetime) -> dict:
    with conn.transaction():
        row = _one(conn, "SELECT * FROM intel_listings WHERE id = %s AND status = 'open' FOR UPDATE", (listing_id,))
        if row is None:
            raise IntelError("That offer is no longer open.")
        if row["seller"] == player_id:
            raise IntelError("That is your own offer.")
        item = _one(conn, "SELECT * FROM intel_items WHERE id = %s", (row["item_id"],))
        if not useful(item, now):
            raise IntelError("That piece is no longer useful.")
        if _one(conn, "SELECT 1 AS x FROM intel_holders WHERE item_id = %s AND player_id = %s", (item["id"], player_id)):
            raise IntelError("You already hold it.")
        w = _now(conn, now)
        try:
            ledger.transfer(conn, payer=ledger.player_account_id(conn, player_id), receiver=ledger.player_account_id(conn, row["seller"]),
                            amount=row["price"], kind="intel_sale", memo="A piece of information bought on the Intelligence Market",
                            period=w["period"], reference=f"intel_listing:{listing_id}")
        except ledger.InsufficientFunds:
            raise IntelError("You have not the cash for it.") from None
        conn.execute("INSERT INTO intel_sales (listing_id, buyer, price, at) VALUES (%s, %s, %s, %s)", (listing_id, player_id, row["price"], now))
        conn.execute("UPDATE intel_listings SET sold = sold + 1 WHERE id = %s", (listing_id,))
        hold(conn, item["id"], player_id, "bought", now, from_player=row["seller"])
    return public(conn, item, now, with_words=True)


def mine(conn: Connection, player_id, now: datetime, limit: int = 40) -> list[dict]:
    out = []
    for h in _rows(conn, "SELECT h.item_id, h.how, h.at FROM intel_holders h WHERE h.player_id = %s ORDER BY h.at DESC LIMIT %s",
                   (player_id, limit)):
        item = _one(conn, "SELECT * FROM intel_items WHERE id = %s", (h["item_id"],))
        out.append({**public(conn, item, now, with_words=True), "how": h["how"], "since": h["at"], **_verdict(conn, item["id"], player_id)})
    return out


# ---------------------------------------------------------------------------
# Sources (Journalist 4)
# ---------------------------------------------------------------------------

def _journalist(conn: Connection, player_id) -> dict:
    p = _player(conn, player_id)
    if p["build"] != "journalist":
        raise IntelError("Only a Financial Journalist builds sources.")
    return p


def sources_allowed(level: int) -> int:
    return min(data.SOURCES_LEAST + level // 10, data.SOURCES_MOST)


def cultivate(conn: Connection, player_id, kind: str, ticker: str | None, now: datetime) -> dict:
    """Begin building a source inside a company, or in the ministries. It takes two quarters; one new source a quarter."""
    _journalist(conn, player_id)
    level = _level(conn, player_id, "journalist")
    w = _now(conn, now)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('sources:' || %s))", (str(player_id),))
        live = _rows(conn, "SELECT * FROM sources WHERE journalist_id = %s AND status IN ('cultivating', 'active')", (player_id,))
        if len(live) >= sources_allowed(level):
            raise IntelError(f"At your level you can keep {sources_allowed(level)} sources. Drop one first.")
        if _one(conn, "SELECT 1 AS x FROM sources WHERE journalist_id = %s AND started_period = %s", (player_id, w["period"])):
            raise IntelError("One new source a quarter: building trust takes time.")
        company = None
        if kind == "company":
            company = _one(conn, "SELECT id, name FROM companies WHERE ticker = %s AND listed", ((ticker or "").upper(),))
            if company is None:
                raise IntelError("There is no listed company with that ticker.")
        elif kind != "ministry":
            raise IntelError("A source is inside a company or in the ministries.")
        low, high = data.SOURCE_RELIABILITY_RANGE_BPS
        reliability = min(max(data.SOURCE_RELIABILITY_BPS + (level - 20) * data.SOURCE_RELIABILITY_PER_LEVEL_BPS, low), high)
        try:
            with conn.transaction():
                conn.execute("INSERT INTO sources (journalist_id, kind, company_id, started_period, ready_period, reliability_bps, at)"
                             " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                             (player_id, kind, company["id"] if company else None, w["period"], w["period"] + data.SOURCE_QUARTERS,
                              reliability, now))
        except errors.UniqueViolation:
            raise IntelError("You already have a source there.") from None
    return {"words": f"You have begun building a source {'inside ' + company['name'] if company else 'in the ministries'}. "
                     f"It will be ready in {clock.period_label(w['period'] + data.SOURCE_QUARTERS)}."}


def drop_source(conn: Connection, player_id, source_id: int) -> None:
    with conn.transaction():
        if not _one(conn, "UPDATE sources SET status = 'dropped' WHERE id = %s AND journalist_id = %s AND status IN ('cultivating', 'active')"
                          " RETURNING id", (source_id, player_id)):
            raise IntelError("You have no such source.")


def sources(conn: Connection, player_id, now: datetime) -> list[dict]:
    today = lagos_day(now)
    return [{"id": s["id"], "kind": s["kind"], "where": s["company_name"] or "the ministries", "ticker": s["ticker"],
             "status": s["status"], "ready": clock.period_label(s["ready_period"]), "reliability_bps": s["reliability_bps"],
             "asked_today": s["last_asked"] == today}
            for s in _rows(conn, "SELECT s.*, c.name AS company_name, c.ticker FROM sources s LEFT JOIN companies c ON c.id = s.company_id"
                                 " WHERE s.journalist_id = %s AND s.status IN ('cultivating', 'active', 'burned') ORDER BY s.id DESC LIMIT 12",
                           (player_id,))]


def ask_source(conn: Connection, player_id, source_id: int, now: datetime) -> dict:
    """Ask a source what is coming. Once a real day. The hint is true as often as the source is reliable."""
    _journalist(conn, player_id)
    w = _now(conn, now)
    with conn.transaction():
        s = _one(conn, "SELECT * FROM sources WHERE id = %s AND journalist_id = %s FOR UPDATE", (source_id, player_id))
        if s is None or s["status"] not in ("active", "cultivating"):
            raise IntelError("You have no such source.")
        if s["status"] == "cultivating":
            raise IntelError(f"This source is not ready yet: it will be in {clock.period_label(s['ready_period'])}.")
        if s["last_asked"] == lagos_day(now):
            raise IntelError("You have asked this source today. Ask again tomorrow.")
        conn.execute("UPDATE sources SET last_asked = %s WHERE id = %s", (lagos_day(now), source_id))
        honest = _roll(conn, "source", source_id, lagos_day(now)) < s["reliability_bps"]
        useful_until = now + timedelta(hours=data.SOURCE_HINT_USEFUL_HOURS)
        common = {"kind": "source_hint", "status": "lead", "period": w["period"], "day": w["day"], "now": now, "source_id": source_id,
                  "reliability_bps": s["reliability_bps"], "found_by": player_id, "useful_until": useful_until}
        if s["kind"] == "company":
            c = _one(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE id = %s", (s["company_id"],))
            evs = coming(conn, c, w["period"], w["day"])
            tone = _effect_tone(evs)
            said = tone if honest else (-tone if tone else (1 if _roll(conn, "srctone", source_id, lagos_day(now)) < 5000 else -1))
            if said == 0:
                words = f"Your source inside {c['name']}: nothing out of the ordinary is coming this quarter."
            else:
                words = f"Your source inside {c['name']}: {(GOOD_WORDS if said > 0 else BAD_WORDS)[source_id % 3]} before the quarter is out."
            truth = "true" if said == tone else "false"
            first = min((e["day"] for e in evs), default=90)
            item = make(conn, **common, topic="company", company_id=c["id"], tone=said, truth=truth, words=words, confidential=True,
                        basis=("event:" + ",".join(str(e["id"]) for e in evs)) if evs else "none",
                        resolves=(w["period"], first if truth == "true" and evs else 90))
        else:
            item = _ministry_hint(conn, s, honest, common, w)
        hold(conn, item["id"], player_id, "found", now)
    return public(conn, item, now, with_words=True)


def _ministry_hint(conn: Connection, s: dict, honest: bool, common: dict, w: dict) -> dict:
    """A source in the ministries: which way the Central Bank is leaning at this quarter's close, or, in a year when a big
    project is due, where the Government will build. Settled at the close."""
    from simulation import macro
    period = w["period"]
    if period % data.INFRA_EVERY_QUARTERS == 1:
        grown = _rows(conn, """
            SELECT a.location, a.spending * 10000 / greatest(b.spending, 1) AS g FROM household_results a
            JOIN household_results b ON b.location = a.location AND b.period = greatest(a.period - 4, 0)
            WHERE a.period = (SELECT max(period) FROM household_results) ORDER BY g DESC, a.location""")
        cities = [g["location"] for g in grown] or list(data.CITY_COST_BPS)
        city = cities[0] if honest else cities[min(1 + s["id"] % max(len(cities) - 1, 1), len(cities) - 1)]
        # Its truth is settled at the close, against where the project is really announced.
        return make(conn, **common, topic="infrastructure", city=city, truth="unknown", basis="infra",
                    resolves=(period, 90), words=f"Your source in the ministries: the Government's next big project will be in {city}.")
    econ = _one(conn, "SELECT next_policy_rate_bps, inflation_bps FROM economy_results ORDER BY period DESC LIMIT 1")
    rate_now = econ["next_policy_rate_bps"] if econ else data.OPENING_RATE_BPS
    guess, _ = macro.decide_rate(rate_now, econ["inflation_bps"] if econ else data.INFLATION_TARGET_BPS)
    lean = 1 if guess > rate_now else -1 if guess < rate_now else 0
    said = lean if honest else (1 if lean <= 0 else -1)
    words = {1: "the Central Bank is leaning towards raising its rate at the quarter's close.",
             -1: "the Central Bank is leaning towards cutting its rate at the quarter's close.",
             0: "the Central Bank is minded to hold its rate at the quarter's close."}[said]
    return make(conn, **common, topic="rate", tone=-said, truth="unknown", basis=f"rate:{said}",
                resolves=(period, 90), words=f"Your source in the ministries: {words}")


def _maybe_burn(conn: Connection, item: dict, how: str, now: datetime) -> bool:
    """Printing a source's hint before it is borne out, or passing it on, may give the source away."""
    chance = data.SOURCE_BURN_STORY_BPS if how == "story" else data.SOURCE_BURN_SALE_BPS
    if _roll(conn, "burn", item["id"], how) >= chance:
        return False
    conn.execute("UPDATE sources SET status = 'burned', burned_at = %s WHERE id = %s AND status = 'active'", (now, item["source_id"]))
    return True


# ---------------------------------------------------------------------------
# Settling what turned out to be true
# ---------------------------------------------------------------------------

def _settle(conn: Connection, item: dict, outcome: str, now: datetime) -> None:
    status = "verified" if outcome == "true" else "disproved"
    conn.execute("UPDATE intel_items SET status = %s, resolved_at = %s WHERE id = %s", (status, now, item["id"]))
    from simulation import newsroom, press
    newsroom.lead_settled(conn, item, outcome == "true", now)
    press.report_settled(conn, item["id"], now)


def tick(conn: Connection, now: datetime) -> None:
    """Every few minutes: a piece whose day has come is borne out (its event is now in the news); a theft found by an audit,
    or a pact uncovered, bears out what was said of it."""
    if not ready(conn) or not _rows(conn, "SELECT 1 AS x FROM world_state"):
        return
    w = _now(conn, now)
    with conn.transaction():
        for item in _rows(conn, "SELECT * FROM intel_items WHERE resolved_at IS NULL AND truth = 'true' AND basis LIKE 'event:%%'"
                                " AND (resolves_period < %s OR (resolves_period = %s AND resolves_day <= %s)) FOR UPDATE SKIP LOCKED",
                          (w["period"], w["period"], w["day"])):
            _settle(conn, item, "true", now)
        for item in _rows(conn, "SELECT i.* FROM intel_items i JOIN empire_books b ON i.basis = 'book:' || b.id"
                                " WHERE i.resolved_at IS NULL AND b.found FOR UPDATE OF i SKIP LOCKED"):
            _settle(conn, item, "true", now)
        for item in _rows(conn, "SELECT i.* FROM intel_items i WHERE i.resolved_at IS NULL AND i.basis = 'planted' AND i.topic = 'theft'"
                                " AND EXISTS (SELECT 1 FROM empire_books b WHERE b.empire_id = i.empire_id AND NOT b.genuine AND b.found AND b.at <= i.found_at)"
                                " FOR UPDATE SKIP LOCKED"):
            _settle(conn, item, "true", now)
        for item in _rows(conn, "SELECT i.* FROM intel_items i JOIN empire_pacts p ON i.basis = 'pact:' || p.id"
                                " WHERE i.resolved_at IS NULL AND p.exposed_at IS NOT NULL FOR UPDATE OF i SKIP LOCKED"):
            _settle(conn, item, "true", now)


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """At the quarter's close: whatever was said about this quarter is settled against what happened. Sources that have had
    their two quarters become ready."""
    if not ready(conn):
        return
    econ = _one(conn, "SELECT policy_rate_bps, next_policy_rate_bps FROM economy_results WHERE period = %s", (period,))
    project = _one(conn, "SELECT d.city FROM infrastructure_projects i JOIN districts d ON d.id = i.district_id WHERE i.announced_period = %s",
                   (period,))
    for item in _rows(conn, "SELECT * FROM intel_items WHERE resolved_at IS NULL AND resolves_period <= %s ORDER BY id", (period,)):
        if item["topic"] == "rate" and econ:
            moved = (econ["next_policy_rate_bps"] > econ["policy_rate_bps"]) - (econ["next_policy_rate_bps"] < econ["policy_rate_bps"])
            said = int(item["basis"].split(":")[1])
            _settle(conn, item, "true" if said == moved else "false", now)
        elif item["topic"] == "infrastructure":
            _settle(conn, item, "true" if project and project["city"] == item["city"] else "false", now)
        elif item["basis"] == "planted" and item["topic"] == "company":
            c = _one(conn, "SELECT id, ticker, name, sector, headquarters FROM companies WHERE id = %s", (item["company_id"],))
            after = [e for e in events.load(conn, item["period"]) if e["day"] > item["day"] and events.touches(e, c)]
            _settle(conn, item, "true" if after and _effect_tone(after) == item["tone"] else "false", now)

        else:
            _settle(conn, item, "true" if item["truth"] == "true" else "false", now)
    conn.execute("UPDATE sources SET status = 'active' WHERE status = 'cultivating' AND ready_period <= %s", (period + 1,))


# ---------------------------------------------------------------------------
# Dealing on confidential information (kept for the courts, Stage 11)
# ---------------------------------------------------------------------------

ACTING: contextvars.ContextVar = contextvars.ContextVar("intel_acting_player", default=None)


def acting(player_id):
    """Say which member is placing an order for an empire (set around an empire's trade, so a trade is laid only at its door)."""
    return ACTING.set(player_id)


def note_trade(conn: Connection, account, company_id, now: datetime) -> None:
    """Record a trade in a company by a player (or by a member for their empire) who holds a useful piece from someone inside it.
    Only the player who placed the order is recorded."""
    if company_id is None or not ready(conn):
        return
    owner = _one(conn, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))
    players = []
    if owner and owner["player_id"]:
        players = [owner["player_id"]]
    elif ACTING.get() is not None and _one(conn, "SELECT 1 AS x FROM empires e JOIN empire_seats s ON s.empire_id = e.id"
                                                 " WHERE e.account_id = %s AND s.player_id = %s", (account, ACTING.get())):
        players = [ACTING.get()]
    for pid in players:
        for item in _rows(conn, "SELECT i.id FROM intel_items i JOIN intel_holders h ON h.item_id = i.id AND h.player_id = %s"
                                " LEFT JOIN sealed_tips t ON t.item_id = i.id AND t.player_id = %s"
                                " WHERE i.confidential AND i.company_id = %s AND (i.useful_until IS NULL OR i.useful_until > %s)"
                                " AND (t.item_id IS NULL OR t.opened_at IS NOT NULL)", (pid, pid, company_id, now)):
            conn.execute("INSERT INTO confidential_dealings (player_id, account_id, item_id, company_id, at) VALUES (%s, %s, %s, %s, %s)",
                         (pid, account, item["id"], company_id, now))


# ---------------------------------------------------------------------------
# Each build's view of the public record (M29: different builds see different pieces)
# ---------------------------------------------------------------------------

def desk_feed(conn: Connection, player_id, now: datetime, limit: int = 12) -> dict:
    """The public record laid out for the player's work. Nothing here is hidden: it is what anybody could find, sorted for a
    build."""
    p = _player(conn, player_id)
    w = _now(conn, now)
    build = p["build"]
    items: list[dict] = []
    if build == "lawyer":
        for r in _rows(conn, "SELECT a.name AS a, b.name AS b, p.legal, p.exposed_at FROM empire_pacts p JOIN empires a ON a.id = p.from_empire"
                             " JOIN empires b ON b.id = p.to_empire WHERE p.exposed_at IS NOT NULL ORDER BY p.exposed_at DESC LIMIT %s", (limit,)):
            items.append({"what": f"{'An unlawful' if not r['legal'] else 'A lawful'} pact between {r['a']} and {r['b']} came to light.",
                          "at": r["exposed_at"]})
        for r in _rows(conn, "SELECT e.name, r.why, r.at FROM empire_reputation r JOIN empires e ON e.id = r.empire_id"
                             " WHERE r.change < 0 AND (r.why LIKE 'Fined:%%' OR r.why LIKE '%%came to light%%') ORDER BY r.id DESC LIMIT %s", (limit,)):
            items.append({"what": f"{r['name']}: {r['why']}", "at": r["at"]})
    elif build == "accountant":
        for r in _rows(conn, "SELECT c.name, r.period, max(r.version) AS v FROM company_reports r JOIN companies c ON c.id = r.company_id"
                             " GROUP BY c.name, r.period HAVING max(r.version) > 1 ORDER BY r.period DESC LIMIT %s", (limit,)):
            items.append({"what": f"{r['name']} restated its accounts for {clock.period_label(r['period'])}.", "at": None})
        for r in _rows(conn, """
                SELECT c.name, r.period, r.net_profit, r.cash, b.cash AS cash_before FROM company_results r JOIN companies c ON c.id = r.company_id
                JOIN company_results b ON b.company_id = r.company_id AND b.period = r.period - 1
                WHERE r.period = (SELECT max(period) FROM company_results) AND r.net_profit > 0 AND r.cash < b.cash * 8 / 10
                ORDER BY r.net_profit DESC LIMIT %s""", (limit,)):
            items.append({"what": f"{r['name']} reported a profit for {clock.period_label(r['period'])}, but its cash fell by a fifth or more:"
                                  " worth a look at where the money went.", "at": None})
    elif build == "investment_banker":
        for r in _rows(conn, "SELECT e.name AS empire, c.name, s.at FROM stake_disclosures s JOIN empires e ON e.id = s.empire_id"
                             " JOIN companies c ON c.id = s.company_id WHERE s.bps > 0 ORDER BY s.at DESC LIMIT %s", (limit,)):
            items.append({"what": f"{r['empire']} disclosed a stake in {r['name']}.", "at": r["at"]})
        for r in _rows(conn, "SELECT tc.name AS target, t.status, t.opens_period FROM takeovers t JOIN companies tc ON tc.id = t.target_company_id"
                             " WHERE t.opens_period <= %s ORDER BY t.id DESC LIMIT %s", (w["period"], limit)):
            items.append({"what": f"A takeover offer for {r['target']}, made in {clock.period_label(r['opens_period'])} ({r['status']}).",
                          "at": None})
    elif build in ("asset_manager", "risk_manager"):
        for r in _rows(conn, "SELECT s.headline, s.lead_outcome, s.published_at FROM stories s WHERE s.status = 'published' AND s.lead IS NOT NULL"
                             " AND (s.period < %s OR (s.period = %s AND s.day <= %s)) ORDER BY s.published_at DESC LIMIT %s",
                       (w["period"], w["period"], w["day"], limit)):
            outcome = {"confirmed": "borne out", "disproved": "proved wrong", None: "not yet settled"}[r["lead_outcome"]]
            items.append({"what": f"Unconfirmed report: “{r['headline']}”: {outcome}.", "at": r["published_at"]})
        if build == "risk_manager":
            for e in _rows(conn, "SELECT kind, location, sector, day FROM events WHERE period = %s AND day <= %s AND severe ORDER BY day DESC LIMIT %s",
                           (w["period"], w["day"], limit)):
                items.append({"what": f"A severe {e['kind'].replace('_', ' ')} on day {e['day']}"
                                      + (f" in {e['location']}" if e["location"] else "") + ".", "at": None})
    elif build == "journalist":
        for s in sources(conn, player_id, now):
            items.append({"what": f"Your source {'inside ' + s['where'] if s['kind'] == 'company' else 'in the ministries'}: {s['status']}"
                                  + (f", ready {s['ready']}" if s["status"] == "cultivating" else "") + ".", "at": None})
    return {"build": BUILD_WORDS.get(build, build), "items": items[:limit * 2]}
