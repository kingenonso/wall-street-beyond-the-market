"""Stage 4, Part B: bonds and Government bills.

Every company's bond can be traded. The Government borrows with bills and bonds.
Two prices, always: a fair value worked out in the open, and the desk's prices.
Interest and repayment go to whoever holds the bond. Nothing can be made out of
nothing: every bond and every naira is in the ledger.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import bonds, clock, exchange, ledger, quarters
from simulation import world_data as data
from simulation.ledger import Leg
from simulation.money import BPS, naira
from tests.conftest import after_quarters, government_budget
from tests.test_market import sound, trader

OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")          # the second day of the first quarter
NIGHT = datetime.fromisoformat("2026-10-06T23:00:00+01:00")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def listed(db, now=OPEN) -> dict:
    return {b["code"]: b for b in bonds.listing(db, now)}


def one(db, kind: str, issuer: str = "Federal Government", now=OPEN) -> dict:
    return next(b for b in bonds.listing(db, now) if b["kind"] == kind and (b["issuer"] == issuer) == (issuer == "Federal Government"))


def corp(db, now=OPEN) -> dict:
    """A sound company's bond, with the pension funds given cash so that the desk can buy as well as sell."""
    funds = ledger.account_id(db, bonds.DEALER)
    if ledger.balance(db, funds) < naira(10_000_000_000):
        ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=funds, amount=naira(50_000_000_000),
                        kind="test_cash", memo="Test: cash for the bond desk")
    return next(b for b in bonds.listing(db, now) if b["issuer"] != "Federal Government" and b["rating"] in ("AAA", "AA", "A", "BBB"))


def state(period=0, policy=1300, left=1.0, index=BPS, companies=None) -> dict:
    return {"period": period, "policy": policy, "left": left, "index": index, "companies": companies or {}}


def bond(**changes) -> dict:
    base = {"issuer": "government", "company_id": None, "kind": "fixed", "face": bonds.FACE, "coupon_bps": 1300, "issued_period": 0,
            "maturity_period": 8, "issue_index_bps": None, "conversion_shares": None, "redeemed_period": None, "principal": None, "units": 1000}
    return {**base, **changes}


# ---------------------------------------------------------------------------
# What exists when the world begins
# ---------------------------------------------------------------------------

def test_every_companys_bond_can_be_traded_and_the_pension_funds_hold_them_all(db):
    debts = _dicts(db, "SELECT d.*, b.asset, b.kind AS bond_kind FROM company_debts d LEFT JOIN bonds b ON b.debt_id = d.id WHERE d.kind = 'bond'")
    assert debts and all(d["asset"] for d in debts)
    funds = ledger.account_id(db, bonds.DEALER)
    for debt in debts:
        units = ledger.amount_in_existence(db, debt["asset"])
        assert units == debt["principal_outstanding"] // bonds.FACE == ledger.balance(db, funds, debt["asset"])
    # Setting up again changes nothing.
    count = _dicts(db, "SELECT count(*) AS n FROM bonds")[0]["n"]
    bonds.setup(db, 0)
    assert _dicts(db, "SELECT count(*) AS n FROM bonds")[0]["n"] == count
    sound(db)


def test_the_government_has_a_bill_and_bonds_of_every_kind_and_length(db):
    government = [b for b in bonds.listing(db, OPEN) if b["issuer"] == "Federal Government"]
    assert sorted(b["kind"] for b in government) == ["bill", "fixed", "fixed", "fixed", "floating", "inflation_linked"]
    assert sorted(b["quarters_left"] for b in government if b["kind"] == "fixed") == [8, 20, 40]
    bill = one(db, "bill")
    # The Government sells its own bills and bonds itself, as many as are asked for.
    assert bill["quarters_left"] == 1 and all(b["on_offer"] is None for b in government)
    sound(db)


def test_the_full_range_is_labelled_in_plain_words(db):
    labels = {b["kind_label"] for b in bonds.listing(db, OPEN)}
    assert {"Government bill", "Fixed-rate bond", "Floating-rate bond", "Inflation-linked bond"} <= labels
    assert labels & {"Company bond", "High-yield bond", "Distressed debt"}


# ---------------------------------------------------------------------------
# Fair value: every payment still to come, counted for less the further off it is
# ---------------------------------------------------------------------------

def test_a_bond_paying_the_going_rate_is_worth_about_its_face_value():
    going = bonds.government_yield_bps(1300, 8)
    value = bonds.fair_value(bond(coupon_bps=going), state())
    assert abs(value - bonds.FACE) < bonds.FACE * 3 // 100


def test_bond_prices_fall_when_interest_rates_rise_and_long_bonds_fall_furthest():
    short, long = bond(maturity_period=8), bond(maturity_period=40)
    before = {name: bonds.fair_value(b, state(policy=1300)) for name, b in (("short", short), ("long", long))}
    after = {name: bonds.fair_value(b, state(policy=1600)) for name, b in (("short", short), ("long", long))}
    assert after["short"] < before["short"] and after["long"] < before["long"]
    assert (before["long"] - after["long"]) * before["short"] > (before["short"] - after["short"]) * before["long"]
    # ...and rise when rates fall.
    assert bonds.fair_value(long, state(policy=1000)) > before["long"]


def test_a_floating_rate_bond_hardly_moves_when_rates_change():
    floating, fixed = bond(kind="floating", coupon_bps=0, maturity_period=12), bond(maturity_period=12)
    moved = abs(bonds.fair_value(floating, state(policy=1600)) - bonds.fair_value(floating, state(policy=1300)))
    assert moved * 4 < abs(bonds.fair_value(fixed, state(policy=1600)) - bonds.fair_value(fixed, state(policy=1300)))


def test_an_inflation_linked_bond_is_worth_more_once_prices_have_risen():
    linked = bond(kind="inflation_linked", coupon_bps=700, issue_index_bps=BPS, maturity_period=20)
    assert bonds.fair_value(linked, state(index=11_000)) > bonds.fair_value(linked, state(index=BPS)) * 108 // 100


def test_a_bill_is_worth_less_than_its_face_and_grows_towards_it_as_its_date_nears():
    bill = bond(kind="bill", coupon_bps=0, maturity_period=1)
    start, middle, end = (bonds.fair_value(bill, state(left=left)) for left in (1.0, 0.5, 0.0))
    assert start < middle < end == bonds.FACE
    assert bonds.FACE * 96 // 100 < start < bonds.FACE * 98 // 100          # about 3% for a quarter at a rate near 13%


def test_a_weaker_company_must_pay_more_and_a_company_in_trouble_trades_far_below_face():
    def worth(rating, overdue=0):
        return bonds.fair_value(bond(issuer="company", company_id="c", coupon_bps=1600, maturity_period=20),
                                state(companies={"c": {"credit_rating": rating, "overdue": overdue}}))
    assert worth("AAA") > worth("BBB") > worth("B")
    assert worth("D") <= bonds.FACE * data.DISTRESSED_RECOVERY_BPS // BPS
    assert worth("BBB", overdue=1) <= bonds.FACE * data.DISTRESSED_RECOVERY_BPS // BPS
    assert [bonds.credit_spread_bps(r) for r in bonds.RATING_ORDER] == sorted(bonds.credit_spread_bps(r) for r in bonds.RATING_ORDER)


def test_the_yield_curve_slopes_upward_and_is_published(db):
    curve = bonds.curve(db)
    yields = [p["yield_bps"] for p in curve["points"]]
    assert yields == sorted(yields) and yields[0] == curve["policy_rate_bps"] - 50 and len(curve["spreads"]) == 8


# ---------------------------------------------------------------------------
# The desk: two prices, always
# ---------------------------------------------------------------------------

def test_the_desk_sells_above_fair_value_and_buys_below_it(db):
    for row in bonds.listing(db, OPEN):
        assert row["bid"] < row["fair"] <= row["ask"] or row["fair"] <= 1, row["name"]


def test_a_player_buys_a_bond_from_the_pension_funds_and_sells_it_back_at_a_loss(db):
    player = trader(db, "ngozi", cash_naira=1_000_000)
    row = corp(db)
    funds = ledger.account_id(db, bonds.DEALER)
    asset = f"BND-{row['code']}"
    funds_cash, funds_bonds = ledger.balance(db, funds), ledger.balance(db, funds, asset)

    bought = bonds.trade(db, account=player, code=row["code"], side="buy", units=100, now=OPEN)
    assert bought["price"] >= row["ask"] and ledger.balance(db, player, asset) == 100
    assert ledger.balance(db, player) == naira(1_000_000) - bought["value"]
    assert ledger.balance(db, funds) == funds_cash + bought["value"] and ledger.balance(db, funds, asset) == funds_bonds - 100

    sold = bonds.trade(db, account=player, code=row["code"], side="sell", units=100, now=OPEN)
    assert sold["price"] < bought["price"] and ledger.balance(db, player) < naira(1_000_000)
    assert ledger.balance(db, player, asset) == 0 and ledger.balance(db, funds, asset) == funds_bonds
    trades = _dicts(db, "SELECT * FROM bond_trades ORDER BY id")
    assert [(t["side"], t["units"]) for t in trades] == [("buy", 100), ("sell", 100)]
    with pytest.raises(errors.RestrictViolation):
        db.execute("DELETE FROM bond_trades")
    sound(db)


def test_buying_pushes_the_desks_prices_up_and_selling_pushes_them_down(db):
    player = trader(db, "ngozi", cash_naira=30_000_000_000)
    row = corp(db)
    before = listed(db)[row["code"]]
    bonds.trade(db, account=player, code=row["code"], side="buy", units=row["outstanding"] // 50, now=OPEN)      # 2% of the issue
    after = listed(db)[row["code"]]
    assert after["ask"] > before["ask"] and after["bid"] > before["bid"] and after["fair"] == before["fair"]
    # It fades: by the next trading day the desk asks less above fair value than it did.
    tomorrow = listed(db, OPEN + timedelta(days=1))[row["code"]]
    assert tomorrow["ask"] * after["fair"] < after["ask"] * tomorrow["fair"]
    # Never by more than the limit, however much is bought.
    bonds.trade(db, account=player, code=row["code"], side="buy", units=row["outstanding"] // 10, now=OPEN)
    assert listed(db)[row["code"]]["ask"] <= -(-before["fair"] * (BPS + 60 + data.MOST_BOND_IMPACT_BPS) // BPS)


def test_no_run_of_buying_and_selling_at_the_desk_ever_makes_money(db):
    """Question 2 (can it be done over and over for gain?): pushing the desk's prices about
    costs the one who pushes."""
    rng = random.Random(7)
    row = corp(db)
    for attempt in range(6):
        player = trader(db, f"pusher{attempt}", cash_naira=20_000_000_000)
        start = ledger.balance(db, player)
        held = 0
        for _ in range(rng.randint(2, 12)):
            if held and rng.random() < 0.5:
                units = rng.randint(1, held)
                bonds.trade(db, account=player, code=row["code"], side="sell", units=units, now=OPEN)
                held -= units
            else:
                units = rng.randint(1, row["outstanding"] // 40)
                bonds.trade(db, account=player, code=row["code"], side="buy", units=units, now=OPEN)
                held += units
        if held:
            bonds.trade(db, account=player, code=row["code"], side="sell", units=held, now=OPEN)
        assert ledger.balance(db, player) < start
    sound(db)


def test_two_accounts_working_together_cannot_milk_the_desk(db):
    pusher, seller = trader(db, "pusher", cash_naira=20_000_000_000), trader(db, "seller", cash_naira=5_000_000_000)
    row = corp(db)
    lot = row["outstanding"] // 40
    bonds.trade(db, account=seller, code=row["code"], side="buy", units=lot, now=OPEN)
    together = ledger.balance(db, pusher) + ledger.balance(db, seller)
    bonds.trade(db, account=pusher, code=row["code"], side="buy", units=row["outstanding"] // 20, now=OPEN)      # push the price up
    bonds.trade(db, account=seller, code=row["code"], side="sell", units=lot, now=OPEN)                         # sell into it
    bonds.trade(db, account=pusher, code=row["code"], side="sell", units=row["outstanding"] // 20, now=OPEN)
    bonds.trade(db, account=seller, code=row["code"], side="buy", units=lot, now=OPEN)
    assert ledger.balance(db, pusher) + ledger.balance(db, seller) < together


def test_the_desk_refuses_what_cannot_be_done(db):
    player = trader(db, "ngozi", cash_naira=100_000)
    row = corp(db)
    refuse = lambda **order: pytest.raises(bonds.BondError).__enter__() and None          # noqa: E731
    for order in ({"side": "buy", "units": 0}, {"side": "buy", "units": -5}, {"side": "buy", "units": True},
                  {"side": "buy", "units": 1.5}, {"side": "lend", "units": 1}, {"side": "sell", "units": 1},
                  {"side": "buy", "units": ledger.balance(db, ledger.account_id(db, bonds.DEALER), f"BND-{row['code']}") + 1}):
        with pytest.raises(bonds.BondError):
            bonds.trade(db, account=player, code=row["code"], now=OPEN, **order)
    with pytest.raises(bonds.BondError, match="no bond"):
        bonds.trade(db, account=player, code="ZZZ999", side="buy", units=1, now=OPEN)
    # Outside the desk's hours only a bill can be bought.
    with pytest.raises(bonds.BondError, match="12:00 to 22:00"):
        bonds.trade(db, account=player, code=row["code"], side="buy", units=1, now=NIGHT)
    # Only players trade at the desk: not a company, not the Treasury, not a computer-run investor.
    for code in ("treasury", "investors:founders", "company:IDC"):
        with pytest.raises(bonds.BondError, match="cannot trade"):
            bonds.trade(db, account=ledger.account_id(db, code), code=row["code"], side="buy", units=1, now=OPEN)
    assert ledger.balance(db, player) == naira(100_000)
    sound(db)
    _ = refuse


# ---------------------------------------------------------------------------
# Government bills: interest on idle cash
# ---------------------------------------------------------------------------

def test_a_bill_bought_today_is_repaid_in_full_when_the_quarter_closes(db):
    player = trader(db, "ngozi", cash_naira=500_000)
    treasury = ledger.account_id(db, ledger.TREASURY)
    bill = one(db, "bill", now=NIGHT)
    treasury_before = ledger.balance(db, treasury)
    bought = bonds.trade(db, account=player, code=bill["code"], side="buy", units=400, now=NIGHT)      # at night: the Treasury sells at any hour
    assert bought["price"] < bonds.FACE and ledger.balance(db, treasury) == treasury_before + bought["value"]
    assert ledger.balance(db, player) == naira(500_000) - bought["value"]

    quarters.close_due_quarters(db, after_quarters(1))
    assert ledger.balance(db, player) == naira(500_000) - bought["value"] + 400 * bonds.FACE         # repaid at ₦1,000 each
    assert ledger.balance(db, player) > naira(500_000)
    assert ledger.balance(db, player, f"BND-{bill['code']}") == 0 and ledger.amount_in_existence(db, f"BND-{bill['code']}") == 0
    # The old bill no longer trades; a new one for the next quarter is on sale.
    now = after_quarters(1)
    assert bill["code"] not in listed(db, now) and one(db, "bill", now=now)["quarters_left"] == 1
    with pytest.raises(bonds.BondError, match="repaid"):
        bonds.trade(db, account=player, code=bill["code"], side="buy", units=1, now=now)
    sound(db)


def test_a_bill_earns_only_for_the_time_it_is_held(db):
    early, late = trader(db, "early", cash_naira=1_000_000), trader(db, "late", cash_naira=1_000_000)
    bill = one(db, "bill")
    first = bonds.trade(db, account=early, code=bill["code"], side="buy", units=100, now=OPEN)
    last = bonds.trade(db, account=late, code=bill["code"], side="buy", units=100, now=after_quarters(1) - timedelta(hours=2))
    assert first["price"] < last["price"] < bonds.FACE * (BPS + 6) // BPS
    # Bought minutes before it is repaid, it costs slightly more than it repays: nothing for nothing.
    assert last["price"] >= bonds.FACE


def test_what_borrowing_costs_the_government_comes_out_of_what_it_spends(db):
    player = trader(db, "ngozi", cash_naira=100_000_000)
    bill = one(db, "bill")
    bought = bonds.trade(db, account=player, code=bill["code"], side="buy", units=40_000, now=OPEN)
    bonds.trade(db, account=player, code=one(db, "fixed")["code"], side="buy", units=20_000, now=OPEN)
    quarters.close_due_quarters(db, after_quarters(1))
    treasury = ledger.account_id(db, ledger.TREASURY)
    interest = 40_000 * bonds.FACE - bought["value"]
    spent = _dicts(db, "SELECT coalesce(-sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                       " WHERE e.account_id = %s AND e.amount < 0 AND t.period = 1 AND t.kind IN ('government_purchase', 'government_wages')",
                   (treasury,))[0]["total"]
    # (The economy upgrade: the Government's share of oil sold abroad is part of what it collects.)
    collected = ledger.received_in_period(db, treasury, 1, kinds=("company_tax", "debt_interest", "share_trade", "exchange_surplus", "oil_royalty"))
    coupons = _dicts(db, "SELECT coalesce(-sum(e.amount), 0)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                         " ON t.id = e.transaction_id WHERE e.account_id = %s AND e.amount < 0 AND t.period = 1 AND t.kind = 'bond_coupon'",
                     (treasury,))[0]["total"]
    assert coupons > 0 and interest > 0
    budget = government_budget(db, 1)
    assert budget <= collected + collected * data.GOVERNMENT_DEFICIT_BPS // BPS - coupons - interest + 100
    assert budget - 100 <= spent <= budget
    sound(db)


# ---------------------------------------------------------------------------
# Interest and repayment go to whoever holds the bond
# ---------------------------------------------------------------------------

def test_a_companys_bond_interest_is_shared_among_its_holders(db):
    player = trader(db, "ngozi", cash_naira=50_000_000)
    row = corp(db)
    bought = bonds.trade(db, account=player, code=row["code"], side="buy", units=10_000, now=OPEN)
    cash = ledger.balance(db, player)
    quarters.close_due_quarters(db, after_quarters(1))
    debt = _dicts(db, "SELECT d.* FROM company_debts d JOIN bonds b ON b.debt_id = d.id WHERE b.asset = %s", (f"BND-{row['code']}",))[0]
    due = (debt["principal_outstanding"] * debt["annual_rate_bps"] + 2 * BPS) // (4 * BPS)
    mine = due * 10_000 // row["outstanding"]
    assert abs(ledger.balance(db, player) - cash - mine) <= 1 and mine > 0
    assert bonds.income_of(db, player) == ledger.balance(db, player) - cash
    held = next(h for h in bonds.holdings_of(db, player, after_quarters(1)) if h["code"] == row["code"])
    assert held["units"] == 10_000 and held["cost"] == bought["value"]
    sound(db)


def test_a_government_bond_pays_its_holder_a_coupon_each_quarter(db):
    player = trader(db, "ngozi", cash_naira=50_000_000)
    row = next(b for b in bonds.listing(db, OPEN) if b["kind"] == "fixed" and b["issuer"] == "Federal Government" and b["quarters_left"] == 8)
    bonds.trade(db, account=player, code=row["code"], side="buy", units=1_000, now=OPEN)
    cash = ledger.balance(db, player)
    quarters.close_due_quarters(db, after_quarters(1))
    coupon = (bonds.FACE * row["coupon_bps"] + 2 * BPS) // (4 * BPS)
    assert ledger.balance(db, player) == cash + 1_000 * coupon


def test_a_bond_that_reaches_its_end_is_replaced_and_its_holders_are_paid_its_face_value(db):
    player = trader(db, "ngozi", cash_naira=500_000_000)
    row = corp(db)
    bonds.trade(db, account=player, code=row["code"], side="buy", units=5_000, now=OPEN)
    asset = f"BND-{row['code']}"
    db.execute("UPDATE company_debts d SET maturity_period = 1 FROM bonds b WHERE b.debt_id = d.id AND b.asset = %s", (asset,))
    db.execute("UPDATE bonds SET maturity_period = 1 WHERE asset = %s", (asset,))
    cash = ledger.balance(db, player)
    before = _dicts(db, "SELECT d.* FROM company_debts d JOIN bonds b ON b.debt_id = d.id WHERE b.asset = %s", (asset,))[0]

    quarters.close_due_quarters(db, after_quarters(1))
    old = _dicts(db, "SELECT b.redeemed_period, d.principal_outstanding FROM bonds b JOIN company_debts d ON d.id = b.debt_id WHERE b.asset = %s", (asset,))[0]
    new = _dicts(db, "SELECT b.*, d.principal_outstanding FROM bonds b JOIN company_debts d ON d.id = b.debt_id"
                     " WHERE b.company_id = %s AND b.issued_period = 1", (before["company_id"],))
    if old["redeemed_period"] == 1 and new:
        # Replaced: the company owes the same, on a new bond; the player was paid the face value and interest.
        assert old["principal_outstanding"] == 0 and new[0]["principal_outstanding"] == before["principal_outstanding"]
        assert ledger.balance(db, player) >= cash + 5_000 * (before["principal_outstanding"] // row["outstanding"])
        assert ledger.balance(db, player, asset) == 0 and ledger.amount_in_existence(db, asset) == 0
    else:
        # It could not be replaced (a loss-making company): it is overdue, and now distressed.
        assert listed(db, after_quarters(1))[row["code"]]["distressed"]
    sound(db)


# ---------------------------------------------------------------------------
# Convertible bonds
# ---------------------------------------------------------------------------

def _convertible(db, ticker="IDC", amount_naira=2_000_000_000, shares_each=30):
    company = _dicts(db, "SELECT c.*, s.name AS sector_name FROM companies c JOIN sectors s ON s.code = c.sector WHERE ticker = %s", (ticker,))[0]
    with db.transaction():
        made = bonds.issue_for_company(db, company, period=0, amount=naira(amount_naira), kind="convertible", rating="AA",
                                       policy_rate_bps=1300, quarters=20, conversion_shares=shares_each)
    return company, made


def test_a_convertible_bond_is_swapped_for_shares_when_the_quarter_closes(db):
    corp(db)
    company, made = _convertible(db)
    code = made["asset"][4:]
    player = trader(db, "ngozi", cash_naira=50_000_000)
    bonds.trade(db, account=player, code=code, side="buy", units=1_000, now=OPEN)
    shares_before = ledger.amount_in_existence(db, company["share_asset"])
    debt_before = _dicts(db, "SELECT principal_outstanding FROM company_debts WHERE id = %s", (made["debt_id"],))[0]["principal_outstanding"]

    asked = bonds.ask_to_convert(db, account=player, code=code, units=400, now=OPEN)
    assert asked["shares"] == 400 * 30 and ledger.balance(db, player, made["asset"]) == 600       # held from the moment of asking
    with pytest.raises(bonds.BondError):
        bonds.trade(db, account=player, code=code, side="sell", units=601, now=OPEN)             # the held ones cannot also be sold
    with pytest.raises(bonds.BondError):
        bonds.ask_to_convert(db, account=player, code=code, units=601, now=OPEN)

    quarters.close_due_quarters(db, after_quarters(1))
    assert ledger.balance(db, player, company["share_asset"]) == 12_000
    assert ledger.amount_in_existence(db, company["share_asset"]) == shares_before + 12_000
    assert ledger.amount_in_existence(db, made["asset"]) == made["units"] - 400
    now = _dicts(db, "SELECT principal_outstanding FROM company_debts WHERE id = %s", (made["debt_id"],))[0]["principal_outstanding"]
    assert debt_before - now == 400 * bonds.FACE
    # The company's accounts show it: less borrowed, more of the owners' money, and they still balance.
    result = _dicts(db, "SELECT r.*, o.share_capital AS opening_capital FROM company_results r JOIN company_results o"
                        " ON o.company_id = r.company_id AND o.period = 0 WHERE r.company_id = %s AND r.period = 1", (company["id"],))[0]
    assert result["share_capital"] == result["opening_capital"] + 400 * bonds.FACE
    assert result["shares_in_issue"] == shares_before + 12_000
    assert "swapped for new shares" in str(result["drivers"])
    # What the shares cost is on record, for the portfolio.
    from simulation import marketview
    mine = next(h for h in marketview.portfolio(db, player, after_quarters(1))["holdings"] if h["ticker"] == "IDC")
    assert mine["shares"] == 12_000 and mine["cost"] == 400 * bonds.FACE
    sound(db)


def test_a_swap_can_be_cancelled_before_the_close_and_only_by_whoever_asked(db):
    corp(db)
    _, made = _convertible(db)
    code = made["asset"][4:]
    player, other = trader(db, "ngozi", cash_naira=50_000_000), trader(db, "other", cash_naira=1_000)
    bonds.trade(db, account=player, code=code, side="buy", units=100, now=OPEN)
    asked = bonds.ask_to_convert(db, account=player, code=code, units=100, now=OPEN)
    with pytest.raises(bonds.BondError):
        bonds.cancel_conversion(db, account=other, request_id=asked["id"], now=OPEN)
    bonds.cancel_conversion(db, account=player, request_id=asked["id"], now=OPEN)
    assert ledger.balance(db, player, made["asset"]) == 100
    with pytest.raises(bonds.BondError):
        bonds.cancel_conversion(db, account=player, request_id=asked["id"], now=OPEN)          # not twice
    with pytest.raises(bonds.BondError, match="swapped for shares"):
        bonds.ask_to_convert(db, account=player, code=one(db, "fixed")["code"], units=1, now=OPEN)
    sound(db)


# ---------------------------------------------------------------------------
# Nothing out of nothing
# ---------------------------------------------------------------------------

def test_the_database_itself_refuses_bonds_or_money_made_for_the_wrong_reason(db):
    treasury, player = ledger.account_id(db, ledger.TREASURY), trader(db, "ngozi", cash_naira=1)
    asset = f"BND-{one(db, 'fixed')['code']}"
    for reason in ("share_issue", "bond_trade", "anything"):
        with pytest.raises(errors.RestrictViolation):
            ledger.post(db, kind=reason, memo="An attempt to make bonds", legs=[Leg(treasury, -10, asset), Leg(player, 10, asset)])
    central_bank = ledger.account_id(db, ledger.CENTRAL_BANK)
    with pytest.raises(errors.RestrictViolation):
        ledger.post(db, kind="bond_issue", memo="An attempt to make money", legs=[Leg(central_bank, -10), Leg(player, 10)])
    share_issuer = ledger.account_id(db, "company:IDC")
    with pytest.raises(errors.RestrictViolation):
        ledger.post(db, kind="bond_issue", memo="An attempt to make shares", legs=[Leg(share_issuer, -10, "SHR-IDC"), Leg(player, 10, "SHR-IDC")])
    with pytest.raises((errors.CheckViolation, errors.RestrictViolation, ledger.LedgerError)):
        ledger.post(db, kind="bond_trade", memo="Selling bonds one does not hold", legs=[Leg(player, -10, asset), Leg(treasury, 10, asset)])
    with pytest.raises(errors.CheckViolation):
        ledger.create_asset(db, code="BND-x", kind="bond", name="x", unit="bond", issuer_account_id=treasury)


@pytest.mark.world("eight")
def test_after_eight_quarters_the_bond_market_is_whole(db):
    assert ledger.audit(db) == [] and exchange.check_books(db) == []
    from simulation import corporate
    assert corporate.check_books(db) == []
    # Eight bills have come and gone; each was closed out.
    bills = _dicts(db, "SELECT redeemed_period, maturity_period FROM bonds WHERE kind = 'bill' ORDER BY maturity_period")
    assert [b["maturity_period"] for b in bills] == list(range(1, 10))
    assert all(b["redeemed_period"] == b["maturity_period"] for b in bills[:-1]) and bills[-1]["redeemed_period"] is None
    # Every bond in issue is held by somebody, and what the Government owes is what its bonds add up to.
    for row in _dicts(db, "SELECT b.asset FROM bonds b WHERE b.redeemed_period IS NULL"):
        held = _dicts(db, "SELECT coalesce(sum(balance), 0)::bigint AS n FROM ledger_balances WHERE asset = %s AND balance > 0", (row["asset"],))[0]["n"]
        assert held == ledger.amount_in_existence(db, row["asset"])
    # A company's bond debt is what its bonds are owed.
    for debt in _dicts(db, "SELECT d.principal_outstanding, b.asset, b.redeemed_period FROM company_debts d JOIN bonds b ON b.debt_id = d.id"):
        if debt["redeemed_period"] is not None:
            assert ledger.amount_in_existence(db, debt["asset"]) == 0


# ---------------------------------------------------------------------------
# Through the server
# ---------------------------------------------------------------------------

def test_the_bond_desk_through_the_server(db, client, player, monkeypatch):
    from server import main
    monkeypatch.setattr(main, "_exchange_time", lambda conn: OPEN)
    seen = client.get("/api/bonds").json()
    assert seen["desk_open"] is True and len(seen["curve"]) == 4 and seen["holdings"] == []
    bill = next(b for b in seen["bonds"] if b["kind"] == "bill")
    done = client.post("/api/bonds/trade", json={"code": bill["code"], "side": "buy", "units": 50})
    assert done.status_code == 201 and done.json()["units"] == 50
    after = client.get("/api/bonds").json()
    assert after["holdings"][0]["units"] == 50 and after["holdings"][0]["code"] == bill["code"]
    assert client.get("/api/market/portfolio").json()["bonds_value_kobo"] == after["holdings"][0]["value_kobo"]
    for bad in ({"code": bill["code"], "side": "buy", "units": "50"}, {"code": bill["code"], "side": "buy", "units": -1},
                {"code": bill["code"], "side": "buy", "units": 1.5}, {"code": "x", "side": "buy", "units": 1},
                {"code": bill["code"], "side": "buy", "units": 1, "price_kobo": 1}, {"code": bill["code"], "side": "steal", "units": 1}):
        assert client.post("/api/bonds/trade", json=bad).status_code == 422, bad
    assert client.post("/api/bonds/trade", json={"code": bill["code"], "side": "sell", "units": 51}).status_code == 409
    assert client.post("/api/bonds/swaps", json={"code": bill["code"], "units": 1}).status_code == 409
    assert client.delete("/api/bonds/swaps/12345").status_code == 409


def test_nobody_but_a_player_reaches_the_bond_desk(client):
    assert client.get("/api/bonds").status_code == 401
    assert client.post("/api/bonds/trade", json={"code": "T0001", "side": "buy", "units": 1}).status_code == 401
    assert client.post("/api/bonds/swaps", json={"code": "T0001", "units": 1}).status_code == 401
    assert client.delete("/api/bonds/swaps/1").status_code == 401
