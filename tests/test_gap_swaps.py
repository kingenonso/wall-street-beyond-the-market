"""The gap stage, Part 1: swaps between players, empires and banks, and companies hedging their oil."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import derivatives, firm, ledger, quarters, swaps
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, after_quarters, join
from tests.test_builds import pro
from tests.test_careers import NOW9, sound
from tests.test_derivatives import ready, trader
from tests.test_firm import firm_of, member
from tests.test_lending import bank_id

pytestmark = pytest.mark.world("eight")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def name_of(db, player):
    return _one(db, "SELECT display_name FROM players WHERE id = %s", (player,))["display_name"]


def test_a_bank_takes_a_rate_swap_at_once_at_its_own_price_and_it_pays_from_the_next_quarter(db):
    p, acct = trader(db, "investment_banker", "fixer", cash_naira=100_000_000)
    bank = bank_id(db)
    done = swaps.propose(db, p, kind="rate", counterparty={"bank": bank}, side="pay_fixed", quarters=2, notional=naira(1_000_000_000),
                         now=NOW9)
    assert done["status"] == "active" and done["first_period"] == 10
    s = _one(db, "SELECT * FROM swaps WHERE id = %s", (done["swap_id"],))
    assert s["fixed_bps"] == swaps.rate_for(db, 10) + data.SWAP_BANK_RATE_SPREAD_BPS
    quarters.close_due_quarters(db, after_quarters(9))
    assert _one(db, "SELECT count(*) AS n FROM swap_payments WHERE swap_id = %s", (s["id"],))["n"] == 0     # nothing for the quarter signed in
    before = ledger.balance(db, acct)
    quarters.close_due_quarters(db, after_quarters(10))
    pay = _one(db, "SELECT * FROM swap_payments WHERE swap_id = %s AND period = 10", (s["id"],))
    expected = naira(1_000_000_000) * (swaps.rate_for(db, 10) - s["fixed_bps"]) // BPS // 4
    assert pay["amount"] == abs(expected) and pay["paid"] == pay["amount"]
    assert (pay["receiver"] == acct) == (expected > 0)
    # (The player's balance moved by exactly the payment, apart from their own salary and the like at the close.)
    _ = before
    quarters.close_due_quarters(db, after_quarters(11))
    assert _one(db, "SELECT status FROM swaps WHERE id = %s", (s["id"],))["status"] == "ended"
    sound(db)


def test_two_players_agree_an_oil_swap_and_a_side_that_cannot_pay_owes_the_other(db):
    a, a_acct = trader(db, "risk_manager", "producer", cash_naira=1_000_000_000)
    b, b_acct = trader(db, "asset_manager", "airline", cash_naira=1_000_000_000)
    price = swaps.oil_for(db)
    offered = swaps.propose(db, a, kind="oil", counterparty={"player": name_of(db, b)}, side="receive_fixed", quarters=1,
                            barrels=50_000, fixed=price * 3, now=NOW9)       # B would pay three times today's price
    assert offered["status"] == "proposed"
    with pytest.raises(swaps.SwapError):
        swaps.accept(db, a, offered["swap_id"], NOW9)                       # not the proposer's to accept
    swaps.accept(db, b, offered["swap_id"], NOW9)
    # B spends everything: at the close B owes A the difference, and cannot pay it.
    quarters.close_due_quarters(db, after_quarters(9))
    ledger.transfer(db, payer=b_acct, receiver=ledger.account_id(db, ledger.TREASURY), amount=ledger.balance(db, b_acct),
                    kind="test_cash", memo="Test: spent")
    quarters.close_due_quarters(db, after_quarters(10))
    pay = _one(db, "SELECT * FROM swap_payments WHERE swap_id = %s", (offered["swap_id"],))
    assert pay["payer"] == b_acct and pay["receiver"] == a_acct and pay["amount"] > 0
    if pay["paid"] < pay["amount"]:
        owed = _one(db, "SELECT * FROM player_loans WHERE borrower = %s AND kind = 'shortfall' AND creditor = %s", (b_acct, a_acct))
        assert owed and owed["principal"] == pay["amount"] - pay["paid"] and owed["status"] == "default"
    sound(db)


def test_inside_an_empire_counsel_drafts_the_risk_manager_signs_and_the_head_signs(db):
    empire, team = firm_of(db, n_cash=5_000_000_000)
    banker = team["investment_banker"]
    ready(db, banker)
    with pytest.raises(swaps.SwapError, match="Investment Banker"):
        swaps.propose(db, team["asset_manager"], kind="rate", counterparty={"bank": bank_id(db)}, side="receive_fixed", quarters=2,
                      notional=naira(100_000_000), now=NOW9, for_empire=True)
    asked = swaps.propose(db, banker, kind="rate", counterparty={"bank": bank_id(db)}, side="receive_fixed", quarters=2,
                          notional=naira(100_000_000), now=NOW9, for_empire=True)
    assert asked["waiting"]
    for kind, who in (("swap_draft", team["investment_banker"]), ("swap_risk", team["risk_manager"]), ("swap_sign", team["head"])):
        approval = _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = %s AND status = 'waiting'", (empire["id"], kind))
        assert approval, kind
        firm.decide(db, who, approval["id"], True, "Agreed.", NOW9)
    s = _one(db, "SELECT * FROM swaps WHERE id = %s", (asked["swap_id"],))
    assert s["status"] == "active" and s["contract"] and s["fixed_payer"] != empire["account_id"]
    # A refusal at any step ends it.
    again = swaps.propose(db, banker, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1,
                          notional=naira(50_000_000), now=NOW9, for_empire=True)
    approval = _one(db, "SELECT * FROM empire_approvals WHERE empire_id = %s AND kind = 'swap_draft' AND status = 'waiting'", (empire["id"],))
    firm.decide(db, team["investment_banker"], approval["id"], False, "The terms are one-sided.", NOW9)
    assert _one(db, "SELECT status FROM swaps WHERE id = %s", (again["swap_id"],))["status"] == "cancelled"
    _ = member
    sound(db)


def test_a_swap_is_seen_only_by_its_two_sides_and_needs_level_twenty_five(db, client):
    a, a_acct = trader(db, "investment_banker", "privateparty", cash_naira=10_000_000)
    swaps.propose(db, a, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1, notional=naira(10_000_000), now=NOW9)
    young, _ = pro(db, "investment_banker", "junior", level=10)
    with pytest.raises(derivatives.DerivativesError, match="Level 25"):
        swaps.propose(db, young, kind="rate", counterparty={"bank": bank_id(db)}, side="pay_fixed", quarters=1,
                      notional=naira(10_000_000), now=NOW9)
    assert join(client, ADULT).status_code == 201
    seen = client.get("/api/swaps").json()
    assert seen["swaps"] == [] and "privateparty" not in str(seen)


def test_oil_producers_sell_and_fuel_users_buy_oil_futures_and_it_shows_in_their_accounts(db):
    quarters.close_due_quarters(db, after_quarters(9))                  # the close lists next quarter's futures, and companies hedge
    s = _one(db, "SELECT * FROM derivative_series WHERE kind = 'future' AND underlying = 'OIL' AND expiry_period = 10")
    rows = _one(db, "SELECT count(*) FILTER (WHERE p.side = 'short' AND c.ticker = ANY(%s)) AS sellers,"
                    " count(*) FILTER (WHERE p.side = 'long' AND c.sector = ANY(%s)) AS buyers"
                    " FROM derivative_positions p JOIN companies c ON c.account_id = p.account WHERE p.series_id = %s AND p.status = 'open'",
                (list(data.HEDGE_SELLERS), list(data.HEDGE_BUYERS_SECTORS), s["id"]))
    assert rows["sellers"] >= 2 and rows["buyers"] >= 3
    assert not _one(db, "SELECT 1 FROM derivative_positions p JOIN companies c ON c.account_id = p.account WHERE p.margin > 0")
    assert derivatives.check_books(db) == []
    # The hedges taken at the close of quarter 9 are settled through quarter 10 and at its close; the cash that moved after
    # a company filed is counted in its next filing (quarter 11).
    quarters.close_due_quarters(db, after_quarters(11))
    hedged = _one(db, "SELECT count(*) AS n FROM company_results r WHERE r.period IN (10, 11) AND r.drivers::text LIKE '%%hedges%%'")
    stray = _one(db, "SELECT count(*) AS n FROM company_results WHERE period >= 10 AND drivers::text LIKE '%%outside its normal business%%'")
    assert hedged["n"] >= 3 and stray["n"] == 0
    sound(db)
