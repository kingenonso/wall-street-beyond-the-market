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
from datetime import timedelta

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from simulation import careers, closingbell, corporate, derivatives, empires, etfs, events, exchange, firm, firm_dealmaking
from simulation import firm_deals, firm_owned, funds, indexes, insight, intel, ledger, marketview, objectives
from simulation import firm_practice, objectives_industries, private, quarters
from simulation import news, news_kinds
from simulation import world_data as data
from simulation.money import BPS, apply_bps, million_naira, naira
from tests.conftest import after_quarters
from tests.test_builds import pro, right_answers
from tests.test_careers import NOW9, professional, sound
from tests.test_dealmaking import cash, house, job_truth
from tests.test_deals import LATER, _one, do_checks, fairness_if_needed, open_a_sale
from tests.test_deals_more import own
from tests.test_firm import firm_of

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


def still_with_founders(db) -> list[dict]:
    """The private companies of the six that their founders still hold, so that one can be handed to an empire."""
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    return [c for c in _rows(db, "SELECT * FROM companies WHERE NOT listed AND ticker = ANY(%s) ORDER BY ticker",
                             (list(NEW_PRIVATE),))
            if ledger.balance(db, founders, c["share_asset"]) > 0]


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
    # This quarter's stories only: the world comes to the test eight quarters old, and it has printed
    # demand surges of its own in the quarters before this one.
    printed = _rows(db, "SELECT * FROM news_items WHERE kind = 'sector_demand_surge' AND period = 9")
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
        # Beside those facts the paper keeps one more thing, `wording`: which of the nine ways of saying this
        # kind of story it used, so that it does not use the same one twice running. Every kind carries it,
        # so it is set aside here rather than counted against the kind's own list.
        # This quarter's only: the world comes to the test eight quarters old, and a bumper harvest is one of
        # the kinds the quarters before this one may already have printed.
        printed = _rows(db, "SELECT * FROM news_items WHERE kind = %s AND period = 9", (kind,))
        assert len(printed) == 1, (kind, len(printed))
        assert (printed[0]["period"], printed[0]["day"]) == (9, 30 + number)
        assert set(printed[0]["facts"]) - {"wording"} <= set(news_kinds.BY_NAME[kind].fields)
        assert "{" not in printed[0]["headline"] and "{" not in printed[0]["body"]

        # Printing the same event again does not print a second story for it.
        news.for_events(db, one)
        assert len(_rows(db, "SELECT * FROM news_items WHERE kind = %s AND period = 9", (kind,))) == 1, kind

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

    # What it should hold is read from the basket's own rules, member by member, adding up to the whole fund —
    # to the whole of it or a point or two short, because each weight is floored on its own and the floors
    # cannot add back up to exactly ten thousand.
    target = etfs._target_basket(db, {"index_code": "RETAIL", "method": "full"}, NOW9)
    assert {t["asset"] for t in target} == {m["asset"] for m in indexes.members(db, "RETAIL")}
    assert BPS - len(target) <= sum(t["weight_bps"] for t in target) <= BPS

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


# ---------------------------------------------------------------------------
# 24. Every industry has work for every build
# ---------------------------------------------------------------------------

def test_every_industry_has_work_for_every_build(db):
    work = objectives_industries.INDUSTRY_WORK
    # One piece of work named for each new industry, and the six of them are the library's own list.
    assert set(work) == set(NEW)
    assert set(work.values()) == {t.code for t in objectives_industries.INDUSTRIES}
    pieces = {industry: objectives.TEMPLATES[code] for industry, code in work.items()}

    # One to each build, so no build is left out, and each opens at Level 5 — above the four modules a new
    # player starts with, and below the bands that were already there.
    assert sorted(t.build for t in pieces.values()) == sorted(careers.BUILDS)
    for piece in pieces.values():
        assert piece.level == 5 and piece.listed and piece.payer == "employer", piece.code
        assert piece.module in {m["module"] for m in objectives.modules(piece.build)}, piece.code
        # Three settings, as every piece has: alone, with the empire, and in the weekend challenge.
        assert {t.setting for t in objectives.TEMPLATES.values() if t.root == piece.code} == {"solo", "empire", "live"}, piece.code
        # And the "How to do this" card: the method the debrief will show afterwards, in words with no figure
        # in them — which is what lets it be shown before the work is done.
        card = objectives.how_to(piece)
        assert card and card == piece.submit.method_text and not any(ch.isdigit() for ch in card), piece.code

    # No exam body is named and no question paper appears, in the new work as in the old.
    words = " ".join(f"{t.module} {t.title} {t.idea}" for t in pieces.values()).upper()
    for body in ("CFA", "ACCA", "ICAN", "FRM", "CPA", "CRM", "EXAM"):
        assert body not in words, body

    # The builds that serve every company can serve the new ones too: every listed company of the six
    # industries is on the list the accountants' and the lawyers' work is drawn from, which is chosen by no
    # list of industries at all — only the banks and insurers, which already have work of their own, are left out.
    served = [c for c in objectives._filed(db, 8) if c["sector"] not in ("banking", "insurance")]
    assert set(NEW) == {c["sector"] for c in served if c["ticker"] in NEW_LISTED}
    assert not ({c["ticker"] for c in served} & set(NEW_PRIVATE))     # a private company is seen only in a data room


# ---------------------------------------------------------------------------
# 25. One new piece of work per industry, with its own test
# ---------------------------------------------------------------------------

def sits(db, build, code, name="ada"):
    """A player of that build takes the piece of work and hands in the right answers: a blank sheet fails,
    the right ones pass, and the debrief is written at all three depths. Returns the figures, the answers,
    and the verdict."""
    player, _ = pro(db, build, name, level=5, cash_naira=1_000_000)
    taken = objectives.accept(db, player, code, NOW9)
    assert taken["state"] == "active" and taken["template"] == code
    assert "figures" not in taken["terms"]                    # the figures behind the answers stay on the server
    figures = objectives.TEMPLATES[code].offer(objectives._context(db, player, NOW9))["figures"]
    with db.transaction(force_rollback=True):
        assert objectives.submit(db, player, taken["id"], {}, NOW9)["state"] == "failed"
    right = right_answers(db, taken["id"])
    done = objectives.submit(db, player, taken["id"], right, NOW9)
    assert done["state"] == "passed", (code, done["result"])
    verdict = done["result"]                     # the verdict itself is kept under "result", as every hand-in's is
    assert all(verdict["debrief"][depth] for depth in ("plain", "method", "maths")), code
    return figures, right, verdict


def test_objective_ib_mining_bond(db):
    """The Investment Banker: a miner's bond in dollars, and what a weaker naira does to it."""
    f, answers, verdict = sits(db, "investment_banker", "ib_mining_bond", "bond")
    interest_dollars = f["borrowed"] * f["coupon"] / 100
    assert abs(answers["naira_now"] - interest_dollars * f["fx"]) <= 0.011
    assert abs(answers["naira_after"] - interest_dollars * f["fx"] * (1 + f["fall"] / 100)) <= 0.011
    assert abs(answers["cover"] - f["dollars_in"] / interest_dollars) <= 0.011
    assert answers["naira_after"] > answers["naira_now"]               # the fall costs the borrower in naira
    assert "naira" in verdict["debrief"]["plain"].lower() and "currency" in verdict["debrief"]["method"].lower()

    # It is locked below its level, as every piece is.
    young, _ = pro(db, "investment_banker", "young", level=1, cash_naira=0)
    with pytest.raises(objectives.ObjectiveError, match="opens at Level 5"):
        objectives.accept(db, young, "ib_mining_bond", NOW9)


def test_objective_am_growth_rates(db):
    """The Asset Manager: a growth share when the long interest rate moves."""
    f, answers, verdict = sits(db, "asset_manager", "am_growth_rates", "growth")
    now = f["profit"] * (1 + f["growth"] / 100) / ((f["rate"] - f["growth"]) / 100)
    after = f["profit"] * (1 + f["growth"] / 100) / ((f["rate"] + f["rise"] - f["growth"]) / 100)
    assert abs(answers["value_now"] - now) <= 0.011 and abs(answers["value_after"] - after) <= 0.011
    assert abs(answers["fall"] - (1 - after / now) * 100) <= 0.011
    assert answers["value_after"] < answers["value_now"] and answers["fall"] > 0
    # The point of the piece: a growth share falls further than the rate rose by, because the gap it is valued on is small.
    assert answers["fall"] > f["rise"]
    assert "rate" in verdict["debrief"]["plain"].lower()


def test_objective_ac_retail_margin(db):
    """The Accountant: a grocer's margin, and how little its sales may fall."""
    f, answers, verdict = sits(db, "accountant", "ac_retail_margin", "grocer")
    gross = f["sales"] * f["margin"] / 100
    profit = gross * (1 - f["overhead"] / 100)
    assert abs(answers["gross"] - gross) <= 0.011 and abs(answers["profit"] - profit) <= 0.011
    # The room left is exactly what is not spent on rent, wages and vans: the costs that do not fall with sales.
    assert abs(answers["fall"] - (100 - f["overhead"])) <= 0.011
    assert 0 < answers["fall"] < 100 and answers["profit"] < answers["gross"]
    assert "margin" in verdict["debrief"]["plain"].lower()


def test_objective_jn_film_quarter(db):
    """The Journalist: a studio's quarter, and what it looks like without the hit."""
    f, answers, verdict = sits(db, "journalist", "jn_film_quarter", "film")
    sales = f["hit"] + f["other"]
    cost = sales * f["cost"] / 100
    assert abs(answers["sales"] - sales) <= 0.011 and abs(answers["profit"] - (sales - cost)) <= 0.011
    assert abs(answers["without"] - (f["other"] - cost)) <= 0.011
    # The lesson of the piece: the hit is more than the quarter's profit, so a story that leaves it out tells the
    # opposite of the truth. (The picture is sign, not the figure: the studio is reported on its slate.)
    assert answers["without"] < answers["profit"]
    assert "hit" in verdict["debrief"]["plain"].lower()
    # Entertainment is a subject for the journalist, not an employer: this is the journalist's piece, and no
    # build is given a film company to work for (decided 3 November 2026, in the checklist).
    assert objectives.TEMPLATES["jn_film_quarter"].build == "journalist"


def test_objective_rm_gas_cost(db):
    """The Risk Manager: a cost that follows the gas price."""
    f, answers, verdict = sits(db, "risk_manager", "rm_gas_cost", "gas")
    bill = f["sales"] * f["cost"] / 100 * f["gas_share"] / 100
    profit_now = f["sales"] * (1 - f["cost"] / 100)
    profit_after = f["sales"] - (f["sales"] * f["cost"] / 100 + bill * f["rise"] / 100)
    assert abs(answers["bill"] - bill) <= 0.011 and abs(answers["profit_now"] - profit_now) <= 0.011
    assert abs(answers["profit_after"] - profit_after) <= 0.011
    assert abs(answers["fall"] - (1 - profit_after / profit_now) * 100) <= 0.011
    assert answers["profit_after"] < answers["profit_now"] and answers["fall"] > 0
    # The rise is measured against profit, not sales: the same extra cost is a small share of sales and a large
    # share of the profit it is taken out of.
    against_sales = f["cost"] / 100 * f["gas_share"] / 100 * f["rise"]
    assert answers["fall"] > against_sales > 0
    assert "gas" in verdict["debrief"]["plain"].lower()


def test_objective_lw_currency_clause(db):
    """The Legal Counsel: a supply contract, and who carries the currency risk."""
    f, answers, verdict = sits(db, "lawyer", "lw_currency_clause", "clause")
    extra = f["order"] * f["fall"] / 100
    assert abs(answers["extra"] - extra) <= 0.011
    assert abs(answers["buyer_pays"] - extra * f["share"] / 100) <= 0.011
    # The clause shares the rise; what the buyer does not pay, the seller does.
    assert answers["buyer_pays"] < answers["extra"] and answers["who"] == "seller"
    assert "clause" in verdict["debrief"]["plain"].lower()


# ---------------------------------------------------------------------------
# 26. The industry insight counts the four-company industries
# ---------------------------------------------------------------------------

def test_the_industry_insight_counts_the_new_industries(db):
    sectors = {s["code"]: s for s in insight.industries(db, NOW9)}
    # Every one of the six is in the insight, with its three listed companies ranked by their share of its sales.
    assert set(NEW) <= set(sectors)
    for code in NEW:
        sector = sectors[code]
        assert len(sector["companies"]) == 3
        sold = [c["sales"] for c in sector["companies"]]
        assert sold == sorted(sold, reverse=True) and all(s > 0 for s in sold)      # ranked by what each one sold
        # The shares are floored one by one, so they add to the whole or a point or two short of it, never over.
        assert sector["sales"] > 0 and BPS - len(sector["companies"]) <= sum(c["share_bps"] for c in sector["companies"]) <= BPS
        assert [c["rank"] for c in sector["companies"]] == [1, 2, 3]

    # The rule the work is offered on: an industry is offered once it has three listed companies and sales.
    # The private fourth files nothing, so it is never counted — and the six still pass, every one of them.
    offered = {s["code"] for s in insight.industries(db, NOW9) if len(s["companies"]) >= 3 and s["sales"] > 0}
    assert set(NEW) <= offered
    assert all(sum(1 for c in data.COMPANIES if c.sector == code and not c.listed) == 1 for code in NEW)

    # And the work itself, worked on a new industry: the journalist's league table, for each of the six, marked right.
    player, _ = pro(db, "journalist", "leader", level=5, cash_naira=1_000_000)
    ctx = objectives._context(db, player, NOW9)
    piece = objectives.TEMPLATES["jr_league"]
    for code in NEW:
        objective = {"terms": {"sector": code}, "progress": {}}
        blank = piece.submit(ctx, objective, {})
        assert blank["state"] == "failed", code
        assert piece.submit(ctx, objective, blank["answers"])["state"] == "passed", code
        leader = sectors[code]["companies"][0]
        assert blank["answers"]["ticker"] == leader["ticker"] and blank["answers"]["count"] == 3


# ---------------------------------------------------------------------------
# 27. A company page names its industry
# ---------------------------------------------------------------------------

def test_a_company_page_names_its_industry(client, player, db):
    # The company page and the facts page both say what industry the company is in, in the words a
    # reader knows, and both say where it stands in it — the same place the Markets page shows.
    shown = {s["code"]: s for s in insight.industries(db, NOW9)}
    for sector in NEW:
        ticker = in_sector(sector)
        name = db.execute("SELECT name FROM sectors WHERE code = %s", (sector,)).fetchone()[0]
        assert "_" not in name and name != sector        # a name, not the code the game keys on

        page = client.get(f"/api/companies/{ticker}").json()
        facts = client.get(f"/api/market/{ticker}/facts").json()
        assert page["sector"] == facts["industry"]["sector"] == name

        # Ranked among the industry's listed companies, by the same sales figures and by the same rule:
        # the private fourth files nothing and is not counted, so the share is out of three and adds to
        # what its two rivals hold.
        place, industry = facts["industry"], shown[sector]
        mine = next(c for c in industry["companies"] if c["ticker"] == ticker)
        assert place["rank"] == mine["rank"] and place["of"] == len(industry["companies"]) == 3
        assert place["share_bps"] == mine["share_bps"] and 0 < place["share_bps"] < BPS
        assert BPS - len(industry["companies"]) <= sum(c["share_bps"] for c in industry["companies"]) <= BPS


def test_a_private_company_page_says_it_is_not_for_sale(client, player, db):
    # A private company has no page of its own — its accounts are seen only in a data room — so the page a
    # reader lands on says what it is instead, and gives no figure away: the answer is still a refusal.
    for sector in NEW:
        ticker = next(c.ticker for c in data.COMPANIES if c.sector == sector and not c.listed)
        name = db.execute("SELECT name FROM companies WHERE ticker = %s", (ticker,)).fetchone()[0]
        page = client.get(f"/api/companies/{ticker}")
        words = page.json()["detail"]
        assert page.status_code == 404                             # nothing inside it is shown, so nothing leaks
        assert name in words and "data room" in words
        assert "not for sale" in words or "for sale, but privately" in words
        assert "There is no company" not in words                  # it exists; it is shut

    # And when its owners put it up, the same page says the other thing: for sale, privately, behind the room.
    founders = ledger.account_id(db, ledger.INVESTORS_FOUNDERS)
    company = next((c for c in still_with_founders(db)
                    if not _one(db, "SELECT 1 AS n FROM sale_processes WHERE company_id = %s AND status = 'open'", (c["id"],))), None)
    assert company is not None, "no company of the six is still held by its founders, so none could be put up for sale"
    private.start_sale(db, company["id"], founders, None, ledger.balance(db, founders, company["share_asset"]), 9,
                       private._seed(db), LATER)
    words = client.get(f"/api/companies/{company['ticker']}").json()["detail"]
    assert "for sale, but privately" in words and "not for sale" not in words


# ---------------------------------------------------------------------------
# 28. The Markets page lists the six baskets
# ---------------------------------------------------------------------------

def test_the_markets_page_lists_the_six_baskets(client, player, db):
    started(db)
    listed = {i["code"]: i for i in client.get("/api/etfs").json()["indexes"]}
    # All fourteen are on the page — the eight that were already there (six baskets of shares, two of bonds)
    # and the six that are new — and nothing else.
    assert set(listed) == {code for code, *_ in data.INDEXES}
    for code in NEW_BASKETS:
        basket = listed[code]
        # Each is the provider's own share basket, published like the rest, with its level and its three companies.
        assert basket["custom"] is False and basket["owner"] == "the index provider"
        assert basket["kind"] == "shares" and basket["members"] == 3
        assert basket["name"].startswith("BSX ") and int(basket["level"]) >= 1
        assert basket["started"] is not None
        # And each one opens from the same page as the older four, with its rules and its members weighed.
        page = client.get(f"/api/indexes/{code}").json()
        assert page["code"] == code and page["name"] == basket["name"]
        assert page["rules"] and "sector:" not in page["rules"] and "_" not in page["rules"]
        assert len(page["weights"]) == 3
        assert {w["ticker"] for w in page["weights"]} == {
            c.ticker for c in data.COMPANIES if c.sector == NEW[NEW_BASKETS.index(code)] and c.listed}
        assert sum(w["weight_bps"] for w in page["weights"]) <= BPS
        assert abs(sum(w["weight_bps"] for w in page["weights"]) - BPS) <= len(page["weights"])   # each weight is floored
        # The weighting rule for three names: the largest is held at half the basket, however much is bought.
        assert max(m["weight_bps"] for m in indexes.members(db, code)) <= BPS // 2
        # The level travels as text, like every figure the exchange page sends, so it is read back as a number.
        assert page["history"] and int(page["history"][-1]["level"]) >= 1


# ---------------------------------------------------------------------------
# 29. The Economy page shows the six industries
# ---------------------------------------------------------------------------

def test_the_economy_page_shows_the_six_industries(client, player, db):
    body = client.get("/api/economy").json()
    spending = {s["sector"]: s["share_bps"] for s in body["household_spending"]}
    names = {code: db.execute("SELECT name FROM sectors WHERE code = %s", (code,)).fetchone()[0] for code in NEW}

    # Every one of the six is on the page, with a share of households' spending like any other industry's.
    assert set(names.values()) <= set(spending)
    assert all(spending[n] > 0 for n in names.values())
    # The shares are shares of one whole, and no industry is twice counted or left out.
    assert 10_000 - len(spending) <= sum(spending.values()) <= 10_000
    assert len(spending) == len(body["household_spending"])          # one line an industry, no industry twice
    shares = [s["share_bps"] for s in body["household_spending"]]
    assert shares == sorted(shares, reverse=True)

    # Each share is what that industry's own companies sold to households in the quarter, so the six are
    # on the page because they trade with households, not because the page was told to name them.
    period = body["period"]
    total = db.execute("SELECT coalesce(sum(r.sales_households), 0)::bigint FROM company_results r"
                       " WHERE r.period = %s", (period,)).fetchone()[0]
    for code, name in names.items():
        sold = db.execute("SELECT coalesce(sum(r.sales_households), 0)::bigint FROM company_results r"
                          " JOIN companies c ON c.id = r.company_id WHERE c.sector = %s AND r.period = %s",
                          (code, period)).fetchone()[0]
        assert sold > 0
        assert spending[name] == sold * 10_000 // total


# ---------------------------------------------------------------------------
# 30. Net worth counts the new shares
# ---------------------------------------------------------------------------

def test_net_worth_counts_the_new_shares(client, player, db):
    account = db.execute("SELECT id FROM ledger_accounts WHERE kind = 'player'").fetchone()[0]
    ticker = in_sector("technology")
    held = 500
    before = objectives.wealth(db, account, NOW9)
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=held,
                    asset=f"SHR-{ticker}", kind="test_shares", memo="Test: shares in a new company to hold")
    price = int(db.execute("SELECT coalesce(m.last_price, m.reference_price) FROM market_instruments m"
                           " JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s", (ticker,)).fetchone()[0])

    # What the player owns counts the shares at the market's price, and the same price in the total.
    worth = objectives.wealth(db, account, NOW9)
    line = next(line for line in worth["lines"] if line["ticker"] == ticker)
    assert line["shares"] == held and line["price"] == price and line["value"] == held * price
    assert line["sector"] == db.execute("SELECT name FROM sectors WHERE code = 'technology'").fetchone()[0]
    # The shares are the only thing that changed, and they changed the worth by exactly what they are worth:
    # nothing else it owns is counted differently for their being there.
    assert worth["shares"] - before["shares"] == held * price
    assert worth["total"] - before["total"] == held * price and worth["cash"] == before["cash"]

    # What the closing bell writes down is the same: the share is in the investments it counts.
    day = exchange.session_of(NOW9)[0]
    closingbell.snapshot_net_worth(db, day)
    cash, investments = marketview.net_worth_of_players(db)[account]
    row = db.execute("SELECT cash, investments FROM net_worth_days WHERE account_id = %s AND session_date = %s",
                     (account, day)).fetchone()
    assert investments == held * price and int(row[1]) == investments
    assert int(row[0]) == cash

    # And the player's own holdings page shows the company, its shares and what they are worth.
    mine = next(h for h in client.get("/api/market/holdings").json() if h["ticker"] == ticker)
    assert mine["shares"] == held and mine["held_for_orders"] == 0
    assert int(mine["value_kobo"]) == held * price


# ---------------------------------------------------------------------------
# 31. A company of a new industry can be taken over
# ---------------------------------------------------------------------------

def smallest_new_target(db) -> dict:
    """The new industry's listed company that costs least to buy, so that a test empire can afford all of it."""
    return _one(db, "SELECT c.*, m.reference_price FROM companies c JOIN market_instruments m ON m.company_id = c.id"
                    " WHERE c.listed AND c.sector = ANY(%s) ORDER BY m.reference_price *"
                    " (SELECT coalesce(sum(b.balance), 0) FROM ledger_balances b WHERE b.asset = c.share_asset) LIMIT 1",
                (list(NEW),))


def test_a_company_of_a_new_industry_can_be_taken_over(db):
    empire, team = firm_of(db, n_cash=200_000_000_000)
    target = smallest_new_target(db)
    assert target is not None and next(c for c in data.COMPANIES if c.ticker == target["ticker"]).sector in NEW
    issued = ledger.amount_in_existence(db, target["share_asset"])
    price = target["reference_price"] * 12 // 10
    shares = issued * 6 // 10

    # An offer is made for it as for any company: the industry it is in plays no part in whether it may be bid for.
    drafted = firm_dealmaking.draft_offer(db, team["investment_banker"], target["id"], price, shares, LATER)
    held_before = ledger.balance(db, empire["account_id"])
    firm.decide(db, team["head"], drafted["approval_id"], True, "Worth it.", LATER)
    bid = corporate.bid_for(db, target["id"])
    assert bid is not None and bid["bidder_empire_id"] == empire["id"]
    # Its cash is set aside for the shares it has offered to buy, and the books still hold while it stands.
    assert bid["reserved"] == price * shares
    assert ledger.balance(db, empire["account_id"]) == held_before - price * shares
    assert ledger.audit(db) == [] and corporate.check_books(db) == []

    # It is decided at the close. Won, the empire holds what it bought; lost, the cash comes back untouched.
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]
    closed = _one(db, "SELECT * FROM takeovers WHERE id = %s", (bid["id"],))
    assert closed["status"] in ("won", "failed") and closed["reserved"] == 0 and closed["outcome"]
    if closed["status"] == "won":
        assert closed["bought"] > 0 and closed["paid"] == closed["bought"] * closed["price"]
        assert ledger.balance(db, empire["account_id"], target["share_asset"]) == closed["bought"]
        # And it controls the company: more than half its shares, as the shareholder record shows.
        assert corporate.control(db, target["id"])["share_bps"] > 5_000
        assert corporate.control(db, target["id"])["controller"] is not None
    else:
        assert closed["bought"] == 0 and closed["paid"] == 0
    # Two quarters have closed over it, and still every naira that should exist does.
    sound(db)
    assert corporate.check_books(db) == []


def test_a_company_of_a_new_industry_is_audited_and_the_fees_taken_from_it_are_found(db):
    # The shadow side reaches a company of the six as it reaches any private company: money for "consulting
    # fees", written into the empire's books as a cost of the company, and found by an independent audit firm.
    empire, team = firm_of(db, n_cash=2_000_000_000)
    other, them = house(db, "Delta Partners")
    audit = firm_practice.found(db, them["accountant"], "audit", "Creek Audit", 0, LATER)["firm_id"]
    held = still_with_founders(db)
    assert held, "no company of the six is still held by its founders, so none could be bought and audited"
    company = own(db, empire, held[0]["ticker"])
    db.execute("UPDATE empire_seats SET signing_limit = %s WHERE player_id = %s", (million_naira(100), team["investment_banker"]))
    company_cash = cash(db, company["account_id"])
    amount = min(company_cash * firm_dealmaking.TAKE_MOST_BPS // BPS, million_naira(50))

    # Nobody outside the empire that controls it may take from it, and what is taken leaves the company's cash.
    with pytest.raises(empires.EmpireError, match="does not control"):
        firm_dealmaking.take_from_company(db, them["investment_banker"], company["id"], amount, LATER)
    taken = firm_dealmaking.take_from_company(db, team["investment_banker"], company["id"], amount, LATER)
    assert cash(db, company["account_id"]) == company_cash - amount
    book = _one(db, "SELECT * FROM empire_books WHERE id = %s", (taken["book_id"],))
    assert not book["genuine"] and book["company_id"] == company["id"]

    # An audit is commissioned on the same terms as at any other company, and it finds the fees.
    job = firm_practice.commission_audit(db, team["head"], company["id"], audit, million_naira(2), LATER)["job_id"]
    firm_practice.open_job(db, them["accountant"], job, LATER)
    right = job_truth(db, job)
    assert right["consulting"] == amount and right["opinion"] == "refused"
    firm_practice.hand_in_job(db, them["accountant"], job, right, LATER + timedelta(hours=1))
    case = _one(db, "SELECT * FROM empire_cases WHERE book_id = %s", (book["id"],))
    assert case and case["player_id"] == team["investment_banker"]
    assert ledger.audit(db) == []


def test_a_company_of_a_new_industry_is_rescued_from_failure(db):
    # A rescue runs on the same rules for the six as for every other private company: a doctor from outside
    # the owning empire, a fee of at most 5% of a quarter's sales, the head's yes, and paid only if it works.
    held = still_with_founders(db)
    assert held, "no company of the six is still held by its founders, so none could be rescued"
    trouble = next((c for c in held if firm_owned.failing(db, c["id"])), None)
    when = LATER
    if trouble is None:
        # None of the six is in trouble at this quarter, so one is put there by the game's own means: a tax
        # assessment its founders never disclosed falls due in the next quarter's accounts (the `hidden_debt`
        # secret, as `tests/test_deals_more.py` proves) — a real expense, so the books still balance, and larger
        # than its cash, so the tax office is left owed and the company is in trouble. Its results cannot be
        # rewritten (the record trigger refuses it), and a bill conjured by hand leaves the balance sheet adrift.
        trouble = held[0]
        due = apply_bps(firm_owned._quarter_sales(db, trouble["id"]), 40_000)
        db.execute("UPDATE private_profiles SET secrets = %s WHERE company_id = %s",
                   (Jsonb([{"code": "hidden_debt", "bps": 0, "amount": due, "from_period": 9, "done": False}]), trouble["id"]))
        assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
        assert firm_owned.failing(db, trouble["id"])
        when = after_quarters(9) + timedelta(hours=12)          # the ninth quarter has just begun

    empire, team = firm_of(db, n_cash=2_000_000_000)
    company = own(db, empire, trouble["ticker"])
    doctor, account = pro(db, "accountant", "new_industry_doctor")
    sales = firm_owned._quarter_sales(db, company["id"])
    with pytest.raises(empires.EmpireError, match="from outside"):
        firm_owned.propose_rescue(db, team["accountant"], company["id"], ["cut_costs"], 0, when)
    with pytest.raises(empires.EmpireError, match="5%"):
        firm_owned.propose_rescue(db, doctor, company["id"], ["cut_costs"], sales, when)
    plan = firm_owned.propose_rescue(db, doctor, company["id"], ["cut_costs"], sales * 2 // 100, when)

    # The head of the empire that owns it has to say yes, as at any other company.
    assert _one(db, "SELECT status FROM company_plans WHERE id = %s", (plan["id"],))["status"] == "proposed"
    firm_owned.answer_rescue(db, team["head"], plan["id"], True, when)
    assert _one(db, "SELECT status FROM company_plans WHERE id = %s", (plan["id"],))["status"] == "running"

    before = ledger.balance(db, account)
    for q in (10, 11, 12, 13):
        assert quarters.close_due_quarters(db, after_quarters(q)) == [q]
    row = _one(db, "SELECT * FROM company_plans WHERE id = %s", (plan["id"],))
    assert row["status"] in ("done", "failed")
    # Paid (or owed) only if it worked, and then exactly the fee, once.
    paid = ledger.balance(db, account) - before
    owed = _one(db, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS n FROM company_payables"
                    " WHERE company_id = %s AND payee_account_id = %s", (company["id"], account))["n"]
    assert (paid + owed == row["fee"]) if row["status"] == "done" else (paid == 0 and owed == 0)
    sound(db)


# ---------------------------------------------------------------------------
# 32. A private company of a new industry can be bought and listed
# ---------------------------------------------------------------------------

def listable_new_private(db) -> dict | None:
    """A private company of the six new industries that can be listed: profitable, its debts not larger than
    everything it owns, and paying its way as the exchange requires."""
    for company in data.COMPANIES:
        if company.sector not in NEW or company.listed:
            continue
        row = _one(db, "SELECT * FROM companies WHERE ticker = %s", (company.ticker,))
        last = _one(db, "SELECT total_equity, net_profit FROM company_results WHERE company_id = %s ORDER BY period DESC LIMIT 1",
                    (row["id"],))
        if row["status"] == "trading" and last and last["total_equity"] > 0 and last["net_profit"] > 0 and not firm_owned.failing(db, row["id"]):
            return row
    return None


def test_a_private_new_company_can_be_bought_and_listed(db):
    company = listable_new_private(db)
    assert company is not None, "No private company of the new industries has filed a profit, so none could be listed."

    # Buying it: through the same file, checks and bid as any private company, with the price held in escrow.
    empire, team = firm_of(db, n_cash=60_000_000_000)
    sale = open_a_sale(db, company["ticker"], mode="sealed")
    file_id = firm_deals.open_file(db, team["investment_banker"], sale["id"], LATER)["file_id"]
    firm_deals.sign_nda(db, team["lawyer"], file_id, LATER)
    do_checks(db, empire, team, file_id)
    # Above what a computer-run buyer will offer (it bids no more than the company is worth), and inside the
    # rule that no bid may be above 150% of what the company is worth or of the asking price.
    in_issue = ledger.amount_in_existence(db, company["share_asset"])
    worth = private.value_of(db, company["id"]) * sale["shares"] // max(in_issue, 1)
    price = max(worth, sale["asking"]) * 14 // 10
    fairness_if_needed(db, team, file_id, price)
    firm_deals.place_bid(db, team["head"], file_id, price, 0, LATER)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]

    owned = _one(db, "SELECT * FROM owned_companies WHERE company_id = %s", (company["id"],))
    assert owned is not None and owned["empire_id"] == empire["id"]
    assert ledger.balance(db, empire["account_id"], company["share_asset"]) == sale["shares"]
    assert firm_deals.check_books(db) == [] and ledger.audit(db) == []

    # Listing it: new shares are offered at a tenth below what the company is worth, and close at the next close.
    when = after_quarters(9) + timedelta(hours=2)
    announced = firm_owned.list_on_exchange(db, team["head"], company["id"], when)
    offer = _one(db, "SELECT * FROM share_offers WHERE company_id = %s AND status = 'open'", (company["id"],))
    assert offer["kind"] == "ipo" and offer["price"] == announced["price"] and offer["shares"] == announced["shares"]
    # A tenth below what the company is worth, for new shares of a quarter of those in issue. (The shares are
    # issued when the offer closes, so what is in issue now is still what the price is worked out over.)
    shares_in_issue = ledger.amount_in_existence(db, company["share_asset"])
    assert offer["price"] == apply_bps(private.value_of(db, company["id"]), firm_owned.LISTING_DISCOUNT_BPS) // shares_in_issue
    assert offer["shares"] == apply_bps(shares_in_issue, firm_owned.LISTING_NEW_BPS)
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]

    # It trades on the exchange from then on, in its own industry, and the empire's stake is counted out at the
    # listing price — the empire is no longer the company's owner, it is a shareholder like any other.
    assert quarters.close_due_quarters(db, after_quarters(11)) == [11]
    listed = _one(db, "SELECT * FROM companies WHERE id = %s", (company["id"],))
    assert listed["listed"], _one(db, "SELECT outcome FROM share_offers WHERE id = %s", (offer["id"],))["outcome"]
    instrument = _one(db, "SELECT * FROM market_instruments WHERE company_id = %s", (company["id"],))
    assert instrument is not None and instrument["listing_price"] > 0
    day, _ = exchange.session_of(after_quarters(11))
    assert company["ticker"] in {s["ticker"] for s in marketview._shares(db, day)}
    assert _one(db, "SELECT kind FROM deal_exits WHERE company_id = %s", (company["id"],))["kind"] == "listing"
    assert not _one(db, "SELECT 1 FROM owned_companies WHERE company_id = %s", (company["id"],))
    # Three quarters have closed over it, and still every naira that should exist does.
    sound(db)
    assert firm_deals.check_books(db) == []
