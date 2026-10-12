"""The economy upgrade (owner, 12 October 2026): 1,000 consumer groups, and the rest of the world
(the oil price, the naira's exchange rate, and foreign investors).
"""

from __future__ import annotations

import time
from collections import Counter

import pytest
from psycopg.rows import dict_row

from simulation import abroad, consumers, economy, exchange, investors, ledger, news
from simulation import world_data as data
from simulation.money import BPS
from tests.conftest import ADULT, join, money_accounted_for

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _closed(db) -> int:
    return db.execute("SELECT last_closed_period FROM world_state").fetchone()[0]


# ---------------------------------------------------------------------------
# Part A: the 1,000 consumer groups
# ---------------------------------------------------------------------------

@pytest.mark.world("fresh")
def test_a_new_world_has_a_thousand_groups_shared_by_population_with_the_old_mix_of_mindsets(db):
    groups = _dicts(db, "SELECT * FROM consumer_groups")
    assert len(groups) == data.CONSUMER_GROUPS == 1000
    by_place = Counter(g["location"] for g in groups)
    assert by_place == {"Lagos": 350, "Kano": 200, "Abuja": 150, "Port Harcourt": 150, "Aba": 150}
    for place, mix in data.MINDSET_MIX.items():
        mine = [g for g in groups if g["location"] == place]
        # Each income level has the location's own mix, so the mix of what is earned (and spent) is the location's mix.
        earned = Counter()
        for g in mine:
            earned[g["mindset"]] += g["earns_bps"]
        total = sum(earned.values())
        assert all(abs(earned[m] * 100 / total - p) <= 1.5 for m, p in zip(data.MINDSETS, mix)), place
        bands = Counter(g["band"] for g in groups if g["location"] == place)
        assert bands["low"] > bands["high"] and set(bands) == set(data.INCOME_BANDS)
    # Every group has its own taste for every kind of good, and richer groups hold more savings each.
    sectors = {r["code"] for r in _dicts(db, "SELECT code FROM sectors")}
    assert all(set(g["tastes"]) == sectors for g in groups)
    low = [g["cash"] for g in groups if g["band"] == "low" and g["location"] == "Lagos"]
    high = [g["cash"] for g in groups if g["band"] == "high" and g["location"] == "Lagos"]
    assert min(high) > max(low)


def test_the_tastes_of_the_income_levels_average_out_so_the_groups_start_where_the_old_blocks_were():
    tastes = consumers._band_tastes()
    weights = [g * e for g, e in zip(data.INCOME_BAND_GROUPS_PERCENT, data.INCOME_BAND_EARNS_BPS)]
    for sector, row in tastes.items():
        assert abs(sum(t * w for t, w in zip(row, weights)) / sum(weights) - BPS) < 2, sector
    # Poorer groups lean to necessities, richer ones to travel.
    assert tastes["agriculture"][0] > tastes["agriculture"][-1] and tastes["aviation"][-1] > tastes["aviation"][0]


def test_the_groups_savings_and_debts_add_up_to_the_ledger_to_the_kobo_whenever_they_decide(db):
    world = economy.load_world(db)
    # (Money reaches households after a close too, from players' pay and empires: the groups share it when they next decide.)
    loaded = consumers.load(db)
    consumers.budgets(db, loaded, world, _closed(db) + 1, borrowed={}, debt_service={}, moods={}, seed="x" * 32,
                      base_weights={"consumer": 1})
    groups = {}
    for g in loaded:
        groups.setdefault(g["location"], {"location": g["location"], "cash": 0, "debt": 0})
        groups[g["location"]]["cash"] += g["cash"]
        groups[g["location"]]["debt"] += g["debt"]
    groups = list(groups.values())
    debts = {r["location"]: r["total"] for r in _dicts(db, "SELECT location, sum(principal)::bigint AS total FROM household_debts GROUP BY location")}
    for g in groups:
        assert g["cash"] == ledger.balance(db, world.households[g["location"]]["account_id"])
        assert g["debt"] == debts.get(g["location"], 0)
    assert ledger.audit(db) == [] and ledger.amount_in_existence(db) == money_accounted_for(db)


def test_each_quarter_the_groups_are_recorded_added_up_and_a_few_move_with_their_money_and_debts(db):
    closed = _closed(db)
    for period in range(0, closed + 1):
        rows = _dicts(db, "SELECT sum(groups)::int AS n FROM consumer_results WHERE period = %s", (period,))
        assert rows[0]["n"] == 1000
    moved = _dicts(db, "SELECT period, sum(groups)::int AS n FROM consumer_moves GROUP BY period")
    assert moved and all(0 < m["n"] <= data.GROUP_MOVES_MOST for m in moved)
    # The people go with the groups: each location's share of the population follows them.
    counts = {r["location"]: r["n"] for r in _dicts(db, "SELECT location, count(*) AS n FROM consumer_groups GROUP BY location")}
    population = {r["name"]: r["population_bps"] for r in _dicts(db, "SELECT name, population_bps FROM locations")}
    assert sum(population.values()) == BPS
    assert all(abs(population[p] - counts[p] * 10) <= 1 for p in population)
    # Moving pays the savings across: as much leaves one place as arrives in another.
    total = db.execute("SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                       " WHERE t.kind = 'household_move'").fetchone()[0]
    assert total == 0
    assert db.execute("SELECT count(*) FROM ledger_transactions WHERE kind = 'household_move'").fetchone()[0] > 0


def test_poorer_groups_spend_more_of_what_they_earn_than_richer_ones(db):
    rows = {r["band"]: r for r in _dicts(db, "SELECT band, sum(income)::bigint AS income, sum(spending)::bigint AS spending"
                                              " FROM consumer_results WHERE period = %s GROUP BY band", (_closed(db),))}
    ratio = {b: rows[b]["spending"] / rows[b]["income"] for b in data.INCOME_BANDS}
    assert ratio["low"] > ratio["middle"] > ratio["high"]


def test_each_mindset_reacts_in_its_own_way_and_the_location_is_the_sum_of_its_groups(db):
    groups = consumers.load(db)
    from simulation import mindsets
    calm = mindsets.Signals()
    fright = mindsets.Signals(severe_local_event=True, income_change_bps=-800, earlier_income_change_bps=-500, jobs_change_bps=-500)
    signals = {place: (fright if place == "Kano" else calm) for place in data.MINDSET_MIX}
    out = consumers.respond(groups, signals)
    assert out["Kano"]["spend_bps"] < out["Lagos"]["spend_bps"]
    fearful = [g for g in groups if g["location"] == "Kano" and g["mindset"] == "fearful"]
    risk_seekers = [g for g in groups if g["location"] == "Kano" and g["mindset"] == "risk_seeking"]
    assert fearful[0]["spend_bps"] < risk_seekers[0]["spend_bps"]


def test_the_groups_part_of_a_quarter_is_fast(db):
    """1,000 groups must not slow the close down: deciding and settling them takes well under two seconds."""
    world = economy.load_world(db)
    groups = consumers.load(db)
    from simulation import mindsets
    started = time.perf_counter()
    consumers.respond(groups, {place: mindsets.Signals() for place in world.households})
    weights, _ = economy.household_sector_weights(world, _closed(db) + 1, "x" * 32, _dicts(db, "SELECT * FROM economy_results ORDER BY period DESC LIMIT 1")[0])
    consumers.budgets(db, groups, world, _closed(db) + 1, borrowed={}, debt_service={}, moods={}, seed="x" * 32, base_weights=weights)
    assert time.perf_counter() - started < 2.0


def test_the_economy_page_shows_the_groups_only_added_up(db, client):
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/economy").json()
    groups = body["consumers"]
    assert sum(b["groups"] for b in groups["bands"]) == 1000
    assert {b["band"] for b in groups["bands"]} == set(data.INCOME_BANDS)
    assert sum(m["groups"] for m in groups["mindsets"]) == 1000
    assert "id" not in str(groups.keys()) and all("id" not in b for b in groups["bands"])
    # The totals by income level are the households' totals.
    spent = sum(int(b["spending"]) for b in groups["bands"])
    recorded = db.execute("SELECT sum(spending) FROM consumer_results WHERE period = %s", (body["period"],)).fetchone()[0]
    assert spent == recorded


# ---------------------------------------------------------------------------
# Part B: the rest of the world
# ---------------------------------------------------------------------------

def test_every_quarter_has_an_oil_price_and_exchange_rate_set_at_the_close_before_it(db):
    rows = _dicts(db, "SELECT * FROM abroad_results ORDER BY period")
    assert [r["period"] for r in rows] == list(range(0, _closed(db) + 1))
    assert rows[0]["oil_cents"] == data.OIL_START_CENTS and rows[0]["fx"] == data.FX_START
    low, high = data.OIL_LIMITS_CENTS
    for before, after in zip(rows, rows[1:]):
        assert low <= after["oil_cents"] <= high
        assert abs(after["fx"] - before["fx"]) * BPS // before["fx"] <= data.FX_MOST_MOVE_BPS
        assert after["reason"].startswith("The naira moved mostly on ")


def test_trade_with_the_rest_of_the_world_goes_through_the_ledger(db):
    rows = {r["period"]: r for r in _dicts(db, "SELECT * FROM abroad_results")}
    abroad_account = ledger.account_id(db, abroad.ABROAD)
    for period in range(1, _closed(db) + 1):
        paid = {r["kind"]: r["total"] for r in _dicts(db, """
            SELECT t.kind, sum(e.amount)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id
            WHERE e.account_id = %s AND t.period = %s GROUP BY t.kind""", (abroad_account, period))}
        assert paid.get("imports", 0) == rows[period]["imports"] > 0
        assert -(paid.get("exports", 0) + paid.get("oil_royalty", 0)) == rows[period]["exports"] > 0
        assert -paid.get("oil_royalty", 0) == rows[period]["oil_royalty"] > 0
        assert rows[period]["oil_royalty"] < rows[period]["oil_exports"] <= rows[period]["exports"]
    # The rest of the world's naira at the latest close.
    last = rows[_closed(db)]
    assert last["reserve"] + 0 >= 0
    # The Government's oil income is part of what it collects and spends.
    assert "oil_royalty" in economy.GOVERNMENT_INCOME


def test_oil_and_gas_companies_sell_abroad_and_say_so_in_their_filings(db):
    rows = _dicts(db, """
        SELECT c.ticker, r.drivers::text AS drivers FROM company_results r JOIN companies c ON c.id = r.company_id
        WHERE r.period = %s AND c.sector = 'oil_gas'""", (_closed(db),))
    assert rows and all("abroad" in r["drivers"] for r in rows)


def test_a_weaker_naira_makes_companies_buy_less_abroad_and_more_at_home():
    usual = data.IMPORT_SHARE_BPS["manufacturing"]
    assert abroad.import_share_bps("manufacturing", BPS) == usual
    assert abroad.import_share_bps("manufacturing", 12_000) < usual < abroad.import_share_bps("manufacturing", 8_000)
    assert abroad.import_share_bps("manufacturing", 1) <= 2 * usual
    # Energy at home is the oil price in naira.
    assert abroad.energy_index_bps(data.OIL_START_CENTS, data.FX_START) == BPS
    assert abroad.energy_index_bps(data.OIL_START_CENTS * 11 // 10, data.FX_START) == 11_000


def test_the_oil_price_comes_from_the_worlds_secret_and_jumps_with_supply_events(db):
    period = _closed(db) + 1
    seed = db.execute("SELECT fortune_seed FROM world_state").fetchone()[0]
    plain = abroad.next_oil(db, period, seed, 0)
    assert plain == abroad.next_oil(db, period, seed, 0)                 # the same world, the same answer
    assert abroad.next_oil(db, period, seed, 1000) > plain                # a supply shock makes it dearer
    assert abroad.next_oil(db, period, "y" * 32, 0) != plain or abroad.next_oil(db, period, "z" * 32, 0) != plain


def test_foreign_investors_bring_money_in_through_the_ledger_and_trade_only_on_the_exchange(db):
    foreign = ledger.account_id(db, abroad.FOREIGN)
    moved = _dicts(db, """SELECT t.kind, sum(e.amount)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t
                          ON t.id = e.transaction_id WHERE e.account_id = %s GROUP BY t.kind""", (foreign,))
    kinds = {r["kind"] for r in moved}
    assert "foreign_investment" in kinds
    # Money moves to and from them only as money sent in or taken out, or through the exchange and what owning shares brings.
    allowed = {"foreign_investment", "foreign_withdrawal", "share_trade", "order_reserve", "order_release", "dividend",
               "rights_issue", "share_offer", "offer_hold", "offer_release", "takeover_payment", "tender_hold", "tender_release"}
    assert kinds <= allowed, kinds - allowed
    # Every share they hold came from a trade on the exchange (or a split of shares bought there).
    held = _dicts(db, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0", (foreign,))
    for h in held:
        net = db.execute("SELECT coalesce(sum(CASE WHEN buyer_account_id = %s THEN quantity ELSE -quantity END), 0)"
                         " FROM market_trades WHERE company_id = %s AND (buyer_account_id = %s OR seller_account_id = %s)",
                         (foreign, h["company_id"], foreign, foreign)).fetchone()[0]
        split = db.execute("SELECT count(*) FROM share_splits WHERE company_id = %s", (h["company_id"],)).fetchone()[0]
        assert net == h["shares"] or (split and net > 0)


def test_foreign_investors_place_small_orders_both_ways_and_never_cross_their_own(db):
    from tests.test_market import OPEN
    foreign = ledger.account_id(db, abroad.FOREIGN)
    assert ledger.balance(db, foreign) > 0
    investors.act(db, OPEN, force=True)
    orders = _dicts(db, "SELECT company_id, side, limit_price, remaining, account_id FROM market_orders WHERE status = 'open'")
    mine = [o for o in orders if o["account_id"] == foreign]
    assert mine, "foreign investors keep orders on the exchange"
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    for company in {o["company_id"] for o in mine}:
        bids = [o["limit_price"] for o in mine if o["company_id"] == company and o["side"] == "buy"]
        asks = [o["limit_price"] for o in mine if o["company_id"] == company and o["side"] == "sell"]
        if bids and asks:
            assert max(bids) < min(asks)
        # Small next to the pension funds: their orders are a fraction of the size.
        theirs = sum(o["remaining"] for o in mine if o["company_id"] == company)
        big = sum(o["remaining"] for o in orders if o["company_id"] == company and o["account_id"] == funds)
        if big:
            assert theirs * 2 < big


def test_the_economy_page_shows_this_quarters_oil_price_and_rate_and_nothing_later(db, client):
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/economy").json()["abroad"]
    last = _dicts(db, "SELECT oil_cents, fx FROM abroad_results ORDER BY period DESC LIMIT 1")[0]
    assert body["oil_cents"] == last["oil_cents"] and body["fx"] == last["fx"]
    assert body["history"][-1]["period"] == _closed(db) + 1
    assert all(q["period"] <= _closed(db) for q in body["trade"])
    holders = {h["holder"] for h in client.get("/api/economy").json()["money"]}
    assert "Abroad" in holders


def test_oil_and_naira_news_is_written_from_the_record_when_they_move_enough(db):
    period = _closed(db)
    was = _dicts(db, "SELECT * FROM abroad_results WHERE period = %s", (period - 1,))[0]
    row = {**_dicts(db, "SELECT * FROM abroad_results WHERE period = %s", (period,))[0],
           "oil_cents": was["oil_cents"] * 12 // 10, "fx": was["fx"] * 105 // 100,
           "reason": "The naira moved mostly on cheaper oil."}
    before = db.execute("SELECT count(*) FROM news_items").fetchone()[0]
    news._abroad_news(db, period, row, {"next_policy_rate_bps": 1300})
    items = _dicts(db, "SELECT kind, period, day, headline, body FROM news_items ORDER BY id DESC LIMIT %s",
                   (db.execute("SELECT count(*) FROM news_items").fetchone()[0] - before,))
    kinds = {i["kind"] for i in items}
    assert {"oil_up", "naira_weaker"} <= kinds
    assert all(i["period"] == period + 1 and i["day"] >= news.DAY_ECONOMY for i in items)
    text = " ".join(i["headline"] + " " + i["body"] for i in items)
    assert f"${row['oil_cents'] / 100:,.2f}" in text or f"₦{row['fx'] / 100:,.0f}" in text


def test_keen_foreign_investors_buy_on_the_exchange_but_stay_a_small_part_of_the_days_trading(db, monkeypatch):
    """When interest rates here pay well, they price shares a little above worth and buy, until they have traded
    about 5% of what everybody else trades on a day; after that their orders only wait."""
    from datetime import timedelta
    from tests.test_market import OPEN
    monkeypatch.setattr(abroad, "tilt_now", lambda conn: data.FOREIGN_MOST_TILT_BPS)
    foreign = ledger.account_id(db, abroad.FOREIGN)
    for minutes in range(0, 120, 10):
        investors.act(db, OPEN + timedelta(minutes=minutes), force=True)
    total = db.execute("SELECT coalesce(sum(price * quantity), 0) FROM market_trades").fetchone()[0]
    theirs = db.execute("SELECT coalesce(sum(price * quantity), 0) FROM market_trades WHERE buyer_account_id = %s OR seller_account_id = %s",
                        (foreign, foreign)).fetchone()[0]
    assert theirs > 0 and db.execute("SELECT count(*) FROM share_owners WHERE account_id = %s AND shares > 0", (foreign,)).fetchone()[0] > 0
    assert theirs * BPS <= total * 600                       # at most about 5% (6% allowed for the last order of the day)
    assert ledger.audit(db) == []


def test_random_moves_do_not_shift_the_population_by_themselves():
    """With jobs growing alike everywhere, as many groups are expected to move from A to B as from B to A."""
    population = {"Lagos": 3500, "Kano": 2000, "Abuja": 1500, "Port Harcourt": 1500, "Aba": 1500}
    places, flat = list(population), {p: 0 for p in population}
    flow = {}
    for here in places:
        weights = consumers.move_weights(here, places, population, flat)
        total = sum(weights.values())
        for there in places:
            if there != here:
                flow[(here, there)] = population[here] * weights[there] / total
    for (a, b), f in flow.items():
        assert abs(f - flow[(b, a)]) < 1e-6
    # Faster job growth somewhere draws people there.
    tilted = consumers.move_weights("Kano", places, population, {**flat, "Lagos": 300})
    assert tilted["Lagos"] > consumers.move_weights("Kano", places, population, flat)["Lagos"]


def test_the_naira_reason_always_names_a_cause_that_pushed_the_way_it_moved(db):
    rows = _dicts(db, "SELECT period, fx, reason FROM abroad_results ORDER BY period")
    weakening = {w for w, _ in abroad._FX_WORDS.values()}
    strengthening = {s for _, s in abroad._FX_WORDS.values()}
    for before, after in zip(rows, rows[1:]):
        cause = after["reason"].removeprefix("The naira moved mostly on ").rstrip(".")
        if after["fx"] > before["fx"]:
            assert cause in weakening, (after["period"], cause)
        elif after["fx"] < before["fx"]:
            assert cause in strengthening, (after["period"], cause)
    assert abroad.fx_reason(120, {"prices": 150, "oil": -60, "swing": 30}) == "prices at home rising faster than abroad"
    assert abroad.fx_reason(-50, {"prices": 150, "oil": -160, "swing": -40}) == "dearer oil"


def test_energy_at_home_is_the_oil_price_set_for_next_quarter_in_naira(db):
    rows = {r["period"]: r for r in _dicts(db, "SELECT period, oil_cents, fx FROM abroad_results")}
    for r in _dicts(db, "SELECT period, energy_bps FROM economy_results WHERE period >= 1"):
        assert r["energy_bps"] == abroad.energy_index_bps(rows[r["period"]]["oil_cents"], rows[r["period"] - 1]["fx"])


def test_foreign_investors_day_budget_follows_what_everybody_else_traded(db):
    from datetime import timedelta
    from tests.test_market import OPEN, place, reference, trader
    from simulation import exchange as ex
    foreign = ledger.account_id(db, abroad.FOREIGN)
    seller = trader(db, "bigseller", shares=2_000_000, ticker="IKB")
    buyer = trader(db, "bigbuyer", cash_naira=1_000_000_000, ticker="IKB")
    price = reference(db, "IKB")
    place(db, seller, "sell", 1_000_000, price, now=OPEN, ticker="IKB")
    place(db, buyer, "buy", 1_000_000, price, now=OPEN, ticker="IKB")
    day, _ = ex.session_of(OPEN)
    traded = db.execute("SELECT sum(price * quantity) FROM market_trades WHERE session_date = %s AND NOT same_owner", (day,)).fetchone()[0]
    nxt, _ = ex.session_of(OPEN + timedelta(days=1))
    assert abroad.day_budget_left(db, foreign, nxt) == max(traded * data.FOREIGN_DAY_SHARE_BPS // BPS, data.FOREIGN_DAY_LEAST_NAIRA * 100)
    # A player trading with themselves does not raise it.
    place(db, buyer, "sell", 1_000, price, now=OPEN, ticker="IKB")
    place(db, buyer, "buy", 1_000, price, now=OPEN, ticker="IKB")
    assert abroad.day_budget_left(db, foreign, nxt) == max(traded * data.FOREIGN_DAY_SHARE_BPS // BPS, data.FOREIGN_DAY_LEAST_NAIRA * 100)
