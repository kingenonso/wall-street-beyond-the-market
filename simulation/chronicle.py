"""Stage 10: the Chronicle, the world's memory (design document, section 20, Stage 10).

Three layers:
  * personal: a player's career, deals, scoops and offices;
  * company: a company's history and the causes of its turning points;
  * world: crises, policy changes, big takeovers and collapses, and a review of each game year.

The game writes the factual record, from what happened. Each entry carries its Ripple key, so "Why?" shows what
led to it. Journalists may add a narrative account of an entry, signed; accounts of the same entry sit side by
side, each with a credibility score worked out from its evidence (the confirmed facts it cites, from the
author's own published stories) and the author's record.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock

TURNING_POINT_BPS = 3000               # a company's profit moving 30% or more on the year is a turning point


class ChronicleError(Exception):
    """A request the Chronicle does not allow. The words are for the player."""


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def write(conn: Connection, layer: str, ref: str, kind: str, title: str, words: str, period: int, day: int, now: datetime,
          *, player_id=None, company_id=None) -> None:
    """Add an entry. The same record never enters a layer twice."""
    if not _rows(conn, "SELECT to_regclass('chronicle_entries') IS NOT NULL AS ok")[0]["ok"]:
        return
    conn.execute("INSERT INTO chronicle_entries (layer, player_id, company_id, kind, ref, title, words, period, day, at)"
                 " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                 (layer, player_id, company_id, kind, ref, title[:200], words[:1000], period, max(min(day, 90), 1), now))


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def at_close(conn: Connection, period: int, now: datetime) -> None:
    """Write the quarter's record: the Central Bank's decision, companies' turning points, defaults and takeovers, and,
    at the end of a game year, the year in review."""
    if not _rows(conn, "SELECT to_regclass('chronicle_entries') IS NOT NULL AS ok")[0]["ok"]:
        return
    from simulation import newsroom_facts
    label = clock.period_label(period)
    econ = _one(conn, "SELECT * FROM economy_results WHERE period = %s", (period,))
    if econ and econ["next_policy_rate_bps"] != econ["policy_rate_bps"]:
        word = "raised" if econ["next_policy_rate_bps"] > econ["policy_rate_bps"] else "cut"
        write(conn, "world", f"rate:{period}", "policy", f"The Central Bank {word} its rate to {_percent(econ['next_policy_rate_bps'])}",
              f"At the close of {label} the Central Bank {word} its rate from {_percent(econ['policy_rate_bps'])} to "
              f"{_percent(econ['next_policy_rate_bps'])}, with prices rising {_percent(econ['inflation_bps'])} a year.", period + 1, 1, now)
    for r in _rows(conn, """
        SELECT c.id, c.ticker, c.name, a.net_profit AS now, b.net_profit AS before
        FROM company_results a JOIN companies c ON c.id = a.company_id AND c.listed
        LEFT JOIN company_results b ON b.company_id = a.company_id AND b.period = a.period - 4
        WHERE a.period = %s""", (period,)):
        before, profit = r["before"], r["now"]
        if before and (before > 0) == (profit > 0) and abs((profit - before) * 10_000 // abs(before)) >= TURNING_POINT_BPS:
            change = (profit - before) * 10_000 // abs(before)
            write(conn, "company", f"results:{r['ticker']}:{period}", "turning_point",
                  f"{r['name']}: profit {'up' if change > 0 else 'down'} {_percent(change)} on the year",
                  f"In {label} {r['name']} made {newsroom_facts.money(profit)}, against {newsroom_facts.money(before)} a year before.",
                  period + 1, 1, now, company_id=r["id"])
        elif before and before > 0 >= profit:
            write(conn, "company", f"results:{r['ticker']}:{period}", "turning_point", f"{r['name']} falls into a loss",
                  f"In {label} {r['name']} lost {newsroom_facts.money(profit)}, after a profit of {newsroom_facts.money(before)} a year before.",
                  period + 1, 1, now, company_id=r["id"])
    for t in _rows(conn, "SELECT t.id, t.outcome, t.status, tc.name AS target, tc.id AS target_id, coalesce(e.name, bc.name) AS bidder"
                         " FROM takeovers t JOIN companies tc ON tc.id = t.target_company_id LEFT JOIN companies bc ON bc.id = t.bidder_company_id"
                         " LEFT JOIN empires e ON e.id = t.bidder_empire_id WHERE t.closes_period = %s AND t.status <> 'open'", (period,)):
        won = t["status"] == "won"
        title = f"{t['bidder']} {'takes over' if won else 'fails to take over'} {t['target']}"
        write(conn, "world", f"takeover:{t['id']}", "takeover", title, f"{title}, {label}.", period + 1, 1, now)
        write(conn, "company", f"takeover:{t['id']}", "takeover", title, f"{title}, {label}.", period + 1, 1, now, company_id=t["target_id"])
    if period % 4 == 0:
        _year_in_review(conn, period, now)


def _year_in_review(conn: Connection, period: int, now: datetime) -> None:
    year = (period - 1) // 4 + 1
    rows = _rows(conn, "SELECT period, policy_rate_bps, next_policy_rate_bps, inflation_bps, company_sales FROM economy_results"
                       " WHERE period BETWEEN %s AND %s ORDER BY period", (period - 3, period))
    if not rows:
        return
    first, last = rows[0], rows[-1]
    growth = (last["company_sales"] - first["company_sales"]) * 10_000 // max(first["company_sales"], 1)
    parts = [f"The Central Bank's rate went from {_percent(first['policy_rate_bps'])} to {_percent(last['next_policy_rate_bps'])}; "
             f"prices were rising {_percent(last['inflation_bps'])} a year by the end; companies' quarterly sales "
             f"{'grew' if growth >= 0 else 'fell'} {_percent(growth)} from the year's first quarter to its last."]
    movers = _rows(conn, """
        SELECT c.name, a.net_profit AS now, b.net_profit AS before FROM company_results a JOIN companies c ON c.id = a.company_id AND c.listed
        JOIN company_results b ON b.company_id = a.company_id AND b.period = a.period - 4
        WHERE a.period = %s AND b.net_profit > 0 AND a.net_profit > 0 ORDER BY a.net_profit::numeric / b.net_profit DESC""", (period,))
    if movers:
        parts.append(f"The year's biggest riser was {movers[0]['name']}; its biggest faller {movers[-1]['name']}.")
    taken = _one(conn, "SELECT count(*) AS n FROM takeovers WHERE closes_period BETWEEN %s AND %s AND status <> 'open'", (period - 3, period))
    if taken and taken["n"]:
        parts.append(f"{taken['n']} takeover offer{'s' if taken['n'] != 1 else ''} came to an end.")
    scoops = _rows(conn, "SELECT s.headline, p.display_name FROM stories s JOIN players p ON p.id = s.author_id"
                         " WHERE s.status = 'published' AND s.scoop AND s.period BETWEEN %s AND %s ORDER BY s.readers DESC LIMIT 3",
                   (period - 3, period))
    if scoops:
        parts.append("The year's biggest scoops: " + "; ".join(f"“{s['headline']}” by {s['display_name']}" for s in scoops) + ".")
    write(conn, "world", f"year:{year}", "year_in_review", f"Year {year} in review", " ".join(parts), period + 1, 1, now)


def entries(conn: Connection, layer: str, *, player_id=None, company_ticker: str | None = None, period_now: int, day_now: int,
            limit: int = 50) -> list[dict]:
    cond = ["e.layer = %s", "(e.period < %s OR (e.period = %s AND e.day <= %s))"]
    params: list = [layer, period_now, period_now, day_now]
    if layer == "personal":
        cond.append("e.player_id = %s")
        params.append(player_id)
    if company_ticker:
        cond.append("e.company_id = (SELECT id FROM companies WHERE ticker = %s)")
        params.append(company_ticker)
    params.append(limit)
    found = _rows(conn, f"SELECT e.id, e.layer, e.kind, e.ref, e.title, e.words, e.period, e.day FROM chronicle_entries e"
                        f" WHERE {' AND '.join(cond)} ORDER BY e.period DESC, e.day DESC, e.id DESC LIMIT %s", params)
    for e in found:
        e["label"] = clock.period_label(e["period"])
        e["accounts"] = _rows(conn, "SELECT a.words, a.credibility, a.evidence, p.display_name AS author FROM chronicle_accounts a"
                                    " JOIN players p ON p.id = a.author_id WHERE a.entry_id = %s ORDER BY a.credibility DESC, a.id", (e["id"],))
    return found


def add_account(conn: Connection, player_id, entry_id: int, words: str, evidence: list[int], period: int, now: datetime) -> dict:
    """A journalist's signed account of an entry. Its evidence is their own published stories; its credibility comes
    from how many of those still stand, and from the author's record."""
    player = _one(conn, "SELECT build FROM players WHERE id = %s", (player_id,))
    if player is None or player["build"] != "journalist":
        raise ChronicleError("Only a Financial Journalist writes accounts in the Chronicle.")
    words = " ".join((words or "").split())
    if not 40 <= len(words) <= 1200:
        raise ChronicleError("An account is between 40 and 1,200 characters.")
    entry = _one(conn, "SELECT * FROM chronicle_entries WHERE id = %s", (entry_id,))
    if entry is None or entry["layer"] == "personal":
        raise ChronicleError("Accounts are written for the company and world layers.")
    evidence = sorted(set(int(e) for e in evidence or []))[:5]
    stories = _rows(conn, "SELECT id, correction_due, correction_id, tickers, facts, period FROM stories WHERE id = ANY(%s) AND author_id = %s"
                          " AND status = 'published'", (evidence, player_id))
    if len(stories) != len(evidence):
        raise ChronicleError("Evidence is your own published stories.")
    # Evidence must be about the entry: the same company, the same record, or (for a year's review) that year.
    ticker = _one(conn, "SELECT ticker FROM companies WHERE id = %s", (entry["company_id"],))["ticker"] if entry["company_id"] else None
    entry_tickers = {ticker} if ticker else set(entry["ref"].split(":")[1:2]) if entry["ref"].split(":")[0] in ("results", "rating") else set()
    for s in stories:
        refs = {f.get("ripple") for f in s["facts"]}
        about = (entry["ref"] in refs or bool(entry_tickers & set(s["tickers"]))
                 or (entry["kind"] == "year_in_review" and (s["period"] - 1) // 4 + 1 == int(entry["ref"].split(":")[1]))
                 or (entry["ref"].startswith("rate:") and any((r or "").startswith("rate:") for r in refs)))
        if not about:
            raise ChronicleError("Each story you cite must be about this entry: the same company, the same record, or that year.")
    standing_stories = sum(1 for s in stories if not s["correction_due"])
    profile = _one(conn, "SELECT credibility FROM journalist_profiles WHERE player_id = %s", (player_id,))
    credibility = min(20 + 15 * standing_stories + (profile["credibility"] if profile else 50) // 2, 100)
    try:
        conn.execute("INSERT INTO chronicle_accounts (entry_id, author_id, words, evidence, credibility, period, at)"
                     " VALUES (%s, %s, %s, %s, %s, %s, %s)", (entry_id, player_id, words, Jsonb(evidence), credibility, period, now))
    except Exception as e:
        raise ChronicleError("You have already written an account of this entry.") from e
    return {"credibility": credibility}
