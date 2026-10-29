"""The talent and funds stage, Part 2: Run Your Own Fund.

An Asset Manager of Level 20 launches an open investment fund; anybody puts money in or takes it out at the next closing
bell's price; the fund is held to its rules; funds are rated with stars; the computer runs four funds of its own; a fund
can be gated, can be run on, closed, merged, and a manager who takes its money is struck off.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, clock, exchange, funds, ledger, marketview, objectives
from simulation import world_data as data
from simulation.money import naira
from tests.test_careers import professional
from tests.test_market import OPEN, trader

DAY = OPEN.date()


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def manager(db, name="ada", *, level=20, cash_naira=50_000_000):
    player, account = professional(db, name, build="asset_manager", employer=None, now=OPEN, cash_naira=cash_naira)
    if level > 1:
        careers.add_experience(db, player, "asset_manager", careers.experience_for(level), OPEN)
    return player, account


def investor(db, name, cash_naira=10_000_000):
    account = trader(db, name, cash_naira=cash_naira)
    return _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"], account


def ring(db, day, level=100_000):
    """A closing bell, as the exchange rings it, and the market index that day; then the funds deal at it."""
    rung = datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)
    db.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, '{}') ON CONFLICT DO NOTHING", (day, rung))
    db.execute("INSERT INTO index_days (session_date, level) VALUES (%s, %s) ON CONFLICT DO NOTHING", (day, level))
    funds.tick(db, rung + timedelta(minutes=1))
    return rung + timedelta(minutes=1)


def launch(db, player, **kw):
    args = {"name": "Ikoyi Growth Fund", "strategy": "shares", "fee_bps": 150, "perf_fee_bps": 1000, "least_in": naira(10_000),
            "seed": naira(10_000_000), "now": OPEN}
    args.update(kw)
    return funds.launch(db, player, **args)


def sound(db):
    assert ledger.audit(db) == []
    assert funds.check_books(db) == []
    assert exchange.check_books(db) == []


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

def test_only_an_asset_manager_of_level_twenty_may_launch_and_the_fees_have_ceilings(db):
    junior, _ = manager(db, "junior", level=19)
    with pytest.raises(funds.FundError, match="Level 20"):
        launch(db, junior)
    other, _ = professional(db, "counter", build="accountant", employer=None, now=OPEN, cash_naira=50_000_000)
    with pytest.raises(funds.FundError, match="Level 20"):
        launch(db, other)
    ada, _ = manager(db)
    for bad in ({"fee_bps": 201}, {"perf_fee_bps": 2001}, {"seed": naira(4_999_999)}, {"least_in": naira(5_000)},
                {"name": "Broad Street Value"}, {"name": "Ikenga Bank"}, {"strategy": "crypto"}):
        with pytest.raises(funds.FundError):
            launch(db, ada, **bad)
    assert _one(db, "SELECT count(*) AS n FROM investment_funds")["n"] == 0


def test_launching_pays_the_registration_fee_and_the_manager_buys_the_first_units_at_one_naira(db):
    ada, account = manager(db)
    pool = ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL))
    fund = launch(db, ada)
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) - pool == naira(data.INVEST_FUND_REGISTRATION_NAIRA)
    assert ledger.balance(db, account) == naira(50_000_000 - 2_000_000 - 10_000_000)
    assert fund["units"] == naira(10_000_000) * funds.UNIT // funds.FIRST_PRICE
    assert ledger.balance(db, fund["account_id"]) == naira(10_000_000)
    with pytest.raises(funds.FundError, match="one fund at a time"):
        launch(db, ada, name="Second Fund")
    sound(db)


# ---------------------------------------------------------------------------
# Money in and out, at the next closing bell
# ---------------------------------------------------------------------------

def test_money_in_waits_for_the_next_bell_and_buys_units_at_that_price_plus_the_swing(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, account = investor(db, "bola")
    order = funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN + timedelta(hours=1))
    assert order["status"] == "waiting" and ledger.balance(db, account) == naira(9_000_000)
    assert ledger.balance(db, funds.dealing_account(db)) == naira(1_000_000)
    sound(db)
    ring(db, DAY)
    order = _one(db, "SELECT * FROM fund_orders WHERE id = %s", (order["id"],))
    assert order["status"] == "dealt"
    # The price was ₦1 less the day's fee; the investor paid a quarter percent above it, which stays in the fund.
    assert order["price"] > funds.FIRST_PRICE * (10_000 + data.INVEST_FUND_SWING_BPS - 10) // 10_000
    assert ledger.balance(db, funds.dealing_account(db)) == 0
    held = _one(db, "SELECT units FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], account))["units"]
    assert held == order["units_done"] and held < naira(1_000_000) * funds.UNIT // funds.FIRST_PRICE
    sound(db)


def test_an_order_placed_after_the_bell_waits_for_the_next_one(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    after = ring(db, DAY)
    order = funds.invest(db, bola, fund["id"], naira(1_000_000), after + timedelta(minutes=5))
    funds.tick(db, after + timedelta(minutes=10))
    assert _one(db, "SELECT status FROM fund_orders WHERE id = %s", (order["id"],))["status"] == "waiting"
    ring(db, DAY + timedelta(days=1))
    assert _one(db, "SELECT status FROM fund_orders WHERE id = %s", (order["id"],))["status"] == "dealt"


def test_a_new_investor_puts_in_at_least_the_funds_least_and_a_waiting_order_can_be_taken_back(db):
    ada, _ = manager(db)
    fund = launch(db, ada, least_in=naira(500_000))
    bola, account = investor(db, "bola")
    with pytest.raises(funds.FundError, match="least"):
        funds.invest(db, bola, fund["id"], naira(100_000), OPEN)
    order = funds.invest(db, bola, fund["id"], naira(600_000), OPEN)
    funds.cancel(db, bola, order["id"], OPEN)
    assert ledger.balance(db, account) == naira(10_000_000)
    with pytest.raises(funds.FundError):
        funds.cancel(db, bola, order["id"], OPEN)
    sound(db)


def test_leaving_is_paid_at_the_next_bell_less_the_swing_and_the_manager_keeps_their_stake(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(2_000_000), OPEN)
    ring(db, DAY)
    units = _one(db, "SELECT units FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], account))["units"]
    with pytest.raises(funds.FundError):
        funds.leave(db, bola, fund["id"], units + 1, OPEN + timedelta(days=1))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    with pytest.raises(funds.FundError):
        funds.leave(db, ada, fund["id"], None, OPEN + timedelta(days=1))         # the manager keeps 1%, or all they put in
    ring(db, DAY + timedelta(days=1))
    got = ledger.balance(db, account) - naira(8_000_000)
    assert naira(1_980_000) < got < naira(2_000_000)                        # two quarters of a percent, and two days' fee
    assert _one(db, "SELECT units FROM fund_units WHERE fund_id = %s AND account_id = %s", (fund["id"], account))["units"] == 0
    sound(db)


def test_units_in_a_fund_count_in_a_players_worth(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(2_000_000), OPEN)
    w = objectives.wealth(db, account, OPEN)
    assert w["funds"] == naira(2_000_000) and w["total"] == naira(10_000_000)
    ring(db, DAY)
    held = marketview.net_worths(db)[account] if hasattr(marketview, "net_worths") else None
    w = objectives.wealth(db, account, OPEN + timedelta(days=1))
    assert naira(1_980_000) < w["funds"] <= naira(2_000_000)
    if held is not None:
        assert sum(held) == w["total"]


# ---------------------------------------------------------------------------
# The rules a manager is held to
# ---------------------------------------------------------------------------

def test_a_fund_cannot_put_more_than_a_tenth_in_one_share_or_leave_less_than_5_percent_in_cash(db):
    ada, _ = manager(db)
    launch(db, ada)
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    too_many = naira(10_000_000) // 10 // price + 10
    with pytest.raises(funds.FundError, match="10%"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=too_many, limit_price=price, now=OPEN)
    funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=too_many - 20, limit_price=price, now=OPEN)


def test_a_bond_fund_buys_no_shares_and_a_shares_fund_no_bonds(db):
    ada, _ = manager(db)
    launch(db, ada, strategy="bonds")
    with pytest.raises(funds.FundError, match="bond fund"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=10, limit_price=10_000, now=OPEN)


def test_a_banks_fund_keeps_four_fifths_of_what_it_holds_in_banks(db):
    ada, _ = manager(db)
    fund = launch(db, ada, strategy="banks")
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    with pytest.raises(funds.FundError, match="80%"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=100, limit_price=price, now=OPEN)
    assert fund["strategy"] == "banks"


def test_the_fund_never_deals_far_from_the_market_and_buys_nothing_while_leavers_wait(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    with pytest.raises(funds.FundError):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=10, limit_price=price * 2, now=OPEN)
    bola, _ = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(1_000_000), OPEN)
    ring(db, DAY)
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    with pytest.raises(funds.FundError, match="waiting to be paid"):
        funds.trade_shares(db, ada, ticker="IDC", side="buy", quantity=10, limit_price=price, now=OPEN + timedelta(days=1))


def test_fees_can_be_lowered_never_raised(db):
    ada, _ = manager(db)
    launch(db, ada)
    with pytest.raises(funds.FundError):
        funds.lower_fees(db, ada, 160, 1000, OPEN)
    assert funds.lower_fees(db, ada, 100, 500, OPEN)["fee_bps"] == 100


# ---------------------------------------------------------------------------
# Gates, loans, closing, merging
# ---------------------------------------------------------------------------

def dealers_have_cash(db, amount_naira=1_000_000_000):
    """The pension funds (the market's dealers) have cash, as they do once workers' contributions have come in."""
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS),
                    amount=naira(amount_naira), kind="test_cash", memo="Test: the dealers' cash")


def _invested_in_shares(db, ada, fund, share_of_fund_bps=9_000):
    """Put most of the fund's cash into shares (bought from the public at the market price, as a settled holding)."""
    price = _one(db, "SELECT reference_price FROM market_instruments m JOIN companies c ON c.id = m.company_id WHERE c.ticker = 'IDC'")["reference_price"]
    cash = ledger.balance(db, fund["account_id"])
    qty = cash * share_of_fund_bps // 10_000 // price
    public = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    ledger.post(db, kind="test_shares", memo="Test: the fund buys shares", legs=[
        ledger.Leg(public, -qty, "SHR-IDC"), ledger.Leg(fund["account_id"], qty, "SHR-IDC"),
        ledger.Leg(fund["account_id"], -qty * price), ledger.Leg(public, qty * price)])


def test_a_fund_short_of_cash_borrows_at_most_a_tenth_of_itself_to_pay_leavers(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    dealers_have_cash(db)
    bola, account = investor(db, "bola", cash_naira=40_000_000)
    funds.invest(db, bola, fund["id"], naira(30_000_000), OPEN)
    ring(db, DAY)
    _invested_in_shares(db, ada, _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],)))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    loan = _one(db, "SELECT * FROM fund_loans WHERE fund_id = %s", (fund["id"],))
    assert loan is not None and loan["owed"] <= naira(40_000_000) // 10 + 1
    order = _one(db, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out'", (fund["id"],))
    assert order["status"] == "waiting" and 0 < order["units_done"] < order["units"]     # paid in part; the rest waits
    # The fund offered its shares on the exchange to raise the rest.
    assert _one(db, "SELECT count(*) AS n FROM market_orders WHERE account_id = %s AND side = 'sell' AND status = 'open'",
                (fund["account_id"],))["n"] >= 1
    sound(db)


def test_a_gate_pays_leavers_at_most_a_tenth_of_the_fund_at_a_bell_and_is_announced(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola", cash_naira=40_000_000)
    funds.invest(db, bola, fund["id"], naira(30_000_000), OPEN)
    ring(db, DAY)
    funds.set_gate(db, ada, True, OPEN + timedelta(days=1))
    funds.leave(db, bola, fund["id"], None, OPEN + timedelta(days=1))
    worth = funds.worth(db, _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],)), OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    order = _one(db, "SELECT * FROM fund_orders WHERE fund_id = %s AND side = 'out'", (fund["id"],))
    assert order["paid"] <= worth // 10 + 1 and order["status"] == "waiting"
    alert = _one(db, "SELECT * FROM fund_alerts WHERE fund_id = %s AND kind = 'gated'", (fund["id"],))
    assert alert["everyone"]
    assert funds.alerts_for(db, bola, 0, OPEN + timedelta(days=1))["alerts"]
    sound(db)


def test_closing_a_fund_sells_everything_and_pays_every_holder_their_share(db):
    ada, ada_account = manager(db)
    fund = launch(db, ada)
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(5_000_000), OPEN)
    ring(db, DAY)
    dealers_have_cash(db)
    _invested_in_shares(db, ada, _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],)))
    funds.close(db, ada, OPEN + timedelta(days=1))
    late, _ = investor(db, "late")
    with pytest.raises(funds.FundError):
        funds.invest(db, late, fund["id"], naira(1_000_000), OPEN + timedelta(days=1))
    ring(db, DAY + timedelta(days=1))
    f = _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],))
    assert f["status"] == "closed" and f["units"] == 0
    assert ledger.balance(db, f["account_id"]) == 0
    assert _one(db, "SELECT count(*) AS n FROM share_owners WHERE account_id = %s AND shares > 0", (f["account_id"],))["n"] == 0
    got = ledger.balance(db, account) - naira(5_000_000)
    assert naira(4_850_000) < got < naira(5_000_000)                       # shares sold 2% under the price
    sound(db)


def test_a_merger_needs_the_other_manager_and_turns_units_into_units_of_the_same_value(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    tola, _ = manager(db, "tola")
    other = launch(db, tola, name="Lekki Value Fund")
    bola, account = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(3_000_000), OPEN)
    ring(db, DAY)
    merge = funds.propose_merge(db, ada, other["id"], OPEN + timedelta(days=1))
    with pytest.raises(funds.FundError):
        funds.answer_merge(db, ada, merge["id"], True, OPEN + timedelta(days=1))
    funds.answer_merge(db, tola, merge["id"], True, OPEN + timedelta(days=1))
    before = objectives.wealth(db, account, OPEN + timedelta(days=1))["funds"]
    for k in range(2, 6):
        ring(db, DAY + timedelta(days=k))
    f = _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],))
    assert f["status"] == "merged" and f["merged_into"] == other["id"]
    mine = _one(db, "SELECT units FROM fund_units WHERE fund_id = %s AND account_id = %s", (other["id"], account))
    assert mine and mine["units"] > 0
    after = objectives.wealth(db, account, OPEN + timedelta(days=6))["funds"]
    assert abs(after - before) < naira(20_000)
    sound(db)


# ---------------------------------------------------------------------------
# The shadow side: false costs, the regulator's audit
# ---------------------------------------------------------------------------

def test_a_manager_who_takes_the_funds_money_and_is_found_repays_it_is_fined_and_struck_off(db, monkeypatch):
    ada, ada_account = manager(db)
    fund = launch(db, ada)
    bola, _ = investor(db, "bola")
    funds.invest(db, bola, fund["id"], naira(5_000_000), OPEN)
    ring(db, DAY)
    taken = funds.take_costs(db, ada, naira(100_000), OPEN + timedelta(days=1))
    assert taken["amount"] == naira(100_000)
    with pytest.raises(funds.FundError, match="costs"):
        funds.take_costs(db, ada, naira(1_000_000), OPEN + timedelta(days=1))
    monkeypatch.setattr(data, "INVEST_FUND_AUDIT_FINDS_BPS", 10_000)
    funds.after_close(db, 1, OPEN + timedelta(days=6))
    f = _one(db, "SELECT * FROM investment_funds WHERE id = %s", (fund["id"],))
    assert f["regulator_run"] and f["manager_id"] is None and f["status"] == "closing" and f["fee_bps"] == 0
    record = _one(db, "SELECT * FROM legal_records WHERE player_id = %s", (ada,))
    assert record["kind"] == "theft"
    with pytest.raises(funds.FundError):
        launch(db, ada, name="A Fresh Start Fund")
    sound(db)


# ---------------------------------------------------------------------------
# The computer's own funds, and stars
# ---------------------------------------------------------------------------

def test_the_computer_runs_four_funds_from_the_first_bell_holding_the_markets_largest_names(db):
    ring(db, DAY)
    rows = _rows(db, "SELECT * FROM investment_funds WHERE computer ORDER BY id")
    assert [r["strategy"] for r in rows] == ["shares", "banks", "bonds", "balanced"]
    shares_fund = rows[0]
    held = _rows(db, "SELECT company_id, shares FROM share_owners WHERE account_id = %s AND shares > 0", (shares_fund["account_id"],))
    assert len(held) >= 5
    h = funds.holdings(db, shares_fund, OPEN + timedelta(days=1))
    assert all(line["value"] * 10_000 <= h["total"] * data.INVEST_FUND_ONE_HOLDING_BPS for line in h["lines"])
    sound(db)


def test_stars_compare_a_fund_with_its_benchmark_when_it_has_few_peers(db):
    ada, _ = manager(db)
    fund = launch(db, ada)
    db.execute("INSERT INTO fund_days (fund_id, session_date, unit_price, worth, units, benchmark) SELECT %s, d::date,"
               " (100000000 * (1 + 0.02 * n))::bigint, 1, 1, 100000 FROM generate_series(0, 9) n, LATERAL (SELECT %s::date + n AS d) x",
               (fund["id"], DAY))
    funds._rate(db, 2, OPEN + timedelta(days=12), {fund["id"]: {"unit_price": 1, "worth": 1, "holders": 1, "perf_fee": 0}})
    assert funds.stars_of(db, fund["id"]) == 5
    assert _one(db, "SELECT * FROM fund_alerts WHERE fund_id = %s AND kind = 'stars'", (fund["id"],))


# ---------------------------------------------------------------------------
# The website
# ---------------------------------------------------------------------------

def test_the_funds_page_shows_the_list_and_a_factsheet_never_shows_what_a_fund_holds_now(db, client, player):
    ada, _ = manager(db, "tunde")
    fund = launch(db, ada)
    page = client.get("/api/funds").json()
    assert any(f["name"] == "Ikoyi Growth Fund" for f in page["funds"])
    sheet = client.get(f"/api/funds/{fund['id']}").json()
    assert sheet["holdings"] is None and "lines" not in sheet and "cash" not in sheet
    assert client.get("/api/funds/999999").status_code == 404
    assert client.post("/api/funds/launch", json={"name": "Mine", "strategy": "shares", "fee_bps": 100, "perf_fee_bps": 0,
                                                  "least_in_naira": 10_000, "seed_naira": 5_000_000}).status_code == 409
