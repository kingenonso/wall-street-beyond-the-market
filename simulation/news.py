"""The automatic news wire (design document, section 12).

The wire prints only what the game's records hold. Each item starts from a
recorded fact (an event, a filed report, a Central Bank decision, a Money
Watch reading), picks one of the three newspapers and one of that paper's
wordings for that kind of news, and fills in the facts.

How it avoids repeating itself:
  * sixty kinds of news, nine wordings each, three newspapers with their own voice;
  * a paper never uses the same wording twice running for the same kind of news;
  * the names, places and figures come from the event itself;
  * items about the same affair share a `story`, so a flood is followed by its bill;
  * small items are gathered into one "in brief" column instead of flooding the page.

An item belongs to a quarter and a day in it. Players are shown it only once
that day has come. The full articles written from these facts are in articles.py (Stage 10).
"""

from __future__ import annotations

import hashlib

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock, events
from simulation import world_data as data
from simulation.money import BPS
from simulation.news_kinds import BY_NAME, OUTLETS
from simulation.news_wordings import abroad as _abroad
from simulation.news_wordings import property as _property
from simulation.news_wordings import property2 as _property2
from simulation.news_wordings import capital as _capital
from simulation.news_wordings import deals as _deals
from simulation.news_wordings import dealmaking as _dealmaking
from simulation.news_wordings import economy as _economy
from simulation.news_wordings import happenings as _happenings
from simulation.news_wordings import places as _places
from simulation.news_wordings import results as _results

WORDINGS: dict[str, dict[str, list[tuple[str, str]]]] = {
    **_abroad.WORDINGS, **_property.WORDINGS, **_property2.WORDINGS, **_places.WORDINGS, **_happenings.WORDINGS, **_economy.WORDINGS, **_results.WORDINGS, **_capital.WORDINGS, **_deals.WORDINGS, **_dealmaking.WORDINGS,
}

# How a kind of business reads in the middle of a sentence.
SECTOR_WORDS = {
    "banking": "banking", "consumer": "consumer goods, food and drinks", "oil_gas": "oil and gas",
    "telecoms": "telecoms", "cement": "cement and building materials", "agriculture": "agriculture",
    "real_estate": "real estate and construction", "manufacturing": "manufacturing", "media": "media",
    "insurance": "insurance", "power": "power and utilities", "transport": "transport and logistics",
    "aviation": "airlines", "hospitality": "hotels and leisure", "shipping": "shipping and ports",
}
COMMODITY_WORDS = {"energy": "energy", "metals": "metals", "agriculture": "farm produce", "materials": "building materials"}
GOOD_NEWS = {"local_boom", "sector_demand_surge", "good_harvest", "contract_win", "new_product"}
# How an earlier event is named when the wire comes back to it.
EVENT_NAMES = {"flood": "the flood in {location}", "factory_fire": "the fire at {company}"}

# The days of a quarter on which each kind of end-of-quarter news comes out.
DAY_RATE, DAY_PRICES, DAY_WATCH, DAY_ECONOMY, DAY_AFTERMATH = 1, 1, 2, 3, 4
RESULTS_FIRST_DAY, RESULTS_DAYS, DAY_ROUNDUP = 5, 16, 22

STRONG_MOVE_BPS = 3000            # profit up or down by 30% is a story of its own
SMALL_MOVE_BPS = 300              # under 3% is not news at all
BIG_JOBS_BPS = 500                # a company changing its staff by 5%
SMALL_JOBS_BPS = 200
COMMODITY_NEWS_BPS = 800          # a commodity ending the quarter 8% up or down
INFLATION_MOVE_BPS = 75
MOST_RESULT_STORIES = 4           # of each kind, per quarter
MOST_RATING_STORIES = 5
NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
ORDINALS = ("", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _pick(*key) -> int:
    """A fixed whole number for a key. It decides which paper and which wording tell a story;
    nothing secret depends on it."""
    return int.from_bytes(hashlib.sha256(":".join(str(k) for k in key).encode()).digest()[:6], "big")


def percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def money_words(kobo: int) -> str:
    amount = abs(kobo) / 100
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if amount >= size:
            return f"₦{amount / size:.1f} {word}".replace(".0 ", " ")
    return f"₦{amount:,.0f}"


def people(count: int) -> str:
    count = abs(count)
    if count >= 10_000:
        count = round(count, -3)
    elif count >= 1000:
        count = round(count, -2)
    elif count >= 100:
        count = round(count, -1)
    return f"about {count:,}"


def number_word(count: int) -> str:
    return NUMBER_WORDS[count] if 0 <= count < len(NUMBER_WORDS) else str(count)


def ordinal(count: int) -> str:
    if 0 < count < len(ORDINALS):
        return ORDINALS[count]
    ending = "th" if 10 <= count % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(count % 10, "th")
    return f"{count}{ending}"


def signed_percent(bps: int) -> str:
    """A percentage that keeps its minus sign, for a figure that a wording calls a rise."""
    return ("-" if bps < 0 else "") + percent(bps)


def names(items: list[str], other: str, tail: str = "") -> str:
    """'A', 'A and B', or 'A, B and 3 other companies'."""
    if len(items) <= 3:
        listed = items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
        return listed
    rest = len(items) - 2
    return f"{items[0]}, {items[1]} and {rest} {other}{tail}"


def severity(event: dict) -> tuple[str, int]:
    """One plain word for how hard an event hits, and where it sits from 0 (mildest) to 100."""
    kind = events.BY_NAME[event["kind"]]
    if kind.damage != (0, 0):
        # Where there is damage, the word describes the damage (the wordings speak of it).
        low, high = kind.damage
        position = (event["damage_bps"] - low) * 100 // (high - low)
        return ("light" if position < 25 else "moderate" if position < 50 else "serious" if position < 80 else "severe"), position
    low, high = kind.sales
    value = event["sales_bps"]
    if low == high:
        return "moderate", 50
    position = (value - low) * 100 // (high - low)
    if event["kind"] in GOOD_NEWS:
        return ("modest" if position < 34 else "strong" if position < 75 else "very strong"), position
    position = 100 - position                # for bad news the lowest figure is the hardest blow
    return ("light" if position < 25 else "moderate" if position < 50 else "serious" if position < 80 else "severe"), position


_held_back: list[dict] | None = None


# A results story compares with the same quarter a year ago once there is one. The wordings
# were written for "the quarter before"; these put the right comparison in.
_YEARLY_WORDS = (
    (" the quarter before", " in the same quarter a year ago"), ("three months earlier", "a year earlier"),
    ("Three months ago", "A year ago"), ("The previous quarter", "The same quarter a year ago"),
    ("the previous quarter", "the same quarter a year ago"),
)


def publish(conn: Connection, *, period: int, day: int, kind: str, story: str, facts: dict,
            tickers=(), sectors=(), locations=(), boost: int = 0) -> list[dict]:
    """Print one piece of news. The more it matters, the more papers carry it, each in its own words."""
    spec = BY_NAME[kind]
    missing = [name for name in spec.fields if name not in facts]
    if missing:
        raise ValueError(f"News of kind {kind} needs the facts {missing}.")
    if _held_back is not None:
        # A quarter's results are gathered first and printed in date order (see `for_results`).
        _held_back.append(dict(period=period, day=day, kind=kind, story=story, facts=facts, tickers=tickers,
                               sectors=sectors, locations=locations, boost=boost))
        return []
    importance = max(min(spec.importance + boost, 100), 0)
    papers = list(OUTLETS)
    first = _pick(story, kind, period, "paper") % len(papers)
    papers = papers[first:] + papers[:first]
    coverage = 3 if importance >= 80 else 2 if importance >= 60 else 1
    printed = []
    for outlet in papers[:coverage]:
        options = WORDINGS[kind][outlet]
        choice = _pick(story, kind, period, outlet, "wording") % len(options)
        # Only items dated before this one count, so what a reader can see today never depends
        # on something still hidden later in the quarter.
        last = _rows(conn, "SELECT facts->>'wording' AS wording FROM news_items WHERE kind = %s AND outlet = %s"
                           " AND (period, day) <= (%s, %s) ORDER BY period DESC, day DESC, id DESC LIMIT 1",
                     (kind, outlet, period, day))
        if last and last[0]["wording"] is not None and int(last[0]["wording"]) == choice:
            choice = (choice + 1) % len(options)          # never the same words twice running
        # No item twice: the same paper never prints the same kind of news about the same affair on the same day.
        if _rows(conn, "SELECT 1 AS x FROM news_items WHERE story = %s AND kind = %s AND outlet = %s AND period = %s AND day = %s LIMIT 1",
                 (story, kind, outlet, period, min(max(day, 1), clock.GAME_DAYS_PER_QUARTER))):
            continue
        # A follow-up points at the first item about the same affair (Stage 10).
        first_item = _rows(conn, "SELECT id FROM news_items WHERE story = %s AND (period, day) < (%s, %s) ORDER BY period, day, id LIMIT 1",
                           (story, period, day))
        headline, body = (text.format(**facts) for text in options[choice])
        if facts.get("yearly"):
            for old, new in _YEARLY_WORDS:
                headline, body = headline.replace(old, new), body.replace(old, new)
        item = {
            "period": period, "day": min(max(day, 1), clock.GAME_DAYS_PER_QUARTER), "outlet": outlet, "kind": kind,
            "story": story, "importance": importance, "headline": headline, "body": body,
            "tickers": list(tickers), "sectors": list(sectors), "locations": list(locations),
            "facts": Jsonb({**facts, "wording": choice}),
            "follows": first_item[0]["id"] if first_item else None,
        }
        columns = list(item)
        conn.execute(
            f"INSERT INTO news_items ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            list(item.values()),
        )
        printed.append(item)
    return printed


# ---------------------------------------------------------------------------
# News of things that happen on a day
# ---------------------------------------------------------------------------

def _story_of(event: dict) -> str:
    target = (event.get("facts") or {}).get("ticker") or event.get("sector") or event.get("location") or "nation"
    return f"{event['kind']}:{target}:{event['period']}"


def for_events(conn: Connection, happening: list[dict]) -> None:
    """Write the news of a quarter's events. Each is dated the day it happens, and stays out of
    sight until then."""
    if not happening:
        return
    companies = _rows(
        conn,
        "SELECT c.id, c.ticker, c.name, c.sector, c.headquarters,"
        "   (SELECT r.base_revenue FROM company_results r WHERE r.company_id = c.id ORDER BY r.period DESC LIMIT 1) AS size"
        " FROM companies c WHERE c.listed ORDER BY 6 DESC NULLS LAST, c.ticker",
    )
    # In date order, so each item's wording depends only on items dated before it.
    for event in sorted(happening, key=lambda e: (e["period"], e["day"], e.get("id") or 0)):
        kind = events.BY_NAME[event["kind"]]
        touched = [c for c in companies if events.touches(event, c)]
        word, position = severity(event)
        facts: dict = {}
        boost = (position - 50) // 6
        if kind.scope == "national":
            facts = {"commodity": COMMODITY_WORDS[event["commodity"]], "size": f"about {percent(event['price_bps'])}"}
            boost = (abs(event["price_bps"]) - 1500) // 150
        elif kind.scope == "company":
            company = next(c for c in companies if c["id"] == event["company_id"])
            touched = [company]
            facts = {"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
                     "sector": SECTOR_WORDS[company["sector"]], "severity": word}
        elif kind.scope == "sector":
            facts = {
                "sector": SECTOR_WORDS[event["sector"]], "severity": word,
                "companies": names([c["name"] for c in touched], "other companies") if touched else "companies in that business",
            }
        else:
            facts = {
                "location": event["location"], "severity": word,
                "companies": names([c["name"] for c in touched], "other companies", " based there") if touched
                             else "businesses in the area",
            }
        publish(
            conn, period=event["period"], day=event["day"], kind=event["kind"], story=_story_of(event), facts=facts,
            tickers=[c["ticker"] for c in touched],
            sectors=sorted({c["sector"] for c in touched} | ({event["sector"]} if event.get("sector") else set())),
            locations=[event["location"]] if event.get("location") else [], boost=boost,
        )


# ---------------------------------------------------------------------------
# News of a quarter's results. It comes out over the first days of the next quarter.
# ---------------------------------------------------------------------------

def _results_day(ticker: str, period: int) -> int:
    return RESULTS_FIRST_DAY + _pick(ticker, period, "results day") % RESULTS_DAYS


_GOOD_SIGNS = ("rose about", "sold well", "won a large contract", "brisk", "jumped", "lifted its sales", "paid it",
               "won customers", "gaining ground", "strong season", "spent more", "lower than usual", "recovered")
_BAD_SIGNS = ("cut its sales", "cost it", "fell about", "took about", "paid out", "destroyed", "wrote off",
              "could not", "higher than usual", "added about", "lost customers", "losing ground", "weak season",
              "spent less", "cut back")


def _cause(result: dict, good: bool) -> str:
    """The company's own explanation of its quarter, as one sentence that fits the direction of the news.
    The first sign listed that appears in its filing wins, so an event is named before a slow drift."""
    drivers = result["drivers"]
    said = [r for r in drivers.get("revenue", []) if "of its sales were to" not in r] + list(drivers.get("notes") or [])
    for sign in (_GOOD_SIGNS if good else _BAD_SIGNS):
        for sentence in said:
            if sign in sentence:
                sentence = sentence.split(": its pull was")[0]
                return sentence if sentence.endswith(".") else sentence + "."
    return "The company gave no single reason."


def _rate_news(conn: Connection, period: int, now: dict) -> None:
    def move(row: dict) -> int:
        return (row["next_policy_rate_bps"] > row["policy_rate_bps"]) - (row["next_policy_rate_bps"] < row["policy_rate_bps"])

    history = _rows(conn, "SELECT period, policy_rate_bps, next_policy_rate_bps FROM economy_results"
                          " WHERE period BETWEEN 1 AND %s ORDER BY period DESC", (period,))
    direction = move(now)
    run = 0
    for row in history:
        if move(row) != direction:
            break
        run += 1
    word = {1: "rise", -1: "cut", 0: "hold"}[direction]
    if direction == 0:
        earlier = next((row for row in history if move(row) != 0), None)
        if run >= 2:
            phrase = f"the {ordinal(run)} quarter without a change"
        elif earlier is not None:
            phrase = f"after a {'rise' if move(earlier) > 0 else 'cut'} the quarter before"
        else:
            phrase = "its first decision"
    elif run >= 2:
        phrase = f"the {ordinal(run)} {word} in a row"
    else:
        same = next((row for row in history[1:] if move(row) == direction), None)
        phrase = f"the first {word} since {clock.period_label(same['period'] + 1)}" if same else f"its first {word} so far"
    publish(
        conn, period=period + 1, day=DAY_RATE, kind=f"rate_{word}", story="central-bank-rate",
        facts={"rate": percent(now["next_policy_rate_bps"]), "old_rate": percent(now["policy_rate_bps"]),
               "inflation": signed_percent(now["inflation_bps"]), "target": percent(data.INFLATION_TARGET_BPS), "run": phrase},
        boost=min(run - 1, 4) * 2 if direction else 0,
    )


def _price_news(conn: Connection, period: int, before: dict, now: dict, moves: dict[str, int], oil_told: bool = False) -> None:
    low = data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS
    high = data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS
    inflation, previous = now["inflation_bps"], before["inflation_bps"]
    if inflation < 0:
        return                         # falling prices are told through the Central Bank's decision
    if inflation > high:
        kind, rising = "inflation_high", True
    elif inflation < low:
        kind, rising = "inflation_low", False
    elif inflation - previous >= INFLATION_MOVE_BPS:
        kind, rising = "inflation_rising", True
    elif previous - inflation >= INFLATION_MOVE_BPS:
        kind, rising = "inflation_easing", False
    else:
        kind, rising = "inflation_steady", None
    dearest = max(moves, key=lambda name: moves[name])
    cheapest = min(moves, key=lambda name: moves[name])
    gap = now["demand_gap_bps"]
    if rising is True:
        driver = (f"dearer {COMMODITY_WORDS[dearest]}" if moves[dearest] >= 600 else
                  "strong household spending" if gap >= 150 else "prices rising across the board")
    elif rising is False:
        driver = (f"cheaper {COMMODITY_WORDS[cheapest]}" if moves[cheapest] <= -600 else
                  "weak household spending" if gap <= -150 else "slower price rises across the board")
    else:
        driver = "steady household spending"
    publish(
        conn, period=period + 1, day=DAY_PRICES, kind=kind, story="prices",
        facts={"inflation": percent(inflation), "previous": percent(previous),
               "target": percent(data.INFLATION_TARGET_BPS), "band": f"{percent(low)} to {percent(high)}", "driver": driver},
    )
    for name, change in moves.items():
        if name == "energy" and oil_told:
            continue                              # energy follows the world oil price, which has news of its own
        if abs(change) >= COMMODITY_NEWS_BPS:
            publish(
                conn, period=period + 1, day=DAY_ECONOMY, kind="commodity_up" if change > 0 else "commodity_down",
                story=f"commodity:{name}", facts={"commodity": COMMODITY_WORDS[name], "size": percent(change)},
                sectors=[data.COMMODITIES[name][0]], boost=(abs(change) - 1200) // 200,
            )


OIL_NEWS_BPS = 800                 # the oil price 8% up or down on the quarter
NAIRA_NEWS_BPS = 300               # the naira 3% weaker or stronger
FOREIGN_NEWS_BPS = 2000            # foreign investors bringing in or taking out a fifth of what they hold


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _naira_rate(fx: int) -> str:
    return f"₦{fx / 100:,.0f}"


def _abroad_news(conn: Connection, period: int, row: dict, now: dict) -> None:
    """The oil price, the naira and foreign investors: news when they moved enough to matter."""
    earlier = _rows(conn, "SELECT oil_cents, fx FROM abroad_results WHERE period = %s", (period - 1,))
    if not earlier:
        return
    was = earlier[0]
    oil_change = (row["oil_cents"] - was["oil_cents"]) * BPS // was["oil_cents"]
    if abs(oil_change) >= OIL_NEWS_BPS:
        publish(conn, period=period + 1, day=DAY_ECONOMY, kind="oil_up" if oil_change > 0 else "oil_down", story="oil",
                facts={"price": _dollars(row["oil_cents"]), "previous": _dollars(was["oil_cents"]),
                       "change": percent(abs(oil_change))},
                sectors=["oil_gas"], locations=[data.PORT_HARCOURT], boost=(abs(oil_change) - 1500) // 200)
    fx_change = (row["fx"] - was["fx"]) * BPS // was["fx"]
    if abs(fx_change) >= NAIRA_NEWS_BPS:
        cause = row["reason"].removeprefix("The naira moved mostly on ").rstrip(".")
        publish(conn, period=period + 1, day=DAY_ECONOMY, kind="naira_weaker" if fx_change > 0 else "naira_stronger",
                story="naira", facts={"rate": _naira_rate(row["fx"]), "previous": _naira_rate(was["fx"]),
                                      "change": percent(abs(fx_change)), "cause": cause},
                boost=(abs(fx_change) - 600) // 100)
    held = row["foreign_cash"] + row["foreign_shares"] - row["foreign_inflow"]
    if held > 0 and abs(row["foreign_inflow"]) * BPS // held >= FOREIGN_NEWS_BPS:
        publish(conn, period=period + 1, day=DAY_ECONOMY + 1, kind="foreign_buying" if row["foreign_inflow"] > 0 else "foreign_selling",
                story="foreign_money", facts={"amount": money_words(abs(row["foreign_inflow"])),
                                              "rate": percent(now["next_policy_rate_bps"])})


def _watch_news(conn: Connection, period: int, watch: dict) -> None:
    earlier = _rows(conn, "SELECT reading FROM money_watch_results WHERE period = %s", (period - 1,))
    was = earlier[0]["reading"] if earlier else "green"
    reading = watch["reading"]
    if reading == "green" and was == "green":
        return
    recorded = _rows(conn, "SELECT money_growth_bps, output_growth_bps FROM money_watch_results WHERE period = %s", (period,))[0]
    publish(
        conn, period=period + 1, day=DAY_WATCH, kind=f"money_watch_{reading}", story="money-watch",
        # What players hold between them is private while they are few, so it is never the printed reason.
        facts={"reason": next((r for r in watch["reasons"] if not r.startswith("Players ")),
                              "The Money Watch has changed its reading."),
               "money_growth": signed_percent(recorded["money_growth_bps"]),
               "output_growth": signed_percent(recorded["output_growth_bps"]), "action": watch["action"]},
        boost=0 if reading != was else -15,           # the same warning again matters less than a new one
    )


def _economy_news(conn: Connection, period: int, before: dict, now: dict, policy_rate_bps: int) -> None:
    # What households owe.
    debts = _rows(conn, "SELECT period, sum(debt)::bigint AS debt, sum(jobs)::bigint AS jobs FROM household_results"
                        " WHERE period IN (%s, %s) GROUP BY period", (period - 1, period))
    by_period = {row["period"]: row for row in debts}
    if period - 1 in by_period and by_period[period - 1]["debt"]:
        was, is_now = by_period[period - 1]["debt"], by_period[period]["debt"]
        change = (is_now - was) * BPS // was
        if change >= 350 or change < 0:
            publish(
                conn, period=period + 1, day=DAY_ECONOMY,
                kind="household_borrowing_up" if change > 0 else "household_borrowing_down", story="household-borrowing",
                facts={"change": percent(change), "amount": money_words(is_now),
                       "rate": percent(policy_rate_bps + data.HOUSEHOLD_LOAN_SPREAD_BPS)},
            )
        # Jobs.
        jobs_was, jobs_now = by_period[period - 1]["jobs"], by_period[period]["jobs"]
        if period >= 2 and jobs_was and abs(jobs_now - jobs_was) * 100 >= jobs_was:
            places = _rows(
                conn,
                "SELECT a.location, a.jobs - b.jobs AS change FROM household_results a JOIN household_results b"
                " ON b.location = a.location AND b.period = %s WHERE a.period = %s", (period - 1, period),
            )
            rising = jobs_now > jobs_was
            most = max(places, key=lambda p: p["change"] if rising else -p["change"])
            publish(
                conn, period=period + 1, day=DAY_ECONOMY, kind="jobs_report_up" if rising else "jobs_report_down",
                story="jobs", facts={"jobs": people(jobs_now), "change": people(jobs_now - jobs_was), "location": most["location"]},
                locations=[most["location"]],
            )
    # The size of the economy, once there is a full year to compare.
    if period >= 5:
        year_ago = _rows(conn, "SELECT company_sales FROM economy_results WHERE period = %s", (period - 4,))[0]["company_sales"]
        two_back = _rows(conn, "SELECT a.company_sales AS now, b.company_sales AS then FROM economy_results a"
                               " JOIN economy_results b ON b.period = a.period - 4 WHERE a.period = %s", (period - 1,))
        growth = (now["company_sales"] - year_ago) * BPS // year_ago if year_ago else 0
        earlier = (two_back[0]["now"] - two_back[0]["then"]) * BPS // two_back[0]["then"] if two_back and two_back[0]["then"] else growth
        if growth > 0 and (period % 4 == 0 or abs(growth - earlier) >= 300):
            publish(
                conn, period=period + 1, day=DAY_ECONOMY,
                kind="economy_slowing" if growth < earlier - 100 else "economy_growing", story="economy",
                facts={"growth": percent(growth), "sales": money_words(now["company_sales"])},
            )
    # What the banks owe the Central Bank.
    owed = _rows(conn, "SELECT coalesce(sum(principal_outstanding), 0)::bigint AS total FROM company_debts"
                       " WHERE kind = 'central_bank_loan'")[0]["total"]
    lent = _rows(
        conn,
        "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
        " ON t.id = e.transaction_id WHERE t.kind = 'central_bank_lending' AND t.period = %s AND e.amount > 0", (period,),
    )[0]["total"]
    if owed > 0 and lent * 100 >= now["money"]:          # new borrowing of one percent of all money
        publish(conn, period=period + 1, day=DAY_ECONOMY, kind="bank_central_borrowing", story="central-bank-lending",
                facts={"amount": money_words(owed), "new": money_words(lent)}, sectors=["banking"])


def _aftermath_news(conn: Connection, period: int, happening: list[dict], companies: list[dict],
                    damages: dict, claims_paid: int) -> None:
    by_id = {c["id"]: c for c in companies}
    received = {
        r["account_id"]: r["total"] for r in _rows(
            conn,
            "SELECT e.account_id, sum(e.amount)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
            " ON t.id = e.transaction_id WHERE t.kind = 'insurance_claim' AND t.period = %s AND e.amount > 0"
            " GROUP BY e.account_id", (period,),
        )
    }
    worst, worst_destroyed = None, 0
    for event in happening:
        if event["damage_bps"] <= 0 or event["kind"] not in EVENT_NAMES:
            continue
        destroyed, paid, touched = 0, 0, []
        for company_id, lost in damages.items():
            company = by_id.get(company_id)
            if company is None or not events.touches(event, company):      # a private company's losses are not reported
                continue
            # A company struck twice in a quarter has its loss shared between the two events.
            whole = (company.get("event_effects") or {}).get("damage_bps", 0) or event["damage_bps"]
            destroyed += lost * event["damage_bps"] // whole
            paid += received.get(company["account_id"], 0) * event["damage_bps"] // whole
            touched.append(company)
        if destroyed <= 0:
            continue
        name = EVENT_NAMES[event["kind"]].format(
            location=event["location"], company=by_id[event["company_id"]]["name"] if event["company_id"] else "")
        if destroyed > worst_destroyed:
            worst, worst_destroyed = name, destroyed
        touched.sort(key=lambda c: -damages[c["id"]])
        publish(
            conn, period=period + 1, day=DAY_AFTERMATH, kind="event_aftermath", story=_story_of(event),
            facts={"event": name, "amount": money_words(destroyed), "paid": money_words(paid),
                   "companies": names([c["name"] for c in touched], "other companies")},
            tickers=[c["ticker"] for c in touched], locations=[event["location"]] if event["location"] else [],
        )
    if claims_paid > 0 and worst:
        insurers = [c["name"] for c in companies if c["sector"] == "insurance"]
        publish(
            conn, period=period + 1, day=DAY_AFTERMATH, kind="insurance_claims", story=f"insurance-claims:{period}",
            facts={"amount": money_words(claims_paid), "cause": worst, "insurers": names(insurers, "other insurers")},
            tickers=[c["ticker"] for c in companies if c["sector"] == "insurance"], sectors=["insurance"],
        )


def _company_news(conn: Connection, period: int, results: list[tuple[dict, dict]]) -> None:
    earlier = {
        r["company_id"]: r for r in _rows(
            conn, "SELECT company_id, net_profit, staff, payables, loan_losses, drivers FROM company_results WHERE period = %s",
            (period - 1,))
    }
    # Profit is set against the same quarter a year ago once there is one: many businesses
    # swing with the seasons, so the quarter before is a poor yardstick.
    year_ago = {
        r["company_id"]: r["net_profit"] for r in _rows(
            conn, "SELECT company_id, net_profit FROM company_results WHERE period = %s AND period >= 1", (period - 4,))
    }
    ratings: dict = {}
    for row in _rows(conn, "SELECT DISTINCT ON (company_id, period) company_id, period, credit_rating FROM company_reports"
                           " WHERE period IN (%s, %s) ORDER BY company_id, period, version DESC", (period - 1, period)):
        ratings.setdefault(row["company_id"], {})[row["period"]] = row["credit_rating"]
    order = list(data.LOAN_SPREAD_BPS)                   # AAA first, D last
    by_size = sorted(results, key=lambda pair: -pair[1]["revenue"])
    rank = {company["id"]: place for place, (company, _) in enumerate(by_size)}
    label = clock.period_label(period)
    brief_results: list[tuple[int, str]] = []
    brief_jobs: list[tuple[int, str]] = []
    borrowers: list[tuple[int, dict]] = []
    sharp_moves: list[tuple[int, bool, str, dict]] = []
    rating_moves: list[tuple[int, int, dict]] = []

    for company, result in results:
        prev = earlier.get(company["id"])
        if prev is None:
            continue
        size_boost = 8 if rank[company["id"]] < 10 else -5 if rank[company["id"]] >= 30 else 0
        day = _results_day(company["ticker"], period)
        who = {"company": company["name"], "ticker": company["ticker"], "location": company["headquarters"],
               "sector": SECTOR_WORDS[company["sector"]]}
        tags = {"tickers": [company["ticker"]], "sectors": [company["sector"]], "locations": [company["headquarters"]]}
        story = f"company:{company['ticker']}"
        notes = result["drivers"].get("notes", [])
        earlier_notes = prev["drivers"].get("notes", []) if prev["drivers"] else []

        # Profit.
        yearly = company["id"] in year_ago
        profit, before = result["net_profit"], year_ago[company["id"]] if yearly else prev["net_profit"]
        figures = {**who, "yearly": yearly, "quarter": label, "profit": money_words(profit), "previous_profit": money_words(before),
                   "sales": money_words(result["revenue"]), "cause": _cause(result, good=profit > before),
                   "change": percent((profit - before) * BPS // abs(before)) if before else "0%"}
        if period >= 2:
            if profit < 0 <= before:
                publish(conn, period=period + 1, day=day, kind="company_loss", story=story, facts=figures, boost=size_boost, **tags)
            elif profit > 0 > before:
                publish(conn, period=period + 1, day=day, kind="back_in_profit", story=story, facts=figures, boost=size_boost, **tags)
            elif profit > 0 and before > 0:
                change = (profit - before) * BPS // before
                brief = f"{company['name']} (profit {'up' if change > 0 else 'down'} {percent(change)})"
                if abs(change) >= STRONG_MOVE_BPS:
                    sharp_moves.append((rank[company["id"]], change > 0, brief, dict(
                        period=period + 1, day=day, kind="results_strong" if change > 0 else "results_weak", story=story,
                        facts=figures, boost=size_boost + min((abs(change) - STRONG_MOVE_BPS) // 1000, 10), **tags)))
                elif abs(change) >= SMALL_MOVE_BPS:
                    brief_results.append((rank[company["id"]],
                                          f"{company['name']} (profit {'up' if change > 0 else 'down'} {percent(change)})"))
            elif profit < 0 and before < 0:
                brief_results.append((rank[company["id"]], f"{company['name']} (a further loss of {money_words(profit)})"))

        # Its credit rating, and whether it paid what it owed.
        new, old = ratings.get(company["id"], {}).get(period), ratings.get(company["id"], {}).get(period - 1)
        owed = result["payables"] + result["drivers"].get("repayments_missed", 0)
        if new and old and new != old:
            if new == "D" and result["principal_overdue"] > 0:
                publish(conn, period=period + 1, day=day, kind="default", story=story,
                        facts={**who, "amount": money_words(result["principal_overdue"])}, boost=size_boost, **tags)
            else:
                steps = abs(order.index(new) - order.index(old))
                rating_moves.append((-steps, rank[company["id"]], dict(
                    period=period + 1, day=min(day + 1, clock.GAME_DAYS_PER_QUARTER),
                    kind="rating_upgrade" if order.index(new) < order.index(old) else "rating_downgrade", story=story,
                    facts={**who, "rating": new, "old_rating": old}, boost=size_boost + 4 * (steps - 1), **tags)))
        if owed > 0 and new != "D":
            owed_before = prev["payables"] + (prev["drivers"] or {}).get("repayments_missed", 0)
            if owed_before == 0 or owed >= 2 * owed_before:
                publish(conn, period=period + 1, day=day, kind="missed_payment", story=story,
                        facts={**who, "amount": money_words(owed)}, boost=size_boost, **tags)

        # Jobs.
        if prev["staff"] > 0 and period >= 2:
            change = result["staff"] - prev["staff"]
            share = abs(change) * BPS // prev["staff"]
            if share >= BIG_JOBS_BPS:
                publish(conn, period=period + 1, day=day, kind="job_cuts" if change < 0 else "hiring", story=story,
                        facts={**who, "jobs": people(change), "staff": people(result["staff"])},
                        boost=size_boost + (share - BIG_JOBS_BPS) // 250, **tags)
            elif share >= SMALL_JOBS_BPS:
                brief_jobs.append((rank[company["id"]],
                                   f"{company['name']} ({people(change)} {'more staff' if change > 0 else 'fewer'})"))

        # Dividend held back, for the first time.
        held = "It held back part of its dividend to protect its cash."
        if held in notes and held not in earlier_notes:
            publish(conn, period=period + 1, day=day, kind="dividend_cut", story=story, facts=who, boost=size_boost, **tags)

        # A lender writing off loans.
        losses = result.get("loan_losses", 0)
        if losses >= 100_000_000_00 and losses >= 2 * max(prev["loan_losses"] or 0, 0):       # ₦100 million
            publish(conn, period=period + 1, day=day, kind="bank_loan_losses", story=story,
                    facts={"company": company["name"], "ticker": company["ticker"], "amount": money_words(losses)},
                    boost=size_boost, **tags)

        borrowed = _rows(
            conn,
            "SELECT coalesce(sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
            " ON t.id = e.transaction_id WHERE t.kind = 'new_loan' AND t.period = %s AND e.account_id = %s AND e.amount > 0",
            (period, company["account_id"]),
        )[0]["total"] if any("to expand" in note and "borrowed" in note for note in notes) else 0
        if borrowed > 0:
            borrowers.append((borrowed, {"who": who, "tags": tags, "story": story, "day": day, "boost": size_boost}))

    # Many profits swing with the seasons. The largest companies' sharp moves each get a story
    # (up to four rises and four falls); the others go into the "in brief" column.
    told = {True: 0, False: 0}
    for place, up, brief, item in sorted(sharp_moves, key=lambda move: move[0]):
        if told[up] < MOST_RESULT_STORIES:
            publish(conn, **item)
            told[up] += 1
        else:
            brief_results.append((place, brief))
    # A rating that moves two steps or more is always news. Of the single steps, the largest companies' are.
    single = 0
    for steps, _, item in sorted(rating_moves, key=lambda move: move[:2]):
        if steps <= -2:
            publish(conn, **item)
        elif single < MOST_RATING_STORIES:
            publish(conn, **item)
            single += 1

    # Borrowing to expand is common, so only a company's first such loan in two years is news,
    # and only the two largest of a quarter.
    printed = 0
    for borrowed, item in sorted(borrowers, key=lambda pair: -pair[0]):
        if printed >= 2:
            break
        recent = _rows(conn, "SELECT 1 FROM news_items WHERE kind = 'expansion' AND story = %s AND period > %s LIMIT 1",
                       (item["story"], period - 8))
        if recent:
            continue
        publish(conn, period=period + 1, day=item["day"], kind="expansion", story=item["story"],
                facts={**item["who"], "amount": money_words(borrowed)}, boost=item["boost"], **item["tags"])
        printed += 1

    # The smaller items, gathered.
    for kind, entries in (("roundup_results", brief_results), ("roundup_jobs", brief_jobs)):
        if len(entries) < 2:
            continue
        entries.sort()
        shown = [text for _, text in entries[:3]]
        listed = shown[0] + " and " + shown[1] if len(shown) == 2 else ", ".join(shown[:-1]) + " and " + shown[-1]
        publish(conn, period=period + 1, day=DAY_ROUNDUP, kind=kind, story=f"{kind}:{period}",
                facts={"quarter": label, "count": number_word(len(entries)), "list": listed})


def for_results(conn: Connection, period: int, *, before: dict, now: dict, watch: dict, happening: list[dict],
                companies: list[dict], results: list[tuple[dict, dict]], damages: dict, claims_paid: int,
                policy_rate_bps: int, abroad_now: dict | None = None) -> None:
    """Write the news of a quarter that has just closed. It is dated in the first days of the next quarter."""
    moves = {
        name: (now[column] - before[column]) * BPS // before[column]
        for name, column in (("energy", "energy_bps"), ("metals", "metals_bps"),
                             ("agriculture", "agriculture_bps"), ("materials", "materials_bps"))
    }
    # Gather everything first, then print it in date order: a paper avoids the wording it used
    # last time for the same kind of news, and "last time" must mean the item dated before it.
    global _held_back
    _held_back = gathered = []
    try:
        _rate_news(conn, period, now)
        _price_news(conn, period, before, now, moves, oil_told=abroad_now is not None)
        if abroad_now is not None:
            _abroad_news(conn, period, abroad_now, now)
        _watch_news(conn, period, watch)
        _economy_news(conn, period, before, now, policy_rate_bps)
        # A private company's accounts are not published, so its quarter is not news.
        listed = [c for c in companies if c.get("listed", True)]
        _aftermath_news(conn, period, happening, listed, damages, claims_paid)
        _company_news(conn, period, [(c, r) for c, r in results if c.get("listed", True)])
    finally:
        _held_back = None
    for item in sorted(gathered, key=lambda item: item["day"]):
        publish(conn, **item)


def visible(conn: Connection, period_now: int, day_now: int, *, limit: int = 60, outlet: str | None = None,
            ticker: str | None = None, before: tuple[int, int] | None = None) -> list[dict]:
    """The news a player may read: everything dated up to today, newest first. Nothing dated later is ever returned."""
    conditions = ["(period < %s OR (period = %s AND day <= %s))"]
    params: list = [period_now, period_now, day_now]
    if outlet:
        conditions.append("outlet = %s")
        params.append(outlet)
    if ticker:
        conditions.append("%s = ANY(tickers)")
        params.append(ticker)
    if before:
        conditions.append("(period, day) < (%s, %s)")
        params.extend(before)
    params.append(limit)
    return _rows(
        conn,
        "SELECT id, period, day, outlet, kind, story, importance, headline, body, tickers, sectors, locations, follows, author_id,"
        " facts->>'author' AS author, facts->>'outlet' AS byline, (facts->>'story_id')::bigint AS story_id FROM news_items"
        f" WHERE {' AND '.join(conditions)} ORDER BY period DESC, day DESC, importance DESC, id DESC LIMIT %s",
        params,
    )


def alerts(conn: Connection, period_now: int, day_now: int, after: tuple[int, int, int] | None, *, limit: int = 3) -> dict:
    """The stories published since the player last looked, for the quiet pop-ups. `after` is the
    mark the last look returned: (period, day, the highest story number already published that day).
    The first look returns no stories, only a mark, so nobody is shown the whole past at once.
    Nothing dated later than today is ever returned, and a mark from the future is treated as today."""
    today = _rows(conn, "SELECT coalesce(max(id), 0) AS top FROM news_items WHERE period = %s AND day = %s", (period_now, day_now))[0]
    mark = (period_now, day_now, today["top"])
    if after is None or tuple(after[:2]) > (period_now, day_now):
        return {"items": [], "more": 0, "mark": mark}
    p, d, top = after
    found = _rows(conn, """
        SELECT period, day, outlet, headline, importance, tickers FROM news_items
        WHERE (period < %(pn)s OR (period = %(pn)s AND day <= %(dn)s))
          AND ((period, day) > (%(p)s, %(d)s) OR (period = %(p)s AND day = %(d)s AND id > %(top)s))
        ORDER BY period DESC, day DESC, importance DESC, id DESC LIMIT 200
    """, {"pn": period_now, "dn": day_now, "p": p, "d": d, "top": top})
    return {"items": found[:limit], "more": max(0, len(found) - limit), "mark": mark}


def price_moves(conn: Connection, items: list[dict], start, now) -> dict:
    """For each story about at most six companies: how each company's share price has moved since the
    story came out, from the last close before that day to the price now. Public prices only; a share
    that had not traded before the story has no move to show. Keyed by (period, day, ticker)."""
    from bisect import bisect_left
    from datetime import timedelta

    from simulation import clock as game_clock
    wanted = {t for item in items if 0 < len(item["tickers"]) <= 6 for t in item["tickers"]}
    if not wanted:
        return {}
    quarter = timedelta(days=game_clock.REAL_DAYS_PER_QUARTER)
    earliest = min(start + (i["period"] - 1) * quarter for i in items if 0 < len(i["tickers"]) <= 6)
    closes: dict = {}
    # Only the days the stories need are read: from a fortnight before the oldest story's quarter.
    for row in _rows(conn, """
        SELECT DISTINCT ON (t.company_id, t.session_date) c.ticker, t.session_date, t.price / split_factor(t.company_id, t.id) AS price
        FROM market_trades t JOIN companies c ON c.id = t.company_id
        WHERE c.ticker = ANY(%s) AND t.session_date >= %s ORDER BY t.company_id, t.session_date, t.id DESC
    """, (list(wanted), (game_clock.to_lagos(earliest) - timedelta(days=14)).date())):
        closes.setdefault(row["ticker"], []).append((row["session_date"], int(row["price"])))
    current = {r["ticker"]: int(r["price"]) for r in _rows(conn, """
        SELECT c.ticker, coalesce(m.last_price, m.reference_price) AS price
        FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = ANY(%s)""", (list(wanted),))}
    out: dict = {}
    for item in items:
        if not 0 < len(item["tickers"]) <= 6:
            continue
        moment = start + (item["period"] - 1) * quarter + quarter * (item["day"] - 1) / game_clock.GAME_DAYS_PER_QUARTER
        if moment > now:
            continue
        day = game_clock.to_lagos(moment).date()
        for ticker in item["tickers"]:
            days = closes.get(ticker, [])
            at = bisect_left([d for d, _ in days], day)
            if at == 0 or ticker not in current:
                continue
            before = days[at - 1][1]
            if before > 0:
                out[(item["period"], item["day"], ticker)] = (current[ticker] - before) * 10_000 // before
    return out
