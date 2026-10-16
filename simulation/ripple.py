"""Stage 10: the Ripple (design document, section 20, Stage 10).

Every significant event remembers what caused it. A link joins an effect to one of its causes, with one line
saying how, and the figures behind it. "Why?" follows the links back from any event and shows the chain at
three depths: one line (the nearest cause), the full chain (every step in words), and the numbers. Links are
kept for good, and feed the Chronicle.

Keys name what they point at, the same way everywhere:
  event:<id>                 an event that happened (a flood, a strike, a contract won)
  results:<TICKER>:<period>  a company's quarter results
  rating:<TICKER>:<period>   its credit rating on those results
  rate:<period>              the Central Bank's decision at that quarter's close
  prices:<period>            inflation that quarter
  watch:<period>             the Money Watch's reading
  homes:<City>:<period>      households' home loans gone bad in a city
  story:<id>                 a player's published story
  nudge:<TICKER>:<date>      a story's push on how investors value a share
  takeover:<id>, stake:<empire>:<TICKER>, infra:<id>, price:<TICKER>:<date>
Only public things are ever linked: a link never names a hidden figure or anything still to come.
"""

from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

MOST_STEPS = 12                       # the longest chain "Why?" follows
NAMES = {
    "event": "an event", "results": "the company's results", "rating": "a credit rating", "rate": "the Central Bank's rate",
    "prices": "prices", "watch": "the Money Watch", "homes": "home loans", "story": "a news story", "nudge": "investors' view",
    "takeover": "a takeover offer", "stake": "a disclosed stake", "infra": "public works", "price": "the share price",
}


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def event_key(conn: Connection, event: dict) -> str:
    """An event's key. Never its number: events are numbered in the order they were drawn, not by day, so numbers would show
    how many are still to come this quarter. The key is a keyed hash, which says nothing about order or count."""
    import hashlib
    import hmac
    seed = _rows(conn, "SELECT fortune_seed FROM world_state")[0]["fortune_seed"]
    mark = hmac.new(seed.encode(), f"event:{event['id']}".encode(), hashlib.sha256).hexdigest()[:12]
    return f"event:{event['period']}:{event['day']}:{mark}"


def link(conn: Connection, effect: str, cause: str, words: str, period: int, now: datetime, numbers: dict | None = None) -> None:
    """Record that `cause` led to `effect`. Recording the same link twice changes nothing."""
    if effect == cause or not words:
        return
    conn.execute("INSERT INTO ripple_links (effect, cause, words, numbers, period, at) VALUES (%s, %s, %s, %s, %s, %s)"
                 " ON CONFLICT (effect, cause) DO NOTHING", (effect, cause, words[:400], Jsonb(numbers or {}), period, now))


def causes(conn: Connection, effect: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM ripple_links WHERE effect = %s ORDER BY id", (effect,))


def effects(conn: Connection, cause: str) -> list[dict]:
    return _rows(conn, "SELECT * FROM ripple_links WHERE cause = %s ORDER BY id", (cause,))


def chain(conn: Connection, key: str, *, visible_period: int | None = None) -> dict:
    """What led to `key`, step by step, at three depths. `visible_period`: links recorded in a quarter after it are left out
    (nothing from the future of the reader's game day). Each cause is followed back once; the first cause of each
    step leads the one-line answer."""
    steps, seen, frontier = [], {key}, [key]
    while frontier and len(steps) < MOST_STEPS:
        nxt = []
        for k in frontier:
            for c in causes(conn, k):
                if visible_period is not None and c["period"] > visible_period:
                    continue
                steps.append({"effect": c["effect"], "cause": c["cause"], "words": c["words"], "numbers": c["numbers"]})
                if c["cause"] not in seen:
                    seen.add(c["cause"])
                    nxt.append(c["cause"])
                if len(steps) >= MOST_STEPS:
                    break
        frontier = nxt
    first = steps[0]["words"] if steps else "No cause is on the record for this."
    return {
        "key": key,
        "one_line": first,
        "chain": [s["words"] for s in steps],
        "numbers": [{"step": s["words"], "figures": s["numbers"]} for s in steps if s["numbers"]],
        "steps": steps,
    }


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def at_close(conn: Connection, period: int, results: list, happening: list[dict], measured: dict, watch: dict, now: datetime) -> None:
    """Link the quarter's results to the events that moved them, credit ratings to the results, and the Central Bank's
    decision to prices and the Money Watch. Only public things, and only what has happened."""
    from simulation import clock, events, newsroom_facts
    label = clock.period_label(period)
    for company, result in results:
        if not company.get("listed"):
            continue
        key = f"results:{company['ticker']}:{period}"
        effect = events.company_effects([e for e in happening if e["period"] == period], company)
        for e in effect["events"]:
            if not e.get("id"):
                continue
            kind = e["kind"].replace("_", " ")
            change = effect["sales_bps"] - 10_000
            link(conn, key, event_key(conn, e),
                 f"A {kind} on day {e['day']} of {label} changed what {company['name']} could sell.", period, now,
                 {"sales effect of the quarter's events": f"{'+' if change >= 0 else '-'}{_percent(change)}"})
        if result.get("interest_expense"):
            link(conn, key, f"rate:{period - 1}",
                 f"{company['name']} paid {newsroom_facts.money(result['interest_expense'])} of interest at the Central Bank's rate.",
                 period, now, {"interest": newsroom_facts.money(result["interest_expense"])})
        link(conn, f"rating:{company['ticker']}:{period}", key,
             f"{company['name']}'s credit rating was worked out from its {label} accounts.", period, now)
    old, new = measured.get("policy_rate_bps"), measured.get("next_policy_rate_bps")
    if new is not None:
        word = "raised" if old is not None and new > old else "cut" if old is not None and new < old else "held"
        link(conn, f"rate:{period}", f"prices:{period}",
             f"Prices were rising {_percent(measured['inflation_bps'])} a year, so the Central Bank {word} its rate"
             f"{'' if word == 'held' else ' to ' + _percent(new)}.", period, now,
             {"inflation": _percent(measured["inflation_bps"]), "rate": _percent(new)})
        if watch and watch.get("rate_extra_bps"):
            link(conn, f"rate:{period}", f"watch:{period}",
                 f"The Money Watch read {watch.get('reading', 'amber')}: the bank set its rate {_percent(watch['rate_extra_bps'])} higher.",
                 period, now, {"extra": _percent(watch["rate_extra_bps"])})
