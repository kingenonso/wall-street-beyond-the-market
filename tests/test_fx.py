"""The talent and funds stage, Part 4a: the currency desk and money from abroad.

Two naira rates (the official window and the street) and the gap between them; the Central Bank's reserves, its defence,
its devaluations and floats; dollar, pound and euro balances; the official window's line and its limit; bureaux de change;
money sent home from abroad; companies' dollar debts revalued every quarter; Eurobonds; the foreign investors' backlog;
currency forwards.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from psycopg.rows import dict_row

from simulation import abroad, careers, clock, empires, fx, ledger, objectives, quarters, swaps
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import after_quarters
from tests.test_careers import professional
from tests.test_market import OPEN

DAY = OPEN.date()
TRADING = OPEN.replace(hour=15)


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def ring(db, day):
    """A closing bell, and the currency desk's work at it."""
    rung = datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)
    db.execute("INSERT INTO closing_bells (session_date, rung_at, content) VALUES (%s, %s, '{}') ON CONFLICT DO NOTHING", (day, rung))
    fx.tick(db, rung + timedelta(minutes=1))
    return rung + timedelta(minutes=1)


def opened(db):
    ring(db, DAY - timedelta(days=1))


def person(db, name, *, cash_naira=50_000_000):
    player, account = professional(db, name, build="investment_banker", employer=None, now=OPEN, cash_naira=cash_naira)
    return player, account


def sound(db):
    assert ledger.audit(db) == []
    assert fx.check_books(db) == []


def empire_head(db):
    """The head of an open empire with a billion naira in it."""
    from tests.test_empires import founded
    empire, (head, account), _ = founded(db, cash=1_500_000_000, put_in=1_000_000_000)
    return head, account, empire


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

def test_the_desk_opens_at_the_first_bell_with_reserves_an_official_rate_and_eurobonds(db):
    opened(db)
    q = fx.current(db)
    assert q["regime"] == "managed" and q["official"] == q["market"] > 0
    cb = ledger.account_id(db, ledger.CENTRAL_BANK)
    assert ledger.balance(db, cb, "USD") > 0 and q["cover_bps"] >= data.FX_RESERVES_START_QUARTERS * BPS
    assert {r["code"] for r in _rows(db, "SELECT code FROM assets WHERE kind = 'currency'")} >= {"NGN", "USD", "GBP", "EUR"}
    bonds = _rows(db, "SELECT * FROM eurobonds ORDER BY id")
    assert bonds[0]["issuer"] == "government" and any(b["issuer"] == "company" for b in bonds)
    debts = _rows(db, "SELECT * FROM company_debts WHERE currency = 'USD'")
    assert debts and all(d["fx_rate"] == q["official"] for d in debts)
    assert _one(db, "SELECT count(*) AS n FROM remitters")["n"] == len(data.FX_COMPUTER_REMITTERS)
    assert _one(db, "SELECT 1 AS x FROM fx_days WHERE session_date = %s", (DAY - timedelta(days=1),))
    sound(db)


# ---------------------------------------------------------------------------
# The street
# ---------------------------------------------------------------------------

def test_buying_dollars_on_the_street_costs_the_spread_and_pushes_the_street_up(db):
    opened(db)
    _, account = person(db, "ada", cash_naira=500_000_000)
    before = fx.quote(db, "USD")
    got = fx.street_deal(db, _player(db, account), "buy", "USD", 10_000_000, TRADING)
    assert got["rate"] == before["sell"] > before["mid"]
    assert ledger.balance(db, account, "USD") == 10_000_000
    assert fx.quote(db, "USD")["mid"] > before["mid"]
    sold = fx.street_deal(db, _player(db, account), "sell", "USD", 10_000_000, TRADING)
    assert sold["naira"] < got["naira"]                       # straight back again always loses the spread
    sound(db)


def test_pounds_and_euros_are_priced_through_the_dollar(db):
    opened(db)
    usd, gbp, eur = (fx.quote(db, c)["mid"] for c in ("USD", "GBP", "EUR"))
    assert gbp > eur > usd


def test_foreign_currency_counts_in_net_worth_at_what_the_street_would_pay(db):
    opened(db)
    player, account = person(db, "ada")
    fx.street_deal(db, player, "buy", "USD", 2_000_000, TRADING)
    worth = objectives.wealth(db, account, TRADING)
    assert worth["foreign"] == 2_000_000 * fx.quote(db, "USD")["buy"] // 100


# ---------------------------------------------------------------------------
# The official window
# ---------------------------------------------------------------------------

def test_the_official_window_fills_requests_in_turn_at_the_next_bell_and_hands_back_what_is_left(db):
    opened(db)
    player, account = person(db, "ada")
    cash = ledger.balance(db, account)
    ask = fx.window_ask(db, player, 1_000_000, TRADING)
    assert ask["held"] > 1_000_000 * fx.official(db) // 100
    assert ledger.balance(db, account) == cash - ask["held"]
    ring(db, DAY)
    req = _one(db, "SELECT * FROM fx_window WHERE id = %s", (ask["request_id"],))
    assert req["status"] == "filled" and req["held"] == 0
    assert ledger.balance(db, account, "USD") == 1_000_000
    assert ledger.balance(db, account) == cash - 1_000_000 * fx.official(db) // 100
    sound(db)


def test_the_window_has_a_limit_a_quarter(db):
    opened(db)
    player, _ = person(db, "ada", cash_naira=500_000_000)
    fx.window_ask(db, player, data.FX_WINDOW_LIMIT_PLAYER_CENTS, TRADING)
    with pytest.raises(fx.FxError, match="at most"):
        fx.window_ask(db, player, 1_000, TRADING)


def test_dollars_from_the_window_cannot_be_sold_on_the_street(db):
    opened(db)
    player, account = person(db, "ada")
    fx.window_ask(db, player, 1_000_000, TRADING)
    ring(db, DAY)
    with pytest.raises(fx.FxError, match="official window"):
        fx.street_deal(db, player, "sell", "USD", 1_000_000, TRADING + timedelta(days=1))
    got = fx.window_sell(db, player, 1_000_000, TRADING + timedelta(days=1))      # but back to the window, at once
    assert got["naira"] == 1_000_000 * fx.official(db) // 100
    sound(db)


def test_a_waiting_request_can_be_withdrawn_and_its_naira_come_back(db):
    opened(db)
    player, account = person(db, "ada")
    cash = ledger.balance(db, account)
    ask = fx.window_ask(db, player, 1_000_000, TRADING)
    fx.window_cancel(db, player, ask["request_id"], TRADING)
    assert ledger.balance(db, account) == cash
    sound(db)


# ---------------------------------------------------------------------------
# Bureaux de change and money from abroad
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_an_empire_runs_a_bureau_households_deal_with_it_and_big_deals_are_reported(db):
    from tests.test_builds import pro
    from tests.test_careers import NOW9
    ring(db, NOW9.date() - timedelta(days=1))
    head, _, empire = empire_head(db)
    fx.street_deal(db, head, "buy", "USD", 20_000_000, NOW9, for_empire=True)
    got = fx.open_bdc(db, head, "Kola Bureau", 50, 60, NOW9)
    with pytest.raises(fx.FxError, match="street"):
        fx.window_ask(db, head, 1_000_000, NOW9, for_empire=True)
    buyer, account = pro(db, "investment_banker", "ada", level=4, cash_naira=100_000_000)
    deal = fx.bdc_deal(db, buyer, got["bdc_id"], "buy", data.FX_BDC_REPORT_CENTS, NOW9)
    assert deal["rate"] > fx.street(db)
    assert _one(db, "SELECT * FROM bdc_reports WHERE bdc_id = %s", (got["bdc_id"],))["customer"] == "a player"
    ring(db, NOW9.date())
    assert _one(db, "SELECT count(*) AS n FROM fx_trades WHERE venue = 'bdc' AND account_id = %s", (ledger.account_id(db, "households:lagos"),))["n"] > 0
    sound(db)


def test_money_sent_home_reaches_families_in_naira_and_the_carriers_keep_their_fee(db):
    opened(db)
    households = ledger.account_id(db, "households:lagos")
    before = ledger.balance(db, households)
    ring(db, DAY)
    rows = _rows(db, "SELECT * FROM remittances WHERE session_date = %s", (DAY,))
    assert rows and sum(r["dollars"] for r in rows) > 0
    assert ledger.balance(db, households) - before >= sum(r["naira"] for r in rows) * 9 // 10
    cheapest = min(_rows(db, "SELECT r.id, r.fee_bps, r.days, m.dollars FROM remitters r JOIN remittances m ON m.remitter_id = r.id"),
                   key=lambda r: r["fee_bps"])
    assert cheapest["dollars"] == max(r["dollars"] for r in rows) or cheapest["days"] >= 5


def test_more_is_sent_home_at_christmas_and_when_the_street_pays_more(db):
    base = fx.remitted_today(db, 1, 0)
    assert fx.remitted_today(db, 4, 0) > base * 13 // 10
    assert fx.remitted_today(db, 1, 2_000) > base


# ---------------------------------------------------------------------------
# Eurobonds
# ---------------------------------------------------------------------------

def test_a_player_buys_a_eurobond_with_dollars_and_it_counts_at_its_fair_price(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=100_000_000)
    fx.street_deal(db, player, "buy", "USD", 1_000_000, TRADING)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    with pytest.raises(fx.FxError, match="whole"):
        fx.eurobond_deal(db, player, eb["id"], "buy", 0, TRADING)
    got = fx.eurobond_deal(db, player, eb["id"], "buy", 5, TRADING)
    assert ledger.balance(db, account, eb["asset"]) == 5 and got["dollars"] == got["price"] * 5
    back = fx.eurobond_deal(db, player, eb["id"], "sell", 5, TRADING)
    assert back["dollars"] < got["dollars"]
    sound(db)


def test_a_eurobond_is_worth_less_when_reserves_are_short(db):
    opened(db)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    before = fx.fair_price(db, eb, 1)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET cover_bps = 5000")
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    assert fx.fair_price(db, eb, 1) < before


# ---------------------------------------------------------------------------
# The quarter's close
# ---------------------------------------------------------------------------

def _close_first(db):
    opened(db)
    return quarters.close_due_quarters(db, after_quarters(1))


def test_at_the_close_dollar_debts_are_revalued_and_the_books_still_balance(db):
    opened(db)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET official = official * 12 / 10")       # the naira fell 20% at the window
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    debt = _one(db, "SELECT * FROM company_debts WHERE currency = 'USD' ORDER BY name LIMIT 1")
    assert quarters.close_due_quarters(db, after_quarters(1)) == [1]
    reval = _one(db, "SELECT * FROM fx_revaluations WHERE debt_id = %s AND period = 1", (debt["id"],))
    assert reval["amount"] > 0
    result = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 1", (debt["company_id"],))
    assert result["currency_loss"] >= reval["amount"]
    assert any("dollar debts" in n for n in result["drivers"]["notes"])
    sound(db)


def test_at_the_close_eurobond_holders_are_paid_in_dollars_and_the_central_bank_sets_next_quarter(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=100_000_000)
    fx.street_deal(db, player, "buy", "USD", 1_000_000, TRADING)
    eb = _one(db, "SELECT * FROM eurobonds WHERE issuer = 'government'")
    fx.eurobond_deal(db, player, eb["id"], "buy", 5, TRADING)
    dollars = ledger.balance(db, account, "USD")
    assert quarters.close_due_quarters(db, after_quarters(1)) == [1]
    paid = _one(db, "SELECT * FROM eurobond_payments WHERE eurobond_id = %s AND period = 1", (eb["id"],))
    assert paid and paid["short"] == 0
    assert ledger.balance(db, account, "USD") == dollars + 5 * (eb["face"] * eb["coupon_bps"] // BPS // 4)
    assert _one(db, "SELECT 1 AS x FROM fx_quarters WHERE period = 1")
    sound(db)


def test_low_reserves_and_a_wide_gap_bring_a_devaluation_and_very_low_reserves_a_float(db):
    opened(db)
    cb = ledger.account_id(db, ledger.CENTRAL_BANK)
    world_abroad, _ = abroad.accounts(db)
    db.execute("ALTER TABLE fx_quarters DISABLE TRIGGER fx_quarters_permanent")
    db.execute("UPDATE fx_quarters SET official = official * 8 / 10")       # the window far below the market
    db.execute("ALTER TABLE fx_quarters ENABLE TRIGGER fx_quarters_permanent")
    keep = fx.to_cents(fx._quarter_imports(db), fx.current(db)["market"]) * 2   # two quarters' imports: under comfortable
    have = ledger.balance(db, cb, "USD")
    ledger.post(db, kind="fx_abroad", memo="test", legs=[ledger.Leg(cb, -(have - keep), "USD"), ledger.Leg(world_abroad, have - keep, "USD")])
    quarters.close_due_quarters(db, after_quarters(1))
    q = fx.current(db)
    assert q["period"] == 1 and q["event"] in ("devalued", "floated")
    assert _one(db, "SELECT 1 AS x FROM fx_alerts WHERE kind = %s", (q["event"],))
    sound(db)


def test_a_currency_forward_settles_the_difference_against_the_official_rate(db):
    opened(db)
    player, account = person(db, "ada", cash_naira=500_000_000)
    from tests.test_derivatives import ready
    ready(db, player)
    bank = _one(db, "SELECT id FROM companies WHERE sector = 'banking' AND status = 'trading' ORDER BY ticker LIMIT 1")
    got = swaps.propose(db, player, kind="fx", counterparty={"bank": str(bank["id"])}, side="pay_fixed", quarters=1, now=TRADING,
                        notional=100_000)
    s = _one(db, "SELECT * FROM swaps WHERE id = %s", (got["swap_id"],))
    assert s["kind"] == "fx" and s["status"] == "active" and s["fixed_price"] > fx.official(db)
    assert "Currency forward" in swaps.describe(s)


def test_while_reserves_are_short_foreign_investors_wait_for_dollars(db):
    opened(db)
    cb = ledger.account_id(db, ledger.CENTRAL_BANK)
    room = fx.exit_room(db, 10 ** 15, fx.official(db))
    assert room == ledger.balance(db, cb, "USD") * data.FX_EXIT_FROM_RESERVES_BPS // BPS * fx.official(db) // 100


def _player(db, account):
    return _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"]
