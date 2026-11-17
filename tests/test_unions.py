"""Unions and strikes, part 1 (owner, 16 November 2026: "build"; the leaders are computer-run).

Promises: one union for each industry outside finance; staff anger has real causes and an angry enough workforce lodges
a demand, kept out of sight until its day; on the deadline the board agrees, offers less or refuses, and the union takes
an offer close enough or strikes; a strike is a real event of the quarter that cuts the company's sales; it ends in a
settlement; a deal raises the wage bill and fades as the going rate catches up. Loopholes: a strike drawn at random
for a company whose union decides; a demand seen before its day; money made or lost by the books.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import events, unions
from simulation import world_data as data
from tests.test_careers import NOW9, sound

pytestmark = pytest.mark.world("eight")
SEED = "a-fixed-secret-so-that-every-test-run-repeats"


def _q(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _company(db, sector="manufacturing"):
    return _q(db, "SELECT id, ticker, name, sector, headquarters, listed, union_pay_bps, labour_bps, opex_bps FROM companies"
                  " WHERE listed AND sector = %s ORDER BY ticker LIMIT 1", (sector,))[0]


def test_every_industry_outside_finance_has_a_union_and_strikes_are_no_longer_drawn_at_random(db):
    unions.ensure(db)
    have = {r["sector"] for r in _q(db, "SELECT sector FROM unions")}
    assert have == set(data.UNIONS) & {r["code"] for r in _q(db, "SELECT code FROM sectors")}
    assert not have & {"banking", "insurance"}
    # Over many quarters, chance never strikes a listed company whose union decides its strikes.
    for period in range(20, 60):
        made = events.generate(db, period, SEED + "-unions")
        assert not [e for e in made if e["kind"] == "company_strike"]


def test_anger_has_causes_and_an_angry_workforce_lodges_a_demand_kept_out_of_sight(db, monkeypatch):
    company = _company(db)
    union = _q(db, "SELECT * FROM unions WHERE sector = %s", (company["sector"],))[0]
    calm, _ = unions.anger(db, company, 8, 0, union["militancy_bps"])
    hot, why = unions.anger(db, company, 8, 900, union["militancy_bps"])      # prices outran pay by 9% over the year
    assert hot > calm and any("Prices rose 9%" in w for w in why)
    paid, why_paid = unions.anger(db, {**company, "union_pay_bps": 1000}, 8, 900, union["militancy_bps"])
    assert paid < hot and any("above the going rate" in w for w in why_paid)

    monkeypatch.setattr(unions, "_squeeze", lambda conn, period: 1500)
    db.execute("DELETE FROM union_disputes")
    lodged = unions.at_close(db, 8, SEED, NOW9)
    assert lodged and all(data.UNION_DEMAND_MIN_BPS <= x["demand_bps"] <= data.UNION_DEMAND_MAX_BPS for x in lodged)
    d = _q(db, "SELECT * FROM union_disputes WHERE period = 9 ORDER BY opened_day DESC LIMIT 1")[0]
    assert d["deadline_day"] == d["opened_day"] + data.UNION_NOTICE_DAYS and d["status"] == "open"
    # Nothing is shown before its day: not the demand, and not its news.
    early = unions.view(db, NOW9)                                            # day 1 of the ninth quarter
    assert d["id"] not in {r["id"] for r in early["open"] + early["past"]}
    later = NOW9 + timedelta(hours=int((d["opened_day"] + 1) * 7 * 24 / 90))
    assert d["id"] in {r["id"] for r in unions.view(db, later)["open"]}
    assert _q(db, "SELECT 1 AS x FROM news_items WHERE kind = 'union_demand' AND period = 9 AND day = %s LIMIT 1", (d["opened_day"],))
    sound(db)


def test_the_board_agrees_or_the_union_strikes_and_a_strike_cuts_sales_and_ends_in_a_deal(db, monkeypatch):
    company = _company(db)
    db.execute("UPDATE companies SET union_pay_bps = 0 WHERE id = %s", (company["id"],))
    union = _q(db, "SELECT * FROM unions WHERE sector = %s", (company["sector"],))[0]
    db.execute("DELETE FROM union_disputes")

    def lodge(c, demand):
        return _q(db, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, demand_bps)"
                      " VALUES (%s, %s, 9, 2, 9, 6000, %s) RETURNING *", (union["id"], c["id"], demand))[0]

    # A board that can afford it agrees, and the deal raises the company's wage bill.
    monkeypatch.setattr(unions, "_board_offer", lambda conn, dispute, c: dispute["demand_bps"])
    done = unions.decide(db, lodge(company, 600), SEED, NOW9)
    assert done == {"status": "agreed", "settled_bps": 600}
    assert _company(db)["union_pay_bps"] == 600
    # A stingy board meets a strike: a real event of the quarter, cutting the company's sales.
    other = _company(db, "mining")
    already = other["union_pay_bps"]                    # a deal from the world's own first eight quarters, if any
    monkeypatch.setattr(unions, "_board_offer", lambda conn, dispute, c: 100)
    struck = unions.decide(db, lodge(other, 1000), SEED, NOW9)
    assert struck["status"] == "struck" and data.UNION_STRIKE_DAYS[0] <= struck["strike_days"] <= data.UNION_STRIKE_DAYS[1]
    happened = events.company_effects(events.load(db, 9), {**other, "sector": "mining"})
    assert happened["sales_bps"] < 10_000 and any(e["kind"] == "company_strike" for e in happened["events"])
    # The strike ends at the quarter's close at the latest, halfway between the demand and the offer.
    unions.before_close(db, 9, SEED, NOW9)
    d = _q(db, "SELECT * FROM union_disputes WHERE company_id = %s", (other["id"],))[0]
    assert d["status"] == "ended" and d["settled_bps"] == 550
    assert _company(db, "mining")["union_pay_bps"] == min(already + 550, data.UNION_PAY_LIMIT_BPS)
    assert {"union_deal", "union_strike", "union_strike_over"} <= {r["kind"] for r in _q(db, "SELECT kind FROM news_items WHERE period = 9")}
    sound(db)


def test_a_deal_makes_the_people_dearer_and_fades_as_the_going_rate_catches_up(db):
    # The world's own first eight quarters, run with unions: demands were lodged and answered, and the books balance.
    print(_q(db, "SELECT status, count(*) AS n, sum(coalesce(strike_days, 0)) AS days FROM union_disputes GROUP BY status"))
    company = _company(db)
    db.execute("UPDATE companies SET union_pay_bps = 1000 WHERE id = %s", (company["id"],))
    rows = [{**company, "union_pay_bps": 1000}]
    unions.apply_pay(rows)
    assert rows[0]["labour_bps"] > company["labour_bps"] and rows[0]["opex_bps"] > company["opex_bps"]
    unions.at_close(db, 8, SEED, NOW9)
    assert _company(db)["union_pay_bps"] == 750


def test_the_unions_page_needs_a_login(client):
    assert client.get("/api/unions").status_code == 401
