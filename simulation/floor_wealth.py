"""Floor extras, slice 3 (owner, 17 November 2026: "Ok go ahead"): the wealth desk.

Rich computer clients come to the Floor looking for someone to look after their money, as a family or a pension scheme
picks a fund manager.

  arriving   now and then, while the market is open and an asset manager is playing, a client arrives with a sum
             (₦200m to ₦2bn), a goal and limits, drawn from five kinds: a retired couple (little in shares, no big falls),
             a family office (growth), a church foundation (no drink, gambling or film), a doctors' pension scheme
             (balanced) and a young tech founder (risk, but no oil or mining). It takes pitches for two game days.
  pitching   an asset manager offers a yearly fee (at most 2%) and a share of the gain above the client's goal (at most
             20%). The client weighs what each would cost against each manager's record with clients before, and picks
             one. With no pitch it goes elsewhere. A manager looks after at most three clients.
  managing   the client's money sits in its own account, which its manager trades on the exchange at prices they name.
             A share in an industry the client will not hold is refused. The manager may not deal against their own
             orders, and a manager who dealt in a share for themselves just before the client did is noted by the
             Money Watch (never shown).
  breaches   through the day the client's limits are looked at: too much in shares, too little cash, or a fall from its
             high past what it accepts. Each is recorded once a day and costs the client's satisfaction; three in one
             quarter and the client leaves at once.
  reviews    at each quarter's close the client judges the quarter: its return against a fair benchmark (the share index
             for the part it would hold in shares, the Central Bank's rate for the rest). It pays the fees from its cash,
             then adds a tenth more money (very happy, after beating the benchmark), stays, warns, or leaves.
  leaving    a client that leaves takes everything back: open orders are cancelled and its cash, shares and bonds go
             back to the households. A manager may hand a client back, which counts as a client lost.

The record a client looks at: the satisfaction of the manager's clients at their reviews, and how many clients left.
Every naira moves through the ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from psycopg import Connection

from simulation import (
    careers,
    clock,
    empires,
    exchange,
    ledger,
    lending,
    marketview,
    objectives,
)
from simulation import floor as fl
from simulation import world_data as data
from simulation.floor import BPS, FloorError, _money, _one, _rows, _unit

GAME_DAY_SECONDS = clock.REAL_DAYS_PER_QUARTER * 86_400 // 90
CHECK_SECONDS = 600
KINDS = {k[0]: {"kind": k[0], "goal": k[1], "most_shares_bps": k[2], "least_cash_bps": k[3], "most_drop_bps": k[4], "goal_bps": k[5],
                "banned": list(k[6]), "index_bps": k[7]} for k in data.WEALTH_CLIENT_KINDS}


def ready(conn: Connection) -> bool:
    return _one(conn, "SELECT to_regclass('wealth_clients') IS NOT NULL AS ok")["ok"]


def _pct(bps: int) -> str:
    return f"{bps / 100:.1f}%"


def _index_now(conn: Connection, now: datetime) -> int:
    day, _ = exchange.session_of(now)
    return marketview.index_level(marketview._shares(conn, day), marketview.index_base(conn))


def _sector_names() -> dict:
    return {s.code: s.name for s in data.SECTORS}


# ---------------------------------------------------------------------------
# Arriving and pitching
# ---------------------------------------------------------------------------

def arrive(conn: Connection, now: datetime, *, kind: str | None = None, key=None) -> dict:
    """A new client comes to the Floor looking for a manager."""
    seed = fl._seed(conn)
    key = key if key is not None else int(now.timestamp())
    names = list(KINDS)
    profile = KINDS[kind] if kind else KINDS[names[int(_unit(seed, "wealth-kind", key) * len(names))]]
    surname = data.WEALTH_CLIENT_NAMES[int(_unit(seed, "wealth-name", key) * len(data.WEALTH_CLIENT_NAMES))]
    name = {"retired couple": f"Mr and Mrs {surname}", "family office": f"The {surname} Family Office",
            "church foundation": f"{surname} Memorial Church Foundation", "doctors' pension scheme": f"{surname} Clinic Doctors' Pension",
            "young tech founder": f"{surname}, a young tech founder"}[profile["kind"]]
    low, high = data.WEALTH_CLIENT_NAIRA
    amount = (low + round(_unit(seed, "wealth-size", key) * (high - low))) // 10_000_000 * 10_000_000 * 100
    row = _one(conn, "INSERT INTO wealth_clients (name, kind, goal, amount, most_shares_bps, least_cash_bps, most_drop_bps, goal_bps, banned,"
                     " arrived_at, pitches_until, satisfaction_bps) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
               (name, profile["kind"], profile["goal"], amount, profile["most_shares_bps"], profile["least_cash_bps"],
                profile["most_drop_bps"], profile["goal_bps"], profile["banned"], now,
                now + timedelta(seconds=data.WEALTH_PITCH_GAME_DAYS * GAME_DAY_SECONDS), data.WEALTH_START_SATISFACTION_BPS))
    fl._note(conn, f"wealth-arrive:{row['id']}", "wealth", f"{name} has come to the Floor with {_money(amount)} to be looked after, "
             f"wanting {profile['goal']}. Asset managers may pitch.", now)
    for p in _rows(conn, "SELECT id FROM players WHERE build = 'asset_manager'"):
        fl._ping_player(conn, p["id"])
    return row


def _is_manager(conn: Connection, player_id) -> bool:
    row = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    return bool(row and row["build"] == "asset_manager")


def _managing(conn: Connection, player_id) -> int:
    return _one(conn, "SELECT count(*)::int AS n FROM wealth_clients WHERE manager_id = %s AND status = 'managed'", (player_id,))["n"]


def pitch(conn: Connection, player_id, client_id: int, fee_bps: int, perf_bps: int, now: datetime) -> dict:
    """An asset manager pitches for a client (a new pitch replaces their last)."""
    if not _is_manager(conn, player_id):
        raise FloorError("The wealth desk is an asset manager's: choose that build to look after clients' money.")
    for value, most, what in ((fee_bps, data.WEALTH_MOST_FEE_BPS, "yearly fee"), (perf_bps, data.WEALTH_MOST_PERF_BPS, "share of the gain")):
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= most:
            raise FloorError(f"The {what} may be nought to {_pct(most)}.")
    client = _one(conn, "SELECT * FROM wealth_clients WHERE id = %s FOR UPDATE", (client_id,))
    if client is None or client["status"] != "seeking" or client["pitches_until"] <= now:
        raise FloorError("That client is no longer taking pitches.")
    if _managing(conn, player_id) >= data.WEALTH_MOST_CLIENTS:
        raise FloorError(f"You already look after {data.WEALTH_MOST_CLIENTS} clients, the most one manager may.")
    conn.execute("INSERT INTO wealth_pitches (client_id, manager_id, fee_bps, perf_bps, at) VALUES (%s, %s, %s, %s, %s)"
                 " ON CONFLICT (client_id, manager_id) DO UPDATE SET fee_bps = EXCLUDED.fee_bps, perf_bps = EXCLUDED.perf_bps, at = EXCLUDED.at",
                 (client_id, player_id, fee_bps, perf_bps, now))
    return {"client_id": client_id, "fee_bps": fee_bps, "perf_bps": perf_bps}


def reputation(conn: Connection, manager_id) -> dict:
    """A manager's record with clients: how happy they were at their reviews, and how many left."""
    row = _one(conn, "SELECT count(*)::int AS reviews, coalesce(avg(satisfaction_bps), 0)::int AS satisfaction"
                     " FROM wealth_reviews WHERE manager_id = %s", (manager_id,))
    gone = _one(conn, "SELECT count(*)::int AS n FROM wealth_clients WHERE manager_id = %s AND status = 'left'", (manager_id,))["n"]
    kept = _one(conn, "SELECT count(*)::int AS n FROM wealth_clients WHERE manager_id = %s AND status = 'managed'", (manager_id,))["n"]
    score = ((row["satisfaction"] - data.WEALTH_START_SATISFACTION_BPS) // 10 if row["reviews"] else 0) - 100 * gone
    return {"reviews": row["reviews"], "satisfaction_bps": row["satisfaction"] if row["reviews"] else None, "left": gone, "kept": kept,
            "score": score}


def cost_bps(fee_bps: int, perf_bps: int) -> int:
    """What a pitch is expected to cost a client in a year: the fee, and the share of an expected 4% beyond its goal."""
    return fee_bps + perf_bps * 400 // BPS


def _choose(conn: Connection, client: dict, now: datetime) -> None:
    pitches = _rows(conn, "SELECT * FROM wealth_pitches WHERE client_id = %s AND status = 'live' ORDER BY at", (client["id"],))
    seed = fl._seed(conn)
    best, best_score = None, None
    for p in pitches:
        if _managing(conn, p["manager_id"]) >= data.WEALTH_MOST_CLIENTS:
            continue
        jitter = round(_unit(seed, "wealth-choose", client["id"], p["manager_id"]) * 40) - 20
        score = reputation(conn, p["manager_id"])["score"] - cost_bps(p["fee_bps"], p["perf_bps"]) + jitter
        if best_score is None or score > best_score:
            best, best_score = p, score
    if best is None:
        conn.execute("UPDATE wealth_clients SET status = 'went_elsewhere', left_at = %s, left_why = 'no manager pitched' WHERE id = %s",
                     (now, client["id"]))
        conn.execute("UPDATE wealth_pitches SET status = 'lost' WHERE client_id = %s", (client["id"],))
        return
    period = careers.world_now(conn, now)["period"]
    account = ledger.create_account(conn, kind="fund", name=f"Wealth client: {client['name']}")
    ledger.transfer(conn, payer=ledger.account_id(conn, ledger.INVESTORS_PUBLIC), receiver=account, amount=client["amount"],
                    kind="wealth_mandate", memo=f"{client['name']}: money handed to its manager", period=period,
                    reference=f"wealth-in:{client['id']}")
    conn.execute("UPDATE wealth_clients SET status = 'managed', account_id = %s, manager_id = %s, fee_bps = %s, perf_bps = %s, started_at = %s,"
                 " started_period = %s, review_value = amount, review_index = %s, high_value = amount WHERE id = %s",
                 (account, best["manager_id"], best["fee_bps"], best["perf_bps"], now, period, _index_now(conn, now), client["id"]))
    conn.execute("UPDATE wealth_pitches SET status = CASE WHEN id = %s THEN 'won' ELSE 'lost' END WHERE client_id = %s", (best["id"], client["id"]))
    manager = _one(conn, "SELECT display_name FROM players WHERE id = %s", (best["manager_id"],))["display_name"]
    fl._note(conn, f"wealth-chose:{client['id']}", "wealth", f"{client['name']} has chosen {manager} to look after its {_money(client['amount'])}.", now)
    for p in pitches:
        fl._ping_player(conn, p["manager_id"])


# ---------------------------------------------------------------------------
# Managing
# ---------------------------------------------------------------------------

def _client_of(conn: Connection, manager_id, client_id: int, *, lock: bool = False) -> dict:
    client = _one(conn, "SELECT * FROM wealth_clients WHERE id = %s" + (" FOR UPDATE" if lock else ""), (client_id,))
    if client is None or client["status"] != "managed" or str(client["manager_id"]) != str(manager_id):
        raise FloorError("That is not a client you look after.")
    return client


def _insiders(conn: Connection, manager_id) -> list:
    """The manager's own account and their empire's: a client's order may not meet theirs."""
    mine = [ledger.player_account_id(conn, manager_id)]
    seat = _one(conn, "SELECT e.account_id FROM empire_seats s JOIN empires e ON e.id = s.empire_id WHERE s.player_id = %s", (manager_id,))
    return [a for a in mine + ([seat["account_id"]] if seat else []) if a]


def trade(conn: Connection, manager_id, client_id: int, ticker: str, side: str, quantity: int, limit_price: int, now: datetime) -> dict:
    """The manager deals in shares for a client, at a price they name."""
    with conn.transaction():
        client = _client_of(conn, manager_id, client_id)
        share = next((s for s in marketview._shares(conn, exchange.session_of(now)[0]) if s["ticker"] == (ticker or "").upper()), None)
        if share is None:
            raise FloorError("There is no share with that code.")
        if side not in ("buy", "sell") or not fl._whole(quantity):
            raise FloorError("Buy or sell a whole number of shares above nothing.")
        if not fl._whole(limit_price):
            raise FloorError("A client's money is dealt only at a price you name.")
        code = _one(conn, "SELECT sector FROM companies WHERE id = %s", (share["id"],))["sector"]
        if side == "buy" and code in client["banned"]:
            raise FloorError(f"{client['name']} will not hold {_sector_names().get(code, code).lower()}.")
        try:
            empires.no_dealing_with_yourself(conn, client["account_id"], share["id"], side, _insiders(conn, manager_id), "the client's account")
        except empires.EmpireError as refused:
            raise FloorError(str(refused)) from None
        _front_running(conn, client, manager_id, share["id"], side, now)
        try:
            return exchange.place_order(conn, account=client["account_id"], ticker=share["ticker"], side=side, kind="limit", quantity=quantity,
                                        limit_price=limit_price, now=now)
        except exchange.ExchangeError as refused:
            raise FloorError(str(refused)) from None


def cancel(conn: Connection, manager_id, client_id: int, order_id: int, now: datetime) -> dict:
    client = _client_of(conn, manager_id, client_id)
    try:
        return exchange.cancel_order(conn, account=client["account_id"], order_id=order_id, now=now)
    except exchange.ExchangeError as refused:
        raise FloorError(str(refused)) from None


def _front_running(conn: Connection, client: dict, manager_id, company_id, side: str, now: datetime) -> None:
    """The Money Watch notes (never shown) a manager who dealt in a share for themselves, the same way, just before the client."""
    me = ledger.player_account_id(conn, manager_id)
    day, _ = exchange.session_of(now)
    column = "buyer_account_id" if side == "buy" else "seller_account_id"
    if _one(conn, f"SELECT 1 AS x FROM market_trades WHERE company_id = %s AND {column} = %s AND session_date >= %s LIMIT 1",
            (company_id, me, day - timedelta(days=2))):
        conn.execute("INSERT INTO money_watch_flags (period, account_id, reason) VALUES (%s, %s, %s)",
                     (careers.world_now(conn, now)["period"], me,
                      f"Wealth manager dealt in a share for themselves just before their client ({client['name']}) did"))


def holdings(conn: Connection, client: dict, now: datetime) -> dict:
    w = objectives.wealth(conn, client["account_id"], now)
    return {"cash": w["cash"], "shares": w["shares"], "bonds": w["bonds"], "total": w["total"],
            "lines": [{"ticker": x["ticker"], "sector": x["sector"], "shares": x["shares"], "value": x["value"]} for x in w["lines"] if x["value"] > 0]}


def _breach(conn: Connection, client: dict, kind: str, words: str, cost: int, now: datetime) -> bool:
    day, _ = exchange.session_of(now)
    period = careers.world_now(conn, now)["period"]
    if kind == "drop" and _one(conn, "SELECT 1 AS x FROM wealth_breaches WHERE client_id = %s AND period = %s AND kind = 'drop'",
                               (client["id"], period)):
        return False                               # a fall is counted once a quarter
    row = _one(conn, "INSERT INTO wealth_breaches (client_id, manager_id, period, day, kind, words, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT (client_id, day, kind) DO NOTHING RETURNING id",
               (client["id"], client["manager_id"], period, day, kind, words, now))
    if row is None:
        return False
    conn.execute("UPDATE wealth_clients SET satisfaction_bps = greatest(satisfaction_bps - %s, 0) WHERE id = %s", (cost, client["id"]))
    fl._ping_player(conn, client["manager_id"])
    count = _one(conn, "SELECT count(*)::int AS n FROM wealth_breaches WHERE client_id = %s AND period = %s", (client["id"], period))["n"]
    if count >= data.WEALTH_BREACHES_TO_LEAVE:
        _leave(conn, client, f"its limits were broken {count} times this quarter", now)
    return True


def check(conn: Connection, client: dict, now: datetime) -> list[str]:
    """Look at a client's limits now. Returns the kinds broken (each recorded at most once a day)."""
    h = holdings(conn, client, now)
    total = max(h["total"], 1)
    broken = []
    high = max(client["high_value"] or h["total"], h["total"])
    conn.execute("UPDATE wealth_clients SET high_value = %s, checked_at = %s WHERE id = %s", (high, now, client["id"]))
    if h["shares"] * BPS > client["most_shares_bps"] * total and _breach(
            conn, client, "shares", f"{_pct(h['shares'] * BPS // total)} of the money is in shares; the client allows {_pct(client['most_shares_bps'])}.",
            data.WEALTH_BREACH_COST_BPS, now):
        broken.append("shares")
    if h["cash"] * BPS < client["least_cash_bps"] * total and _breach(
            conn, client, "cash", f"Only {_pct(h['cash'] * BPS // total)} is in cash; the client wants at least {_pct(client['least_cash_bps'])}.",
            data.WEALTH_BREACH_COST_BPS, now):
        broken.append("cash")
    fall = (high - h["total"]) * BPS // max(high, 1)
    if fall > client["most_drop_bps"] and _breach(
            conn, client, "drop", f"It has fallen {_pct(fall)} from its high; the client accepts {_pct(client['most_drop_bps'])}.",
            data.WEALTH_DROP_COST_BPS, now):
        broken.append("drop")
    return broken


def _leave(conn: Connection, client: dict, why: str, now: datetime) -> None:
    """The client takes everything back to the households."""
    account = client["account_id"]
    for o in _rows(conn, "SELECT id FROM market_orders WHERE account_id = %s AND status = 'open'", (account,)):
        exchange.cancel_order(conn, account=account, order_id=o["id"], now=now)
    public = ledger.account_id(conn, ledger.INVESTORS_PUBLIC)
    period = careers.world_now(conn, now)["period"]
    for b in _rows(conn, "SELECT asset, balance::bigint AS n FROM ledger_balances WHERE account_id = %s AND balance > 0 ORDER BY asset", (account,)):
        ledger.transfer(conn, payer=account, receiver=public, amount=b["n"], asset=b["asset"], kind="wealth_left",
                        memo=f"{client['name']} takes its money back from its manager", period=period)
    conn.execute("UPDATE wealth_clients SET status = 'left', left_at = %s, left_why = %s WHERE id = %s", (now, why, client["id"]))
    manager = _one(conn, "SELECT display_name FROM players WHERE id = %s", (client["manager_id"],))["display_name"]
    fl._note(conn, f"wealth-left:{client['id']}", "wealth", f"{client['name']} has left {manager} and taken its money back: {why}.", now)
    fl._ping_player(conn, client["manager_id"])


def hand_back(conn: Connection, manager_id, client_id: int, now: datetime) -> dict:
    """A manager gives a client up. It counts as a client lost."""
    with conn.transaction():
        client = _client_of(conn, manager_id, client_id, lock=True)
        _leave(conn, client, "its manager handed it back", now)
    return {"client_id": client_id}


def tick(conn: Connection, now: datetime) -> None:
    """Clients arrive and choose; managed clients' limits are looked at every ten minutes of an open market."""
    if not ready(conn):
        return
    for c in _rows(conn, "SELECT * FROM wealth_clients WHERE status = 'seeking' AND pitches_until <= %s ORDER BY id", (now,)):
        with conn.transaction():
            _choose(conn, c, now)
    if clock.market_state(now).value != "open":
        return
    for c in _rows(conn, "SELECT * FROM wealth_clients WHERE status = 'managed' AND (checked_at IS NULL OR checked_at <= %s) ORDER BY id",
                   (now - timedelta(seconds=CHECK_SECONDS),)):
        with conn.transaction():
            check(conn, c, now)
    slot = int(now.timestamp()) // 1800
    seeking = _one(conn, "SELECT count(*)::int AS n FROM wealth_clients WHERE status = 'seeking'")["n"]
    if seeking < data.WEALTH_SEEKING_MOST and _one(conn, "SELECT 1 AS x FROM players WHERE build = 'asset_manager' LIMIT 1") \
            and _unit(fl._seed(conn), "wealth-arrive", slot) * data.WEALTH_ARRIVAL_CHANCE < 1 \
            and not _one(conn, "SELECT 1 AS x FROM wealth_clients WHERE arrived_at >= %s", (datetime.fromtimestamp(slot * 1800, now.tzinfo),)):
        with conn.transaction():
            arrive(conn, now, key=slot)


# ---------------------------------------------------------------------------
# The quarter's review
# ---------------------------------------------------------------------------

def benchmark_bps(conn: Connection, client: dict, index_then: int, index_now: int) -> int:
    """A fair quarter for this client: the share index for the part it would hold in shares, the Central Bank's rate for the rest."""
    index_bps = KINDS[client["kind"]]["index_bps"]
    shares = (index_now - index_then) * BPS // max(index_then, 1)
    cash = lending.policy_rate(conn) // 4
    return (shares * index_bps + cash * (BPS - index_bps)) // BPS


def review(conn: Connection, client: dict, period: int, now: datetime) -> dict:
    h = holdings(conn, client, now)
    start = client["review_value"] or client["amount"]
    index_now = _index_now(conn, now)
    bench = benchmark_bps(conn, client, client["review_index"] or index_now, index_now)
    gain = h["total"] - start
    ret = gain * BPS // max(start, 1)
    breaches = _one(conn, "SELECT count(*)::int AS n FROM wealth_breaches WHERE client_id = %s AND period = %s", (client["id"], period))["n"]
    # The fees, from the client's cash: a quarter of the yearly fee, and the share of the gain above a quarter of its goal.
    fee = h["total"] * client["fee_bps"] // BPS // 4
    above = gain - start * client["goal_bps"] // BPS // 4
    perf = max(above, 0) * client["perf_bps"] // BPS
    manager_account = ledger.player_account_id(conn, client["manager_id"])
    paid = ledger.pay_up_to(conn, payer=client["account_id"], receiver=manager_account, wanted=fee + perf, kind="wealth_fee",
                            memo=f"{client['name']}: the manager's fee for {clock.period_label(period)}", period=period,
                            reference=f"wealth-fee:{client['id']}:{period}") if fee + perf > 0 else 0
    after_fees = ret - paid * BPS // max(start, 1)
    sat = client["satisfaction_bps"] + max(min((after_fees - bench) * 3, 2000), -3000)
    sat = max(min(sat, BPS), 0)
    if sat < data.WEALTH_LEAVE_BELOW_BPS:
        verdict, words = "leaves", "Unhappy with the quarter, it is leaving."
    elif sat < data.WEALTH_WARN_BELOW_BPS:
        verdict, words = "warns", "It is unhappy, and warns that another quarter like this and it will leave."
    elif sat >= data.WEALTH_ADD_ABOVE_BPS and after_fees > bench:
        verdict, words = "adds", "Very pleased, it hands over a tenth more money."
    else:
        verdict, words = "stays", "It is content, and stays."
    review_row = {"client_id": client["id"], "manager_id": client["manager_id"], "period": period, "start_value": start,
                  "end_value": h["total"], "return_bps": after_fees, "benchmark_bps": bench, "breaches": breaches, "fee": min(paid, fee),
                  "perf_fee": max(paid - fee, 0), "satisfaction_bps": sat, "verdict": verdict, "words": words}
    conn.execute("INSERT INTO wealth_reviews (client_id, manager_id, period, start_value, end_value, return_bps, benchmark_bps, breaches, fee,"
                 " perf_fee, satisfaction_bps, verdict, words, at) VALUES (%(client_id)s, %(manager_id)s, %(period)s, %(start_value)s,"
                 " %(end_value)s, %(return_bps)s, %(benchmark_bps)s, %(breaches)s, %(fee)s, %(perf_fee)s, %(satisfaction_bps)s, %(verdict)s,"
                 " %(words)s, %(at)s) ON CONFLICT (client_id, period) DO NOTHING", {**review_row, "at": now})
    value = h["total"] - paid
    if verdict == "adds":
        more = value * data.WEALTH_ADD_BPS // BPS
        if more > 0:
            ledger.transfer(conn, payer=ledger.account_id(conn, ledger.INVESTORS_PUBLIC), receiver=client["account_id"], amount=more,
                            kind="wealth_mandate", memo=f"{client['name']}: more money handed to its manager", period=period,
                            reference=f"wealth-more:{client['id']}:{period}")
            value += more
    conn.execute("UPDATE wealth_clients SET satisfaction_bps = %s, review_value = %s, review_index = %s, high_value = %s WHERE id = %s",
                 (sat, value, index_now, value, client["id"]))
    if verdict == "leaves":
        _leave(conn, {**client, "satisfaction_bps": sat}, "it was unhappy with the quarter", now)
    fl._ping_player(conn, client["manager_id"])
    return review_row


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """Each managed client reviews its manager (a client taken on this quarter judges the part it has seen)."""
    if not ready(conn):
        return
    for c in _rows(conn, "SELECT * FROM wealth_clients WHERE status = 'managed' ORDER BY id"):
        if _one(conn, "SELECT 1 AS x FROM wealth_reviews WHERE client_id = %s AND period = %s", (c["id"], period)):
            continue
        review(conn, c, period, now)


# ---------------------------------------------------------------------------
# What each side sees
# ---------------------------------------------------------------------------

def _client_public(c: dict) -> dict:
    names = _sector_names()
    return {"id": c["id"], "name": c["name"], "kind": c["kind"], "goal": c["goal"], "amount": c["amount"],
            "most_shares_bps": c["most_shares_bps"], "least_cash_bps": c["least_cash_bps"], "most_drop_bps": c["most_drop_bps"],
            "goal_bps": c["goal_bps"], "banned": [names.get(b, b) for b in c["banned"]], "index_bps": KINDS[c["kind"]]["index_bps"]}


def view(conn: Connection, player_id, now: datetime) -> dict:
    if not ready(conn):
        return {"ready": False}
    out: dict = {"ready": True, "manager": _is_manager(conn, player_id), "most_fee_bps": data.WEALTH_MOST_FEE_BPS,
                 "most_perf_bps": data.WEALTH_MOST_PERF_BPS, "most_clients": data.WEALTH_MOST_CLIENTS}
    seeking = []
    for c in _rows(conn, "SELECT * FROM wealth_clients WHERE status = 'seeking' AND pitches_until > %s ORDER BY pitches_until", (now,)):
        mine = _one(conn, "SELECT fee_bps, perf_bps FROM wealth_pitches WHERE client_id = %s AND manager_id = %s", (c["id"], player_id))
        rivals = _one(conn, "SELECT count(*)::int AS n FROM wealth_pitches WHERE client_id = %s AND manager_id <> %s", (c["id"], player_id))["n"]
        seeking.append({**_client_public(c), "pitches_until": c["pitches_until"], "my_pitch": mine, "rivals": rivals})
    out["seeking"] = seeking
    if not out["manager"]:
        return out
    out["record"] = reputation(conn, player_id)
    clients = []
    for c in _rows(conn, "SELECT * FROM wealth_clients WHERE manager_id = %s AND status = 'managed' ORDER BY id", (player_id,)):
        h = holdings(conn, c, now)
        total = max(h["total"], 1)
        start = c["review_value"] or c["amount"]
        clients.append({**_client_public(c), "fee_bps": c["fee_bps"], "perf_bps": c["perf_bps"], "started_at": c["started_at"],
                        "satisfaction_bps": c["satisfaction_bps"], "worth": h["total"], "cash": h["cash"], "shares_value": h["shares"],
                        "shares_bps": h["shares"] * BPS // total, "cash_bps": h["cash"] * BPS // total,
                        "quarter_bps": (h["total"] - start) * BPS // max(start, 1),
                        "fall_bps": (max(c["high_value"] or 0, h["total"]) - h["total"]) * BPS // max(c["high_value"] or 1, 1),
                        "lines": h["lines"],
                        "orders": _rows(conn, "SELECT o.id, c.ticker, o.side, o.quantity, o.remaining, o.limit_price FROM market_orders o JOIN companies c"
                                              " ON c.id = o.company_id WHERE o.account_id = %s AND o.status = 'open' ORDER BY o.id", (c["account_id"],)),
                        "breaches": _rows(conn, "SELECT kind, words, at FROM wealth_breaches WHERE client_id = %s ORDER BY id DESC LIMIT 5", (c["id"],)),
                        "reviews": _rows(conn, "SELECT period, return_bps, benchmark_bps, breaches, fee, perf_fee, satisfaction_bps, verdict, words"
                                               " FROM wealth_reviews WHERE client_id = %s ORDER BY period DESC LIMIT 4", (c["id"],))})
    out["clients"] = clients
    out["gone"] = _rows(conn, "SELECT name, left_at, left_why FROM wealth_clients WHERE manager_id = %s AND status = 'left' ORDER BY left_at DESC LIMIT 5",
                        (player_id,))
    return out
