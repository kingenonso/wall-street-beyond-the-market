"""Stage 3, Part B: banks that lend for real, insurance, the Central Bank, prices,
commodities, the ten mindsets, real causes of good and bad quarters, the Money Watch.

Each section is one item of the approved checklist. The news wire is in test_news.py.
"""

from __future__ import annotations

import pytest
from psycopg import errors
from psycopg.rows import dict_row

from simulation import banking, economy, events, ledger, macro, mindsets, moneywatch, quarters
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.conftest import after_quarters, money_accounted_for


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _add_event(db, kind: str, **fields) -> None:
    """Make something happen in the first quarter, on top of whatever the world had decided."""
    row = {"period": 1, "day": 10, "kind": kind, **fields}
    db.execute(f"INSERT INTO events ({', '.join(row)}) VALUES ({', '.join(['%s'] * len(row))})", list(row.values()))


# ---------------------------------------------------------------------------
# 9. Banks lend for real
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_households_pay_interest_repay_and_borrow_through_the_ledger(db):
    moved = {
        (r["period"], r["kind"]): r["total"] for r in _dicts(
            db, "SELECT t.period, t.kind, sum(e.amount)::bigint AS total FROM ledger_entries e JOIN ledger_transactions t"
                " ON t.id = e.transaction_id WHERE e.amount > 0 AND t.kind IN ('loan_interest', 'household_loan',"
                " 'household_loan_repayment') GROUP BY 1, 2")
    }
    for period in range(1, 9):
        assert all(moved[(period, kind)] > 0 for kind in ("loan_interest", "household_loan", "household_loan_repayment"))
    # What households owe today is what they owed at the start, plus every loan, less every repayment.
    opening = db.execute("SELECT sum(customer_loans) FROM company_results r JOIN companies c ON c.id = r.company_id"
                         " WHERE r.period = 0 AND c.sector = 'banking'").fetchone()[0]
    lent = sum(v for (_, kind), v in moved.items() if kind == "household_loan")
    repaid = sum(v for (_, kind), v in moved.items() if kind == "household_loan_repayment")
    owed = db.execute("SELECT sum(principal) FROM household_debts").fetchone()[0]
    assert owed == opening + lent - repaid
    # And each bank's balance sheet shows exactly what its households owe it.
    for r in _dicts(db, "SELECT r.customer_loans, (SELECT sum(principal) FROM household_debts h WHERE h.bank_company_id = c.id) AS owed"
                        " FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period = 8 AND c.sector = 'banking'"):
        assert r["customer_loans"] == r["owed"]


@pytest.mark.world("eight")
def test_the_interest_a_household_pays_follows_the_central_banks_rate(db):
    for period in range(1, 9):
        rate = macro.state(db, period - 1)["next_policy_rate_bps"] + data.HOUSEHOLD_LOAN_SPREAD_BPS
        paid = db.execute("SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                          " WHERE t.kind = 'loan_interest' AND t.period = %s AND e.amount > 0", (period,)).fetchone()[0]
        owed_before = db.execute("SELECT sum(debt) FROM household_results WHERE period = %s", (period - 1,)).fetchone()[0] \
            if period > 1 else db.execute("SELECT sum(customer_loans) FROM company_results r JOIN companies c ON c.id = r.company_id"
                                          " WHERE r.period = 0 AND c.sector = 'banking'").fetchone()[0]
        expected = owed_before * rate // (4 * BPS)
        assert abs(paid - expected) <= expected // 500          # within a fifth of a percent: only rounding


@pytest.mark.world("eight")
def test_every_bank_loan_carries_the_central_banks_rate_plus_an_amount_for_the_borrowers_rating(db):
    """Item 11 as well: a change in the Central Bank's rate reaches every loan."""
    rate = macro.state(db, 7)["next_policy_rate_bps"]           # the rate in force during quarter 8
    loans = _dicts(
        db, "SELECT d.*, (SELECT p.credit_rating FROM company_reports p WHERE p.company_id = d.company_id AND p.period = 7"
            " ORDER BY version DESC LIMIT 1) AS rating FROM company_debts d WHERE d.kind = 'bank_loan' AND d.principal_outstanding > 0")
    assert len(loans) > 20
    for loan in loans:
        assert loan["annual_rate_bps"] == macro.loan_rate_bps(rate, loan["rating"], loan["name"].startswith("overdue")), loan["name"]
    assert macro.loan_rate_bps(1300, "AAA") < macro.loan_rate_bps(1300, "BBB") < macro.loan_rate_bps(1300, "CCC")
    # Bonds were sold at a fixed rate and keep it.
    assert db.execute("SELECT count(DISTINCT annual_rate_bps) FROM company_debts WHERE kind = 'bond'").fetchone()[0] >= 1


@pytest.mark.world("eight")
def test_a_lender_loses_money_when_a_borrower_fails(db):
    bad = _dicts(db, "SELECT d.*, c.name AS lender FROM company_debts d JOIN companies c ON c.account_id = d.lender_account_id"
                     " WHERE d.provision > 0")
    assert bad, "expected at least one loan past its date in eight quarters"
    for loan in bad:
        assert loan["maturity_period"] <= 8 and loan["principal_outstanding"] > 0      # only loans past their date
    lenders = _dicts(db, "SELECT c.name, c.account_id, sum(r.loan_losses)::bigint AS lost FROM company_results r"
                         " JOIN companies c ON c.id = r.company_id GROUP BY 1, 2 HAVING sum(r.loan_losses) <> 0")
    assert {l["name"] for l in lenders} == {loan["lender"] for loan in bad}
    for lender in lenders:
        # What it has written off in its accounts is what its loan records say, to the kobo.
        written = db.execute("SELECT sum(provision) FROM company_debts WHERE lender_account_id = %s", (lender["account_id"],)).fetchone()[0]
        assert lender["lost"] == written > 0
    # The borrower still owes every kobo: a write-off is the lender's loss, not the borrower's gain.
    for loan in bad:
        assert db.execute("SELECT borrowings FROM company_results WHERE company_id = %s AND period = 8",
                          (loan["company_id"],)).fetchone()[0] >= loan["principal_outstanding"]


def test_a_bank_may_lend_only_what_its_own_funds_support():
    bank = {"total_equity": naira(100), "household_loans": naira(500), "company_loans": naira(250), "customer_funds": naira(400)}
    assert banking.lending_room(bank) == naira(50)                       # eight times its funds, less what is already lent
    assert banking.lending_room({**bank, "household_loans": naira(700)}) == 0
    assert banking.lending_room({**bank, "total_equity": -naira(5)}) == 0   # a bank with no funds of its own lends nothing
    assert banking.reserve(bank) == naira(40)


def test_households_borrow_less_the_more_they_already_owe():
    income = naira(100)
    assert banking.room_to_borrow_bps(3 * income, income) == BPS         # three quarters' income: the usual
    assert banking.room_to_borrow_bps(income, income) > BPS
    assert banking.room_to_borrow_bps(6 * income, income) == 0           # twice that: their borrowing stops growing
    assert banking.room_to_borrow_bps(income, 0) == 0
    assert macro.credit_appetite_bps(1100) > macro.credit_appetite_bps(1300) == BPS > macro.credit_appetite_bps(1600)


@pytest.mark.world("eight")
def test_new_money_appears_only_as_central_bank_loans_to_banks_and_is_all_accounted_for(db):
    assert ledger.amount_in_existence(db) == money_accounted_for(db)
    lent = _dicts(db, "SELECT c.sector, d.annual_rate_bps, d.principal_outstanding FROM company_debts d"
                      " JOIN companies c ON c.id = d.company_id WHERE d.kind = 'central_bank_loan'")
    assert all(loan["sector"] == "banking" for loan in lent)
    # Whoever received newly made money is a bank, and nobody else.
    receivers = {r["sector"] for r in _dicts(
        db, "SELECT c.sector FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " LEFT JOIN companies c ON c.account_id = e.account_id WHERE t.kind = 'central_bank_lending' AND e.amount > 0")}
    assert receivers <= {"banking"}
    assert ledger.audit(db) == []


def test_nobody_but_the_central_bank_can_make_a_central_bank_loan(db):
    """Loophole question 2: money from nothing. The reason 'central_bank_lending' lets the
    Central Bank go below zero. It does not let anybody else."""
    treasury = ledger.account_id(db, ledger.TREASURY)
    prize = db.execute("SELECT id FROM ledger_accounts WHERE kind = 'prize_pool'").fetchone()[0]
    bank = db.execute("SELECT account_id FROM companies WHERE sector = 'banking' LIMIT 1").fetchone()[0]
    before = ledger.amount_in_existence(db)
    with pytest.raises((ledger.LedgerError, errors.Error)):
        ledger.transfer(db, payer=prize, receiver=bank, amount=ledger.balance(db, prize) + 1,
                        kind="central_bank_lending", memo="An attempt to lend what is not there")
    with pytest.raises((ledger.LedgerError, errors.Error)):
        ledger.transfer(db, payer=bank, receiver=treasury, amount=ledger.balance(db, bank) + 1,
                        kind="central_bank_lending", memo="A bank tries to print money for itself")
    assert ledger.amount_in_existence(db) == before


# ---------------------------------------------------------------------------
# 10. Insurance
# ---------------------------------------------------------------------------

def test_after_a_flood_insurers_pay_for_what_was_destroyed(db):
    _add_event(db, "flood", location=data.LAGOS, sales_bps=-600, damage_bps=100, mood_bps=-300, severe=True)
    assert quarters.close_due_quarters(db, after_quarters(1)) == [1]

    hit = _dicts(db, "SELECT c.name, c.sector, r.fixed_assets AS before, n.drivers, n.depreciation FROM companies c"
                     " JOIN company_results r ON r.company_id = c.id AND r.period = 0"
                     " JOIN company_results n ON n.company_id = c.id AND n.period = 1 WHERE c.headquarters = %s", (data.LAGOS,))
    destroyed = 0
    for company in hit:
        told = any("of its buildings and machines were destroyed" in note for note in company["drivers"]["notes"])
        # Banks and insurers hold little in buildings and are spared by a flood.
        assert told == (company["sector"] not in ("banking", "insurance")), company["name"]
        if told:
            destroyed += apply_bps(company["before"], 100)
    assert destroyed > 0
    # Insurers paid companies 70% of it, and a little to the households of the flooded city.
    paid = dict(db.execute(
        "SELECT CASE WHEN a.kind = 'company' THEN 'companies' ELSE 'households' END, sum(e.amount)::bigint"
        " FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " JOIN ledger_accounts a ON a.id = e.account_id WHERE t.kind = 'insurance_claim' AND e.amount > 0 GROUP BY 1").fetchall())
    assert abs(paid["companies"] - apply_bps(destroyed, data.INSURED_SHARE_BPS)) <= len(hit) * 4      # only rounding
    lagos = _dicts(db, "SELECT * FROM household_results WHERE period = 1 AND location = %s", (data.LAGOS,))[0]
    assert lagos["claims"] == paid["households"] > 0
    assert db.execute("SELECT sum(claims) FROM household_results WHERE period = 1 AND location <> %s", (data.LAGOS,)).fetchone()[0] == 0
    # The insurers' own accounts carry the cost, and say so.
    insurers = _dicts(db, "SELECT r.drivers, r.cost_of_sales FROM company_results r JOIN companies c ON c.id = r.company_id"
                          " WHERE c.sector = 'insurance' AND r.period = 1")
    assert all(any("in claims after this quarter's events" in note for note in i["drivers"]["notes"]) for i in insurers)
    # Paid from the insurers' own cash: no money was made.
    assert ledger.amount_in_existence(db) == money_accounted_for(db) and ledger.audit(db) == []
    # After a disaster, cover costs more.
    assert macro.state(db, 1)["premium_index_bps"] > BPS


def test_insurers_pay_only_what_they_can_afford(db):
    """A disaster too large for the insurers leaves them empty, not below zero, and makes no money."""
    _add_event(db, "flood", location=data.LAGOS, sales_bps=-600, damage_bps=5000, mood_bps=-300, severe=True)
    quarters.close_due_quarters(db, after_quarters(1))
    below = db.execute("SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset"
                       " WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id").fetchone()[0]
    assert below == 0
    assert ledger.amount_in_existence(db) == money_accounted_for(db) and ledger.audit(db) == []
    assert db.execute("SELECT count(*) FROM company_results WHERE period = 1 AND total_assets <> total_liabilities + total_equity").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# 11. The Central Bank's published rule
# ---------------------------------------------------------------------------

def test_the_central_bank_raises_its_rate_when_prices_run_hot_and_cuts_when_they_cool():
    target = data.INFLATION_TARGET_BPS
    up, why_up = macro.decide_rate(1300, target + 300)
    down, why_down = macro.decide_rate(1300, target - 300)
    held, why_held = macro.decide_rate(1300, target)
    assert up == 1300 + data.RATE_STEP_BPS and "raised its rate from 13% to 13.5%" in why_up and "above the 6% target" in why_up
    assert down == 1300 - data.RATE_STEP_BPS and "cut its rate from 13% to 12.5%" in why_down
    assert held == 1300 and "held its rate at 13%" in why_held
    # It moves in steps: however hot prices run, at most half a point a quarter.
    assert macro.decide_rate(1300, 4000)[0] == 1350
    # It never leaves its limits.
    assert macro.decide_rate(data.RATE_CEILING_BPS, 9000)[0] == data.RATE_CEILING_BPS
    assert macro.decide_rate(data.RATE_FLOOR_BPS, -3000)[0] == data.RATE_FLOOR_BPS
    # Spending running ahead of supply counts too, and so does a warning from the Money Watch.
    assert macro.decide_rate(1300, target, demand_gap_bps=400)[0] > 1300
    extra, why_extra = macro.decide_rate(1300, target, extra_bps=100)
    assert extra > 1300 and "Money Watch" in why_extra
    # It moves in quarter points.
    for inflation in range(-500, 3000, 137):
        assert macro.decide_rate(1325, inflation)[0] % 25 == 0


@pytest.mark.world("eight")
def test_each_quarters_rate_is_the_one_the_rule_set_and_the_reason_is_published(db):
    rows = _dicts(db, "SELECT * FROM economy_results ORDER BY period")
    assert [r["period"] for r in rows] == list(range(9))
    watch = {r["period"]: r["reading"] for r in _dicts(db, "SELECT period, reading FROM money_watch_results")}
    for before, now in zip(rows, rows[1:]):
        assert now["policy_rate_bps"] == before["next_policy_rate_bps"]         # the rate in force is the one announced
        expected, reason = macro.decide_rate(now["policy_rate_bps"], now["inflation_bps"],
                                             moneywatch.RATE_EXTRA_BPS[watch[now["period"]]], now["demand_gap_bps"])
        assert (now["next_policy_rate_bps"], now["rate_reason"]) == (expected, reason)
        assert data.RATE_FLOOR_BPS <= now["next_policy_rate_bps"] <= data.RATE_CEILING_BPS


# ---------------------------------------------------------------------------
# 12. Prices and inflation
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_a_price_level_is_measured_every_quarter(db):
    rows = {r["period"]: r for r in _dicts(db, "SELECT * FROM economy_results")}
    assert rows[0]["price_index_bps"] == BPS
    for period in range(1, 9):
        row = rows[period]
        assert row["price_index_bps"] > 0 and row["wage_index_bps"] >= rows[period - 1]["wage_index_bps"]      # wages do not fall
        assert row["household_spending"] == db.execute(
            "SELECT sum(spending) FROM household_results WHERE period = %s", (period,)).fetchone()[0]
        assert row["company_sales"] == db.execute(
            "SELECT sum(revenue) FROM company_results WHERE period = %s", (period,)).fetchone()[0]
        assert row["money"] > 0
    # Once there is a full year to look back on, inflation is simply this year's prices against last year's.
    for period in range(4, 9):
        assert rows[period]["inflation_bps"] == round((rows[period]["price_index_bps"] / rows[period - 4]["price_index_bps"] - 1) * BPS)


@pytest.mark.world("eight")
def test_prices_rise_faster_when_households_spend_more_than_the_economy_can_supply(db):
    """Two versions of the ninth quarter, the same in everything except what households spent."""
    usual = macro.state(db, 8)["household_spending"]
    results = {}
    for name, percent in (("calm", 100), ("hot", 120), ("cold", 80)):
        with db.transaction(force_rollback=True):
            results[name] = macro.close_quarter(
                db, 9, "x" * 32, company_sales=usual * 2, household_spending=usual * percent // 100, money=10**15,
                commodity_events={}, premium_index_bps=BPS, confidence_bps=BPS, rate_extra_bps=0)
    assert results["hot"]["price_index_bps"] > results["calm"]["price_index_bps"] > results["cold"]["price_index_bps"]
    assert results["hot"]["demand_gap_bps"] > results["calm"]["demand_gap_bps"] > results["cold"]["demand_gap_bps"]
    assert results["hot"]["next_policy_rate_bps"] >= results["calm"]["next_policy_rate_bps"] >= results["cold"]["next_policy_rate_bps"]
    assert results["hot"]["next_policy_rate_bps"] > results["cold"]["next_policy_rate_bps"]


@pytest.mark.world("eight")
def test_the_economys_records_cannot_be_rewritten(db):
    """Loophole question 6: nobody, not even the game's own code, can change what was recorded:
    past prices and rates, Money Watch readings, the events that happened, the news that was printed."""
    for table in ("economy_results", "money_watch_results", "events", "news_items"):
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] > 0
        with pytest.raises(errors.Error):
            db.execute(f"UPDATE {table} SET period = period")              # noqa: S608 (fixed names)
        with pytest.raises(errors.Error):
            db.execute(f"DELETE FROM {table}")                             # noqa: S608
        with pytest.raises(errors.Error):
            db.execute(f"TRUNCATE {table}")                                # noqa: S608


# ---------------------------------------------------------------------------
# 13. Commodity prices
# ---------------------------------------------------------------------------

def test_a_price_shock_moves_the_commodity_and_reaches_the_companies_that_buy_it(db):
    _add_event(db, "energy_price_jump", commodity="energy", price_bps=2500)
    quarters.close_due_quarters(db, after_quarters(1))
    state = macro.state(db, 1)
    assert state["energy_bps"] > 12_000                       # about a quarter dearer
    assert state["metals_bps"] < 11_000                       # the others only drift
    assert state["price_index_bps"] > BPS                     # and the general price level feels it
    # Next quarter, whoever buys from oil and gas companies pays more for the same supplies.
    dear = economy.relative_prices(state)
    assert dear["oil_gas"] > BPS and dear.get("telecoms", BPS) == BPS
    # A commodity drifts back towards the general price level when nothing new happens.
    assert set(data.COMMODITIES) == {"energy", "agriculture", "metals", "materials"}


def test_commodity_moves_in_one_quarter_are_bounded():
    wild = [{"commodity": "energy", "price_bps": 9000}, {"commodity": "energy", "price_bps": 9000},
            {"commodity": "metals", "price_bps": -9000}, {"commodity": None, "price_bps": 0}]
    assert events.commodity_moves(wild) == {"energy": 6000, "metals": -5000}


# ---------------------------------------------------------------------------
# 14. The ten mindsets
# ---------------------------------------------------------------------------

def test_there_are_ten_mindsets_and_each_location_has_its_own_mix(db):
    assert len(data.MINDSETS) == 10
    stored = _dicts(db, "SELECT location, mindset, share_bps FROM household_mindsets")
    assert len(stored) == 50
    by_place: dict = {}
    for row in stored:
        by_place.setdefault(row["location"], {})[row["mindset"]] = row["share_bps"]
    assert all(sum(mix.values()) == BPS and set(mix) == set(data.MINDSETS) for mix in by_place.values())
    assert len({tuple(sorted(mix.items())) for mix in by_place.values()}) == 5


def test_each_mindset_decides_differently():
    calm = mindsets.reactions(mindsets.Signals())
    shock = mindsets.reactions(mindsets.Signals(severe_local_event=True, jobs_change_bps=-500))
    boom = mindsets.reactions(mindsets.Signals(income_change_bps=600, national_spending_change_bps=500))
    dear = mindsets.reactions(mindsets.Signals(rate_above_neutral_bps=300, inflation_bps=1200))
    assert len(set(calm.values())) >= 6                              # even on a quiet day they do not agree
    assert calm["optimistic"][0] > 0 > calm["pessimistic"][0]
    assert calm["loyal"] == (0, 0) == shock["loyal"]                 # the loyal carry on
    assert shock["fearful"][0] < -500 and calm["fearful"][0] == 0    # the fearful panic, but only when there is cause
    assert shock["risk_averse"][0] < calm["risk_averse"][0]
    assert boom["herding"][0] > 0 > boom["contrarian"][0]            # one follows the crowd, the other goes against it
    assert dear["risk_averse"][0] < 0 and dear["opportunistic"] < calm["opportunistic"]
    assert calm["risk_seeking"][1] > calm["risk_averse"][1]          # and they differ in how readily they borrow
    late = mindsets.reactions(mindsets.Signals(earlier_income_change_bps=500))
    assert late["sceptical"][0] > calm["sceptical"][0]               # the sceptical wait a quarter before believing


def test_the_same_news_moves_two_cities_differently():
    mixes = {place: dict(zip(data.MINDSETS, (share * 100 for share in mix))) for place, mix in data.MINDSET_MIX.items()}
    signals = mindsets.Signals(severe_local_event=True, jobs_change_bps=-400, national_spending_change_bps=-300)
    lagos = mindsets.location_response(mixes[data.LAGOS], signals)
    kano = mindsets.location_response(mixes[data.KANO], signals)
    assert lagos["spend_bps"] != kano["spend_bps"] and lagos["borrow_bps"] != kano["borrow_bps"]
    assert kano["loyalty_bps"] > lagos["loyalty_bps"]                # Kano has more loyal shoppers
    assert lagos["moved_most_by"] in data.MINDSETS


@pytest.mark.world("eight")
def test_mindset_settings_are_not_sent_to_players(client, player):
    for path in ("/api/economy", "/api/companies", "/api/news"):
        text = client.get(path).text
        for hidden in ("mindset", "optimistic", "risk_averse", "fortune", "spend_from", "moved_most_by"):
            assert hidden not in text, (path, hidden)


# ---------------------------------------------------------------------------
# 15. Real causes of good and bad quarters
# ---------------------------------------------------------------------------

def test_an_event_is_a_named_cause_in_the_filings_of_the_companies_it_touches(db):
    idc = _dicts(db, "SELECT id, name FROM companies WHERE ticker = 'IDC'")[0]
    _add_event(db, "company_strike", company_id=idc["id"], location=data.LAGOS, sales_bps=-1500)
    _add_event(db, "drought", location=data.KANO, sales_bps=-1200, mood_bps=-200, commodity="agriculture", price_bps=1500)
    quarters.close_due_quarters(db, after_quarters(1))

    def why(ticker: str) -> list[str]:
        return db.execute("SELECT r.figures->'notes'->'why_revenue' FROM company_reports r JOIN companies c ON c.id = r.company_id"
                          " WHERE c.ticker = %s AND r.period = 1", (ticker,)).fetchone()[0]

    assert "A strike by its own staff cut its sales by about 15%" in why("IDC")
    # A local event hits the companies based there, and only the kinds of business it can touch.
    assert "Drought around Kano cut its sales by about 12%" in why("BHF")            # a Kano farm business
    assert not any("Drought" in reason for reason in why("KTX"))                      # a Kano textile maker
    assert not any("Drought" in reason or "strike" in reason for reason in why("OFF"))  # a Lagos farm business


def test_a_local_event_reaches_only_companies_based_there():
    flood = {"kind": "flood", "location": data.PORT_HARCOURT, "sector": None, "company_id": None,
             "sales_bps": -800, "cost_bps": 0, "damage_bps": 100}
    here = {"id": 1, "sector": "oil_gas", "headquarters": data.PORT_HARCOURT}
    elsewhere = {"id": 2, "sector": "oil_gas", "headquarters": data.LAGOS}
    bank_here = {"id": 3, "sector": "banking", "headquarters": data.PORT_HARCOURT}
    assert events.company_effects([flood], here) == {"sales_bps": 9200, "cost_bps": 0, "damage_bps": 100, "events": [flood]}
    for spared in (elsewhere, bank_here):
        assert events.company_effects([flood], spared)["events"] == []
    # Two blows in one quarter compound, and the damage is capped.
    assert events.company_effects([flood, flood], here)["sales_bps"] == 9200 * 9200 // BPS
    assert events.company_effects([{**flood, "damage_bps": 9000}], here)["damage_bps"] == 5000


def test_events_are_decided_by_the_worlds_secret_and_cannot_be_guessed_without_it(db):
    def decided(seed: str) -> list[tuple]:
        with db.transaction(force_rollback=True):
            return [(e["kind"], e["day"], e["location"], e["sector"], e["company_id"], e["sales_bps"], e["price_bps"])
                    for e in events.generate(db, 2, seed)]

    secret = "a-fixed-secret-so-that-every-test-run-repeats"
    assert decided(secret) == decided(secret)                              # the same secret always decides the same events
    worlds = {tuple(decided(f"another-secret-of-the-same-length-{n:012d}")) for n in range(6)}
    assert len(worlds) == 6 and tuple(decided(secret)) not in worlds      # and a different secret, different events
    assert db.execute("SELECT count(*) FROM events WHERE period = 2").fetchone()[0] == 0
    with pytest.raises(ValueError):
        events.generate(db, 2, "short")


@pytest.mark.world("eight")
def test_good_and_bad_quarters_both_happen(db):
    """The owner's rule: companies must not simply be in profit and having a good time."""
    assert db.execute("SELECT count(*) FROM events WHERE period <= 8").fetchone()[0] >= 12
    assert db.execute("SELECT count(DISTINCT kind) FROM events WHERE period <= 8").fetchone()[0] >= 8
    assert db.execute("SELECT count(*) FROM company_results WHERE period >= 1 AND net_profit < 0").fetchone()[0] >= 10
    ratings = {r for (r,) in db.execute("SELECT DISTINCT credit_rating FROM company_reports WHERE period = 8").fetchall()}
    assert ratings & {"CCC", "D"} and ratings & {"AAA", "AA", "A"}


# ---------------------------------------------------------------------------
# 16. The Money Watch
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_money_watch_takes_a_reading_every_quarter(db):
    rows = _dicts(db, "SELECT * FROM money_watch_results ORDER BY period")
    assert [r["period"] for r in rows] == list(range(1, 9))
    for r in rows:
        assert r["reading"] in ("green", "amber", "red") and r["reasons"] and r["action"]
        assert r["money"] == macro.state(db, r["period"])["money"]
        assert 9_990 <= sum(r["holders"].values()) <= BPS                 # where every naira sits, as shares of the whole


@pytest.mark.world("eight")
def test_the_money_watch_warns_when_money_outgrows_the_economy(db):
    money = ledger.amount_in_existence(db)

    def reading(money_growth, output_growth, inflation=600):
        with db.transaction(force_rollback=True):
            return moneywatch.measure(db, 9, money=money, money_growth_bps=money_growth, output_growth_bps=output_growth,
                                      inflation_bps=inflation)

    def money_reasons(result):
        return [r for r in result["reasons"] if "now hold" not in r]

    calm, amber, red = reading(700, 800), reading(1400, 800), reading(2600, 800)
    assert money_reasons(calm) in ([], ["Money is growing in step with the economy, and is not pooling in one place."])
    assert amber["reading"] == "amber" and amber["rate_extra_bps"] == 50 and "faster than the economy" in " ".join(amber["reasons"])
    assert red["reading"] == "red" and red["rate_extra_bps"] == 100 and "far too fast" in " ".join(red["reasons"])
    # On red, new lending is halved the following quarter.
    with db.transaction(force_rollback=True):
        moneywatch.measure(db, 9, money=money, money_growth_bps=2600, output_growth_bps=800)
        assert moneywatch.lending_factor_bps(db, 10) == 5000
    assert moneywatch.lending_factor_bps(db, 9) == BPS


@pytest.mark.world("eight")
def test_the_money_watch_does_not_mistake_a_slump_for_too_much_money(db):
    """Found by the independent review: when sales fell, the gap between money and sales opened
    by itself, the Watch read red, lending was halved, and the slump got deeper."""
    money = ledger.amount_in_existence(db)
    with db.transaction(force_rollback=True):
        slump = moneywatch.measure(db, 9, money=money, money_growth_bps=120, output_growth_bps=-2500, inflation_bps=-300)
    assert slump["rate_extra_bps"] == 0 or all("now hold" in r for r in slump["reasons"])
    assert not any("too fast" in r or "faster than the economy" in r for r in slump["reasons"])
    # And it does see too much money when the naira sales figures hide it: prices give it away.
    with db.transaction(force_rollback=True):
        hot = moneywatch.measure(db, 9, money=money, money_growth_bps=4000, output_growth_bps=4200, inflation_bps=1300)
        assert hot["reading"] == "amber" and "Prices rose 13%" in " ".join(hot["reasons"])
    with db.transaction(force_rollback=True):
        assert moneywatch.measure(db, 9, money=money, money_growth_bps=9000, output_growth_bps=9500, inflation_bps=4300)["reading"] == "red"


@pytest.mark.world("eight")
def test_an_account_that_gains_too_much_too_fast_is_listed_for_review_and_moves_nothing_else(db, client, player):
    """Loophole questions 2 and 3. If anybody ever finds a way to pour money into an account, it is
    seen. But the list is private and changes nothing: the review showed that two players passing
    money back and forth could otherwise turn the reading red and halve the country's lending."""
    account = db.execute("SELECT id FROM ledger_accounts WHERE kind = 'player'").fetchone()[0]
    treasury = ledger.account_id(db, ledger.TREASURY)
    money = ledger.amount_in_existence(db)
    limit = naira(data.MONEY_UNUSUAL_RECEIPT_NAIRA)

    # Passing the same naira back and forth a hundred times is not a gain.
    with db.transaction(force_rollback=True):
        for _ in range(101):
            ledger.transfer(db, payer=treasury, receiver=account, amount=naira(600_000), kind="test_wash", memo="Test: out")
            ledger.transfer(db, payer=account, receiver=treasury, amount=naira(600_000), kind="test_wash", memo="Test: and back")
        washed = moneywatch.measure(db, 9, money=money, money_growth_bps=0, output_growth_bps=0)
        assert washed["flagged"] == 0 and db.execute("SELECT count(*) FROM money_watch_flags").fetchone()[0] == 0

    # A real windfall is listed, even when the payment carries no quarter number.
    ledger.transfer(db, payer=treasury, receiver=account, amount=limit + 1, kind="test_windfall", memo="Test: a windfall")
    result = moneywatch.measure(db, 9, money=money, money_growth_bps=0, output_growth_bps=0)
    assert result["flagged"] == 1
    assert [f["account_id"] for f in _dicts(db, "SELECT * FROM money_watch_flags")] == [account]
    # The reading, the interest rate and lending are untouched, and nothing public mentions it.
    assert result["rate_extra_bps"] == 0 or all("now hold" in r for r in result["reasons"])
    assert not any("account" in r for r in result["reasons"])
    assert moneywatch.lending_factor_bps(db, 10) == BPS
    # It never takes the money away: that is for a person to decide.
    assert ledger.balance(db, account) > limit
    # The starting grant alone never raises a flag.
    assert naira(data.STARTING_GRANT_NAIRA) < limit
    assert "money_watch_flags" not in client.get("/api/economy").text and "review" not in client.get("/api/economy").text


# ---------------------------------------------------------------------------
# Found by the independent review of Part B. Each test is one of its attacks.
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_money_can_be_made_for_three_reasons_only_each_in_its_place(db):
    central = db.execute("SELECT id FROM ledger_accounts WHERE kind = 'central_bank'").fetchone()[0]
    household = db.execute("SELECT account_id FROM households LIMIT 1").fetchone()[0]
    before = ledger.amount_in_existence(db)
    # A share issue cannot make naira, and opening balances cannot be paid once the world is running.
    for reason in ("share_issue", "opening_balance", "gift", "bonus"):
        with pytest.raises(errors.Error) as refused:
            ledger.transfer(db, payer=central, receiver=household, amount=naira(10), kind=reason, memo="An attempt to make money")
        assert refused.value.diag.constraint_name == "ledger_issuance_reason", reason
    # Naira cannot be destroyed by paying it to the Central Bank, except as a bank's loan repayment.
    with pytest.raises(errors.Error) as refused:
        ledger.transfer(db, payer=household, receiver=central, amount=naira(10), kind="gift", memo="An attempt to destroy money")
    assert refused.value.diag.constraint_name == "ledger_destruction_reason"
    assert ledger.amount_in_existence(db) == before and ledger.audit(db) == []


@pytest.mark.world("eight")
def test_the_quarter_end_check_notices_money_that_no_loan_record_explains(db):
    assert ledger.audit(db) == []
    with db.transaction(force_rollback=True):
        db.execute("UPDATE company_debts SET principal_outstanding = principal_outstanding + 1 WHERE kind = 'central_bank_loan'"
                   " AND id = (SELECT id FROM company_debts WHERE kind = 'central_bank_loan' LIMIT 1)")
        if db.execute("SELECT count(*) FROM company_debts WHERE kind = 'central_bank_loan'").fetchone()[0]:
            assert ledger.audit(db) == ["The money in existence is not the opening money plus what banks owe the Central Bank."]


def test_the_central_bank_does_not_lend_to_a_bank_with_no_funds_of_its_own(db):
    world = economy.load_world(db)
    bank = _dicts(db, "SELECT c.id, c.name, c.account_id, r.total_equity, r.customer_funds FROM companies c"
                      " JOIN company_results r ON r.company_id = c.id AND r.period = 0 WHERE c.ticker = 'IKB'")[0]
    cash, money = ledger.balance(db, bank["account_id"]), ledger.amount_in_existence(db)

    banking.ensure_cash(db, world, {**bank, "total_equity": 0}, cash * 5, 1, 1300)
    banking.ensure_cash(db, world, {**bank, "total_equity": -naira(1_000_000)}, cash * 5, 1, 1300)
    assert ledger.amount_in_existence(db) == money                         # nothing lent

    banking.ensure_cash(db, world, {**bank, "total_equity": naira(1000)}, cash * 5, 1, 1300)
    assert ledger.amount_in_existence(db) - money == data.CENTRAL_BANK_LENDING_LIMIT_X * naira(1000)     # lent up to its limit
    banking.ensure_cash(db, world, {**bank, "total_equity": naira(1000)}, cash * 50, 1, 1450)
    assert ledger.amount_in_existence(db) - money == data.CENTRAL_BANK_LENDING_LIMIT_X * naira(1000)     # and no further
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


def test_draining_the_banks_does_not_print_money_without_end(db):
    """The review emptied every bank each quarter: the Central Bank refilled them without limit,
    money more than doubled and inflation reached 43%. Now a bank's own funds cap what it may borrow."""
    sink = ledger.account_id(db, ledger.TREASURY)
    start = ledger.amount_in_existence(db)
    for quarter in range(1, 7):
        for (account,) in db.execute("SELECT account_id FROM companies WHERE sector = 'banking'").fetchall():
            if ledger.balance(db, account) > 0:
                ledger.transfer(db, payer=account, receiver=sink, amount=ledger.balance(db, account), kind="test_theft",
                                memo="Test: a bank is emptied")
        assert quarters.close_due_quarters(db, after_quarters(quarter)) == [quarter]           # the calendar never stops
    equity = db.execute("SELECT sum(greatest(r.total_equity, 0)) FROM company_results r JOIN companies c ON c.id = r.company_id"
                        " WHERE c.sector = 'banking' AND r.period = 0").fetchone()[0]
    assert ledger.amount_in_existence(db) - start <= data.CENTRAL_BANK_LENDING_LIMIT_X * equity
    assert ledger.amount_in_existence(db) == money_accounted_for(db) and ledger.audit(db) == []
    assert db.execute("SELECT count(*) FROM company_results WHERE total_assets <> total_liabilities + total_equity").fetchone()[0] == 0
    assert macro.state(db, 6)["inflation_bps"] < 2000


def test_an_event_of_an_unknown_kind_cannot_be_stored(db):
    """One stored row of a kind the game does not know would have stopped every later quarter from closing."""
    with pytest.raises(errors.CheckViolation):
        db.execute("INSERT INTO events (period, day, kind) VALUES (1, 5, 'meteor')")
    stored = db.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'events_kind_check'").fetchone()[0]
    assert all(f"'{kind.name}'" in stored for kind in events.KINDS)


@pytest.mark.world("eight")
def test_the_money_page_has_no_line_that_is_the_players_money_alone(db, client, player):
    body = client.get("/api/economy").json()
    lines = {m["holder"]: int(m["amount_kobo"]) for m in body["money"]}
    assert "Players" not in lines and "Other" not in lines
    mine = int(client.get("/api/me").json()["cash"]["amount_kobo"])
    assert mine not in lines.values()
    assert sum(lines.values()) == int(body["money_in_existence_kobo"])       # and still every naira is on the page


@pytest.mark.world("eight")
def test_the_economy_page_shows_prices_rates_commodities_and_the_money_watch(client, player):
    body = client.get("/api/economy").json()
    prices, watch = body["prices"], body["money_watch"]
    assert prices["inflation_target_bps"] == 600 and (prices["inflation_low_bps"], prices["inflation_high_bps"]) == (300, 900)
    assert prices["household_loan_rate_bps"] == prices["policy_rate_bps"] + data.HOUSEHOLD_LOAN_SPREAD_BPS
    assert prices["rate_reason"].endswith(".") and "Central Bank" in prices["rate_reason"]
    assert [c["name"] for c in prices["commodities"]] == ["Energy (oil, gas, fuel)", "Farm produce", "Metals", "Building materials"]
    assert int(prices["household_debt_kobo"]) > 0
    assert watch["reading"] in ("green", "amber", "red") and watch["reasons"] and watch["action"]
    assert len(body["macro_history"]) == 8 and body["macro_history"][-1]["period"] == 8
    assert all({"claims_kobo", "debt_kobo"} <= set(h) for h in body["households"])
    # With one player, nothing on the page says what players hold between them.
    assert "Players" not in {m["holder"] for m in body["money"]}
    assert not any(reason.startswith("Players ") for reason in watch["reasons"])
    assert client.get("/api/economy").status_code == 200
    client.cookies.clear()
    assert client.get("/api/economy").status_code == 401


# ---------------------------------------------------------------------------
# The stage test: five game years with inflation in its band, and twenty without the
# economy seizing up, every balance sheet balancing, no naira without a recorded payer.
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_twenty_game_years_run_and_inflation_stays_in_its_band_for_the_first_five(db):
    assert quarters.close_due_quarters(db, after_quarters(80)) == list(range(9, 81))
    rows = _dicts(db, "SELECT * FROM economy_results WHERE period >= 1 ORDER BY period")
    low, high = data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS, data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS

    # Five game years: inflation inside the Central Bank's band in every quarter.
    assert all(low <= r["inflation_bps"] <= high for r in rows[:20]), [r["inflation_bps"] for r in rows[:20]]
    # Twenty game years: no impossible values anywhere.
    for r in rows:
        assert -200 <= r["inflation_bps"] <= 1500, (r["period"], r["inflation_bps"])
        assert data.RATE_FLOOR_BPS <= r["policy_rate_bps"] <= data.RATE_CEILING_BPS
        assert all(r[c] > 0 for c in ("price_index_bps", "wage_index_bps", "energy_bps", "metals_bps", "agriculture_bps",
                                      "materials_bps", "company_sales", "household_spending", "money"))
    # The economy never seized up: sales never fell by a tenth in a quarter, and it is larger at the end.
    sales = [r["company_sales"] for r in rows[1:]]
    assert all(now > before * 90 // 100 for before, now in zip(sales, sales[1:]))
    assert sales[-1] > sales[0]
    jobs = [j for (j,) in db.execute("SELECT sum(jobs) FROM household_results WHERE period >= 1 GROUP BY period ORDER BY period").fetchall()]
    assert min(jobs) > jobs[0] * 80 // 100
    # Every balance sheet balances, in every quarter, for every company.
    assert db.execute("SELECT count(*) FROM company_results r JOIN companies c ON c.id = r.company_id WHERE c.listed").fetchone()[0] == 50 * 81
    assert db.execute("SELECT count(*) FROM company_results WHERE total_assets <> total_liabilities + total_equity").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM company_results WHERE cash < 0 OR staff < 0 OR revenue < 0").fetchone()[0] == 0
    # No naira without a recorded payer: every transaction adds up to zero, nobody but the
    # Central Bank is below zero, and all money is the opening money plus the banks' borrowing from it.
    assert ledger.audit(db) == []
    assert db.execute("SELECT count(*) FROM ledger_balances b JOIN assets a ON a.code = b.asset"
                      " WHERE b.balance < 0 AND b.account_id <> a.issuer_account_id").fetchone()[0] == 0
    assert ledger.amount_in_existence(db) == money_accounted_for(db)
    assert db.execute("SELECT count(*) FROM company_results WHERE drivers::text LIKE '%outside its normal business%'").fetchone()[0] == 0
    # The Money Watch never reached red by itself.
    assert db.execute("SELECT count(*) FROM money_watch_results WHERE reading = 'red'").fetchone()[0] == 0
    # Households did not run out of money, and did not drown in debt.
    last = _dicts(db, "SELECT sum(cash) AS cash, sum(debt) AS debt, sum(income) AS income FROM household_results WHERE period = 80")[0]
    assert last["cash"] > 0 and last["debt"] < 6 * last["income"]
