"""Firm challenges (Proven Talent, the talent and funds stage, Part 1).

A firm approved by an administrator sets a challenge: a theme, a start, a time after which no more can join or answer,
and an end. Players join; at the end the game scores every entry, places them, and the firm sees the best finishers who
agreed to be seen. A firm gets its name on the challenge and nothing else: no advantage of any kind inside the world, and
nothing a player wins is money.

Five kinds. The first four are sealed: nothing an entrant does in them touches the live world.

  paper       a paper portfolio: every entrant starts with the same paper cash and deals in the listed shares while the
              market is open, at the average price paid across the day so far (or, before the day's first trade,
              yesterday's closing price), paying a dealing fee, and never more in a day than the real market could have
              supplied. Valued at each day's average price, never the last trade, which one small real trade could move,
              and at the end at the average of the trading day that ends with or after the challenge. Scored on the
              return; a smaller worst fall breaks a tie.
  valuation   value one company: a price for each share, with the reasons. Scored on how close it came to the game's
              own valuation of the company, worked out from the accounts it files at the end of the quarter in which
              answers close (so the answer cannot be copied from figures already out, nor won by trading the share).
  weak_bank   find the weakest bank: scored on the trust savers have in the bank chosen when the challenge ends; a
              bank that has been closed scores best of all.
  forecast    forecast one company's profit for the running quarter: scored on how close it came to the profit
              the company files when the quarter closes.
  live        the entrants' real investing record over the challenge's weeks, worked out exactly as Proven Talent
              works it out. Entrants must join before it starts.

Entrants held back by the honesty checks are scored but not placed, and so are entrants who entered from the same
device as another entrant of the same challenge (one person, one entry).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, ledger, talent
from simulation.money import naira

KINDS = {"paper": "Paper portfolio", "valuation": "Value a company", "weak_bank": "Find the weakest bank",
         "forecast": "Forecast a profit", "live": "Real record"}
KIND_WORDS = {
    "paper": "Every entrant starts with the same paper cash and deals in listed shares while the market is open, at the average"
             " price paid across the day so far. Nothing touches the real market. Scored on the return at the end.",
    "valuation": "Give a price for each share of the company, with your reasons. Scored on how close it comes to the game's own"
                 " valuation of the company, worked out from the accounts it files at the end of this quarter.",
    "weak_bank": "Choose the bank you think is weakest. Scored on how little trust its savers have in it when the challenge ends.",
    "forecast": "Forecast the company's profit for the running quarter. Scored on how close it comes to the profit it files.",
    "live": "Your real investing record over the challenge's weeks, worked out from the game's books. Join before it starts.",
}
PAPER_FEE_BPS = 50
PAPER_DAY_SHARE_BPS = 2_000          # a paper portfolio may buy at most a fifth of what really traded in a share...
PAPER_LOOKBACK_DAYS = 7              # ...a day, on average over the last seven trading days...
PAPER_LEAST_SHARES = 1_000           # ...and never less than this many shares a day
PAPER_CASH_LIMITS = (naira(1_000_000), naira(100_000_000_000))
MAX_OPEN_PER_FIRM = 3
LONGEST = timedelta(weeks=12)
GIVE_UP_AFTER = timedelta(weeks=2)   # a challenge waiting on figures that never come is closed with nobody placed
SHORTEST = timedelta(days=1)


class ChallengeError(Exception):
    """A request about a challenge the rules do not allow. The words are for the player or the firm."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _money(kobo: int) -> str:
    return f"₦{kobo / 100:,.0f}"


def _pct(bps: int) -> str:
    return f"{bps / 100:+.1f}%"


def _challenge(conn: Connection, challenge_id: int, *, lock: bool = False) -> dict:
    c = _one(conn, "SELECT * FROM talent_challenges WHERE id = %s" + (" FOR UPDATE" if lock else ""), (challenge_id,))
    if c is None:
        raise ChallengeError("There is no such challenge.")
    return c


def _company(conn: Connection, ticker: str) -> dict:
    c = _one(conn, "SELECT c.id, c.ticker, c.name, c.sector, c.share_asset, m.halted_reason, coalesce(m.last_price, m.reference_price) AS price"
                   " FROM companies c JOIN market_instruments m ON m.company_id = c.id WHERE c.ticker = %s", ((ticker or "").upper(),))
    if c is None:
        raise ChallengeError(f"There is no listed company with the ticker {ticker!r}.")
    return c


# ---------------------------------------------------------------------------
# Setting a challenge (a firm)
# ---------------------------------------------------------------------------

def create(conn: Connection, firm_id, *, kind: str, title: str, brief: str, opens_at: datetime, locks_at: datetime | None,
           ends_at: datetime, now: datetime, ticker: str | None = None, starting_cash: int = naira(5_000_000_000), top_shown: int = 10) -> dict:
    firm = _one(conn, "SELECT * FROM talent_firms WHERE id = %s FOR UPDATE", (firm_id,))
    if firm is None or firm["status"] != "approved":
        raise ChallengeError("Only a firm an administrator has approved can set challenges.")
    if kind not in KINDS:
        raise ChallengeError("That is not a kind of challenge.")
    title, brief = " ".join(title.split()), brief.strip()
    if not 4 <= len(title) <= 90:
        raise ChallengeError("A title needs 4 to 90 characters.")
    if len(brief) > 1200:
        raise ChallengeError("The brief can be at most 1,200 characters.")
    if opens_at < now - timedelta(minutes=5):
        raise ChallengeError("A challenge cannot start in the past.")
    if kind == "live":
        locks_at = opens_at                             # the real record: everybody must be in before it starts
    locks_at = locks_at or opens_at + (ends_at - opens_at) / 2
    if not (opens_at <= locks_at <= ends_at) or not SHORTEST <= ends_at - opens_at <= LONGEST:
        raise ChallengeError("A challenge runs for between a day and twelve weeks, and closes to new answers between its start and its end.")
    if not 1 <= top_shown <= 50:
        raise ChallengeError("A firm may see between 1 and 50 of the best finishers.")
    open_now = _one(conn, "SELECT count(*) AS n FROM talent_challenges WHERE firm_id = %s AND status = 'open'", (firm_id,))["n"]
    if open_now >= MAX_OPEN_PER_FIRM:
        raise ChallengeError(f"A firm can run at most {MAX_OPEN_PER_FIRM} challenges at a time.")
    company_id = target = None
    if kind in ("valuation", "forecast"):
        company = _company(conn, ticker)
        if company["halted_reason"]:
            raise ChallengeError("Trading in that company is stopped: choose another.")
        company_id = company["id"]
    if kind in ("forecast", "valuation"):
        from simulation import careers
        target = careers.world_now(conn, now)["period"]
        start = talent._start(conn)
        quarter_end = clock.next_quarter_end(now, start) if start else None
        if quarter_end and locks_at > quarter_end - timedelta(hours=1):
            raise ChallengeError("Answers must close at least an hour before the quarter ends: they are scored on what the company"
                                 " files then.")
        ends_at = max(ends_at, quarter_end) if quarter_end else ends_at
    if kind == "paper" and not PAPER_CASH_LIMITS[0] <= starting_cash <= PAPER_CASH_LIMITS[1]:
        raise ChallengeError("Paper cash must be between ₦1 million and ₦100 billion.")
    return _one(conn, "INSERT INTO talent_challenges (firm_id, kind, title, brief, company_id, target_period, starting_cash, opens_at, locks_at,"
                      " ends_at, top_shown, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                (firm_id, kind, title, brief, company_id, target, starting_cash if kind == "paper" else 0, opens_at, locks_at, ends_at,
                 top_shown, now))


def cancel(conn: Connection, firm_id, challenge_id: int, now: datetime) -> None:
    c = _challenge(conn, challenge_id, lock=True)
    if c["firm_id"] != firm_id:
        raise ChallengeError("There is no such challenge.")
    entrants = _one(conn, "SELECT count(*) AS n FROM challenge_entries WHERE challenge_id = %s", (challenge_id,))["n"]
    if c["status"] != "open" or (entrants and now >= c["opens_at"]):
        raise ChallengeError("A challenge that has started with entrants, or has ended, cannot be called off.")
    conn.execute("UPDATE talent_challenges SET status = 'cancelled' WHERE id = %s", (challenge_id,))


# ---------------------------------------------------------------------------
# Taking part (a player)
# ---------------------------------------------------------------------------

def _entry(conn: Connection, challenge_id: int, player_id, *, lock: bool = False) -> dict:
    e = _one(conn, "SELECT * FROM challenge_entries WHERE challenge_id = %s AND player_id = %s" + (" FOR UPDATE" if lock else ""),
             (challenge_id, player_id))
    if e is None:
        raise ChallengeError("Join the challenge first.")
    return e


def join(conn: Connection, challenge_id: int, player_id, seen_by_sponsor: bool, now: datetime) -> dict:
    c = _challenge(conn, challenge_id)
    if c["status"] != "open" or now >= c["locks_at"]:
        raise ChallengeError("This challenge is closed to new entrants.")
    if ledger.player_account_id(conn, player_id) is None:
        raise ChallengeError("Open your account first.")
    row = conn.execute("INSERT INTO challenge_entries (challenge_id, player_id, joined_at, seen_by_sponsor, cash) VALUES (%s, %s, %s, %s, %s)"
                       " ON CONFLICT (challenge_id, player_id) DO NOTHING RETURNING id",
                       (challenge_id, player_id, now, seen_by_sponsor, c["starting_cash"])).fetchone()
    if row is None:
        raise ChallengeError("You have already joined this challenge.")
    return _entry(conn, challenge_id, player_id)


def let_sponsor_see(conn: Connection, challenge_id: int, player_id, on: bool) -> None:
    _entry(conn, challenge_id, player_id)
    conn.execute("UPDATE challenge_entries SET seen_by_sponsor = %s WHERE challenge_id = %s AND player_id = %s", (on, challenge_id, player_id))


def answer(conn: Connection, challenge_id: int, player_id, now: datetime, *, amount: int | None = None, ticker: str | None = None,
           reasons: str = "") -> dict:
    c = _challenge(conn, challenge_id)
    e = _entry(conn, challenge_id, player_id, lock=True)
    if c["kind"] not in ("valuation", "weak_bank", "forecast"):
        raise ChallengeError("This challenge takes no answer: it is scored on what you do.")
    if c["status"] != "open" or not c["opens_at"] <= now < c["locks_at"]:
        raise ChallengeError("Answers are taken only between the challenge's start and the time it closes to answers.")
    reasons = reasons.strip()[:1000]
    company = None
    if c["kind"] == "weak_bank":
        from simulation import deposits
        bank = deposits.bank(conn, (ticker or "").upper()) if ticker else None
        if bank is None:
            raise ChallengeError("Choose one of the banks that keep savers' money.")
        company = bank["id"]
        amount = None
    else:
        if amount is None or (c["kind"] == "valuation" and amount <= 0):
            raise ChallengeError("Give an amount." if c["kind"] == "forecast" else "Give a price above nothing.")
        if abs(amount) > naira(10_000_000_000_000):
            raise ChallengeError("That amount is too large to be a serious answer.")
    conn.execute("UPDATE challenge_entries SET answer = %s, answer_company = %s, answer_text = %s, answered_at = %s WHERE id = %s",
                 (amount, company, reasons, now, e["id"]))
    return _entry(conn, challenge_id, player_id)


def day_price(conn: Connection, company_id, day) -> int:
    """A share's price for a whole trading day: the average paid across the day, weighted by the shares traded, so one small
    trade at the end cannot move it. With no trades that day, the average of the last day before that had trades; failing
    that, the reference price."""
    row = _one(conn, "SELECT (sum(price * quantity)::numeric / nullif(sum(quantity), 0))::bigint AS p FROM market_trades"
                     " WHERE company_id = %s AND session_date = (SELECT max(session_date) FROM market_trades WHERE company_id = %s"
                     " AND session_date <= %s)", (company_id, company_id, day))
    if row and row["p"]:
        return row["p"]
    return _one(conn, "SELECT reference_price AS p FROM market_instruments WHERE company_id = %s", (company_id,))["p"]


def deal_price(conn: Connection, company_id, now: datetime) -> int:
    """The price a paper deal is made at: the average paid across the trading day so far, weighted by shares, so that one
    small real trade cannot move it; before the day's first trade, the reference price (yesterday's close)."""
    today = clock.to_lagos(now).date()
    row = _one(conn, "SELECT (sum(price * quantity)::numeric / nullif(sum(quantity), 0))::bigint AS p FROM market_trades"
                     " WHERE company_id = %s AND session_date = %s AND traded_at <= %s", (company_id, today, now))
    if row and row["p"]:
        return row["p"]
    return _one(conn, "SELECT reference_price AS p FROM market_instruments WHERE company_id = %s", (company_id,))["p"]


def paper_value(conn: Connection, entry: dict, day=None) -> int:
    """A paper portfolio's value: at the live prices, or (for marking and scoring) at a trading day's average prices."""
    held = _rows(conn, "SELECT p.company_id, p.quantity, coalesce(m.last_price, m.reference_price) AS price FROM challenge_positions p"
                       " JOIN market_instruments m ON m.company_id = p.company_id WHERE p.entry_id = %s AND p.quantity > 0", (entry["id"],))
    if day is None:
        return entry["cash"] + sum(h["quantity"] * h["price"] for h in held)
    return entry["cash"] + sum(h["quantity"] * day_price(conn, h["company_id"], day) for h in held)


def _day_room(conn: Connection, entry: dict, company_id, now: datetime) -> int:
    """How many more shares of a company a paper portfolio may buy today: a fifth of what really traded in it on an average
    day lately, less what it bought today already."""
    today = clock.to_lagos(now).date()
    traded = _one(conn, "SELECT coalesce(sum(quantity), 0)::bigint AS q, count(DISTINCT session_date) AS d FROM market_trades"
                        " WHERE company_id = %s AND session_date < %s AND session_date >= %s",
                  (company_id, today, today - timedelta(days=PAPER_LOOKBACK_DAYS * 2)))
    usual = traded["q"] // max(traded["d"], 1)
    room = max(PAPER_LEAST_SHARES, usual * PAPER_DAY_SHARE_BPS // 10_000)
    bought = _one(conn, "SELECT coalesce(sum(quantity), 0)::bigint AS q FROM challenge_trades WHERE entry_id = %s AND company_id = %s"
                        " AND side = 'buy' AND at >= %s", (entry["id"], company_id, datetime.combine(today, datetime.min.time(), tzinfo=clock.LAGOS)))["q"]
    return max(0, room - bought)


def paper_trade(conn: Connection, challenge_id: int, player_id, *, ticker: str, side: str, quantity: int, now: datetime) -> dict:
    c = _challenge(conn, challenge_id)
    if c["kind"] != "paper":
        raise ChallengeError("Only a paper-portfolio challenge has paper dealing.")
    if c["status"] != "open" or not c["opens_at"] <= now < c["ends_at"]:
        raise ChallengeError("Paper dealing is open only while the challenge runs.")
    if clock.market_state(now) != clock.MarketState.OPEN:
        raise ChallengeError("Paper deals are made at the live prices, so only while the market is open (12:00 to 22:00 Lagos time).")
    if side not in ("buy", "sell") or quantity <= 0 or quantity > 1_000_000_000_000:
        raise ChallengeError("Choose to buy or sell a number of shares above nothing.")
    e = _entry(conn, challenge_id, player_id, lock=True)
    company = _company(conn, ticker)
    if company["halted_reason"] or not company["price"]:
        raise ChallengeError("Trading in that company is stopped.")
    price = deal_price(conn, company["id"], now)
    gross = price * quantity
    fee = max(1, gross * PAPER_FEE_BPS // 10_000)
    held = _one(conn, "SELECT * FROM challenge_positions WHERE entry_id = %s AND company_id = %s FOR UPDATE", (e["id"], company["id"]))
    if side == "buy":
        if gross + fee > e["cash"]:
            raise ChallengeError(f"Not enough paper cash: that costs {_money(gross + fee)} with the fee, and you have {_money(e['cash'])}.")
        room = _day_room(conn, e, company["id"], now)
        if quantity > room:
            raise ChallengeError(f"The real market could not have sold you that many today: you may buy at most {room:,} more shares of"
                                 f" {company['ticker']} today (a fifth of what usually trades in a day).")
        conn.execute("UPDATE challenge_entries SET cash = cash - %s WHERE id = %s", (gross + fee, e["id"]))
        conn.execute("INSERT INTO challenge_positions (entry_id, company_id, quantity, cost) VALUES (%s, %s, %s, %s)"
                     " ON CONFLICT (entry_id, company_id) DO UPDATE SET quantity = challenge_positions.quantity + EXCLUDED.quantity,"
                     " cost = challenge_positions.cost + EXCLUDED.cost", (e["id"], company["id"], quantity, gross + fee))
    else:
        if not held or held["quantity"] < quantity:
            raise ChallengeError("You cannot sell paper shares you do not hold: there is no short selling in a paper portfolio.")
        part = held["cost"] * quantity // held["quantity"]
        conn.execute("UPDATE challenge_positions SET quantity = quantity - %s, cost = cost - %s WHERE entry_id = %s AND company_id = %s",
                     (quantity, part, e["id"], company["id"]))
        conn.execute("UPDATE challenge_entries SET cash = cash + %s WHERE id = %s", (gross - fee, e["id"]))
    conn.execute("INSERT INTO challenge_trades (entry_id, company_id, side, quantity, price, fee, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (e["id"], company["id"], side, quantity, price, fee, now))
    return {"price": price, "fee": fee, "cash": _entry(conn, challenge_id, player_id)["cash"]}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _mark_days(conn: Connection, now: datetime) -> None:
    """Each trading day, every paper portfolio's value at the closing prices: for the worst fall that breaks a tie."""
    bell = _one(conn, "SELECT session_date, rung_at FROM closing_bells ORDER BY session_date DESC LIMIT 1")
    if bell is None:
        return
    for c in _rows(conn, "SELECT * FROM talent_challenges WHERE kind = 'paper' AND status = 'open' AND opens_at <= %s AND ends_at >= %s",
                   (bell["rung_at"], bell["rung_at"])):
        for e in _rows(conn, "SELECT e.* FROM challenge_entries e WHERE e.challenge_id = %s AND NOT EXISTS (SELECT 1 FROM challenge_days d"
                             " WHERE d.entry_id = e.id AND d.session_date = %s)", (c["id"], bell["session_date"])):
            conn.execute("INSERT INTO challenge_days (entry_id, session_date, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                         (e["id"], bell["session_date"], paper_value(conn, e, bell["session_date"])))


def _worst_fall(conn: Connection, entry: dict, start: int) -> int:
    peak, worst = start, 0
    for d in _rows(conn, "SELECT value FROM challenge_days WHERE entry_id = %s ORDER BY session_date", (entry["id"],)):
        peak = max(peak, d["value"])
        if peak:
            worst = min(worst, (d["value"] - peak) * 10_000 // peak)
    return worst


def _score(conn: Connection, c: dict, e: dict) -> tuple[int | None, str]:
    kind = c["kind"]
    if kind == "paper":
        value = paper_value(conn, e, _final_day(conn, c) or clock.to_lagos(c["ends_at"]).date())
        ret = (value - c["starting_cash"]) * 10_000 // c["starting_cash"] if c["starting_cash"] else 0
        fall = _worst_fall(conn, e, c["starting_cash"])
        # The return decides; a smaller worst fall breaks a tie (it moves the score by less than one basis point).
        return ret * 10_000 + (10_000 + max(fall, -9_999)), f"{_pct(ret)} (worst fall {fall / 100:.1f}%)"
    if kind == "live":
        ret = talent.window_return_bps(conn, e["player_id"], clock.to_lagos(c["opens_at"]).date(), clock.to_lagos(c["ends_at"]).date())
        if ret is None:
            return None, "Not enough record in the challenge's weeks to score."
        return ret, _pct(ret)
    if kind == "valuation":
        if e["answer"] is None:
            return None, "No answer given."
        fair = _one(conn, "SELECT value_per_share FROM company_valuations WHERE company_id = %s AND period = %s", (c["company_id"], c["target_period"]))
        if not fair or fair["value_per_share"] <= 0:
            return None, "The company could not be valued."
        error = abs(e["answer"] - fair["value_per_share"]) * 10_000 // fair["value_per_share"]
        return -error, f"{error / 100:.1f}% from the game's valuation of {_money(fair['value_per_share'])} a share"
    if kind == "forecast":
        if e["answer"] is None:
            return None, "No answer given."
        result = _one(conn, "SELECT net_profit FROM company_results WHERE company_id = %s AND period = %s", (c["company_id"], c["target_period"]))
        if result is None:
            return None, "The company's results are not filed yet."
        actual = result["net_profit"]
        error = abs(e["answer"] - actual) * 10_000 // max(abs(actual), naira(1_000_000))
        return -error, f"{error / 100:.1f}% from the filed profit of {_money(actual)}"
    if kind == "weak_bank":
        if e["answer_company"] is None:
            return None, "No bank chosen."
        from simulation import crisis, deposits
        if deposits.closed(conn, e["answer_company"]):
            return 200, "The bank chosen was closed: the best answer there could be."
        trust = crisis.trust_now(conn).get(e["answer_company"])
        score = trust["score"] if trust else 76
        return 100 - score, f"Savers' trust in the bank chosen: {score} of 100"
    return None, ""


def _final_day(conn: Connection, c: dict):
    """The trading day a paper portfolio is valued on at the end: the first whose closing bell rang at or after the end, so
    deals made on the last day are never valued at the day before's prices."""
    row = _one(conn, "SELECT min(session_date) AS d FROM closing_bells WHERE rung_at >= %s", (c["ends_at"],))
    return row["d"] if row else None


def _due(conn: Connection, c: dict, now: datetime) -> bool:
    if now < c["ends_at"]:
        return False
    if now >= c["ends_at"] + GIVE_UP_AFTER:
        return True
    if c["kind"] == "paper":
        return _final_day(conn, c) is not None
    if c["kind"] == "forecast":
        return bool(_one(conn, "SELECT 1 AS x FROM company_results WHERE company_id = %s AND period = %s", (c["company_id"], c["target_period"])))
    if c["kind"] == "valuation":
        return bool(_one(conn, "SELECT 1 AS x FROM company_valuations WHERE company_id = %s AND period = %s", (c["company_id"], c["target_period"])))
    return True


def _one_device(conn: Connection, entries: list[dict]) -> set:
    """Entrants who entered from the same device as another entrant of the same challenge (a check not yet cleared)."""
    ids = [e["player_id"] for e in entries]
    return {r["player_id"] for r in _rows(conn, "SELECT DISTINCT player_id FROM talent_flags WHERE kind = 'shared_device' AND cleared_at IS NULL"
                                                " AND player_id = ANY(%s) AND other_id = ANY(%s)", (ids, ids))}


def score_challenge(conn: Connection, c: dict, now: datetime) -> dict | None:
    c = _one(conn, "SELECT * FROM talent_challenges WHERE id = %s FOR UPDATE", (c["id"],))
    if c["status"] != "open":
        return None                                   # scored (or called off) already, perhaps by another server
    entries = _rows(conn, "SELECT * FROM challenge_entries WHERE challenge_id = %s ORDER BY joined_at, id FOR UPDATE", (c["id"],))
    scored = []
    twins = _one_device(conn, entries)
    for e in entries:
        score, words = _score(conn, c, e)
        held = talent.held_back(conn, e["player_id"]) or e["player_id"] in twins
        if held and score is not None:
            words = "Scored, but held back from the places while a routine check is made."
        conn.execute("UPDATE challenge_entries SET score = %s, score_words = %s, place = NULL WHERE id = %s", (score, words, e["id"]))
        if score is not None and not held:
            scored.append((score, e))
    # Ties: the earlier answer (a harder call to make) or, with no answer to give, the earlier entrant.
    scored.sort(key=lambda x: (-x[0], x[1]["answered_at"] or x[1]["joined_at"], x[1]["joined_at"], x[1]["id"]))
    for place, (_, e) in enumerate(scored, start=1):
        conn.execute("UPDATE challenge_entries SET place = %s WHERE id = %s", (place, e["id"]))
    results = {"entrants": len(entries), "placed": len(scored)}
    conn.execute("UPDATE talent_challenges SET status = 'scored', scored_at = %s, results = %s WHERE id = %s", (now, Jsonb(results), c["id"]))
    for e in entries:
        talent.refresh(conn, e["player_id"], now)
    return results


def tick(conn: Connection, now: datetime) -> int:
    _mark_days(conn, now)
    done = 0
    for c in _rows(conn, "SELECT * FROM talent_challenges WHERE status = 'open' AND ends_at <= %s ORDER BY id", (now,)):
        if _due(conn, c, now):
            with conn.transaction():
                done += score_challenge(conn, c, now) is not None
    return done


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _public(conn: Connection, c: dict, now: datetime) -> dict:
    firm = _one(conn, "SELECT name, colour, tagline, website FROM talent_firms WHERE id = %s", (c["firm_id"],))
    company = _one(conn, "SELECT ticker, name FROM companies WHERE id = %s", (c["company_id"],)) if c["company_id"] else None
    entrants = _one(conn, "SELECT count(*) AS n FROM challenge_entries WHERE challenge_id = %s", (c["id"],))["n"]
    phase = ("cancelled" if c["status"] == "cancelled" else "scored" if c["status"] == "scored" else "waiting" if now < c["opens_at"]
             else "open" if now < c["locks_at"] else "running" if now < c["ends_at"] else "scoring")
    return {"id": c["id"], "kind": c["kind"], "kind_name": KINDS[c["kind"]], "kind_words": KIND_WORDS[c["kind"]], "title": c["title"],
            "brief": c["brief"], "firm": firm, "company": company, "starting_cash": c["starting_cash"], "opens_at": c["opens_at"],
            "locks_at": c["locks_at"], "ends_at": c["ends_at"], "phase": phase, "entrants": entrants, "top_shown": c["top_shown"],
            "target_period": clock.period_label(c["target_period"]) if c["target_period"] else None}


def scoreboard(conn: Connection, c: dict, limit: int = 20, *, for_firm: bool = False) -> list[dict]:
    """The places. Players in the game see each other's names; the firm sees the names only of those who agreed to be seen
    by it."""
    if c["status"] != "scored":
        return []
    rows = _rows(conn, "SELECT e.place, p.display_name AS name, e.score_words, e.seen_by_sponsor FROM challenge_entries e"
                       " JOIN players p ON p.id = e.player_id WHERE e.challenge_id = %s AND e.place IS NOT NULL ORDER BY e.place LIMIT %s",
                 (c["id"], limit))
    for r in rows:
        if for_firm and not r["seen_by_sponsor"]:
            r["name"] = "A player who chose not to be seen"
        del r["seen_by_sponsor"]
    return rows


def player_list(conn: Connection, player_id, now: datetime) -> list[dict]:
    """Every challenge a player can see: those open or running, and the last ones scored."""
    out = []
    for c in _rows(conn, "SELECT * FROM talent_challenges WHERE status = 'open' OR (status = 'scored' AND scored_at > %s)"
                         " ORDER BY status, ends_at LIMIT 40", (now - timedelta(weeks=4),)):
        item = _public(conn, c, now)
        e = _one(conn, "SELECT * FROM challenge_entries WHERE challenge_id = %s AND player_id = %s", (c["id"], player_id))
        mine = None
        if e:
            mine = {"seen_by_sponsor": e["seen_by_sponsor"], "answer": e["answer"], "answered_at": e["answered_at"], "answer_text": e["answer_text"],
                    "answer_ticker": None, "score_words": e["score_words"], "place": e["place"]}
            if e["answer_company"]:
                mine["answer_ticker"] = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (e["answer_company"],))["ticker"]
            if c["kind"] == "paper":
                mine["cash"] = e["cash"]
                mine["value"] = paper_value(conn, e)
                mine["holdings"] = _rows(conn, "SELECT c.ticker, c.name, p.quantity, p.cost, coalesce(m.last_price, m.reference_price) AS price"
                                               " FROM challenge_positions p JOIN companies c ON c.id = p.company_id"
                                               " JOIN market_instruments m ON m.company_id = p.company_id WHERE p.entry_id = %s AND p.quantity > 0"
                                               " ORDER BY c.ticker", (e["id"],))
        item["mine"] = mine
        item["scoreboard"] = scoreboard(conn, c)
        out.append(item)
    return out


def firm_list(conn: Connection, firm_id, now: datetime) -> list[dict]:
    """A firm's own challenges, with the best finishers who agreed to be seen by it."""
    out = []
    for c in _rows(conn, "SELECT * FROM talent_challenges WHERE firm_id = %s ORDER BY created_at DESC LIMIT 30", (firm_id,)):
        item = _public(conn, c, now)
        item["scoreboard"] = scoreboard(conn, c, 50, for_firm=True)
        item["finishers"] = []
        if c["status"] == "scored":
            for e in _rows(conn, "SELECT e.place, e.score_words, e.player_id, e.answer_text, p.display_name AS name FROM challenge_entries e"
                                 " JOIN players p ON p.id = e.player_id WHERE e.challenge_id = %s AND e.place IS NOT NULL"
                                 " AND e.place <= %s AND e.seen_by_sponsor ORDER BY e.place", (c["id"], c["top_shown"])):
                show = set(talent.settings(conn, e["player_id"])["show"]) | {"conduct"}
                item["finishers"].append({**e, "badges": [b["label"] for b in talent.badges(conn, e["player_id"])
                                                          if talent.badge_section(b["code"]) in show]})
        out.append(item)
    return out
