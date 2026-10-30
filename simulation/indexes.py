"""The game's family of indexes (the talent and funds stage, Part 3), and indexes fund managers publish themselves.

Every index has published rules. Share indexes count each company by the value of its freely traded shares (shares held
by the founders, or by any one owner with 30% or more, are left out), and no company may be more than 15% of an index (with
fewer than seven members, more than one and a half times an equal share). Bond indexes count each bond by the amount owed
on it. Every quarter, as the quarter closes, the index provider reviews each index: who comes in, who goes out, and the new
weights. The changes are announced at once and made at the third closing bell after, so everybody knows that the funds
copying the index will have to buy the newcomers and sell the leavers on that day.

An index's level is worked out at every closing bell, chained from one bell to the next: the members' prices against the
last bell's, each counted by the "index shares" set at the last review. A change of members never moves the level itself.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import bonds, careers, clock, exchange, ledger, marketview
from simulation import world_data as data
from simulation.money import BPS

log = logging.getLogger("wsbm.indexes")
SCALE = Decimal(10) ** 10


class IndexError_(Exception):
    """A request about an index the rules do not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def ready(conn: Connection) -> bool:
    return bool(_one(conn, "SELECT to_regclass('market_indexes') IS NOT NULL AS ok")["ok"])


# ---------------------------------------------------------------------------
# Who could be in an index, and what each is worth
# ---------------------------------------------------------------------------

def _listed(conn: Connection, day: date) -> list[dict]:
    """Every listed company with its price, its free float and what that free float is worth."""
    shares = {s["id"]: s for s in marketview._shares(conn, day)}
    rows = _rows(conn, "SELECT c.id, c.ticker, c.name, c.sector, c.share_asset AS asset FROM companies c JOIN market_instruments m"
                       " ON m.company_id = c.id WHERE c.listed AND c.status = 'trading' ORDER BY c.ticker")
    founders = ledger.account_id(conn, ledger.INVESTORS_FOUNDERS)
    strategic = {}
    for r in _rows(conn, "SELECT h.company_id, sum(h.held)::bigint AS held FROM (SELECT o.company_id, o.account_id, sum(o.shares) AS held"
                         "  FROM share_owners o GROUP BY o.company_id, o.account_id) h JOIN ledger_accounts a ON a.id = h.account_id"
                         " WHERE a.id = %s OR (a.kind IN ('player', 'empire', 'company')"
                         "  AND h.held * %s >= %s * (SELECT r.shares_in_issue FROM company_results r WHERE r.company_id = h.company_id"
                         "                           ORDER BY r.period DESC LIMIT 1))"
                         " GROUP BY h.company_id", (founders, BPS, data.INDEX_STRATEGIC_HOLDER_BPS)):
        strategic[r["company_id"]] = r["held"]
    out = []
    for r in rows:
        s = shares.get(r["id"])
        if not s or not s["price"] or not s["shares"]:
            continue
        free = max(s["shares"] - strategic.get(r["id"], 0), 0)
        if free <= 0:
            continue
        out.append({**r, "price": s["price"], "free": free, "value": free * s["price"]})
    return out


def _dividend_yields(conn: Connection, companies: list[dict]) -> dict:
    last = _one(conn, "SELECT max(period) AS p FROM company_results")["p"] or 0
    paid = {r["company_id"]: int(r["paid"]) for r in _rows(conn, "SELECT company_id, sum(dividends_paid) AS paid FROM company_results"
                                                                 " WHERE period > %s AND period <= %s GROUP BY company_id", (last - 4, last))}
    out = {}
    for c in companies:
        whole = c["price"] * _one(conn, "SELECT shares_in_issue FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                                  (c["id"],))["shares_in_issue"]
        if paid.get(c["id"], 0) > 0 and whole > 0:
            out[c["id"]] = paid[c["id"]] * BPS // whole
    return out


def _bond_candidates(conn: Connection, issuer: str, now: datetime) -> list[dict]:
    state = bonds.market(conn, now)
    out = []
    for b in bonds._load(conn, "b.issuer = %s AND b.redeemed_period IS NULL", (issuer,)):
        if b["maturity_period"] <= state["period"] or b["units"] <= 0:
            continue
        if issuer == "company" and bonds.distressed(b, state):
            continue
        fair = bonds.fair_value(b, state)
        if fair <= 0:
            continue
        out.append({"asset": b["asset"], "ticker": b["asset"][4:], "name": b["name"], "price": fair, "value": fair * b["units"],
                    "free": b["units"]})
    return out


def candidates(conn: Connection, index: dict, now: datetime) -> list[dict]:
    """Who the index's rules take today, largest first."""
    day = exchange.session_of(now)[0]
    rule = index["rule"]
    if rule == "govbond":
        return sorted(_bond_candidates(conn, "government", now), key=lambda x: -x["value"])
    if rule == "corpbond":
        return sorted(_bond_candidates(conn, "company", now), key=lambda x: -x["value"])
    listed = _listed(conn, day)
    if rule == "top30":
        return sorted(listed, key=lambda x: -x["value"])[:30]
    if rule.startswith("sector:"):
        return sorted([c for c in listed if c["sector"] == rule.split(":", 1)[1]], key=lambda x: -x["value"])
    if rule == "dividend":
        ylds = _dividend_yields(conn, listed)
        best = sorted([c for c in listed if c["id"] in ylds], key=lambda c: -ylds[c["id"]])[:data.INDEX_DIVIDEND_MEMBERS]
        return sorted(best, key=lambda x: -x["value"])
    if rule == "custom":
        chosen = {m["ticker"] for m in _rows(conn, "SELECT ticker FROM index_members WHERE index_code = %s", (index["code"],))}
        return sorted([c for c in listed if c["ticker"] in chosen], key=lambda x: -x["value"])
    return []


def capped_weights(values: list[int], cap_bps: int) -> list[int]:
    """Weights in basis points, in proportion to value, none above the cap (the excess shared among the rest)."""
    n = len(values)
    if n == 0:
        return []
    cap = cap_bps if n >= data.INDEX_CAP_FEW_MEMBERS else max(cap_bps, BPS * 3 // (2 * n))
    cap = max(cap, -(-BPS // n))
    w = [float(v) for v in values]
    total = sum(w) or 1.0
    w = [x / total for x in w]
    limit = cap / BPS
    for _ in range(50):
        over = [i for i, x in enumerate(w) if x > limit + 1e-12]
        if not over:
            break
        excess = sum(w[i] - limit for i in over)
        for i in over:
            w[i] = limit
        free = [i for i, x in enumerate(w) if x < limit - 1e-12]
        room = sum(w[i] for i in free)
        if not free or room <= 0:
            break
        for i in free:
            w[i] += excess * w[i] / room
    out = [int(round(x * BPS)) for x in w]
    out[out.index(max(out))] += BPS - sum(out)
    return out


def plan_for(conn: Connection, index: dict, now: datetime) -> list[dict]:
    found = candidates(conn, index, now)
    if index["weighting"] == "equal":
        weights = capped_weights([1] * len(found), max(index["cap_bps"], BPS))
    else:
        weights = capped_weights([c["value"] for c in found], index["cap_bps"])
    return [{"asset": c["asset"], "ticker": c["ticker"], "name": c["name"], "weight_bps": w, "price": c["price"]}
            for c, w in zip(found, weights) if w > 0]


def _install(conn: Connection, code: str, plan: list[dict], prices: dict, day: date) -> None:
    """Set the members and their index shares, at today's prices: each counts in proportion to its weight."""
    conn.execute("DELETE FROM index_members WHERE index_code = %s", (code,))
    for m in plan:
        price = prices.get(m["asset"]) or m.get("price")
        if not price:
            continue
        conn.execute("INSERT INTO index_members (index_code, asset, ticker, quantity, weight_bps, last_price, since_day)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                     (code, m["asset"], m["ticker"], Decimal(m["weight_bps"]) * SCALE / Decimal(price), m["weight_bps"], price, day))


# ---------------------------------------------------------------------------
# Prices and levels
# ---------------------------------------------------------------------------

def prices_now(conn: Connection, assets: list[str], now: datetime) -> dict:
    """The price of each member now: for a share, the volume-weighted price of its latest session's trades (so one small trade
    near the bell cannot move an index, an ETF's value or a contract on them), or the reference price when nothing traded;
    for a bond, its fair value."""
    out = {}
    shares = [a for a in assets if a.startswith("SHR-")]
    if shares:
        for r in _rows(conn, """
            SELECT c.share_asset AS asset, m.reference_price, m.last_price,
                   (SELECT sum(t.price * t.quantity) / nullif(sum(t.quantity), 0) FROM market_trades t
                    WHERE t.company_id = m.company_id AND t.session_date = (SELECT max(x.session_date) FROM market_trades x
                                                                            WHERE x.company_id = m.company_id AND x.traded_at <= %s)
                      AND t.id > coalesce((SELECT max(s.after_trade_id) FROM share_splits s WHERE s.company_id = m.company_id), 0))::bigint AS vwap
            FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.share_asset = ANY(%s)""", (now, shares)):
            out[r["asset"]] = r["vwap"] or r["reference_price"] or r["last_price"]
    others = [a for a in assets if not a.startswith("SHR-")]
    if others:
        state = bonds.market(conn, now)
        for b in bonds._load(conn, "b.asset = ANY(%s)", (others,)):
            out[b["asset"]] = bonds.fair_value(b, state) if b["redeemed_period"] is None else 0
    return out


def after_split(conn: Connection, company_id, ratio: int) -> None:
    asset = _one(conn, "SELECT share_asset FROM companies WHERE id = %s", (company_id,))["share_asset"]
    conn.execute("UPDATE index_members SET quantity = quantity * %s, last_price = greatest(last_price / %s, 1) WHERE asset = %s",
                 (ratio, ratio, asset))


def members(conn: Connection, code: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM index_members WHERE index_code = %s ORDER BY weight_bps DESC, ticker", (code,))


def level_now(conn: Connection, code: str, now: datetime) -> int | None:
    """The index's level at this moment: its last level, moved by its members' prices since that bell."""
    idx = _one(conn, "SELECT * FROM market_indexes WHERE code = %s", (code,))
    if idx is None or idx["level"] is None:
        return None
    mem = members(conn, code)
    if not mem:
        return idx["level"]
    prices = prices_now(conn, [m["asset"] for m in mem], now)
    before = sum(m["quantity"] * m["last_price"] for m in mem)
    after = sum(m["quantity"] * (prices.get(m["asset"]) or m["last_price"]) for m in mem)
    return int(Decimal(idx["level"]) * after / before) if before else idx["level"]


def weights_now(conn: Connection, code: str, now: datetime) -> list[dict]:
    """Each member's share of the index at today's prices."""
    mem = members(conn, code)
    prices = prices_now(conn, [m["asset"] for m in mem], now)
    values = [(m, m["quantity"] * (prices.get(m["asset"]) or m["last_price"])) for m in mem]
    total = sum(v for _, v in values) or 1
    return [{"asset": m["asset"], "ticker": m["ticker"], "weight_bps": int(v * BPS / total), "price": prices.get(m["asset"]) or m["last_price"]}
            for m, v in values]


# ---------------------------------------------------------------------------
# Starting, the closing bell, the review
# ---------------------------------------------------------------------------

def setup(conn: Connection, day: date, now: datetime) -> bool:
    """The game's own indexes, made the first time the world meets them, all at 1,000 on the same day."""
    if _one(conn, "SELECT 1 AS x FROM market_indexes WHERE owner_id IS NULL LIMIT 1"):
        return False
    for code, name, kind, rule, words in data.INDEXES:
        idx = _one(conn, "INSERT INTO market_indexes (code, name, kind, rule, rules_words, cap_bps, level, level_day, started_day, created_at)"
                         " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (code, name, kind, rule, _rules_words(kind, words), data.INDEX_CAP_BPS, data.INDEX_START_LEVEL, day, day, now))
        plan = plan_for(conn, idx, now)
        _install(conn, code, plan, prices_now(conn, [m["asset"] for m in plan], now), day)
        conn.execute("INSERT INTO index_levels (index_code, session_date, level) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (code, day, data.INDEX_START_LEVEL))
    return True


def _rules_words(kind: str, words: str) -> str:
    if kind == "bonds":
        return f"{words} Reviewed every quarter; changes are announced as the quarter closes and made at the third closing bell after."
    return (f"{words} Each counted by the value of its freely traded shares (not those of its founders, or of any one owner with 30% or"
            " more), and none above 15% of the index (with fewer than seven members, one and a half times an equal share). Reviewed"
            " every quarter; changes are announced as the quarter closes and made at the third closing bell after.")


def at_bell(conn: Connection, day: date, now: datetime) -> list[str]:
    """After a closing bell: every index's level, written down for good; then any change due at this bell is made.
    Returns the codes of the indexes whose members changed."""
    changed = []
    for idx in _rows(conn, "SELECT * FROM market_indexes WHERE status = 'live' AND level IS NOT NULL ORDER BY code FOR UPDATE"):
        if idx["level_day"] is not None and idx["level_day"] >= day:
            continue
        mem = members(conn, idx["code"])
        prices = prices_now(conn, [m["asset"] for m in mem], now)
        before = sum(m["quantity"] * m["last_price"] for m in mem)
        after = sum(m["quantity"] * (prices.get(m["asset"]) or m["last_price"]) for m in mem)
        level = max(int(Decimal(idx["level"]) * after / before), 1) if before else idx["level"]
        conn.execute("INSERT INTO index_levels (index_code, session_date, level) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (idx["code"], day, level))
        conn.execute("UPDATE market_indexes SET level = %s, level_day = %s WHERE code = %s", (level, day, idx["code"]))
        for m in mem:
            p = prices.get(m["asset"])
            if p:
                conn.execute("UPDATE index_members SET last_price = %s WHERE index_code = %s AND asset = %s", (p, idx["code"], m["asset"]))
        # A bond repaid leaves its index at once (its money has gone back to its holders).
        for m in mem:
            if prices.get(m["asset"], 1) == 0:
                conn.execute("DELETE FROM index_members WHERE index_code = %s AND asset = %s", (idx["code"], m["asset"]))
        due = _one(conn, "SELECT * FROM index_changes WHERE index_code = %s AND status = 'announced' AND effective_day <= %s"
                         " ORDER BY id DESC LIMIT 1", (idx["code"], day))
        if due:
            live = prices_now(conn, [m["asset"] for m in due["plan"]], now)
            _install(conn, idx["code"], [m for m in due["plan"] if live.get(m["asset"])], live, day)
            conn.execute("UPDATE index_changes SET status = 'made' WHERE index_code = %s AND status = 'announced' AND effective_day <= %s",
                         (idx["code"], day))
            changed.append(idx["code"])
        elif not mem and idx["owner_id"] is None:
            # An index with nobody in it yet (no government bonds, or no dividends, in a new world) takes its first members as soon
            # as there are any: there is nothing for anybody to trade around.
            plan = plan_for(conn, idx, now)
            if plan:
                _install(conn, idx["code"], plan, prices_now(conn, [m["asset"] for m in plan], now), day)
                changed.append(idx["code"])
    return changed


def effective_day(now: datetime) -> date:
    """The day of the third closing bell from now."""
    first = exchange.session_of(now)[0]             # the trading day an order placed now belongs to (after 22:00, the next)
    return first + timedelta(days=data.INDEX_CHANGE_NOTICE_BELLS - 1)


def review(conn: Connection, period: int, now: datetime) -> list[dict]:
    """As a quarter closes: each of the game's indexes reviewed; changes announced, to be made at the third bell after."""
    out = []
    for idx in _rows(conn, "SELECT * FROM market_indexes WHERE status = 'live' AND owner_id IS NULL AND level IS NOT NULL ORDER BY code"):
        if _one(conn, "SELECT 1 AS x FROM index_changes WHERE index_code = %s AND period = %s", (idx["code"], period)):
            continue
        plan = plan_for(conn, idx, now)
        if not plan:
            continue
        before = {m["asset"]: m for m in members(conn, idx["code"])}
        after = {m["asset"]: m for m in plan}
        adds = [{"ticker": m["ticker"], "name": m["name"]} for a, m in after.items() if a not in before]
        drops = [{"ticker": m["ticker"], "name": _name_of(conn, a, m["ticker"])} for a, m in before.items() if a not in after]
        row = _one(conn, "INSERT INTO index_changes (index_code, period, announced_at, effective_day, adds, drops, plan) VALUES"
                         " (%s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (idx["code"], period, now, effective_day(now), Jsonb(adds), Jsonb(drops),
                    Jsonb([{k: m[k] for k in ("asset", "ticker", "weight_bps")} for m in plan])))
        out.append({**row, "index": idx})
    return out


def _name_of(conn: Connection, asset: str, ticker: str) -> str:
    row = _one(conn, "SELECT name FROM companies WHERE share_asset = %s", (asset,)) or _one(conn, "SELECT name FROM bonds WHERE asset = %s", (asset,))
    return row["name"] if row else ticker


# ---------------------------------------------------------------------------
# A manager's own index
# ---------------------------------------------------------------------------

def create_custom(conn: Connection, player_id, *, code: str, name: str, tickers: list[str], weighting: str, now: datetime) -> dict:
    """An Asset Manager of Level 20 publishes an index of their own: up to 30 listed companies, counted by value (capped at
    15%) or equally. It starts at 1,000 today; its members change only with three bells' notice."""
    with conn.transaction():
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise IndexError_(str(closing)) from None
        mine = careers.career(conn, player_id, "asset_manager")
        if mine is None or mine["level"] < data.ETF_LEVEL:
            raise IndexError_(f"Only an Asset Manager of Level {data.ETF_LEVEL} or above may publish an index.")
        code = (code or "").upper().strip()
        if not code.isalnum() or not 3 <= len(code) <= 8 or _one(conn, "SELECT 1 AS x FROM market_indexes WHERE code = %s", (code,)):
            raise IndexError_("Give the index a code of 3 to 8 letters and numbers that is not taken.")
        name = " ".join((name or "").split())
        if not 3 <= len(name) <= 60:
            raise IndexError_("Give the index a name of 3 to 60 letters.")
        if _one(conn, "SELECT count(*) AS n FROM market_indexes WHERE owner_id = %s AND status = 'live'", (player_id,))["n"] >= 3:
            raise IndexError_("A manager may publish at most three indexes.")
        if weighting not in ("value", "equal"):
            raise IndexError_("Count the companies by value or equally.")
        day = exchange.session_of(now)[0]
        listed = {c["ticker"]: c for c in _listed(conn, day)}
        chosen = sorted({(t or "").upper() for t in tickers})
        if not 5 <= len(chosen) <= data.INDEX_CUSTOM_MOST or any(t not in listed for t in chosen):
            raise IndexError_(f"Choose 5 to {data.INDEX_CUSTOM_MOST} companies listed on the exchange.")
        rules = (f"Chosen by its manager: {', '.join(chosen)}. Counted {'equally' if weighting == 'equal' else 'by the value of their freely traded shares, none above 15%'}."
                 " Changes are announced three closing bells ahead.")
        idx = _one(conn, "INSERT INTO market_indexes (code, name, kind, rule, rules_words, cap_bps, owner_id, weighting, level, level_day, started_day,"
                         " created_at) VALUES (%s, %s, 'shares', 'custom', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *",
                   (code, name, rules, data.INDEX_CAP_BPS, player_id, weighting, data.INDEX_START_LEVEL, _last_bell_day(conn, day), day, now))
        found = [listed[t] for t in chosen]
        weights = capped_weights([1] * len(found) if weighting == "equal" else [c["value"] for c in found],
                                 BPS if weighting == "equal" else data.INDEX_CAP_BPS)
        plan = [{"asset": c["asset"], "ticker": c["ticker"], "name": c["name"], "weight_bps": w, "price": c["price"]} for c, w in zip(found, weights)]
        _install(conn, code, plan, prices_now(conn, [m["asset"] for m in plan], now), day)
        return idx


def change_custom(conn: Connection, player_id, code: str, tickers: list[str], now: datetime) -> dict:
    """A custom index's members change only with three bells' notice, at most once a game quarter, and the change is
    announced to everybody holding a fund that copies it."""
    with conn.transaction():
        try:
            careers.books_open(conn, now)
        except careers.CareerError as closing:
            raise IndexError_(str(closing)) from None
        mine = careers.career(conn, player_id, "asset_manager")
        if mine is None or mine["level"] < data.ETF_LEVEL:
            raise IndexError_(f"Only an Asset Manager of Level {data.ETF_LEVEL} or above may change a published index.")
        idx = _one(conn, "SELECT * FROM market_indexes WHERE code = %s AND owner_id = %s AND status = 'live' FOR UPDATE", (code, player_id))
        if idx is None:
            raise IndexError_("You publish no index with that code.")
        if _one(conn, "SELECT 1 AS x FROM index_changes WHERE index_code = %s AND status = 'announced'", (code,)):
            raise IndexError_("A change to this index is already announced.")
        if _one(conn, "SELECT 1 AS x FROM index_changes WHERE index_code = %s AND announced_at > %s", (code, now - timedelta(days=clock.REAL_DAYS_PER_QUARTER))):
            raise IndexError_("A published index can be changed at most once a game quarter.")
        day = exchange.session_of(now)[0]
        listed = {c["ticker"]: c for c in _listed(conn, day)}
        chosen = sorted({(t or "").upper() for t in tickers})
        if not 5 <= len(chosen) <= data.INDEX_CUSTOM_MOST or any(t not in listed for t in chosen):
            raise IndexError_(f"Choose 5 to {data.INDEX_CUSTOM_MOST} companies listed on the exchange.")
        found = [listed[t] for t in chosen]
        weights = capped_weights([1] * len(found) if idx["weighting"] == "equal" else [c["value"] for c in found],
                                 BPS if idx["weighting"] == "equal" else data.INDEX_CAP_BPS)
        before = {m["ticker"] for m in members(conn, code)}
        plan = [{"asset": c["asset"], "ticker": c["ticker"], "weight_bps": w} for c, w in zip(found, weights)]
        period = careers.world_now(conn, now)["period"]
        row = _one(conn, "INSERT INTO index_changes (index_code, period, announced_at, effective_day, adds, drops, plan, orders_placed) VALUES"
                         " (%s, %s, %s, %s, %s, %s, %s, true) RETURNING *",
                   (code, period, now, effective_day(now), Jsonb([{"ticker": t, "name": listed[t]["name"]} for t in chosen if t not in before]),
                    Jsonb([{"ticker": t, "name": t} for t in sorted(before) if t not in chosen]), Jsonb(plan)))
        conn.execute("INSERT INTO etf_alerts (index_code, kind, everyone, headline, words, at) VALUES (%s, 'index_change', false, %s, %s, %s)",
                     (code, f"{idx['name']}: changes announced", f"Its manager is changing its members from the closing bell on"
                      f" {row['effective_day']:%d %b}: {', '.join(chosen)}.", now))
        return row


def _last_bell_day(conn: Connection, day: date) -> date:
    row = _one(conn, "SELECT max(session_date) AS d FROM closing_bells WHERE session_date < %s", (day,))
    return row["d"] if row and row["d"] else day - timedelta(days=1)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def summary(conn: Connection, idx: dict, now: datetime) -> dict:
    hist = _rows(conn, "SELECT session_date, level FROM index_levels WHERE index_code = %s ORDER BY session_date DESC LIMIT 29", (idx["code"],))
    live = level_now(conn, idx["code"], now) or idx["level"]

    def since(n):
        return (live - hist[n]["level"]) * BPS // hist[n]["level"] if len(hist) > n and hist[n]["level"] else None
    owner = _one(conn, "SELECT display_name FROM players WHERE id = %s", (idx["owner_id"],)) if idx["owner_id"] else None
    return {"code": idx["code"], "name": idx["name"], "kind": idx["kind"], "level": live, "day_bps": since(0),
            "quarter_bps": since(7), "year_bps": since(28), "members": _one(conn, "SELECT count(*) AS n FROM index_members WHERE index_code = %s",
                                                                             (idx["code"],))["n"],
            "custom": idx["owner_id"] is not None, "owner": owner["display_name"] if owner else "the index provider",
            "started": idx["started_day"]}


def listing(conn: Connection, now: datetime) -> list[dict]:
    return [summary(conn, i, now) for i in _rows(conn, "SELECT * FROM market_indexes WHERE status = 'live' ORDER BY owner_id NULLS FIRST, code")]


def page(conn: Connection, code: str, now: datetime) -> dict:
    idx = _one(conn, "SELECT * FROM market_indexes WHERE code = %s", (code,))
    if idx is None:
        raise IndexError_("There is no such index.")
    out = summary(conn, idx, now)
    out["rules"] = idx["rules_words"]
    names = {r["asset"]: r["name"] for r in _rows(conn, "SELECT share_asset AS asset, name FROM companies")}
    names.update({r["asset"]: r["name"] for r in _rows(conn, "SELECT asset, name FROM bonds")})
    out["weights"] = [{**w, "name": names.get(w["asset"], w["ticker"])} for w in weights_now(conn, code, now)]
    out["history"] = _rows(conn, "SELECT session_date, level FROM index_levels WHERE index_code = %s ORDER BY session_date DESC LIMIT 200",
                           (code,))[::-1]
    out["changes"] = _rows(conn, "SELECT period, announced_at, effective_day, adds, drops, status FROM index_changes WHERE index_code = %s"
                                 " ORDER BY id DESC LIMIT 8", (code,))
    for c in out["changes"]:
        c["label"] = clock.period_label(c["period"])
    return out
