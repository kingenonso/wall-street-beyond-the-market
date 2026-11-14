"""Stage 11: the courts, as a docket.

The court's subject is money, its evidence is the ledger, and its remedy is money moving. These tests prove the four
kinds of case against the market from the record itself: dealing on confidential information, manipulation (wash
trading and ramping), an undisclosed stake, and a naked short. They then follow a case through the docket: the
regulator's budget, a player's bond, settling, fighting, the judgment, the ban, and the money paid down over quarters.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, courts, exchange, intel, ledger
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.conftest import after_quarters
from tests.test_careers import NOW9
from tests.test_firm import firm_of
from tests.test_market import place, reference, trader
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")
P = 9                 # the running quarter at NOW9
T = "IDC"             # Idanre Cement, about ₦20 a share at the start of the world
# The shares in a fixture's trade. Big enough that the profit, or the turnover, clears the court's own floor: a claim
# worth less than ₦100,000 is not worth a case, so a trade of a few hundred naira proves nothing but the floor.
INSIDER_SHARES = 100_000        # 10% of a ₦20 share, a hundred thousand times, is ₦200,000 before the fees
WASH_SHARES = 3_000             # three trades of three thousand shares at ₦20 is ₦180,000 of turnover


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def company(db, ticker=T):
    return _one(db, "SELECT id, ticker, name FROM companies WHERE ticker = %s", (ticker,))


def player_of(db, account):
    return _one(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))["player_id"]


def clear_book(db, ticker=T):
    """Cancel every order waiting in a share and start the day, so a test's own trades are the only ones that happen."""
    for row in _rows(db, "SELECT o.id, o.account_id FROM market_orders o JOIN companies c ON c.id = o.company_id"
                         " WHERE c.ticker = %s AND o.status = 'open' ORDER BY o.id", (ticker,)):
        try:
            exchange.cancel_order(db, account=row["account_id"], order_id=row["id"], now=NOW9)
        except exchange.ExchangeError:
            pass
    day, _ = exchange.session_of(NOW9)
    share = _one(db, "SELECT m.session_date, m.auction_done FROM market_instruments m"
                     " JOIN companies c ON c.id = m.company_id WHERE c.ticker = %s", (ticker,))
    if share["session_date"] < day:
        db.execute("UPDATE market_instruments SET session_date = %s, reference_price = coalesce(last_price, reference_price),"
                   " auction_done = true WHERE company_id = (SELECT id FROM companies WHERE ticker = %s)", (day, ticker))
    elif not share["auction_done"]:
        db.execute("UPDATE market_instruments SET auction_done = true"
                   " WHERE company_id = (SELECT id FROM companies WHERE ticker = %s)", (ticker,))


def trade(db, account, side, quantity, price, ticker=T, now=NOW9):
    return place(db, account, side, quantity, price, now=now, ticker=ticker)


def dealing(db, player_id, account, company_id, at=None):
    """A confidential dealing, recorded as Stage 10B records it: a tip held, and a trade laid on it."""
    at = at or NOW9 - timedelta(hours=1)
    w = careers.world_now(db, NOW9)
    item = intel.make(db, kind="tip", topic="company", truth="true", basis="none", period=w["period"], day=w["day"],
                      now=at, company_id=company_id, tone=1, status="rumour", confidential=True,
                      useful_until=NOW9 + timedelta(hours=4), words="Word from inside: good news is coming.")
    intel.hold(db, item["id"], player_id, "found", at)
    db.execute("INSERT INTO confidential_dealings (player_id, account_id, item_id, company_id, at)"
               " VALUES (%s, %s, %s, %s, %s)", (player_id, account, item["id"], company_id, at))
    return item


def fees_of(db, account, company_id, since):
    """The fees the account itself paid on its trades in a company since a moment (not the other side's)."""
    rows = _rows(db, "SELECT buyer_account_id = %s AS bought, seller_account_id = %s AS sold, buyer_fee, seller_fee"
                     " FROM market_trades WHERE company_id = %s AND (buyer_account_id = %s OR seller_account_id = %s)"
                     " AND traded_at >= %s", (account, account, company_id, account, account, since))
    return sum((r["buyer_fee"] if r["bought"] else 0) + (r["seller_fee"] if r["sold"] else 0) for r in rows)


def insider_wrong(db, *, cash=100_000_000):
    """A player deals on a tip: buys at the reference price, sells at the day's highest, and the profit is the number."""
    c = company(db)
    clear_book(db)
    base = reference(db, T)
    high = exchange.price_limits(base)[1]
    insider = trader(db, "insider", cash_naira=cash)
    seller = trader(db, "seller", shares=INSIDER_SHARES + 5_000)
    buyer = trader(db, "buyer", cash_naira=cash)
    pid = player_of(db, insider)
    dealing(db, pid, insider, c["id"])
    trade(db, seller, "sell", INSIDER_SHARES, base)
    trade(db, insider, "buy", INSIDER_SHARES, base)
    trade(db, insider, "sell", INSIDER_SHARES, high)
    trade(db, buyer, "buy", INSIDER_SHARES, high)
    wrong = next(w for w in courts._wrongs(db, P, NOW9)
                 if w["kind"] == "insider" and str(w["defendant_id"]) == str(pid))
    return {"wrong": wrong, "insider": insider, "pid": pid, "company": c, "base": base, "high": high}


def wash_wrong(db):
    """A player trades with itself three times in a quarter: the turnover that was not real is the number."""
    c = company(db)
    clear_book(db)
    base = reference(db, T)
    washer = trader(db, "washer", cash_naira=100_000_000, shares=10_000)
    pid = player_of(db, washer)
    for _ in range(data.COURT_WASH_TRADES):
        trade(db, washer, "sell", WASH_SHARES, base)
        trade(db, washer, "buy", WASH_SHARES, base)
    wrong = next(w for w in courts._wrongs(db, P, NOW9)
                 if w["kind"] == "manipulation" and str(w["defendant_id"]) == str(pid))
    return {"wrong": wrong, "washer": washer, "pid": pid, "company": c, "base": base}


def stake_wrong(db):
    """An empire holds a 5% step in a listed company and never made it public."""
    c = company(db)
    empire, team = firm_of(db)
    shares_in_issue = ledger.amount_in_existence(db, f"SHR-{T}")
    held = shares_in_issue * data.COURT_STAKE_STEP_BPS // BPS
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"],
                    amount=held, asset=f"SHR-{T}", kind="test_shares", memo="Test: a stake kept out of sight")
    wrong = next(w for w in courts._wrongs(db, P, NOW9)
                 if w["kind"] == "undisclosed_stake" and str(w["defendant_id"]) == str(team["head"]))
    return {"wrong": wrong, "empire": empire, "team": team, "company": c, "shares_in_issue": shares_in_issue}


def short_wrong(db):
    """Borrowed shares that had to be bought in, at a profit."""
    c = company(db)
    borrower = trader(db, "shorter", cash_naira=1_000_000)
    pid = player_of(db, borrower)
    lender = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    opened, closed, shares = 700_000, 600_000, 10_000
    db.execute("INSERT INTO short_positions (borrower, lender, company_id, shares, collateral, opened_price,"
               " opened_period, status, closed_price, at, closed_at)"
               " VALUES (%s, %s, %s, %s, 0, %s, 8, 'bought_in', %s, %s, %s)",
               (borrower, lender, c["id"], shares, opened, closed, NOW9 - timedelta(hours=2), NOW9 - timedelta(hours=1)))
    wrong = next(w for w in courts._wrongs(db, P, NOW9)
                 if w["kind"] == "naked_short" and str(w["defendant_id"]) == str(pid))
    return {"wrong": wrong, "borrower": borrower, "pid": pid, "company": c,
            "opened": opened, "closed": closed, "shares": shares}


def open_regulator_case(db, *, kind="insider", defendant_id, company_id, amount=None):
    amount = amount or naira(10_000_000)
    return courts.open_case(db, kind=kind, defendant_id=defendant_id, claimant_id=None, company_id=company_id,
                            amount=amount, evidence={"key": f"{kind}:test", "total": amount, "lines": []},
                            words=f"A test case of {kind}.", period=P, now=NOW9)


# ---------------------------------------------------------------------------
# The evidence: what the record proves, and the number it proves
# ---------------------------------------------------------------------------

def test_an_informed_trade_is_proved_from_the_record_and_the_profit_is_the_number(db):
    found = insider_wrong(db)
    wrong, base, high = found["wrong"], found["base"], found["high"]
    expected = (high - base) * INSIDER_SHARES - fees_of(db, found["insider"], found["company"]["id"],
                                                        NOW9 - timedelta(hours=1))
    assert wrong["amount"] == expected > 0
    assert wrong["company_id"] == found["company"]["id"]
    assert wrong["lines"] and wrong["lines"][0]["side"] == "bought"
    assert "confidential information" in wrong["words"] and T in wrong["words"]
    # The number is the profit, not the turnover: the fees the account paid are taken off.
    assert wrong["amount"] < (high - base) * INSIDER_SHARES


def test_a_trade_on_a_tip_that_lost_money_is_not_a_case(db):
    c = company(db)
    clear_book(db)
    base = reference(db, T)
    low = exchange.price_limits(base)[0]
    insider = trader(db, "insider", cash_naira=100_000_000)
    seller = trader(db, "seller", shares=5_000)
    buyer = trader(db, "buyer", cash_naira=100_000_000)
    pid = player_of(db, insider)
    dealing(db, pid, insider, c["id"])
    trade(db, seller, "sell", 1_000, base)
    trade(db, insider, "buy", 1_000, base)
    trade(db, insider, "sell", 1_000, low)
    trade(db, buyer, "buy", 1_000, low)
    assert not [w for w in courts._wrongs(db, P, NOW9)
                if w["kind"] == "insider" and str(w["defendant_id"]) == str(pid)]


def test_wash_trading_is_manipulation_and_the_turnover_is_the_number(db):
    found = wash_wrong(db)
    wrong = found["wrong"]
    assert wrong["amount"] == found["base"] * WASH_SHARES * data.COURT_WASH_TRADES
    assert "same person on both sides" in wrong["words"]
    assert len(wrong["lines"]) == data.COURT_WASH_TRADES


def test_a_ramp_is_proved_from_the_buys_and_the_sales_into_the_rise(db):
    c = company(db)
    clear_book(db)
    base = reference(db, T)
    ramper = trader(db, "ramper", cash_naira=100_000_000)
    seller = trader(db, "seller", shares=10_000)
    buyer = trader(db, "buyer", cash_naira=100_000_000)
    # A trade before the campaign fixes the price it started from.
    trade(db, seller, "sell", 100, base)
    trade(db, buyer, "buy", 100, base)
    since = NOW9 + timedelta(minutes=1)
    for step in (1, 2, 3):
        price = base + base // 100 * step
        trade(db, seller, "sell", 100, price, now=since)
        trade(db, ramper, "buy", 100, price, now=since)
    top = base + base // 100 * 4
    trade(db, ramper, "sell", 300, top, now=since)
    trade(db, buyer, "buy", 300, top, now=since)
    found = courts._ramp_evidence(db, ramper, c["id"], since, since + timedelta(hours=1), T)
    assert found is not None
    assert found["amount"] == (top - base) * 300
    assert "sold into the rise" in found["words"]


def test_an_undisclosed_stake_is_proved_from_the_holdings_and_the_disclosure(db):
    found = stake_wrong(db)
    wrong = found["wrong"]
    price = _one(db, "SELECT last_price, reference_price FROM market_instruments WHERE company_id = %s",
                 (found["company"]["id"],))
    price = price["last_price"] or price["reference_price"]
    assert wrong["amount"] == data.COURT_STAKE_STEP_BPS * found["shares_in_issue"] // BPS * price
    assert "kept out of sight" in wrong["words"]
    # Once the step is made public, there is nothing left to prove.
    db.execute("INSERT INTO stake_disclosures (empire_id, company_id, bps, at) VALUES (%s, %s, %s, %s)"
               " ON CONFLICT (empire_id, company_id) DO UPDATE SET bps = EXCLUDED.bps, at = EXCLUDED.at",
               (found["empire"]["id"], found["company"]["id"], data.COURT_STAKE_STEP_BPS, NOW9))
    assert not [w for w in courts._wrongs(db, P, NOW9)
                if w["kind"] == "undisclosed_stake" and str(w["defendant_id"]) == str(found["team"]["head"])]


def test_a_naked_short_is_proved_from_the_buy_in_and_the_profit_is_the_number(db):
    found = short_wrong(db)
    wrong = found["wrong"]
    assert wrong["amount"] == (found["opened"] - found["closed"]) * found["shares"]
    assert "bought in" in wrong["words"]


def test_a_claim_below_the_courts_minimum_is_not_brought(db):
    c = company(db)
    borrower = trader(db, "shorter", cash_naira=1_000_000)
    pid = player_of(db, borrower)
    lender = ledger.account_id(db, ledger.INVESTORS_PUBLIC)
    # A short that made ₦1,000: not worth the court's time.
    db.execute("INSERT INTO short_positions (borrower, lender, company_id, shares, collateral, opened_price,"
               " opened_period, status, closed_price, at, closed_at)"
               " VALUES (%s, %s, %s, 10, 0, 100_000, 8, 'bought_in', 90_000, %s, %s)",
               (borrower, lender, c["id"], NOW9 - timedelta(hours=2), NOW9 - timedelta(hours=1)))
    assert not [w for w in courts._wrongs(db, P, NOW9)
                if w["kind"] == "naked_short" and str(w["defendant_id"]) == str(pid)]


# ---------------------------------------------------------------------------
# The regulator: a budget, and a choice about what is worth proving
# ---------------------------------------------------------------------------

def test_the_regulator_brings_a_case_it_can_afford_and_not_one_it_cannot(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    wrong = {"kind": "insider", "key": "insider:test", "defendant_id": pid, "company_id": c["id"], "ticker": T,
             "amount": naira(10_000_000), "lines": [{"what": "trade"}], "words": "Dealt on confidential information."}
    courts.ensure(db)
    budget = ledger.account_id(db, courts.REGULATOR)
    before = ledger.balance(db, budget)
    case_id = courts._regulator_brings(db, wrong, P, NOW9)
    assert case_id is not None
    assert ledger.balance(db, budget) == before - naira(data.COURT_CASE_COST_NAIRA)
    case = courts.case(db, case_id)
    assert case["claimant"] == "The regulator" and case["status"] == "open" and case["bond"] == 0
    # The cost of proving a case is a ledger transaction, paid to the Treasury.
    assert _one(db, "SELECT 1 AS x FROM ledger_transactions WHERE kind = 'court_cost' AND period = %s", (P,))
    # A regulator with no money brings nothing.
    ledger.transfer(db, payer=budget, receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=ledger.balance(db, budget), kind="test_spend", memo="Test: empty the budget")
    assert courts._regulator_brings(db, wrong, P, NOW9) is None
    assert ledger.audit(db) == []


def test_enforcement_is_probabilistic_and_spends_the_budget(db, monkeypatch):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    wrong = {"kind": "insider", "key": "insider:test", "defendant_id": pid, "company_id": c["id"], "ticker": T,
             "amount": naira(10_000_000), "lines": [{"what": "trade"}], "words": "Dealt on confidential information."}
    courts.ensure(db)
    monkeypatch.setattr(courts, "_wrongs", lambda conn, period, now: [wrong])
    monkeypatch.setattr(courts, "_roll", lambda *a: BPS)               # the draw never falls inside the chance
    assert courts.enforce(db, P, NOW9) == 0
    monkeypatch.setattr(courts, "_roll", lambda *a: 0)                 # the draw always does
    assert courts.enforce(db, P, NOW9) == 1
    assert _one(db, "SELECT count(*) AS n FROM court_cases")["n"] == 1


def test_the_regulator_view_counts_what_it_has_brought_won_and_settled(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    courts.ensure(db)
    won = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    courts.judge(db, won, P, NOW9)
    settled = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"])
    courts.respond(db, pid, settled, "settle", P, NOW9)
    view = courts.regulator(db)
    assert view["brought"] == 2 and view["won"] == 1 and view["settled"] == 1
    assert view["fines"] == apply_bps(naira(10_000_000), data.COURT_FINE_BPS["insider"])
    assert view["cost"] == naira(data.COURT_CASE_COST_NAIRA)


# ---------------------------------------------------------------------------
# Answering a case: settle, or fight
# ---------------------------------------------------------------------------

def test_a_defendant_settles_at_six_tenths_and_the_money_moves(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    amount = naira(10_000_000)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"], amount=amount)
    courts.ensure(db)
    fund = ledger.account_id(db, courts.COMPENSATION_FUND)
    before = ledger.balance(db, fund)
    case = courts.respond(db, pid, case_id, "settle", P, NOW9)
    price = apply_bps(amount, data.COURT_SETTLE_BPS)
    assert case["status"] == "settled" and case["paid"] == price and case["owed"] == 0
    assert ledger.balance(db, fund) == before + price
    assert ledger.balance(db, defendant) == naira(100_000_000) - price
    assert _one(db, "SELECT kind FROM legal_records WHERE player_id = %s", (pid,))["kind"] == "settled"
    assert ledger.audit(db) == []


def test_a_defendant_who_cannot_afford_to_settle_must_be_judged(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"])
    with pytest.raises(courts.CourtError, match="do not have"):
        courts.respond(db, pid, case_id, "settle", P, NOW9)
    assert courts.case(db, case_id)["status"] == "open"


def test_a_judgment_reads_like_arithmetic_and_a_manipulation_carries_a_ban(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    amount = naira(10_000_000)
    case_id = open_regulator_case(db, kind="manipulation", defendant_id=pid, company_id=c["id"], amount=amount)
    courts.ensure(db)
    reputation = _one(db, "SELECT reputation FROM players WHERE id = %s", (pid,))["reputation"]
    case = courts.respond(db, pid, case_id, "fight", P, NOW9)
    fine = apply_bps(amount, data.COURT_FINE_BPS["manipulation"])
    costs = apply_bps(amount, data.COURT_COSTS_BPS)
    assert case["status"] == "judged"
    assert case["disgorgement"] == 0 and case["fine"] == fine and case["costs"] == costs
    assert case["ban_quarters"] == data.COURT_BAN_QUARTERS["manipulation"]
    assert case["paid"] == fine + costs and case["owed"] == 0
    assert _one(db, "SELECT reputation FROM players WHERE id = %s", (pid,))["reputation"] == reputation - data.COURT_REPUTATION
    assert courts.banned_until(db, pid) == P + data.COURT_BAN_QUARTERS["manipulation"]
    with pytest.raises(exchange.ExchangeError, match="banned"):
        courts.check_trade(db, defendant, NOW9)
    assert _one(db, "SELECT kind FROM legal_records WHERE player_id = %s", (pid,))["kind"] == "judged"
    assert ledger.audit(db) == []


def test_an_insider_judgment_disgorges_the_profit_and_fines_the_same_again(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    amount = naira(10_000_000)
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"], amount=amount)
    courts.ensure(db)
    case = courts.judge(db, case_id, P, NOW9)
    assert case["disgorgement"] == amount
    assert case["fine"] == apply_bps(amount, data.COURT_FINE_BPS["insider"])
    assert case["costs"] == apply_bps(amount, data.COURT_COSTS_BPS)
    assert case["ban_quarters"] == 0
    assert case["paid"] == case["disgorgement"] + case["fine"] + case["costs"]
    # The fine is split: half funds the regulator, half goes to the Treasury.
    regulator = ledger.account_id(db, courts.REGULATOR)
    assert ledger.balance(db, regulator) >= apply_bps(case["fine"], data.COURT_FINE_TO_REGULATOR_BPS)
    assert ledger.audit(db) == []


def test_an_insurance_fraud_judgment_fines_and_bans_the_defendant(db):
    """The insurer refers a claim on a loss of the claimant's own making (tests/test_insurance_loopholes.py opens one
    from a real refusal); judged, it is fined, costed and banned like any other wrong."""
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    amount = naira(1_000_000)
    courts.ensure(db)
    case_id = courts.open_case(db, kind="insurance_fraud", defendant_id=pid, claimant_id=None, company_id=None,
                               amount=amount, evidence={"key": "insurance_fraud:test", "total": amount, "lines": []},
                               words="Claimed on a loss of their own making.", period=P, now=NOW9)
    case = courts.judge(db, case_id, P, NOW9)
    assert case["status"] == "judged"
    assert case["disgorgement"] == 0
    assert case["fine"] == apply_bps(amount, data.COURT_FINE_BPS["insurance_fraud"])
    assert case["costs"] == apply_bps(amount, data.COURT_COSTS_BPS)
    assert case["ban_quarters"] == data.COURT_BAN_QUARTERS["insurance_fraud"]
    assert courts.banned_until(db, pid) == P + data.COURT_BAN_QUARTERS["insurance_fraud"]
    assert ledger.audit(db) == []


def test_a_judgment_is_paid_down_over_quarters_as_the_defendant_has_money(db):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    amount = naira(10_000_000)
    case_id = open_regulator_case(db, kind="insider", defendant_id=pid, company_id=c["id"], amount=amount)
    courts.ensure(db)
    case = courts.judge(db, case_id, P, NOW9)
    owed = case["disgorgement"] + case["fine"] + case["costs"]
    assert case["paid"] == naira(1_000_000) and case["owed"] == owed - naira(1_000_000)
    # Next quarter, with money again, the rest is paid down.
    give_cash(db, defendant, 100_000_000)
    paid = courts.pay(db, case_id, P + 1, after_quarters(9))
    assert paid == owed - naira(1_000_000)
    assert courts.case(db, case_id)["owed"] == 0
    # A case already paid is not paid again.
    assert courts.pay(db, case_id, P + 2, after_quarters(10)) == 0
    assert ledger.audit(db) == []


def test_a_case_left_unanswered_is_judged_at_the_next_close(db, monkeypatch):
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=100_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, kind="manipulation", defendant_id=pid, company_id=c["id"])
    monkeypatch.setattr(courts, "_wrongs", lambda conn, period, now: [])
    result = courts.at_close(db, P + 1, after_quarters(9))
    assert result["judged"] == 1
    assert courts.case(db, case_id)["status"] == "judged"
    assert courts.banned_until(db, pid) == P + 1 + data.COURT_BAN_QUARTERS["manipulation"]


# ---------------------------------------------------------------------------
# The docket, a player's cases, and the legal record
# ---------------------------------------------------------------------------

def test_the_docket_is_public_and_a_players_cases_are_their_own(db):
    c = company(db)
    a = trader(db, "a", cash_naira=100_000_000)
    b = trader(db, "b", cash_naira=100_000_000)
    a_pid, b_pid = player_of(db, a), player_of(db, b)
    regulator_case = open_regulator_case(db, defendant_id=a_pid, company_id=c["id"])
    brought = courts.open_case(db, kind="insider", defendant_id=b_pid, claimant_id=a_pid, company_id=c["id"],
                               amount=naira(10_000_000), evidence={"key": "insider:test", "total": naira(10_000_000),
                                                                   "lines": []}, words="A case brought by a player.",
                               period=P, now=NOW9, bond=naira(1_000_000))
    docket = courts.docket(db)
    assert {k["id"] for k in docket} == {regulator_case, brought}
    assert next(k for k in docket if k["id"] == regulator_case)["claimant"] == "The regulator"
    assert next(k for k in docket if k["id"] == brought)["claimant"] == "a"
    assert [k["id"] for k in courts.my_cases(db, a_pid)["defending"]] == [regulator_case]
    assert [k["id"] for k in courts.my_cases(db, a_pid)["brought"]] == [brought]
    assert [k["id"] for k in courts.my_cases(db, b_pid)["defending"]] == [brought]
    assert courts.my_cases(db, b_pid)["brought"] == []
    # A decided case leaves the docket but stays on the player's record.
    courts.respond(db, a_pid, regulator_case, "settle", P, NOW9)
    assert regulator_case not in {k["id"] for k in courts.docket(db)}
    assert [k["id"] for k in courts.my_cases(db, a_pid)["defending"]] == [regulator_case]


def test_a_case_once_opened_is_not_rewritten(db):
    from psycopg import errors
    c = company(db)
    defendant = trader(db, "defendant", cash_naira=1_000_000)
    pid = player_of(db, defendant)
    case_id = open_regulator_case(db, defendant_id=pid, company_id=c["id"])
    with pytest.raises(errors.RestrictViolation):
        db.execute("UPDATE court_cases SET amount = amount + 1 WHERE id = %s", (case_id,))
    with pytest.raises(errors.RestrictViolation):
        db.execute("UPDATE court_cases SET evidence = '{}'::jsonb WHERE id = %s", (case_id,))


# ---------------------------------------------------------------------------
# The website
# ---------------------------------------------------------------------------

def test_the_court_page_shows_the_docket_and_keeps_the_worlds_secret(client, player, db, monkeypatch):
    from server import court_routes
    monkeypatch.setattr(court_routes, "_exchange_time", lambda conn: NOW9)
    got = client.get("/api/court")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["ready"] is True
    assert set(body) >= {"docket", "claims", "mine", "regulator", "fund", "kinds", "rules"}
    assert len(body["kinds"]) == 5
    # Money is sent as text, so no figure is ever rounded on the way.
    assert isinstance(body["regulator"]["budget"], str) and isinstance(body["fund"], str)
    # The world's secret, which decides which wrongs become cases, is never sent.
    for hidden in ("fortune_seed", "secret", "_roll", "enforce_bps"):
        assert hidden not in got.text


def test_a_player_brings_a_case_through_the_website_and_posts_a_bond(client, player, db, monkeypatch):
    from server import court_routes
    monkeypatch.setattr(court_routes, "_exchange_time", lambda conn: NOW9)
    c = company(db)
    empire, team = firm_of(db)
    shares_in_issue = ledger.amount_in_existence(db, f"SHR-{T}")
    held = shares_in_issue * data.COURT_STAKE_STEP_BPS // BPS
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=empire["account_id"],
                    amount=held, asset=f"SHR-{T}", kind="test_shares", memo="Test: a stake kept out of sight")
    account = ledger.player_account_id(db, player["id"])
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account,
                    amount=1_000, asset=f"SHR-{T}", kind="test_shares", memo="Test: a shareholding")
    give_cash(db, account, 100_000_000_000)          # a tenth of a large stake is a large bond
    before = ledger.balance(db, account)
    page = client.get("/api/court").json()
    claim = next(x for x in page["claims"]
                 if x["kind"] == "undisclosed_stake" and x["defendant_id"] == str(team["head"]))
    answer = client.post("/api/court/cases", json={"kind": "undisclosed_stake", "defendant_id": str(team["head"]),
                                                   "company_id": str(c["id"])})
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["mine"]["brought"][0]["kind"] == "undisclosed_stake"
    assert body["mine"]["brought"][0]["bond"] == claim["bond"]
    assert ledger.balance(db, account) == before - int(claim["bond"])


def test_a_defendant_answers_a_case_through_the_website(client, player, db, monkeypatch):
    from server import court_routes
    monkeypatch.setattr(court_routes, "_exchange_time", lambda conn: NOW9)
    c = company(db)
    account = ledger.player_account_id(db, player["id"])
    give_cash(db, account, 100_000_000)
    case_id = open_regulator_case(db, defendant_id=player["id"], company_id=c["id"])
    answer = client.post(f"/api/court/cases/{case_id}/answer", json={"choice": "settle"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["mine"]["defending"][0]["status"] == "settled"
    # Somebody else's case cannot be answered.
    other = trader(db, "other", cash_naira=1_000_000)
    other_case = open_regulator_case(db, defendant_id=player_of(db, other), company_id=c["id"])
    refused = client.post(f"/api/court/cases/{other_case}/answer", json={"choice": "fight"})
    assert refused.status_code == 409 and "Only the person" in refused.json()["detail"]


def test_the_court_pages_refuse_strangers_and_explain_refusals_in_plain_words(client, player, db, monkeypatch):
    from server import court_routes
    monkeypatch.setattr(court_routes, "_exchange_time", lambda conn: NOW9)
    c = company(db)
    # A kind the player cannot bring, and a case that does not exist.
    refused = client.post("/api/court/cases", json={"kind": "manipulation", "defendant_id": str(player["id"]),
                                                    "company_id": str(c["id"])})
    assert refused.status_code == 409
    assert client.post("/api/court/cases/999999/answer", json={"choice": "settle"}).status_code == 409
    # A made-up answer is refused before it reaches the court.
    assert client.post("/api/court/cases/1/answer", json={"choice": "appeal"}).status_code == 422
    assert client.post("/api/court/cases", json={"kind": "treason", "defendant_id": str(player["id"])}).status_code == 422
    client.cookies.clear()
    assert client.get("/api/court").status_code == 401
