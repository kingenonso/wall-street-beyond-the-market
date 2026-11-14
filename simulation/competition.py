"""Competition, part 1 (owner, 14 November 2026: "the main aim for this game is to compete with other empires and
players").

Two kinds of work with a winner, both read from what the world then does, so nobody can argue with the result:

  Contested mandates   A company selling new shares invites every empire to pitch to arrange the sale. An empire's
                       Investment Banker (or its head) names a fee and forecasts how much of the issue will be taken
                       up. The company chooses for itself, from the record: the lowest fee once it allows for how far it
                       trusts the banker (their level, and how close their empire's past forecasts came). Pitches are
                       sealed until it chooses, and it never chooses by who asked first. The winner is paid its fee on
                       what is actually raised, and earns its empire league points. The others get nothing.

  Ranked work          Each quarter, one company for each build and one figure about it: the Asset Manager forecasts
                       its share price at the close, the Investment Banker its sales, the Risk Manager its profit or
                       loss. Forecasts close a third of the way into the quarter and are sealed until it closes. Then
                       everybody is ranked by how close they came, and the best entry from each empire earns points for
                       it, so a second account in the same empire buys nothing.

Up to Level 5 a player's work is marked alone, as before: a beginner learns before meeting experienced empires.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row

from simulation import careers, clock, empires, ledger, leagues
from simulation import world_data as data
from simulation.money import BPS

MEASURES = {
    "asset_manager": ("close_price", "its share price when the quarter closes"),
    "investment_banker": ("revenue", "its sales for the quarter, as filed"),
    "risk_manager": ("net_profit", "its profit (or loss) for the quarter, as filed"),
}


class CompetitionError(Exception):
    """A request the rules refuse, in words for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def money(kobo: int) -> str:
    sign = "−" if kobo < 0 else ""
    return f"{sign}₦{abs(kobo) / 100:,.2f}"


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('contests') IS NOT NULL AS ok")["ok"] is True


def _hash(*parts) -> int:
    return int.from_bytes(hashlib.blake2b(":".join(str(p) for p in parts).encode(), digest_size=8).digest(), "big")


def _level(conn: Connection, player_id) -> int:
    mine = careers.career(conn, player_id)
    return mine["level"] if mine else 0


def _seat(conn: Connection, player_id) -> dict | None:
    seat = empires.seat_of(conn, player_id)
    if seat is None or seat["empire_status"] != "active" or seat["empire_kind"] == "pension":
        return None
    return seat


def _past_protection(conn: Connection, player_id) -> None:
    if _level(conn, player_id) <= data.COMPETITION_PROTECTED_LEVEL:
        raise CompetitionError(f"Up to Level {data.COMPETITION_PROTECTED_LEVEL} your work is marked alone, while you learn. "
                               f"Competing against other players opens at Level {data.COMPETITION_PROTECTED_LEVEL + 1}.")


# ---------------------------------------------------------------------------
# Contested mandates
# ---------------------------------------------------------------------------

def open_mandates(conn: Connection, period: int, now: datetime) -> int:
    """After a quarter's close: every new sale of shares to existing owners or the public is put out to pitch (a first
    listing has its own underwriters, the small banks), and so is the defence of every company facing a hostile bid.
    Pitches are made in the quarter that follows."""
    made = 0
    for offer in _rows(conn, "SELECT o.* FROM share_offers o WHERE o.status = 'open' AND o.kind IN ('rights', 'public')"
                             " AND o.closes_period = %s AND NOT EXISTS (SELECT 1 FROM mandates m WHERE m.offer_id = o.id)",
                       (period + 1,)):
        conn.execute("INSERT INTO mandates (offer_id, company_id, period, at) VALUES (%s, %s, %s, %s)",
                     (offer["id"], offer["company_id"], period + 1, now))
        made += 1
    if _one(conn, "SELECT 1 AS x FROM information_schema.columns WHERE table_name = 'mandates' AND column_name = 'kind'"):
        for bid in _rows(conn, "SELECT t.* FROM takeovers t WHERE t.status = 'open' AND t.hostile AND t.closes_period = %s"
                               " AND NOT EXISTS (SELECT 1 FROM mandates m WHERE m.takeover_id = t.id)", (period + 1,)):
            conn.execute("INSERT INTO mandates (kind, takeover_id, company_id, period, at) VALUES ('defence', %s, %s, %s, %s)",
                         (bid["id"], bid["target_company_id"], period + 1, now))
            made += 1
    return made


def largest_empire_holder(conn: Connection, company_id) -> dict | None:
    """The empire holding most of a company's shares, and what share of them it holds."""
    row = _one(conn, "SELECT e.id, e.name, b.balance AS held, (SELECT sum(balance) FROM ledger_balances WHERE asset = c.share_asset"
                     " AND balance > 0) AS issued FROM companies c JOIN ledger_balances b ON b.asset = c.share_asset AND b.balance > 0"
                     " JOIN empires e ON e.account_id = b.account_id AND e.status = 'active' WHERE c.id = %s"
                     " ORDER BY b.balance DESC, e.id LIMIT 1", (company_id,))
    if row is None or not row["issued"]:
        return None
    return {"empire_id": row["id"], "name": row["name"], "stake_bps": int(row["held"] * BPS // row["issued"])}


def _track_record_bps(conn: Connection, empire_id) -> int | None:
    """How far an empire's last few forecasts of take-up missed, on mandates it won."""
    rows = _rows(conn, "SELECT p.error_bps FROM mandate_pitches p JOIN mandates m ON m.winner_id = p.id"
                       " WHERE p.empire_id = %s AND p.error_bps IS NOT NULL ORDER BY m.id DESC LIMIT %s",
                 (empire_id, data.MANDATE_RECORD_COUNT))
    if not rows:
        return None
    return sum(r["error_bps"] for r in rows) // len(rows)


def trust_bps(conn: Connection, player_id, empire_id) -> int:
    """What a company trusts a banker for: their level, and how close their empire's forecasts have come."""
    level = min(_level(conn, player_id), data.MANDATE_TRUST_TOP_LEVEL)
    trust = level * data.MANDATE_TRUST_PER_LEVEL_BPS
    record = _track_record_bps(conn, empire_id)
    if record is not None:
        trust += max(data.MANDATE_RECORD_MOST_BPS - record, 0)      # a forecast that missed by nothing earns it all
    return trust


def pitch(conn: Connection, player_id, mandate_id: int, fee_bps: int, take_up_bps: int, now: datetime) -> dict:
    """Pitch for a mandate, for your empire. One pitch for each empire, sealed when it is made."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        _past_protection(conn, player_id)
        seat = _seat(conn, player_id)
        if seat is None:
            raise CompetitionError("Mandates are won by empires. Take a seat in one to pitch.")
        if seat["build"] != "investment_banker" and seat["head_player_id"] != player_id:
            raise CompetitionError("An empire's Investment Banker pitches for mandates, or its head.")
        m = _one(conn, "SELECT * FROM mandates WHERE id = %s FOR UPDATE", (mandate_id,))
        if m is None or m["status"] != "open":
            raise CompetitionError("That mandate is not open for pitches.")
        state = careers.world_now(conn, now)
        if state["period"] != m["period"] or state["day"] > data.MANDATE_PITCH_LAST_DAY:
            raise CompetitionError(f"Pitches close on day {data.MANDATE_PITCH_LAST_DAY} of the quarter.")
        for value, low, high, what in ((fee_bps, data.MANDATE_FEE_LEAST_BPS, data.MANDATE_FEE_MOST_BPS, "The fee"),
                                       (take_up_bps, 0, BPS, "The forecast of take-up")):
            if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
                raise CompetitionError(f"{what} must be between {low / 100:.2f}% and {high / 100:.2f}%.")
        # (For a defence the forecast is of the share of the shares sought that their owners will sell to the bidder.)
        if m.get("kind") == "defence":
            bid = _one(conn, "SELECT bidder_company_id FROM takeovers WHERE id = %s", (m["takeover_id"],))
            behind = largest_empire_holder(conn, bid["bidder_company_id"])
            if behind and behind["empire_id"] == seat["empire_id"] and behind["stake_bps"] >= data.RIVAL_STAKE_BPS:
                raise CompetitionError("Your empire stands behind the bidder. Nobody defends a company against their own bid.")
        if _one(conn, "SELECT 1 AS x FROM mandate_pitches WHERE mandate_id = %s AND empire_id = %s", (mandate_id, seat["empire_id"])):
            raise CompetitionError("Your empire has already pitched for this mandate. A pitch is sealed when it is made.")
        row = _one(conn, "INSERT INTO mandate_pitches (mandate_id, empire_id, player_id, fee_bps, take_up_bps, at)"
                         " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                   (mandate_id, seat["empire_id"], player_id, fee_bps, take_up_bps, now))
        return {"pitch_id": row["id"], "mandate_id": mandate_id, "fee_bps": fee_bps, "take_up_bps": take_up_bps}


def award(conn: Connection, period: int, now: datetime) -> int:
    """At the close, before the sale is settled: each company chooses the pitch that is best for it. It reads the fee and
    what it trusts the banker for, never the outcome, and a tie goes by lot, never to whoever asked first."""
    if not ready(conn):
        return 0
    chosen = 0
    for m in _rows(conn, "SELECT * FROM mandates WHERE status = 'open' AND period = %s ORDER BY id FOR UPDATE", (period,)):
        pitches = _rows(conn, "SELECT * FROM mandate_pitches WHERE mandate_id = %s", (m["id"],))
        if m.get("kind") == "defence":
            going = _one(conn, "SELECT status FROM takeovers WHERE id = %s", (m["takeover_id"],))["status"] == "open"
        else:
            going = _one(conn, "SELECT status FROM share_offers WHERE id = %s", (m["offer_id"],))["status"] == "open"
        if not pitches or not going:
            conn.execute("UPDATE mandates SET status = 'lapsed', words = %s WHERE id = %s",
                         ("No empire pitched for it." if not pitches else "The sale did not go ahead.", m["id"]))
            continue
        scored = []
        for p in pitches:
            t = trust_bps(conn, p["player_id"], p["empire_id"])
            conn.execute("UPDATE mandate_pitches SET trust_bps = %s WHERE id = %s", (t, p["id"]))
            scored.append((p["fee_bps"] * (BPS - t), _hash("mandate", m["id"], p["empire_id"]), p))
        best = min(scored, key=lambda s: (s[0], s[1]))[2]
        conn.execute("UPDATE mandates SET status = 'awarded', winner_id = %s WHERE id = %s", (best["id"], m["id"]))
        chosen += 1
    return chosen


def settle(conn: Connection, period: int, now: datetime) -> int:
    """After the sale is settled: the winner is paid its fee on what was raised, every forecast is scored against what
    was taken up, and the winner's empire earns its points."""
    if not ready(conn):
        return 0
    paid_total = 0
    for m in _rows(conn, "SELECT m.*, o.raised, o.shares, o.shares_sold, o.status AS offer_status, c.name, c.account_id"
                         " FROM mandates m JOIN share_offers o ON o.id = m.offer_id JOIN companies c ON c.id = m.company_id"
                         " WHERE m.status = 'awarded' AND m.period = %s AND m.offer_id IS NOT NULL ORDER BY m.id", (period,)):
        if m["offer_status"] != "done":
            conn.execute("UPDATE mandates SET status = 'lapsed', words = 'The sale did not go ahead.' WHERE id = %s", (m["id"],))
            continue
        taken = (m["shares_sold"] or 0) * BPS // max(m["shares"], 1)
        for p in _rows(conn, "SELECT * FROM mandate_pitches WHERE mandate_id = %s", (m["id"],)):
            conn.execute("UPDATE mandate_pitches SET error_bps = %s WHERE id = %s", (abs(p["take_up_bps"] - taken), p["id"]))
        win = _one(conn, "SELECT p.*, e.account_id, e.name AS empire FROM mandate_pitches p JOIN empires e ON e.id = p.empire_id"
                         " WHERE p.id = %s", (m["winner_id"],))
        fee = (m["raised"] or 0) * win["fee_bps"] // BPS
        got = ledger.pay_up_to(conn, payer=m["account_id"], receiver=win["account_id"], wanted=fee, kind="mandate_fee",
                               memo=f"{win['empire']}'s fee for arranging {m['name']}'s sale of shares", period=period) if fee else 0
        conn.execute("UPDATE mandates SET status = 'settled', taken_up_bps = %s, fee_paid = %s, words = %s WHERE id = %s",
                     (taken, got, f"{win['empire']} arranged it for {win['fee_bps'] / 100:.2f}% and was paid {money(got)}.",
                      m["id"]))
        leagues.award(conn, win["empire_id"], data.LEAGUE_POINTS["mandate"], f"Won the mandate for {m['name']}'s sale of shares",
                      period, now, reference=f"mandate:{m['id']}")
        paid_total += got
    if _one(conn, "SELECT 1 AS x FROM information_schema.columns WHERE table_name = 'mandates' AND column_name = 'kind'"):
        paid_total += _settle_defences(conn, period, now)
    return paid_total


def _settle_defences(conn: Connection, period: int, now: datetime) -> int:
    """After the bid has closed: if it failed, the defender is paid its fee on what the bid was worth, and earns its
    points; if it succeeded, the defender is paid nothing. Every forecast of how much was sold is scored either way."""
    paid_total = 0
    for m in _rows(conn, "SELECT m.*, t.status AS bid_status, t.accepted, t.shares_sought, t.price, c.name, c.account_id"
                         " FROM mandates m JOIN takeovers t ON t.id = m.takeover_id JOIN companies c ON c.id = m.company_id"
                         " WHERE m.status = 'awarded' AND m.period = %s AND m.kind = 'defence' ORDER BY m.id", (period,)):
        if m["bid_status"] == "open":
            continue                                   # (settled at a later close)
        sold = min((m["accepted"] or 0) * BPS // max(m["shares_sought"], 1), BPS)
        for p in _rows(conn, "SELECT * FROM mandate_pitches WHERE mandate_id = %s", (m["id"],)):
            conn.execute("UPDATE mandate_pitches SET error_bps = %s WHERE id = %s", (abs(p["take_up_bps"] - sold), p["id"]))
        win = _one(conn, "SELECT p.*, e.account_id, e.name AS empire FROM mandate_pitches p JOIN empires e ON e.id = p.empire_id"
                         " WHERE p.id = %s", (m["winner_id"],))
        got = 0
        if m["bid_status"] == "failed":
            fee = m["price"] * m["shares_sought"] * win["fee_bps"] // BPS
            got = ledger.pay_up_to(conn, payer=m["account_id"], receiver=win["account_id"], wanted=fee, kind="mandate_fee",
                                   memo=f"{win['empire']}'s fee for defending {m['name']} against a takeover", period=period)
            words = f"{win['empire']} defended it, and the bid failed: paid {money(got)} at {win['fee_bps'] / 100:.2f}%."
            leagues.award(conn, win["empire_id"], data.LEAGUE_POINTS["defence"], f"Defended {m['name']} against a takeover",
                          period, now, reference=f"defence:{m['id']}")
        else:
            words = f"{win['empire']} defended it, but the bid succeeded: no fee."
        conn.execute("UPDATE mandates SET status = 'settled', taken_up_bps = %s, fee_paid = %s, words = %s WHERE id = %s",
                     (sold, got, words, m["id"]))
        paid_total += got
    return paid_total


# ---------------------------------------------------------------------------
# Calls on rivals (part 2)
# ---------------------------------------------------------------------------

CALLS = {
    "overvalued": {"build": "asset_manager", "name": "Overvalued",
                   "words": "its share price falls by a tenth or more within two quarters"},
    "weak_bank": {"build": "risk_manager", "name": "A weak bank",
                  "words": "its credit rating is cut within two quarters"},
}
RATINGS = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")


def _price(conn: Connection, company_id) -> int | None:
    row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s", (company_id,))
    return row["p"] if row else None


def _rating(conn: Connection, company_id) -> str | None:
    row = _one(conn, "SELECT credit_rating FROM company_reports WHERE company_id = %s ORDER BY period DESC, version DESC LIMIT 1",
               (company_id,))
    return row["credit_rating"] if row else None


def call_targets(conn: Connection, empire_id, kind: str) -> list[dict]:
    """The companies an empire may make this kind of call on: listed, and held a twentieth or more by another empire."""
    out = []
    for c in _rows(conn, "SELECT c.id, c.ticker, c.name, c.sector FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                         " WHERE c.status = 'trading'" + (" AND c.sector = 'banking'" if kind == "weak_bank" else "")
                         + " ORDER BY c.ticker"):
        holder = largest_empire_holder(conn, c["id"])
        rivals = _rows(conn, "SELECT e.id, e.name, b.balance FROM companies x JOIN ledger_balances b ON b.asset = x.share_asset"
                             " AND b.balance > 0 JOIN empires e ON e.account_id = b.account_id AND e.status = 'active'"
                             " WHERE x.id = %s AND e.id <> %s ORDER BY b.balance DESC, e.id LIMIT 1", (c["id"], empire_id))
        if not rivals or holder is None:
            continue
        issued = holder["stake_bps"] and _one(conn, "SELECT sum(balance) AS s FROM ledger_balances b JOIN companies x"
                                                    " ON x.share_asset = b.asset WHERE x.id = %s AND b.balance > 0", (c["id"],))["s"]
        stake = int(rivals[0]["balance"] * BPS // issued) if issued else 0
        if stake >= data.RIVAL_STAKE_BPS:
            out.append({**c, "rival_id": rivals[0]["id"], "rival": rivals[0]["name"], "rival_stake_bps": stake})
    return out


def make_call(conn: Connection, player_id, kind: str, company_id, now: datetime) -> dict:
    """Call a rival empire's company overvalued, or its bank weak. Public from the moment it is made; the record judges it."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        _past_protection(conn, player_id)
        if kind not in CALLS:
            raise CompetitionError("A call is that a rival's company is overvalued, or that a rival's bank is weak.")
        seat = _seat(conn, player_id)
        if seat is None:
            raise CompetitionError("Calls are made for an empire, against another. Take a seat in one first.")
        if seat["build"] != CALLS[kind]["build"] and seat["head_player_id"] != player_id:
            raise CompetitionError(f"This call is made by an empire's {careers.BUILDS[CALLS[kind]['build']]['name']}, or its head.")
        conn.execute("SELECT 1 FROM empires WHERE id = %s FOR UPDATE", (seat["empire_id"],))
        if _one(conn, "SELECT count(*) AS n FROM rival_calls WHERE empire_id = %s AND status = 'open'",
                (seat["empire_id"],))["n"] >= data.CALL_MOST_OPEN:
            raise CompetitionError(f"An empire may have {data.CALL_MOST_OPEN} calls open at once. Wait for one to be judged.")
        target = next((t for t in call_targets(conn, seat["empire_id"], kind) if str(t["id"]) == str(company_id)), None)
        if target is None:
            raise CompetitionError("A call is made on a listed company in which a rival empire holds a twentieth or more"
                                   + (", and this one must be a bank." if kind == "weak_bank" else "."))
        if _one(conn, "SELECT 1 AS x FROM rival_calls WHERE empire_id = %s AND company_id = %s AND status = 'open'",
                (seat["empire_id"], target["id"])):
            raise CompetitionError("Your empire already has a call open on that company.")
        period = careers.world_now(conn, now)["period"]
        price = _price(conn, target["id"]) if kind == "overvalued" else None
        rating = _rating(conn, target["id"]) if kind == "weak_bank" else None
        if kind == "weak_bank" and rating in (None, "D"):
            raise CompetitionError("That bank's rating cannot be cut any further.")
        row = _one(conn, "INSERT INTO rival_calls (kind, empire_id, player_id, company_id, rival_id, rival_stake_bps, period,"
                         " ends_period, from_price, from_rating, at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                   (kind, seat["empire_id"], player_id, target["id"], target["rival_id"], target["rival_stake_bps"], period,
                    period + data.CALL_QUARTERS - 1, price, rating, now))
        return {"call_id": row["id"], "kind": kind, "company": target["name"], "rival": target["rival"],
                "judged": clock.period_label(period + data.CALL_QUARTERS - 1)}


def judge_calls(conn: Connection, period: int, now: datetime) -> int:
    """At the close of a call's last quarter: the record says whether it was right. A caller's empire that sold the shares
    it called overvalued while the call was open has made its own fall, and the call is void."""
    if _one(conn, "SELECT to_regclass('rival_calls') IS NOT NULL AS ok")["ok"] is not True:
        return 0
    judged = 0
    for c in _rows(conn, "SELECT r.*, c.name, e.account_id FROM rival_calls r JOIN companies c ON c.id = r.company_id"
                         " JOIN empires e ON e.id = r.empire_id WHERE r.status = 'open' AND r.ends_period <= %s ORDER BY r.id",
                   (period,)):
        if c["kind"] == "overvalued":
            rival = _one(conn, "SELECT account_id FROM empires WHERE id = %s", (c["rival_id"],))["account_id"]
            sold = _one(conn, "SELECT coalesce(sum(quantity) FILTER (WHERE seller_account_id = %s), 0) AS caller,"
                              " coalesce(sum(quantity) FILTER (WHERE seller_account_id = %s), 0) AS rival FROM market_trades"
                              " WHERE company_id = %s AND session_date >= %s",
                        (c["account_id"], rival, c["company_id"], c["at"].date()))
            if sold["caller"] or sold["rival"]:
                # Either side selling while the call is open could make the fall itself: the caller to win, or a friendly
                # "rival" to hand it the points. Neither earns anything.
                who = "the caller's own empire" if sold["caller"] else "the rival empire itself"
                conn.execute("UPDATE rival_calls SET status = 'void', outcome = %s WHERE id = %s",
                             (f"Void: {who} sold the shares while the call was open.", c["id"]))
                continue
            now_price = _price(conn, c["company_id"]) or c["from_price"]
            fall = (c["from_price"] - now_price) * BPS // max(c["from_price"], 1)
            right = fall >= data.CALL_FALL_BPS
            outcome = f"The price went from {money(c['from_price'])} to {money(now_price)} ({-fall / 100:+.1f}%)."
        else:
            now_rating = _rating(conn, c["company_id"]) or c["from_rating"]
            right = RATINGS.index(now_rating) > RATINGS.index(c["from_rating"])
            outcome = f"The rating went from {c['from_rating']} to {now_rating}."
        conn.execute("UPDATE rival_calls SET status = %s, outcome = %s WHERE id = %s",
                     ("right" if right else "wrong", outcome, c["id"]))
        what = f"{CALLS[c['kind']]['name'].lower()} call on {c['name']}"
        if right:
            leagues.award(conn, c["empire_id"], data.LEAGUE_POINTS["call_right"], f"Right in its {what}", period, now,
                          reference=f"call:{c['id']}")
            leagues.award(conn, c["rival_id"], -data.LEAGUE_POINTS["call_exposed"], f"Exposed by a rival's {what}", period, now,
                          reference=f"call_exposed:{c['id']}")
        else:
            leagues.award(conn, c["empire_id"], -data.LEAGUE_POINTS["call_wrong"], f"Wrong in its {what}", period, now,
                          reference=f"call:{c['id']}")
        judged += 1
    return judged


SOURCES = (("mandate", "Mandates"), ("defence", "Defences"), ("contest", "Ranked forecasts"), ("call", "Calls on rivals"),
           ("call_exposed", "Exposed by rivals"))


def scoreboard(conn: Connection, now: datetime) -> list[dict]:
    """The league this game year, by what earned each empire its points."""
    season = leagues.season_of(careers.world_now(conn, now)["period"])
    rows = _rows(conn, "SELECT p.empire_id, e.name, split_part(coalesce(p.reference, ''), ':', 1) AS source, sum(p.points)::int AS pts"
                       " FROM league_points p JOIN empires e ON e.id = p.empire_id WHERE p.season = %s"
                       " GROUP BY p.empire_id, e.name, source", (season,))
    known = {k for k, _ in SOURCES}
    board: dict = {}
    for r in rows:
        b = board.setdefault(r["empire_id"], {"empire": r["name"], "total": 0, **{k: 0 for k in known}, "other": 0})
        b[r["source"] if r["source"] in known else "other"] += r["pts"]
        b["total"] += r["pts"]
    return sorted(board.values(), key=lambda b: (-b["total"], b["empire"]))


# ---------------------------------------------------------------------------
# Ranked work
# ---------------------------------------------------------------------------

def open_contests(conn: Connection, period: int, seed: str, now: datetime) -> int:
    """After a quarter's close: next quarter's three forecasts, one company for each build, chosen by lot from the
    companies whose shares trade and whose accounts are filed."""
    if not ready(conn):
        return 0
    nxt = period + 1
    listed = [r["id"] for r in _rows(conn, "SELECT c.id FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                                            " WHERE EXISTS (SELECT 1 FROM company_reports r WHERE r.company_id = c.id"
                                            " AND r.period = %s) ORDER BY c.ticker", (period,))]
    if not listed:
        return 0
    made = 0
    for build, (measure, _words) in MEASURES.items():
        pick = listed[_hash("contest", seed, nxt, build) % len(listed)]
        done = conn.execute("INSERT INTO contests (period, build, company_id, measure, at) VALUES (%s, %s, %s, %s, %s)"
                            " ON CONFLICT (period, build) DO NOTHING", (nxt, build, pick, measure, now)).rowcount
        made += done
    return made


def enter(conn: Connection, player_id, contest_id: int, guess: int, now: datetime) -> dict:
    """Hand in a forecast. One each, sealed when it is handed in, and only in the first third of the quarter."""
    with conn.transaction():
        careers.books_open(conn, now)
        conn.execute("SELECT 1 FROM players WHERE id = %s FOR UPDATE", (player_id,))
        _past_protection(conn, player_id)
        c = _one(conn, "SELECT * FROM contests WHERE id = %s", (contest_id,))
        if c is None or c["status"] != "open":
            raise CompetitionError("That forecast is not open.")
        mine = careers.career(conn, player_id)
        if mine is None or mine["build"] != c["build"]:
            raise CompetitionError("Each build forecasts its own figure. This one is for another build.")
        if careers.current_job(conn, player_id) is None:
            raise CompetitionError("Ranked work is for people in work. Find a job first.")
        state = careers.world_now(conn, now)
        if state["period"] != c["period"] or state["day"] > data.CONTEST_LAST_DAY:
            raise CompetitionError(f"Forecasts close on day {data.CONTEST_LAST_DAY} of the quarter, so nobody forecasts "
                                   "what they can already see.")
        if not isinstance(guess, int) or isinstance(guess, bool) or abs(guess) > 10 ** 17:
            raise CompetitionError("Name a figure.")
        if c["measure"] != "net_profit" and guess <= 0:
            raise CompetitionError("That figure cannot be nought or less.")
        if _one(conn, "SELECT 1 AS x FROM contest_entries WHERE contest_id = %s AND player_id = %s", (contest_id, player_id)):
            raise CompetitionError("You have handed in your forecast. It is sealed until the quarter closes.")
        seat = _seat(conn, player_id)
        row = _one(conn, "INSERT INTO contest_entries (contest_id, player_id, empire_id, guess, at) VALUES (%s, %s, %s, %s, %s)"
                         " RETURNING id", (contest_id, player_id, seat["empire_id"] if seat else None, guess, now))
        return {"entry_id": row["id"], "contest_id": contest_id, "guess": guess}


def _truth(conn: Connection, c: dict) -> int | None:
    if c["measure"] == "close_price":
        row = _one(conn, "SELECT coalesce(last_price, reference_price) AS p FROM market_instruments WHERE company_id = %s",
                   (c["company_id"],))
        return row["p"] if row else None
    report = _one(conn, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s ORDER BY version LIMIT 1",
                  (c["company_id"], c["period"]))
    if report is None:
        return None
    return int(report["figures"]["income_statement"][c["measure"]])


def judge(conn: Connection, period: int, now: datetime) -> int:
    """When the quarter has closed: the figure is read from the record, every forecast is ranked by how close it came,
    and the best entry of each empire earns its empire points (a second account in the same empire buys nothing)."""
    if not ready(conn):
        return 0
    judged = 0
    for c in _rows(conn, "SELECT * FROM contests WHERE period = %s AND status = 'open' ORDER BY id", (period,)):
        truth = _truth(conn, c)
        if truth is None:
            conn.execute("UPDATE contests SET status = 'void' WHERE id = %s", (c["id"],))
            continue
        entries = _rows(conn, "SELECT * FROM contest_entries WHERE contest_id = %s", (c["id"],))
        scored = sorted(((min(abs(e["guess"] - truth) * BPS // max(abs(truth), 1), 10 ** 9), e) for e in entries),
                        key=lambda s: s[0])
        place, last = 0, None
        for n, (error, e) in enumerate(scored, start=1):
            if error != last:
                place, last = n, error                 # an equal miss shares the place
            conn.execute("UPDATE contest_entries SET error_bps = %s, place = %s WHERE id = %s", (error, place, e["id"]))
        empires_in = {e["empire_id"] for _, e in scored if e["empire_id"] is not None}
        if len(empires_in) >= data.CONTEST_LEAST_EMPIRES:
            counted: set = set()
            for error, e in scored:
                if e["empire_id"] is None or e["empire_id"] in counted:
                    continue
                counted.add(e["empire_id"])
                place_now = _one(conn, "SELECT place FROM contest_entries WHERE id = %s", (e["id"],))["place"]
                points = data.CONTEST_POINTS.get(place_now, 0) if error <= data.CONTEST_MOST_ERROR_BPS else 0
                if points:
                    conn.execute("UPDATE contest_entries SET points = %s WHERE id = %s", (points, e["id"]))
                    leagues.award(conn, e["empire_id"], points, f"A member placed {place_now} in the quarter's ranked forecast",
                                  period, now, reference=f"contest:{c['id']}:{e['empire_id']}")
        conn.execute("UPDATE contests SET truth = %s, status = 'judged' WHERE id = %s", (truth, c["id"]))
        judged += 1
    return judged


def at_close(conn: Connection, period: int, seed: str, now: datetime) -> dict:
    """After the quarter has closed and its accounts are filed: forecasts judged, then next quarter's opened, and the
    sales of shares just announced put out to pitch."""
    if not ready(conn):
        return {}
    return {"judged": judge(conn, period, now), "calls": judge_calls(conn, period, now),
            "contests": open_contests(conn, period, seed, now),
            "mandates": open_mandates(conn, period, now)}


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def _company(conn: Connection, company_id) -> dict:
    return _one(conn, "SELECT id, ticker, name, sector FROM companies WHERE id = %s", (company_id,))


def view(conn: Connection, player_id, now: datetime) -> dict:
    """What a player sees: this quarter's forecasts (their own entry only, until the close), the mandates open to pitch
    (their own empire's pitch only, until the company chooses), what was decided before, and the tables."""
    if not ready(conn):
        return {"ready": False}
    state = careers.world_now(conn, now)
    period = state["period"]
    mine = careers.career(conn, player_id)
    seat = _seat(conn, player_id)
    level = mine["level"] if mine else 0
    contests = []
    for c in _rows(conn, "SELECT * FROM contests WHERE period IN (%s, %s) ORDER BY period DESC, build", (period, period - 1)):
        entry = _one(conn, "SELECT guess, error_bps, place, points FROM contest_entries WHERE contest_id = %s AND player_id = %s",
                     (c["id"], player_id))
        judged = c["status"] == "judged"
        top = []
        if judged:
            top = [{"name": r["display_name"], "empire": r["empire"], "guess": r["guess"], "error_bps": r["error_bps"],
                    "place": r["place"], "points": r["points"]}
                   for r in _rows(conn, "SELECT e.guess, e.error_bps, e.place, e.points, p.display_name, x.name AS empire"
                                        " FROM contest_entries e JOIN players p ON p.id = e.player_id"
                                        " LEFT JOIN empires x ON x.id = e.empire_id WHERE e.contest_id = %s"
                                        " ORDER BY e.place, e.id LIMIT 10", (c["id"],))]
        contests.append({
            "id": c["id"], "quarter": clock.period_label(c["period"]), "build": c["build"],
            "build_name": careers.BUILDS[c["build"]]["name"], "company": _company(conn, c["company_id"]),
            "measure": c["measure"], "measure_words": MEASURES[c["build"]][1], "status": c["status"],
            "open": c["status"] == "open" and c["period"] == period and state["day"] <= data.CONTEST_LAST_DAY,
            "yours": bool(mine and mine["build"] == c["build"]), "entry": entry,
            "entries": _one(conn, "SELECT count(*) AS n FROM contest_entries WHERE contest_id = %s", (c["id"],))["n"],
            "truth": c["truth"] if judged else None, "top": top})
    mandates = []
    for m in _rows(conn, "SELECT m.*, coalesce(o.kind, 'defence') AS kind, coalesce(o.price, t.price) AS price,"
                         " coalesce(o.shares, t.shares_sought) AS shares, coalesce(o.reason, 'A hostile bid by ' || b.name ||"
                         " ': the company wants it defeated.') AS reason FROM mandates m LEFT JOIN share_offers o ON o.id = m.offer_id"
                         " LEFT JOIN takeovers t ON t.id = m.takeover_id LEFT JOIN companies b ON b.id = t.bidder_company_id"
                         " WHERE m.period IN (%s, %s) ORDER BY m.period DESC, m.id DESC LIMIT 20", (period, period - 1)):
        ours = _one(conn, "SELECT fee_bps, take_up_bps, error_bps FROM mandate_pitches WHERE mandate_id = %s AND empire_id = %s",
                    (m["id"], seat["empire_id"])) if seat else None
        winner = None
        if m["winner_id"] and m["status"] in ("awarded", "settled"):
            w = _one(conn, "SELECT p.fee_bps, p.take_up_bps, p.error_bps, e.name FROM mandate_pitches p JOIN empires e"
                           " ON e.id = p.empire_id WHERE p.id = %s", (m["winner_id"],))
            winner = {"empire": w["name"], "fee_bps": w["fee_bps"], "take_up_bps": w["take_up_bps"], "error_bps": w["error_bps"]}
        mandates.append({
            "id": m["id"], "quarter": clock.period_label(m["period"]), "company": _company(conn, m["company_id"]),
            "kind": m["kind"], "amount": m["price"] * m["shares"], "reason": m["reason"], "status": m["status"],
            "open": m["status"] == "open" and m["period"] == period and state["day"] <= data.MANDATE_PITCH_LAST_DAY,
            "pitches": _one(conn, "SELECT count(*) AS n FROM mandate_pitches WHERE mandate_id = %s", (m["id"],))["n"],
            "ours": ours, "winner": winner, "taken_up_bps": m["taken_up_bps"], "fee_paid": m["fee_paid"], "words": m["words"]})
    analysts = [{"name": r["display_name"], "build_name": careers.BUILDS[r["build"]]["name"], "entries": r["n"],
                 "average_error_bps": r["avg"], "wins": r["wins"]}
                for r in _rows(conn, "SELECT p.display_name, c.build, count(*) AS n, (avg(e.error_bps))::int AS avg,"
                                     " count(*) FILTER (WHERE e.place = 1) AS wins FROM contest_entries e"
                                     " JOIN contests c ON c.id = e.contest_id JOIN players p ON p.id = e.player_id"
                                     " WHERE c.status = 'judged' GROUP BY p.display_name, c.build"
                                     " HAVING count(*) >= %s ORDER BY avg, n DESC LIMIT 15", (data.ANALYST_TABLE_LEAST,))]
    calls = [{"id": r["id"], "kind": r["kind"], "name": CALLS[r["kind"]]["name"], "words": CALLS[r["kind"]]["words"],
              "empire": r["caller"], "rival": r["rival"], "company": {"ticker": r["ticker"], "name": r["company"]},
              "made": clock.period_label(r["period"]), "judged": clock.period_label(r["ends_period"]), "status": r["status"],
              "outcome": r["outcome"], "ours": bool(seat and r["empire_id"] == seat["empire_id"]),
              "against_us": bool(seat and r["rival_id"] == seat["empire_id"])}
             for r in _rows(conn, "SELECT r.*, a.name AS caller, b.name AS rival, c.ticker, c.name AS company FROM rival_calls r"
                                  " JOIN empires a ON a.id = r.empire_id JOIN empires b ON b.id = r.rival_id"
                                  " JOIN companies c ON c.id = r.company_id ORDER BY (r.status = 'open') DESC, r.id DESC LIMIT 30")]
    can_call = {}
    targets = {}
    if seat and level > data.COMPETITION_PROTECTED_LEVEL:
        for kind, spec in CALLS.items():
            if seat["build"] == spec["build"] or seat["head_player_id"] == player_id:
                can_call[kind] = True
                targets[kind] = [{"id": t["id"], "ticker": t["ticker"], "name": t["name"], "rival": t["rival"],
                                  "rival_stake_bps": t["rival_stake_bps"]} for t in call_targets(conn, seat["empire_id"], kind)]
    can_pitch = bool(seat and level > data.COMPETITION_PROTECTED_LEVEL
                     and (seat["build"] == "investment_banker" or seat["head_player_id"] == player_id))
    return {
        "ready": True, "quarter": clock.period_label(period), "day": state["day"], "level": level,
        "protected": level <= data.COMPETITION_PROTECTED_LEVEL, "protected_level": data.COMPETITION_PROTECTED_LEVEL,
        "contest_last_day": data.CONTEST_LAST_DAY, "pitch_last_day": data.MANDATE_PITCH_LAST_DAY,
        "fee_least_bps": data.MANDATE_FEE_LEAST_BPS, "fee_most_bps": data.MANDATE_FEE_MOST_BPS,
        "empire": seat["empire_name"] if seat else None, "can_pitch": can_pitch,
        "trust_bps": trust_bps(conn, player_id, seat["empire_id"]) if can_pitch else None,
        "contests": contests, "mandates": mandates, "analysts": analysts,
        "calls": calls, "can_call": can_call, "call_targets": targets, "scoreboard": scoreboard(conn, now),
        "call_rules": {"fall_bps": data.CALL_FALL_BPS, "quarters": data.CALL_QUARTERS, "most_open": data.CALL_MOST_OPEN,
                       "stake_bps": data.RIVAL_STAKE_BPS, "right": data.LEAGUE_POINTS["call_right"],
                       "exposed": data.LEAGUE_POINTS["call_exposed"], "wrong": data.LEAGUE_POINTS["call_wrong"],
                       "defence": data.LEAGUE_POINTS["defence"]},
        "points": {"mandate": data.LEAGUE_POINTS["mandate"], "places": data.CONTEST_POINTS,
                   "most_error_bps": data.CONTEST_MOST_ERROR_BPS, "least_empires": data.CONTEST_LEAST_EMPIRES},
    }
