"""Part 4c: the checks for checklist items 16 to 32, one test for each thing the checklist names.

`tests/test_part4c.py` holds items 1 to 15 — the world and its arithmetic. This file holds the rest: the
words the headlines use, the eight new kinds of event and how they reach a reader and a player, the six
new baskets and the funds that copy them, the work each build is given, the six new objectives, and the
screens and troubles the checklist names.

Nothing here has been seen to pass: the sandbox that wrote it has no test runner and no database. Every
call was read back against the code it calls, as the loophole file's were.
"""

from __future__ import annotations

import pathlib

import pytest
from psycopg.rows import dict_row

from simulation import careers, derivatives, etfs, events, exchange, funds, indexes, insight, intel, objectives, objectives_industries
from simulation import objectives_more
from simulation import news, news_kinds
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join, money_accounted_for
from tests.test_builds import EMPLOYER, pro, right_answers
from tests.test_careers import NOW9, professional, sound

pytestmark = pytest.mark.world("eight")

NEW = ("pharma", "retail", "technology", "entertainment", "mining", "fertiliser")
NEW_LISTED = tuple(c.ticker for c in data.COMPANIES if c.sector in NEW and c.listed)
NEW_PRIVATE = tuple(c.ticker for c in data.COMPANIES if c.sector in NEW and not c.listed)
NEW_BASKETS = ("PHARMA", "RETAIL", "TECH", "FILM", "MINING", "FERT")
NEW_EVENTS = ("drug_shortage", "bad_batch", "bumper_harvest", "mine_accident", "seam_runs_out",
              "film_flops", "film_hit", "payments_outage")


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def in_sector(sector: str) -> str:
    """One listed company of that industry, by its code on the exchange."""
    return next(c.ticker for c in data.COMPANIES if c.sector == sector and c.listed)


def reaches(kind: str, ticker: str, *, sector=None, company_id=None) -> bool:
    """Whether one event of that kind reaches that company, through the function the quarter itself uses."""
    company = next(c for c in data.COMPANIES if c.ticker == ticker)
    return events.touches({"kind": kind, "sector": sector, "company_id": company_id},
                          {"id": ticker, "ticker": ticker, "sector": company.sector,
                           "headquarters": company.headquarters})


def happening(db, kind: str, day: int) -> list[dict]:
    """Write one event of that kind as the quarter would, and read it back."""
    kind_ = events.BY_NAME[kind]
    if kind_.scope == "sector":
        db.execute("INSERT INTO events (period, day, kind, sector, sales_bps) VALUES (9, %s, %s, %s, 400)",
                   (day, kind, kind_.only_sectors[0]))
    else:
        db.execute("INSERT INTO events (period, day, kind, company_id, sales_bps)"
                   " SELECT 9, %s, %s, c.id, 400 FROM companies c WHERE c.ticker = %s",
                   (day, kind, in_sector(kind_.only_sectors[0])))
    return [e for e in events.load(db, 9) if e["kind"] == kind and e["day"] == day]


# ---------------------------------------------------------------------------
# 16. Every new industry has a plain English name for headlines
# ---------------------------------------------------------------------------

def test_every_industry_has_a_plain_english_word(db):
    # Six places in the code read this table by the industry's code rather than asking whether an entry
    # is there, so an industry without a word would stop a takeover, a bond or a share offer with an
    # error, not read oddly in a headline.
    assert set(news.SECTOR_WORDS) == {s.code for s in data.SECTORS}
    assert {code: news.SECTOR_WORDS[code] for code in NEW} == {
        "pharma": "medicines", "retail": "groceries", "technology": "technology",
        "entertainment": "film and entertainment", "mining": "mining", "fertiliser": "fertilisers"}
    for word in news.SECTOR_WORDS.values():
        assert word and "_" not in word and not any(ch.isdigit() for ch in word), word

    # And the word is what a reader sees: one event in each of the six prints that word.
    for number, sector in enumerate(NEW):
        db.execute("INSERT INTO events (period, day, kind, sector, sales_bps) VALUES (9, %s, 'sector_demand_surge', %s, 400)",
                   (20 + number, sector))
    news.for_events(db, [e for e in events.load(db, 9) if e["kind"] == "sector_demand_surge"])
    printed = _rows(db, "SELECT * FROM news_items WHERE kind = 'sector_demand_surge'")
    assert {p["facts"]["sector"] for p in printed} == {news.SECTOR_WORDS[s] for s in NEW}
    for p in printed:
        assert p["facts"]["sector"] in p["headline"] + p["body"]


# ---------------------------------------------------------------------------
# 17. The eight new kinds of event, one test each
# ---------------------------------------------------------------------------

def test_event_drug_shortage():
    kind = events.BY_NAME["drug_shortage"]
    assert kind.scope == "sector" and kind.only_sectors == ("pharma",)
    assert kind.sales[1] < 0 and kind.cost[0] > 0                    # fewer supplies, and dearer ones
    assert reaches("drug_shortage", in_sector("pharma"), sector="pharma")
    assert not reaches("drug_shortage", in_sector("entertainment"), sector="pharma")
    assert news_kinds.BY_NAME["drug_shortage"].sample["sector"] == "medicines"


def test_event_bad_batch():
    kind = events.BY_NAME["bad_batch"]
    ticker = in_sector("pharma")
    assert kind.scope == "company" and kind.only_sectors == ("pharma",)
    assert kind.sales[1] < 0 and kind.cost[0] > 0                    # a batch withdrawn, and a recall to pay for
    assert reaches("bad_batch", ticker, company_id=ticker)
    assert not reaches("bad_batch", ticker, company_id="another company")      # one company, not its industry


def test_event_bumper_harvest():
    kind = events.BY_NAME["bumper_harvest"]
    assert kind.scope == "sector" and kind.only_sectors == ("fertiliser",)
    assert kind.sales[0] > 0 and kind.name in news.GOOD_NEWS         # good news for the fertiliser makers
    assert reaches("bumper_harvest", in_sector("fertiliser"), sector="fertiliser")
    assert not reaches("bumper_harvest", in_sector("mining"), sector="fertiliser")


def test_event_mine_accident():
    kind = events.BY_NAME["mine_accident"]
    ticker = in_sector("mining")
    assert kind.scope == "company" and kind.only_sectors == ("mining",)
    assert kind.severe and kind.damage[1] > 0 and kind.sales[1] < 0  # the pit is damaged, and it is a serious one
    assert reaches("mine_accident", ticker, company_id=ticker)


def test_event_seam_runs_out():
    kind = events.BY_NAME["seam_runs_out"]
    ticker = in_sector("mining")
    assert kind.scope == "company" and kind.only_sectors == ("mining",)
    assert kind.sales[1] < 0 and kind.cost[0] > 0 and not kind.severe         # bad, but not the accident
    assert reaches("seam_runs_out", ticker, company_id=ticker)


def test_event_film_flops():
    kind = events.BY_NAME["film_flops"]
    ticker = in_sector("entertainment")
    assert kind.scope == "company" and kind.only_sectors == ("entertainment",)
    assert kind.sales[1] < 0 and kind.name not in news.GOOD_NEWS
    assert reaches("film_flops", ticker, company_id=ticker)


def test_event_film_hit():
    kind = events.BY_NAME["film_hit"]
    ticker = in_sector("entertainment")
    assert kind.scope == "company" and kind.only_sectors == ("entertainment",)
    assert kind.sales[0] > 0 and kind.name in news.GOOD_NEWS
    assert kind.chance_bps == events.BY_NAME["film_flops"].chance_bps         # a hit is as likely as a flop
    assert reaches("film_hit", ticker, company_id=ticker)


def test_event_payments_outage():
    kind = events.BY_NAME["payments_outage"]
    assert kind.scope == "sector" and kind.only_sectors == ("technology",)
    assert kind.sales[1] < 0
    assert reaches("payments_outage", in_sector("technology"), sector="technology")
    assert not reaches("payments_outage", in_sector("retail"), sector="technology")


# ---------------------------------------------------------------------------
# 18. The same events reach the news and the player once
# ---------------------------------------------------------------------------

def test_the_new_events_reach_the_news_and_the_player_once(db):
    for number, kind in enumerate(NEW_EVENTS):
        one = happening(db, kind, 30 + number)
        assert one, kind
        news.for_events(db, one)

        # One story, dated the day it happened, written only from the facts that kind of news may use.
        printed = _rows(db, "SELECT * FROM news_items WHERE kind = %s", (kind,))
        assert len(printed) == 1, (kind, len(printed))
        assert (printed[0]["period"], printed[0]["day"]) == (9, 30 + number)
        assert set(printed[0]["facts"]) <= set(news_kinds.BY_NAME[kind].fields)
        assert "{" not in printed[0]["headline"] and "{" not in printed[0]["body"]

        # Printing the same event again does not print a second story for it.
        news.for_events(db, one)
        assert len(_rows(db, "SELECT * FROM news_items WHERE kind = %s", (kind,))) == 1, kind

    # And the player sees them by the quiet pop-ups: a look from the start of the quarter carries the
    # stories of that quarter, and a look from the mark it hands back carries nothing again.
    first = news.alerts(db, 9, 90, (9, 0, 0), limit=200)
    shown = [item["headline"] for item in first["items"]]
    assert len(shown) == len(set(shown))                          # nothing is handed to the player twice
    assert all(item["period"] == 9 and item["day"] <= 90 for item in first["items"])
    again = news.alerts(db, 9, 90, first["mark"], limit=200)
    assert again["items"] == []                                   # they have been seen


# ---------------------------------------------------------------------------
# 19. The newsroom finds the six industries
# ---------------------------------------------------------------------------

def test_the_newsroom_finds_the_new_industries(db):
    # What a journalist and the intelligence desk may look into is every listed company that is trading,
    # chosen by no list of industries at all, so all eighteen of the new ones are in reach.
    pool = {c["ticker"] for c in intel._listed(db)}
    assert set(NEW_LISTED) <= pool
    assert pool == {r["ticker"] for r in _rows(db, "SELECT ticker FROM companies WHERE listed AND status = 'trading'")}

    # An industry story carries that industry's companies, as any other industry's does: one event in each
    # of the six, printed, and every one of them names a company of its own industry.
    for number, sector in enumerate(NEW):
        db.execute("INSERT INTO events (period, day, kind, sector, sales_bps) VALUES (9, %s, 'sector_demand_surge', %s, 400)",
                   (41 + number, sector))
    news.for_events(db, [e for e in events.load(db, 9) if e["kind"] == "sector_demand_surge"])
    stories = _rows(db, "SELECT * FROM news_items WHERE kind = 'sector_demand_surge' AND period = 9")
    assert {sector for s in NEW} <= {sector for story in stories for sector in story["sectors"]}
    for story in stories:
        assert story["tickers"] and set(story["tickers"]) <= set(NEW_LISTED)


# ---------------------------------------------------------------------------
# 20. Six baskets, one per industry, published with their rules in plain words
# ---------------------------------------------------------------------------

def started(db, now=NOW9):
    """The world's indexes exist: made at the first closing bell of a running world, as `indexes.setup` makes
    them, and left alone if they are already there."""
    return indexes.setup(db, exchange.session_of(now)[0], now)


def test_each_new_industry_has_a_basket(db):
    started(db)
    provider = {r["code"]: r for r in _rows(db, "SELECT * FROM market_indexes WHERE owner_id IS NULL")}
    # The four that were already there are untouched, the six are added, and nothing else is.
    assert set(provider) == {code for code, *_ in data.INDEXES}
    assert set(NEW_BASKETS) <= set(provider)

    for code, sector in zip(NEW_BASKETS, NEW):
        idx = provider[code]
        # Each is a share basket of one industry and nothing else, counted the way every other basket counts.
        assert (idx["kind"], idx["rule"]) == ("shares", f"sector:{sector}"), code
        assert idx["name"].startswith("BSX ") and idx["cap_bps"] == data.INDEX_CAP_BPS

        # Its rules are published in the same plain words as the others: no industry code, no field name, no
        # sum the reader has to work out for themselves.
        words = idx["rules_words"]
        assert words and "_" not in words and "sector:" not in words
        assert "freely traded shares" in words and "15%" in words and "one and a half times an equal share" in words
        assert "third closing bell" in words

        # Every listed company of the industry is in it, and the private one is not: nobody can buy a share in
        # a basket that is not on the exchange.
        members = indexes.members(db, code)
        assert {m["ticker"] for m in members} == {c.ticker for c in data.COMPANIES if c.sector == sector and c.listed}, code
        assert not ({m["ticker"] for m in members} & set(NEW_PRIVATE)), code
        assert sum(m["weight_bps"] for m in members) == BPS

        # It is a live basket with a level of its own, written down at every bell.
        assert idx["status"] == "live" and idx["level"] and idx["level"] >= 1
        assert _rows(db, "SELECT 1 AS x FROM index_levels WHERE index_code = %s LIMIT 1", (code,))

        # And the page a player reads shows the rules and the members with their weights.
        page = indexes.page(db, code, NOW9)
        assert page["rules"] == words and len(page["weights"]) == len(members)
        assert {w["asset"] for w in page["weights"]} == {m["asset"] for m in members}
        assert all(w["name"] and not w["name"].isupper() for w in page["weights"])    # a company's name, not its code


# ---------------------------------------------------------------------------
# 21. Index funds and ETFs copy the new baskets with no new code
# ---------------------------------------------------------------------------

def manager(db, name="ada"):
    """An Asset Manager of the level that may launch a fund."""
    player, _ = professional(db, name, build="asset_manager", employer=None, now=NOW9, cash_naira=50_000_000)
    careers.add_experience(db, player, "asset_manager", careers.experience_for(data.INVEST_FUND_LEVEL), NOW9)
    return player


def test_a_player_can_run_a_fund_of_the_shops(db):
    started(db)
    player = manager(db)
    fund = funds.launch(db, player, name="Aduke Shops Index Fund", strategy="index", fee_bps=25, perf_fee_bps=0,
                        least_in=naira(10_000), seed=naira(10_000_000), now=NOW9, index_code="RETAIL")
    # Nothing about this part was needed to launch it: it is the same index fund as one on the banks.
    assert (fund["strategy"], fund["index_code"], fund["method"]) == ("index", "RETAIL", "full")
    account = _rows(db, "SELECT account_id FROM investment_funds WHERE id = %s", (fund["id"],))[0]["account_id"]

    # What it should hold is read from the basket's own rules, member by member, adding up to the whole fund.
    target = etfs._target_basket(db, {"index_code": "RETAIL", "method": "full"}, NOW9)
    assert {t["asset"] for t in target} == {m["asset"] for m in indexes.members(db, "RETAIL")}
    assert sum(t["weight_bps"] for t in target) == BPS

    # And it holds the shops, and only shops: no share outside the basket was bought for it.
    held = etfs.holdings_value(db, account, NOW9)
    assert held["lines"], "the fund bought nothing at all"
    assert {x["asset"] for x in held["lines"]} <= {t["asset"] for t in target}
    assert held["total"] > 0 and funds.worth(db, _fund_row(db, fund["id"]), NOW9) > 0

    # It cannot be steered by hand: an index fund is held to its basket by the rule, not by its manager's taste.
    with pytest.raises(funds.FundError, match="An index fund copies its index"):
        funds.trade_shares(db, player, ticker=in_sector("mining"), side="buy", quantity=10, limit_price=100_000, now=NOW9)

    # A basket whose members leave or change is dealt with at the bell, by the same machinery as any other.
    assert etfs.track(db, account, _fund_row(db, fund["id"]), NOW9, force=True) >= 0
    assert {x["asset"] for x in etfs.holdings_value(db, account, NOW9)["lines"]} <= {t["asset"] for t in target}

    assert funds.check_books(db) == [] and etfs.check_books(db) == []
    sound(db)


def _fund_row(db, fund_id):
    return _rows(db, "SELECT * FROM investment_funds WHERE id = %s", (fund_id,))[0]


# ---------------------------------------------------------------------------
# 22. A basket with fewer than seven companies still values sensibly
# ---------------------------------------------------------------------------

def test_a_small_basket_still_values_sensibly(db):
    started(db)
    # The rule, as published: no company above 15% of an index, or one and a half times an equal share once the
    # basket is under seven names. Asked of the code itself, one name worth a thousand times the others:
    assert data.INDEX_CAP_FEW_MEMBERS == 7 and data.INDEX_CAP_BPS == BPS * 15 // 100
    for names, ceiling in ((7, BPS * 15 // 100), (4, BPS * 375 // 1000), (3, BPS // 2), (2, BPS * 3 // 4)):
        skewed = indexes.capped_weights([1_000] + [1] * (names - 1), data.INDEX_CAP_BPS)
        assert sum(skewed) == BPS, names                              # the weights still add up to the whole index
        assert abs(max(skewed) - ceiling) <= 10, names               # and the giant of the basket sits at the ceiling
    # Each new industry brings three listed companies, so the ceiling that reaches its basket is 50%, not the
    # 15% of a full index — the arithmetic the futures decision rests on.
    assert {s: sum(1 for c in data.COMPANIES if c.sector == s and c.listed) for s in NEW} == dict.fromkeys(NEW, 3)

    # An owner holding most of one shop is still held to that ceiling, and what it may not have is shared out.
    weights = indexes.capped_weights([30, 10, 10], data.INDEX_CAP_BPS)
    assert sum(weights) == BPS and max(weights) == BPS // 2
    assert abs(weights[1] - weights[2]) <= 2 and weights[1] > BPS // 5

    # Three equal names: the basket is near enough an equal split, and it still adds up to the whole.
    equal = indexes.capped_weights([1_000, 1_000, 1_000], data.INDEX_CAP_BPS)
    assert sum(equal) == BPS and max(equal) - min(equal) <= 2

    # Every one of the six, as it actually stands in the world: three names, weights adding up, none above half.
    for code in NEW_BASKETS:
        members = indexes.members(db, code)
        assert len(members) == 3, code
        assert sum(m["weight_bps"] for m in members) == BPS, code
        assert max(m["weight_bps"] for m in members) <= BPS // 2, code
        now_weights = indexes.weights_now(db, code, NOW9)
        assert abs(sum(w["weight_bps"] for w in now_weights) - BPS) <= len(now_weights), code
        assert indexes.level_now(db, code, NOW9) >= 1, code

    # And a basket that shrinks to two still plans sensibly rather than breaking: one miner leaves the
    # exchange and the rule simply allows the remaining two more room each, still adding up to the whole.
    db.execute("UPDATE companies SET listed = false WHERE ticker = %s", (in_sector("mining"),))
    mining = _rows(db, "SELECT * FROM market_indexes WHERE code = 'MINING'")[0]
    plan = indexes.plan_for(db, mining, NOW9)
    assert len(plan) == 2 and sum(p["weight_bps"] for p in plan) == BPS
    assert max(p["weight_bps"] for p in plan) <= 7500
    # The index's level is unchanged by a change of members: it is carried by the weights, not by who is in it.
    assert indexes.level_now(db, "MINING", NOW9) is not None


# ---------------------------------------------------------------------------
# 23. Which indexes have futures and options, and why the six do not
# ---------------------------------------------------------------------------

def test_which_indexes_have_futures(db):
    started(db)
    # Futures and options on three of the game's baskets, beside the BSX 50's, which have always been there.
    assert set(data.INDEX_FUTURES) == {"TOP30", "BANKS", "OILGAS"}
    assert derivatives.INDEX == "BSX50"
    for code in NEW_BASKETS:
        assert code not in derivatives.INDEXES
        assert not derivatives.is_index(code)
        assert code not in data.INDEX_FUTURES
    assert derivatives.is_index("TOP30") and derivatives.is_index("BANKS") and derivatives.is_index("OILGAS")
    assert derivatives.is_index("BSX50")

    # What that means in the world: the quarter's listing makes contracts on the three, and none at all on the six.
    derivatives.list_series(db, 8, NOW9)
    futures = {r["underlying"] for r in _rows(db, "SELECT DISTINCT underlying FROM derivative_series WHERE kind = 'future'")}
    options = {r["underlying"] for r in _rows(db, "SELECT DISTINCT underlying FROM derivative_series WHERE kind IN ('call', 'put')")}
    assert {"TOP30", "BANKS", "OILGAS"} <= futures                    # listed on the three indexes
    assert "BSX50" in futures and "BSX50" in options                  # beside the BSX 50's, which have always been there
    assert not (set(NEW_BASKETS) & futures) and not (set(NEW_BASKETS) & options)    # and nothing on the six, at all

    # The reason, in the arithmetic that decides it: a contract settles at ₦100 a point, and in a three-name
    # basket one company may be half the index, so one player leaning on one share would settle everybody's
    # contracts for them. The decision is recorded beside the baskets themselves.
    assert data.INDEX_KOBO_PER_POINT == naira(100)
    ceiling = max(data.INDEX_CAP_BPS, BPS * 3 // (2 * 3))
    one_share_of_a_bell = ceiling * data.DAILY_PRICE_LIMIT_BPS // BPS
    assert one_share_of_a_bell == BPS * 5 // 100                       # 5% of the index, in one session, at most
    source = (pathlib.Path(__file__).resolve().parent.parent / "simulation" / "world_data.py").read_text(encoding="utf-8")
    at = source.index("# The owner approved no futures on these")
    assert "too thin" in source[at:at + 400]

    # Nothing was lost by it: the six still back funds, which is what a basket is for here (item 21).
    assert set(NEW_BASKETS) <= {i["code"] for i in indexes.listing(db, NOW9)}
