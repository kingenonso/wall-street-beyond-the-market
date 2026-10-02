"""Stage 3, Part A: households, wages, spending, companies buying from each
other, rivalry, head offices, pension saving, and money that keeps circulating.

The numbers before each group of tests are the items of the approved checklist.
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import economy, genesis, ledger, quarters
from simulation import world_data as data
from simulation.money import BPS, apply_bps, million_naira, naira
from tests.conftest import after_quarters


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


# --- 1. Households exist ---

def test_each_of_the_five_locations_has_its_households_with_their_own_savings(db):
    rows = _dicts(db, "SELECT h.location, l.population_bps, a.name, a.id FROM households h"
                      " JOIN locations l ON l.name = h.location JOIN ledger_accounts a ON a.id = h.account_id")
    assert {r["location"] for r in rows} == {"Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"}
    assert sum(r["population_bps"] for r in rows) == 10_000
    savings = million_naira(data.HOUSEHOLDS_OPENING_M)
    for r in rows:
        assert r["name"] == f"Households of {r['location']}"
        assert ledger.balance(db, r["id"]) == apply_bps(savings, r["population_bps"])     # shared out by population


def test_the_single_stand_in_account_for_the_public_is_gone(db):
    assert db.execute("SELECT count(*) FROM ledger_accounts WHERE code = 'public'").fetchone()[0] == 0


# --- 2. Wages and jobs ---

@pytest.mark.world("eight")
def test_every_company_pays_wages_every_quarter_to_households(db):
    paid = db.execute(
        "SELECT count(DISTINCT (e.account_id, t.period)) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " JOIN companies c ON c.account_id = e.account_id WHERE t.kind = 'wages' AND e.amount < 0 AND t.period BETWEEN 1 AND 8"
    ).fetchone()[0]
    assert paid >= 50 * 8 - 20            # all but the few quarters in which a failing company had no cash at all
    # Wages go to households and to the pension funds, and to nobody else.
    receivers = {r[0] for r in db.execute(
        "SELECT DISTINCT a.code FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " JOIN ledger_accounts a ON a.id = e.account_id WHERE t.kind = 'wages' AND e.amount > 0").fetchall()}
    assert receivers == {"households:lagos", "households:abuja", "households:port harcourt", "households:aba",
                         "households:kano", "investors:institutions"}
    assert db.execute("SELECT min(staff) FROM company_results").fetchone()[0] >= 1


@pytest.mark.world("eight")
def test_a_company_in_trouble_cuts_jobs_and_a_growing_one_hires(db):
    notes = [n for (d,) in db.execute("SELECT drivers FROM company_results WHERE period >= 2").fetchall() for n in d["notes"]]
    assert any(n.startswith("It cut about") for n in notes)
    assert any(n.startswith("It took on about") for n in notes)
    # Bonny Tide Shipping begins in default and loses money: it employs fewer people after eight quarters.
    first, last = (db.execute(
        "SELECT r.staff FROM company_results r JOIN companies c ON c.id = r.company_id WHERE c.ticker = 'BTS' AND r.period = %s",
        (p,)).fetchone()[0] for p in (0, 8))
    assert last < first


@pytest.mark.world("eight")
def test_half_of_a_companys_pay_goes_to_its_head_office_location(db):
    account = db.execute("SELECT account_id FROM companies WHERE ticker = 'IDC'").fetchone()[0]      # based in Lagos
    legs = dict(db.execute(
        "SELECT a.code, sum(e.amount) FROM ledger_entries e JOIN ledger_accounts a ON a.id = e.account_id"
        " WHERE e.amount > 0 AND a.code LIKE 'households:%%' AND e.transaction_id IN ("
        "   SELECT t.id FROM ledger_transactions t JOIN ledger_entries p ON p.transaction_id = t.id"
        "   WHERE t.kind = 'wages' AND p.account_id = %s AND p.amount < 0) GROUP BY a.code", (account,)).fetchall())
    total = sum(legs.values())
    # Half to Lagos as its home, plus Lagos's 35% share of the other half: 67.5%.
    assert abs(legs["households:lagos"] * 1000 // total - 675) <= 2
    assert abs(legs["households:kano"] * 1000 // total - 100) <= 2          # Kano: 20% of the other half


# --- 3. Spending ---

@pytest.mark.world("eight")
def test_households_spend_from_what_they_earned_last_quarter_and_never_more_than_they_have(db):
    habits = {r["location"]: r for r in _dicts(db, "SELECT * FROM households")}
    rows = _dicts(db, "SELECT * FROM household_results ORDER BY location, period")
    by = {(r["location"], r["period"]): r for r in rows}
    for (location, period), r in by.items():
        if period == 0:
            continue
        before = by[(location, period - 1)]
        planned = (apply_bps(before["income"], habits[location]["spend_from_income_bps"])
                   + apply_bps(before["cash"], habits[location]["spend_from_savings_bps"]))
        assert 0 < r["spending"] <= before["cash"]
        assert planned - 1_000_000 <= r["spending"] <= planned      # the plan, less a few kobo lost to rounding when it is shared out
        assert r["income"] == r["wages"] + r["government"] + r["pensions"]


@pytest.mark.world("eight")
def test_household_spending_reaches_only_companies(db):
    receivers = {r[0] for r in db.execute(
        "SELECT DISTINCT a.kind FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " JOIN ledger_accounts a ON a.id = e.account_id WHERE t.kind = 'customer_revenue' AND e.amount > 0").fetchall()}
    assert receivers == {"company"}


def test_when_jobs_are_lost_in_a_location_its_households_spend_less_the_next_quarter(db):
    """Take a quarter's pay away from Kano's households and they spend less the quarter after."""
    quarters.close_due_quarters(db, after_quarters(2))
    normal = db.execute("SELECT spending FROM household_results WHERE location = 'Kano' AND period = 2").fetchone()[0]
    kano = ledger.account_id(db, "households:kano")
    ledger.transfer(db, payer=kano, receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=ledger.balance(db, kano) * 9 // 10, kind="test_drain", memo="Test: Kano loses its savings")
    quarters.close_due_quarters(db, after_quarters(3))
    poorer = db.execute("SELECT spending FROM household_results WHERE location = 'Kano' AND period = 3").fetchone()[0]
    assert poorer < normal * 99 // 100


# --- 4. Companies buy from each other ---

@pytest.mark.world("eight")
def test_companies_buy_from_other_companies(db):
    kinds = {r[0] for r in db.execute(
        "SELECT DISTINCT a.kind FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " JOIN ledger_accounts a ON a.id = e.account_id WHERE t.kind = 'business_purchase'").fetchall()}
    assert kinds == {"company"}                       # buyer and seller are both companies
    # Nobody buys from itself.
    assert db.execute(
        "SELECT count(*) FROM (SELECT transaction_id, account_id FROM ledger_entries e JOIN ledger_transactions t"
        " ON t.id = e.transaction_id WHERE t.kind = 'business_purchase' GROUP BY 1, 2 HAVING count(*) > 1) x").fetchone()[0] == 0


@pytest.mark.world("eight")
def test_builders_buy_cement_and_power_companies_buy_gas(db):
    def bought(buyer_sector: str, seller_sector: str) -> int:
        return db.execute(
            "SELECT coalesce(sum(r.amount), 0) FROM ledger_transactions t"
            " JOIN ledger_entries p ON p.transaction_id = t.id AND p.amount < 0 JOIN companies b ON b.account_id = p.account_id"
            " JOIN ledger_entries r ON r.transaction_id = t.id AND r.amount > 0 JOIN companies s ON s.account_id = r.account_id"
            " WHERE t.kind = 'business_purchase' AND b.sector = %s AND s.sector = %s", (buyer_sector, seller_sector)).fetchone()[0]
    assert bought("real_estate", "cement") > 0 and bought("power", "oil_gas") > 0
    assert bought("cement", "real_estate") == 0       # cement makers do not buy buildings as supplies
    assert bought("real_estate", "cement") > bought("real_estate", "power")


@pytest.mark.world("eight")
def test_a_companys_sales_are_what_households_companies_and_government_paid_it(db):
    for r in _dicts(db, "SELECT * FROM company_results WHERE period >= 1"):
        assert r["revenue"] == r["sales_households"] + r["sales_business"] + r["sales_government"]
    totals = db.execute("SELECT sum(sales_households), sum(sales_business), sum(sales_government) FROM company_results"
                        " WHERE period = 8").fetchone()
    assert all(t > 0 for t in totals)


# --- 5. Rivals compete ---

def _world_with(companies: list[dict]) -> economy.World:
    return economy.World(treasury=None, founders=None, institutions=None, small_investors=None, locations=[],
                         households={}, demand={}, inputs={}, seasons={}, members={"cement": companies})


def test_what_one_company_gains_its_rivals_lose():
    rivals = [{"account_id": "a", "headquarters": "Lagos", "pull": 100}, {"account_id": "b", "headquarters": "Abuja", "pull": 100}]
    even = economy.allocate(_world_with(rivals), 1_000_000, {"cement": 1})
    rivals[0]["pull"] = 150
    after = economy.allocate(_world_with(rivals), 1_000_000, {"cement": 1})
    assert even == {"a": 500_000, "b": 500_000}
    assert after["a"] > even["a"] and after["b"] < even["b"]
    assert after["a"] + after["b"] == 1_000_000                 # the customers' spending is the same; it has only moved


def test_sharing_out_never_hands_out_more_than_there_is():
    for amount in (1, 7, 999, 10**15 + 7):
        shares = economy.split(amount, {"a": 3, "b": 3, "c": 1})
        assert sum(shares.values()) <= amount and all(v >= 0 for v in shares.values())
    assert economy.split(0, {"a": 1}) == {} and economy.split(100, {}) == {} and economy.split(-5, {"a": 1}) == {}


@pytest.mark.world("eight")
def test_companies_in_one_sector_take_different_shares_that_shift_over_time(db):
    def shares(period: int) -> dict:
        rows = db.execute(
            "SELECT c.ticker, r.sales_households FROM company_results r JOIN companies c ON c.id = r.company_id"
            " WHERE c.sector = 'consumer' AND r.period = %s", (period,)).fetchall()
        total = sum(v for _, v in rows)
        return {ticker: value * 10_000 // total for ticker, value in rows}
    early, late = shares(1), shares(8)
    assert abs(sum(early.values()) - 10_000) <= 6 and abs(sum(late.values()) - 10_000) <= 6
    assert any(late[t] > early[t] + 20 for t in early) and any(late[t] < early[t] - 20 for t in early)


# --- 6. Head offices matter ---

def test_the_same_company_costs_less_to_run_in_kano_than_in_lagos():
    sector = next(s for s in data.SECTORS if s.code == "agriculture")
    lagos = genesis._company_shape(0, data.Company("AAA", "Test Farms", "agriculture", data.LAGOS, 100_000), sector)
    kano = genesis._company_shape(0, data.Company("AAA", "Test Farms", "agriculture", data.KANO, 100_000), sector)
    assert kano["base_opex"] < lagos["base_opex"]
    assert lagos["location_cost_bps"] == 11_000                  # Lagos rents and wages
    assert kano["location_cost_bps"] == 8_500 - 600              # cheaper, and farming suits Kano
    assert kano["base_revenue"] == lagos["base_revenue"]         # same business, different place


def test_buyers_favour_companies_based_in_their_own_location():
    rivals = [{"account_id": "lagos-co", "headquarters": "Lagos", "pull": 100},
              {"account_id": "kano-co", "headquarters": "Kano", "pull": 100}]
    from_kano = economy.allocate(_world_with(rivals), 1_000_000, {"cement": 1}, location="Kano")
    from_lagos = economy.allocate(_world_with(rivals), 1_000_000, {"cement": 1}, location="Lagos")
    assert from_kano["kano-co"] > from_kano["lagos-co"] and from_lagos["lagos-co"] > from_lagos["kano-co"]


@pytest.mark.world("eight")
def test_every_location_has_jobs_and_lagos_has_the_most(db):
    jobs = dict(db.execute("SELECT location, jobs FROM household_results WHERE period = 8").fetchall())
    assert all(count > 0 for count in jobs.values())
    assert max(jobs, key=jobs.get) == "Lagos"
    assert sum(jobs.values()) <= db.execute("SELECT sum(staff) FROM company_results WHERE period = 8").fetchone()[0]


# --- 7. Pension saving ---

@pytest.mark.world("eight")
def test_part_of_every_wage_goes_into_the_pension_funds_with_the_employer_adding_more(db):
    funds = ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)
    for r in _dicts(db, "SELECT r.wages, r.operating_expenses, r.payables, c.account_id, c.name FROM company_results r"
                        " JOIN companies c ON c.id = r.company_id WHERE r.period = 8 AND r.payables = 0"):
        saved = db.execute(
            "SELECT coalesce(sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " WHERE t.kind = 'wages' AND t.period = 8 AND e.account_id = %s AND e.transaction_id IN"
            " (SELECT transaction_id FROM ledger_entries WHERE account_id = %s AND amount < 0)", (funds, r["account_id"])).fetchone()[0]
        # 8% taken from the wage and 10% added by the employer: 18% of the wage.
        expected = apply_bps(r["wages"], data.PENSION_EMPLOYEE_BPS + data.PENSION_EMPLOYER_BPS)
        assert abs(saved - expected) <= 2, r["name"]
        assert abs(r["operating_expenses"] - apply_bps(r["wages"], BPS + data.PENSION_EMPLOYER_BPS)) <= 6, r["name"]


@pytest.mark.world("eight")
def test_pension_funds_pay_pensions_to_households_every_quarter(db):
    for period, paid in db.execute("SELECT period, sum(pensions) FROM household_results WHERE period >= 1 GROUP BY period").fetchall():
        assert paid > 0, period
    # They pay out of what they hold: never more.
    assert ledger.balance(db, ledger.account_id(db, ledger.INVESTORS_INSTITUTIONS)) >= 0


# --- 8. Money keeps circulating ---

@pytest.mark.world("eight")
def test_no_money_is_made_or_lost_and_the_whole_ledger_agrees(db):
    opening = db.execute(
        "SELECT sum(e.amount) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
        " WHERE t.kind = 'opening_balance' AND e.amount > 0").fetchone()[0]
    assert ledger.amount_in_existence(db) == opening
    assert ledger.audit(db) == []


@pytest.mark.world("eight")
def test_the_government_spends_exactly_the_tax_it_collected_and_keeps_its_reserve(db):
    treasury = ledger.account_id(db, ledger.TREASURY)
    for period in range(1, 9):
        collected = ledger.received_in_period(db, treasury, period, kinds=("company_tax",))
        spent = db.execute(
            "SELECT coalesce(-sum(e.amount), 0) FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
            " WHERE e.account_id = %s AND e.amount < 0 AND t.period = %s"
            " AND t.kind IN ('government_purchase', 'government_wages')", (treasury, period)).fetchone()[0]
        assert collected - 100 <= spent <= collected
    assert ledger.balance(db, treasury) >= million_naira(data.TREASURY_OPENING_M)


def test_money_does_not_pile_up_in_one_place_over_twenty_quarters(db):
    """The Stage 2 fault: money pooled in companies and banks until customers ran dry at about quarter 29."""
    def held() -> dict:
        return dict(db.execute(
            "SELECT CASE WHEN a.code LIKE 'households:%' THEN 'households' WHEN a.kind = 'company' THEN 'companies'"
            " ELSE 'others' END, sum(b.balance) FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
            " WHERE b.asset = 'NGN' AND b.balance > 0 GROUP BY 1").fetchall())
    start = held()
    assert quarters.close_due_quarters(db, after_quarters(20)) == list(range(1, 21))
    end = held()
    assert end["households"] > start["households"] * 85 // 100          # households keep their savings
    assert end["companies"] < start["companies"] * 150 // 100           # companies have not swallowed the money
    sales = [s for (s,) in db.execute("SELECT sum(revenue) FROM company_results WHERE period >= 2 GROUP BY period ORDER BY period").fetchall()]
    assert min(sales) > max(sales) * 80 // 100                          # no slump: sales stay within a fifth of their best
    spending = [s for (s,) in db.execute("SELECT sum(spending) FROM household_results WHERE period >= 2 GROUP BY period ORDER BY period").fetchall()]
    assert min(spending) > max(spending) * 80 // 100
    assert ledger.audit(db) == []


@pytest.mark.world("eight")
def test_a_sound_borrowers_debt_is_renewed_and_a_failing_ones_is_not(db):
    sound = db.execute("SELECT min(d.maturity_period) FROM company_debts d JOIN companies c ON c.id = d.company_id"
                       " WHERE c.ticker = 'IDC' AND d.kind = 'bank_loan'").fetchone()[0]
    failing = db.execute("SELECT max(d.maturity_period) FROM company_debts d JOIN companies c ON c.id = d.company_id"
                         " WHERE c.ticker = 'BTS' AND d.kind = 'bank_loan'").fetchone()[0]
    assert sound > data.LOAN_TERM_QUARTERS and failing == data.LOAN_TERM_QUARTERS


# --- A world from before households existed ---

@pytest.mark.world("empty")
def test_a_world_made_before_households_existed_is_refused_clearly(db):
    with pytest.raises(economy.WorldTooOld):
        economy.load_world(db)


# --- What players are shown ---

@pytest.mark.world("eight")
def test_the_economy_page_reports_households_money_and_history(client, player):
    body = client.get("/api/economy").json()
    assert body["period"] == 8 and body["period_label"] == "Year 2 Q4"
    assert [h["location"] for h in body["households"]] == ["Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"]
    lagos = body["households"][0]
    assert int(lagos["income_kobo"]) == int(lagos["wages_kobo"]) + int(lagos["government_kobo"]) + int(lagos["pensions_kobo"])
    assert len(body["history"]) == 8 and body["history"][-1]["period"] == 8
    # Every naira is somewhere, and the holders add up to all the money there is.
    assert sum(int(m["amount_kobo"]) for m in body["money"]) == int(body["money_in_existence_kobo"])
    assert {m["holder"] for m in body["money"]} >= {"Households", "Companies", "Banks and insurers", "Pension funds", "Players"}
    assert abs(sum(s["share_bps"] for s in body["household_spending"]) - 10_000) <= 12


@pytest.mark.world("eight")
def test_a_company_page_shows_its_people_its_place_its_customers_and_its_suppliers(client, player):
    body = client.get("/api/companies/KTX").json()
    notes = body["reports"][-1]["figures"]["notes"]
    assert isinstance(notes["staff"], int) and notes["staff"] > 0
    assert int(notes["wages"]) > 0
    assert set(notes["sales_to"]) == {"households", "other_companies", "government"}
    assert body["location"]["running_cost_bps"] == 8_500 - 200
    assert any("Kano" in reason for reason in body["location"]["reasons"])
    assert body["buys_from"][0]["sector"] == "Power and utilities"


def test_the_economy_page_needs_a_login_and_works_before_the_first_quarter(client):
    assert client.get("/api/economy").status_code == 401


def test_the_economy_page_before_any_quarter_has_closed(client, player):
    body = client.get("/api/economy").json()
    assert body["period"] == 0 and body["history"] == [] and len(body["households"]) == 5


@pytest.mark.world("eight")
def test_how_households_decide_what_to_spend_is_never_sent_to_players(client, player):
    text = client.get("/api/economy").text + client.get("/api/companies/KTX").text
    for hidden in ("spend_from", "fortune", "volatility", '"pull"', "base_revenue", "opex_bps", "labour_bps"):
        assert hidden not in text
