"""Stage 10: full articles for the news wire (owner's suggestion 5, as the owner decided on 16 October 2026).

The owner has no paid writing service yet, so the game writes the articles itself, from the recorded facts only:
  1. the wire item itself;
  2. the background, from the companies' filed accounts and the market;
  3. the wider picture (the Central Bank's rate, prices, the BSX 50);
  4. what it means, in plain words, for a reader learning how the economy works.

Every figure in an article is checked against the record before it is shown: a figure that is not in the item's own
facts or in the background drawn from the record stops the article, and the plain wire item stays. A paid service
can be plugged in later (NEWS_SERVICE_URL and NEWS_SERVICE_KEY); it is given the recorded facts only, never the
world's secret or anything still to come, and its text passes the same check. At most twenty articles are written a
game day; an article is written only for an item a reader can already see.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import clock
from simulation import world_data as data

NUMBER = re.compile(r"₦?\d[\d,]*(?:\.\d+)?(?:%| (?:million|billion|trillion))?")
MEANS = {
    "results": "A company's profit is what is left of its sales after it has paid for what it sells, its staff, its interest and "
               "its tax. Investors value a share by the profit they expect it to earn, so a profit well above or below what they "
               "expected usually moves the share price.",
    "rating": "A credit rating says how likely a company is to pay its debts. A lower rating makes borrowing dearer for it, and "
              "the lenders and investors who hold its bonds and shares look again at what they are worth.",
    "rate": "The Central Bank's rate is the price of borrowing for the whole economy. When it rises, loans cost more, households "
            "and companies borrow and spend less, and prices rise more slowly; when it falls, the opposite.",
    "prices": "Inflation is how fast prices are rising. The Central Bank aims to keep it in its band; when it runs above, the bank "
              "usually raises its rate.",
    "takeover": "In a takeover, a buyer offers the owners of a company more than the market price for their shares. The extra, "
                "the premium, is what persuades them to sell; the share price usually jumps towards the offer.",
    "event": "Events on the ground (a flood, a strike, a new contract) change how much a company can sell and what it costs to "
             "run. Investors mark its shares up or down as they judge how much of its next results will be affected.",
    "property": "Property prices follow the rent a building can earn and the cost of borrowing to buy it. Public works, zoning and "
                "home loans all change what land and buildings are worth.",
    "economy": "The economy's figures (jobs, spending, borrowing) show how much households earn and spend. Companies' sales follow "
               "them, and so, in time, do their shares.",
    "market": "Prices on the exchange move when buyers and sellers change their minds about what a share is worth.",
}
FAMILY = {
    "results_strong": "results", "results_weak": "results", "company_loss": "results", "back_in_profit": "results",
    "rating_upgrade": "rating", "rating_downgrade": "rating", "default": "rating", "missed_payment": "rating",
    "rate_rise": "rate", "rate_cut": "rate", "rate_hold": "rate",
    "inflation_high": "prices", "inflation_low": "prices", "inflation_rising": "prices", "inflation_easing": "prices", "inflation_steady": "prices",
    "takeover_bid": "takeover", "takeover_hostile": "takeover", "takeover_won": "takeover", "takeover_failed": "takeover",
    "empire_offer": "takeover", "empire_offer_won": "takeover", "empire_offer_failed": "takeover", "offer_topped": "takeover",
    "property_up": "property", "property_down": "property", "rezoning": "property", "infrastructure_announced": "property",
    "infrastructure_done": "property", "home_repossessions": "property", "development_done": "property", "property_claim": "property",
    "jobs_report_up": "economy", "jobs_report_down": "economy", "economy_growing": "economy", "economy_slowing": "economy",
    "household_borrowing_up": "economy", "household_borrowing_down": "economy",
}
SERVICE = None                       # a function (facts: dict) -> str | None, set when a paid service is plugged in


def _rows(conn: Connection, sql: str, params=()) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _one(conn: Connection, sql: str, params=()) -> dict | None:
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _money(kobo: int) -> str:
    from simulation import newsroom_facts
    return newsroom_facts.money(kobo)


def _percent(bps: int) -> str:
    return f"{abs(bps) / 100:.1f}".rstrip("0").rstrip(".") + "%"


def figures_in(text: str) -> list[str]:
    return [m.group(0).rstrip(".,") for m in NUMBER.finditer(text)]


def check(text: str, allowed: set[str]) -> list[str]:
    """The figures in `text` that are not in the record. An empty list means every figure stands. A figure must match one in
    the record with its unit: "₦12 billion" is not vouched for by "12%"."""
    known = {f.replace(",", "") for a in allowed for f in figures_in(a)}
    return [f for f in figures_in(text) if f.replace(",", "") not in known]


def _background(conn: Connection, item: dict, label_period: int) -> tuple[list[str], set[str]]:
    from simulation import insight
    from simulation import news
    parts, allowed = [], set()
    for ticker in (item["tickers"] or [])[:2]:
        c = _one(conn, "SELECT c.id, c.name, c.sector, c.headquarters FROM companies c WHERE c.ticker = %s", (ticker,))
        if c is None:
            continue
        reports = insight._filed(conn, c["id"], label_period)
        line = f"{c['name']} is a {news.SECTOR_WORDS.get(c['sector'], c['sector'])} company based in {c['headquarters']}."
        if reports and reports[-1]["period"] >= 1:
            r = reports[-1]
            profit, sales = r["income"]["net_profit"], r["income"]["revenue"]
            p, s = _money(profit), _money(sales)
            line += f" In {clock.period_label(r['period'])} it {'made' if profit >= 0 else 'lost'} {p} on sales of {s}."
            allowed |= {p, s, clock.period_label(r["period"])}
        parts.append(line)
    econ = _one(conn, "SELECT next_policy_rate_bps, inflation_bps, period FROM economy_results WHERE period <= %s ORDER BY period DESC LIMIT 1",
                (label_period,))
    if econ:
        rate, infl = _percent(econ["next_policy_rate_bps"]), _percent(econ["inflation_bps"])
        parts.append(f"The Central Bank's rate stands at {rate}, and prices are rising {infl} a year.")
        allowed |= {rate, infl}
    return parts, allowed


def _quota_left(conn: Connection, period: int, day: int) -> int:
    used = _one(conn, "SELECT count(*) AS n FROM news_articles WHERE period = %s AND day = %s", (period, day))["n"]
    return data.ARTICLES_A_DAY - used


def _service_text(facts: dict) -> str | None:
    if SERVICE is not None:
        return SERVICE(facts)
    url, key = os.environ.get("NEWS_SERVICE_URL"), os.environ.get("NEWS_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        request = urllib.request.Request(url, data=json.dumps({"facts": facts}).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(request, timeout=20) as response:       # noqa: S310 (the owner's own service)
            return json.loads(response.read().decode()).get("article")
    except Exception:
        return None                         # the service is down: the game's own writer and the wire carry on


def article(conn: Connection, item_id: int, period_now: int, day_now: int, now: datetime) -> dict | None:
    """The full article for a wire item a reader can see, written once and kept. None if the day's quota is used up, or
    if the item is a player's story (it is already the author's own words) or not yet published."""
    item = _one(conn, "SELECT * FROM news_items WHERE id = %s", (item_id,))
    if item is None or item["author_id"] is not None or (item["period"], item["day"]) > (period_now, day_now):
        return None
    done = _one(conn, "SELECT * FROM news_articles WHERE news_item_id = %s", (item_id,))
    if done:
        return {"body": done["body"], "writer": done["writer"]}
    # Articles are written for the latest news only (the last few game days), so old archive items cannot use up the day's quota.
    if (period_now - item["period"]) * clock.GAME_DAYS_PER_QUARTER + day_now - item["day"] > data.ARTICLE_FRESH_DAYS:
        return None
    with conn.transaction():          # one writer at a time for the day's quota
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('articles:' || %s || ':' || %s))", (period_now, day_now))
        if _quota_left(conn, period_now, day_now) <= 0:
            return None
        facts = {k: v for k, v in (item["facts"] or {}).items() if k != "wording"}
        allowed = {str(v) for v in facts.values()} | set(figures_in(item["headline"])) | set(figures_in(item["body"]))
        allowed |= {str(item["day"]), clock.period_label(item["period"]), clock.period_label(item["period"] - 1)}
        background, more = _background(conn, item, item["period"] - 1)
        allowed |= more
        writer, body = "built_in", None
        text = _service_text({"headline": item["headline"], "wire": item["body"], "facts": facts, "background": background})
        if text and not check(text, allowed):
            writer, body = "service", text.strip()
        if body is None:
            family = FAMILY.get(item["kind"]) or ("event" if item["kind"] in _event_kinds() else "market")
            body = "\n\n".join([item["body"], " ".join(background), "What it means: " + MEANS[family]])
            if check(body, allowed):
                return None                      # a figure not on the record: no article, the wire item stands alone
        conn.execute("INSERT INTO news_articles (news_item_id, writer, body, figures, period, day, at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                     " ON CONFLICT DO NOTHING", (item_id, writer, body, Jsonb(figures_in(body)), period_now, day_now, now))
        return {"body": body, "writer": writer}


def _event_kinds() -> set[str]:
    from simulation import events
    return set(events.BY_NAME)
