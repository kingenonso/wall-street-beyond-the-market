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
    # A company's own page shows its union and its dispute (owner, 17 November 2026: no Unions tab).
    ticker = _q(db, "SELECT ticker FROM companies WHERE id = %s", (d["company_id"],))[0]["ticker"]
    mine = unions.view(db, later, ticker)["company"]
    assert mine["ticker"] == ticker and mine["union"] and d["id"] in {r["id"] for r in mine["now"]}
    assert d["id"] not in {r["id"] for r in unions.view(db, NOW9, ticker)["company"]["now"]}
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


def test_the_unions_page_needs_a_login_and_a_proper_ticker(client, player):
    assert client.get("/api/unions", params={"ticker": "x'; DROP TABLE unions;--"}).status_code == 422
    client.cookies.clear()
    assert client.get("/api/unions").status_code == 401


# ---------------------------------------------------------------------------
# Part 2: the empire at the table (owner, 17 November 2026)
# ---------------------------------------------------------------------------

def _table_dispute(db, demand=1000, deadline=40):
    """A player-run empire owns a private company, and its union has a demand open (made public on day 2)."""
    from tests.test_deals_more import own
    from tests.test_firm import firm_of
    empire, team = firm_of(db)
    team = {k: v[0] if isinstance(v, tuple) else v for k, v in team.items()}     # player ids
    company = own(db, empire, "ENI")
    union = _q(db, "SELECT * FROM unions WHERE sector = %s", (company["sector"],))
    if not union:
        unions.ensure(db)
        union = _q(db, "SELECT * FROM unions WHERE sector = %s", (company["sector"],))
    d = _q(db, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, demand_bps, empire_id)"
               " VALUES (%s, %s, 9, 2, %s, 6000, %s, %s) RETURNING *", (union[0]["id"], company["id"], deadline, demand, empire["id"]))[0]
    return empire, team, company, d


def test_the_head_answers_members_advise_and_others_cannot_sit_at_the_table(db):
    from simulation import ledger
    empire, team, company, d = _table_dispute(db)
    assert unions.controlling_empire(db, company["id"])["id"] == empire["id"]
    assert [w["ticker"] for w in unions.waiting(db, team["head"], NOW9)] == [company["ticker"]]
    # A member who is not the head may advise, but not answer.
    with pytest.raises(unions.UnionError, match="Only the empire's head"):
        unions.answer(db, team["risk_manager"], d["id"], "agree", None, NOW9)
    unions.advise(db, team["risk_manager"], d["id"], "offer", 600, "A strike costs more than 6%.", NOW9)
    page = unions.view(db, NOW9, company["ticker"], team["head"])
    table = page["company"]["now"][0]["table"]
    assert table["is_head"] and table["advice"][0]["advice"] == "offer" and table["advice"][0]["build"] == "Risk Manager"
    assert table["risk"]["strike_long"] > table["risk"]["strike_short"] > 0 and table["risk"]["rise_two_years"] > 0
    # A player outside the empire sees the dispute but not the table, and cannot act.
    from tests.test_builds import pro
    outsider = pro(db, "asset_manager", "Outsider")[0]
    assert "table" not in unions.view(db, NOW9, company["ticker"], outsider)["company"]["now"][0]
    with pytest.raises(unions.UnionError, match="controls this company"):
        unions.advise(db, outsider, d["id"], "agree", None, "", NOW9)
    # More time is asked once; a mediator is paid from the empire's account, through the books.
    first = unions.more_time(db, team["head"], d["id"], NOW9)
    with pytest.raises(unions.UnionError, match="already asked"):
        unions.more_time(db, team["head"], d["id"], NOW9)
    after = _q(db, "SELECT deadline_day FROM union_disputes WHERE id = %s", (d["id"],))[0]["deadline_day"]
    assert after == (40 + data.UNION_MORE_TIME_DAYS if first["granted"] else 40)
    before = ledger.balance(db, empire["account_id"])
    fee = unions.hire_mediator(db, team["head"], d["id"], NOW9)["fee"]
    assert ledger.balance(db, empire["account_id"]) == before - fee and fee >= data.UNION_MEDIATOR_FEE_NAIRA[0] * 100
    # The head agrees: no strike, and at a private company the empire's own pay rises by the deal.
    pay = _q(db, "SELECT pay_index_bps FROM private_profiles WHERE company_id = %s", (company["id"],))[0]["pay_index_bps"]
    done = unions.answer(db, team["head"], d["id"], "agree", None, NOW9)
    assert done["status"] == "agreed"
    assert _q(db, "SELECT pay_index_bps FROM private_profiles WHERE company_id = %s", (company["id"],))[0]["pay_index_bps"] == pay + pay * 1000 // 10_000
    with pytest.raises(unions.UnionError, match="already been answered"):
        unions.answer(db, team["head"], d["id"], "refuse", None, NOW9)
    assert _q(db, "SELECT 1 AS x FROM empire_events WHERE empire_id = %s AND words LIKE 'Deal at%%'", (empire["id"],))
    assert unions.waiting(db, team["head"], NOW9) == []
    sound(db)


def test_a_refusal_or_silence_brings_a_strike(db):
    empire, team, company, d = _table_dispute(db)
    struck = unions.answer(db, team["head"], d["id"], "refuse", None, NOW9)
    assert struck["status"] == "struck"
    row = _q(db, "SELECT * FROM union_disputes WHERE id = %s", (d["id"],))[0]
    assert row["answer"] == "refuse" and row["decided_day"] < row["deadline_day"]          # the strike begins the day of the answer
    # Silence: nobody answers by the deadline, and at the quarter's close the staff take it as a no.
    from tests.test_deals_more import own
    second = own(db, empire, "ENI")                       # the founders' next company of the same industry
    assert second["id"] != company["id"]
    union = _q(db, "SELECT id FROM unions WHERE sector = %s", (second["sector"],))[0]
    quiet = _q(db, "INSERT INTO union_disputes (union_id, company_id, period, opened_day, deadline_day, anger_bps, demand_bps, empire_id)"
                   " VALUES (%s, %s, 9, 2, 40, 6000, 800, %s) RETURNING *", (union["id"], second["id"], empire["id"]))[0]
    unions.before_close(db, 9, SEED, NOW9)
    row = _q(db, "SELECT * FROM union_disputes WHERE id = %s", (quiet["id"],))[0]
    assert row["answer"] == "none" and row["strike_days"] and row["status"] == "ended"
    sound(db)


def test_a_private_companys_staff_count_its_pay_and_morale_and_no_walkout_comes_by_chance(db):
    from tests.test_deals_more import own
    from tests.test_firm import firm_of
    empire, _team = firm_of(db)
    company = own(db, empire, "ENI")
    union = _q(db, "SELECT militancy_bps FROM unions WHERE sector = %s", (company["sector"],))[0]
    base, _ = unions.anger(db, {**company, "union_pay_bps": 0}, 8, 0, union["militancy_bps"])
    wage = _q(db, "SELECT wage_index_bps FROM economy_results WHERE period = 8")[0]["wage_index_bps"]
    db.execute("UPDATE private_profiles SET pay_index_bps = %s, morale_bps = 7000 WHERE company_id = %s", (wage * 90 // 100, company["id"]))
    low, why = unions.anger(db, {**company, "union_pay_bps": 0}, 8, 0, union["militancy_bps"])
    assert low > base and any("below the going rate" in w for w in why) and any("morale is low" in w for w in why)


def test_only_the_head_of_the_controlling_empire_can_answer_through_the_website(client, player):
    for path, body in (("/api/unions/answer", {"dispute_id": 1, "choice": "agree"}), ("/api/unions/more-time", {"dispute_id": 1}),
                       ("/api/unions/mediator", {"dispute_id": 1}), ("/api/unions/advise", {"dispute_id": 1, "advice": "refuse"})):
        assert client.post(path, json=body).status_code in (404, 409)
    assert client.post("/api/unions/answer", json={"dispute_id": 1, "choice": "surrender"}).status_code == 422
    assert client.post("/api/unions/answer", json={"dispute_id": 1, "choice": "offer", "offer_bps": -5}).status_code == 422


# ---------------------------------------------------------------------------
# Part 3: union crimes (owner, 17 November 2026)
# ---------------------------------------------------------------------------

def _rival(db):
    """A second empire run by players, with its own private company."""
    from simulation import empires
    from simulation.money import naira
    from tests.test_builds import pro
    from tests.test_deals_more import own
    from tests.test_objectives import give_cash
    head, _ = pro(db, "asset_manager", "rival chief", level=20, cash_naira=60_000_000)
    empire = empires.found(db, head, "Creek Road Partners", naira(40_000_000), 0, NOW9)
    for build in ("investment_banker", "asset_manager", "risk_manager"):
        player, _ = pro(db, build, f"rival {build}", level=4, cash_naira=100_000)
        empires.apply(db, player, empire["id"], NOW9)
        asked = _q(db, "SELECT id FROM empire_applications WHERE player_id = %s AND status = 'waiting'", (player,))[0]["id"]
        empires.decide_application(db, head, asked, True, NOW9)
    empire = empires.open_empire(db, head, NOW9)
    give_cash(db, empire["account_id"], 2_000_000_000)
    return empires._empire(db, empire["id"]), head, own(db, empire, "ENI")


def test_a_rival_can_pay_a_leader_to_make_trouble_and_it_may_come_out(db, monkeypatch):
    from simulation import ledger
    _empire, team, company, d = _table_dispute(db, demand=1000)
    rival, rival_head, _theirs = _rival(db)
    # Only between players: a company the computer runs, or one's own, cannot be a target.
    listed = _company(db)
    with pytest.raises(unions.UnionError, match="another empire"):
        unions.bribe(db, rival_head, listed["ticker"], "strike", NOW9)
    with pytest.raises(unions.UnionError, match="Only the head"):
        unions.bribe(db, team["risk_manager"], company["ticker"], "strike", NOW9)
    monkeypatch.setattr(data, "UNION_BRIBE_REFUSE_BPS", 0)          # this leader takes it
    before = ledger.balance(db, rival["account_id"])
    first_chance = unions.tell_chance(db, rival["id"])
    done = unions.bribe(db, rival_head, company["ticker"], "strike", NOW9)
    assert done["taken"] and ledger.balance(db, rival["account_id"]) == before - done["paid"]
    assert first_chance == data.UNION_TELL_BASE_BPS and unions.tell_chance(db, rival["id"]) == first_chance + data.UNION_TELL_PER_REPEAT_BPS
    with pytest.raises(unions.UnionError, match="already paid"):
        unions.bribe(db, rival_head, company["ticker"], "strike", NOW9)
    # The leader turns hard: an offer of 90% that a fair leader would take is refused, and the staff walk out.
    struck = unions.answer(db, team["head"], d["id"], "offer", 900, NOW9)
    assert struck["status"] == "struck"
    # Nothing is on the court's record while it is hidden; a journalist's file can find it.
    from simulation import courts, press
    assert not [w for w in courts._wrongs(db, 9, NOW9) if w["kind"] == "union_bribery"]
    assert any(b.startswith("bribe:") for b in press._wrongdoing(db, rival["id"]))
    # The leader tells: the news, the rival's standing, and a case the hit empire's head may bring.
    bribe = _q(db, "SELECT * FROM union_bribes WHERE empire_id = %s", (rival["id"],))[0]
    unions._expose(db, bribe, "leader", NOW9)
    assert _q(db, "SELECT 1 AS x FROM news_items WHERE kind = 'union_bribe_exposed' LIMIT 1")
    wrong = [w for w in courts._wrongs(db, 9, NOW9) if w["kind"] == "union_bribery"]
    assert wrong and str(wrong[0]["defendant_id"]) == str(rival_head) and wrong[0]["amount"] >= bribe["amount"]
    assert courts._standing(db, team["head"], wrong[0]) is None
    assert courts._standing(db, team["risk_manager"], wrong[0]) is not None
    assert not press._wrongdoing(db, rival["id"])
    sound(db)


def test_an_owner_can_pay_a_leader_to_settle_and_a_refusing_leader_goes_public(db, monkeypatch):
    empire, team, company, d = _table_dispute(db, demand=1000)
    monkeypatch.setattr(data, "UNION_BRIBE_REFUSE_BPS", 10_000)     # this leader refuses, and tells at once
    told = unions.bribe(db, team["head"], company["ticker"], "calm", NOW9)
    assert not told["taken"]
    assert _q(db, "SELECT exposed_how FROM union_bribes WHERE empire_id = %s", (empire["id"],))[0]["exposed_how"] == "refused"
    assert unions.tell_chance(db, empire["id"]) == data.UNION_TELL_BASE_BPS       # a refused bribe was never paid
    monkeypatch.setattr(data, "UNION_BRIBE_REFUSE_BPS", 0)
    assert unions.bribe(db, team["head"], company["ticker"], "calm", NOW9)["taken"]
    # Half the demand will do now.
    assert unions.answer(db, team["head"], d["id"], "offer", 500, NOW9)["status"] == "agreed"
    sound(db)
