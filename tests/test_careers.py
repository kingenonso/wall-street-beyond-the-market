"""Stage 5: players as professionals.

A player chooses a build, is hired, is paid a salary by their employer out of the employer's
own cash, chooses a bank and saves for retirement. Nothing here makes money.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import careers, clock, ledger, objectives, quarters
from simulation import world_data as data
from simulation.money import BPS, apply_bps, naira
from tests.conftest import TEST_DATABASE_URL, after_quarters, money_accounted_for
from tests.test_market import trader

OPEN = datetime.fromisoformat("2026-10-06T13:00:00+01:00")           # the second day of the first quarter
NOW9 = after_quarters(8) + timedelta(hours=12)                        # the ninth quarter has just begun


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def professional(db, name="ada", *, build="asset_manager", employer="IKB", bank="IKB", now=OPEN, cash_naira=0):
    """A player with a build, a bank and a job. Returns (player id, account)."""
    account = trader(db, name, cash_naira=cash_naira)
    player = _dicts(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))[0]["player_id"]
    careers.choose_build(db, player, build, now)
    if bank:
        careers.choose_bank(db, player, bank, now)
    if employer:
        careers.take_job(db, player, employer, now)
    return player, account


def sound(db) -> None:
    assert ledger.audit(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


def pass_one(db, player, now) -> dict:
    """Finish one real piece of accountancy work correctly."""
    taken = objectives.accept(db, player, "ac_ratios", now)
    row = _dicts(db, "SELECT terms FROM objectives WHERE id = %s", (taken["id"],))[0]["terms"]
    figures = _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s ORDER BY version DESC LIMIT 1",
                     (row["company_id"], row["filed_period"]))[0]["figures"]
    income, sheet = figures["income_statement"], figures["balance_sheet"]
    ebitda = income["operating_profit"] + income["depreciation"]
    return objectives.submit(db, player, taken["id"], {
        "ebitda": ebitda / 1e8, "margin": income["net_profit"] / income["revenue"] * 100,
        "debt_to_ebitda": sheet["borrowings"] / (4 * ebitda), "interest_cover": income["operating_profit"] / income["interest_expense"],
    }, now)


# ---------------------------------------------------------------------------
# Levels and pay
# ---------------------------------------------------------------------------

def test_the_salary_scale_matches_the_design_document():
    for level, monthly in data.SALARY_PER_MONTH_NAIRA:
        assert careers.salary_per_quarter(level) == naira(monthly * 3)
    # Pay rises with every level, and keeps pace with wages in the economy.
    scale = [careers.salary_per_quarter(level) for level in range(1, 101)]
    assert scale == sorted(scale) and len(set(scale)) == 100
    assert careers.salary_per_quarter(1, 12_000) == naira(900_000) * 12 // 10


def test_about_forty_percent_is_taken_and_every_kobo_is_accounted_for():
    for level in (1, 7, 20, 55, 100):
        pay = careers.split_salary(careers.salary_per_quarter(level))
        assert pay["pension_yours"] + pay["tax"] + pay["living_costs"] + pay["take_home"] == pay["gross"]
        taken = pay["gross"] - pay["take_home"]
        assert taken * BPS // pay["gross"] == 4000


def test_levels_come_from_experience_and_stop_at_twenty_until_rank_cases_exist():
    # Levels 1-10 come twice as fast since the redesign (owner, 12 October 2026): Level 2 needs 30, not 60.
    assert careers.level_for(0) == 1 and careers.level_for(29) == 1 and careers.level_for(30) == 2
    assert careers.level_for(careers.experience_for(20)) == 20
    assert careers.level_for(10 ** 9) == data.LEVEL_CAP == 20
    for level in range(1, 20):
        assert careers.experience_for(level + 1) > careers.experience_for(level)


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def test_only_the_six_starting_builds_can_be_chosen(db):
    account = trader(db, "ada")
    player = _dicts(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))[0]["player_id"]
    for build in ("ceo", "head", "", "Accountant"):
        with pytest.raises(careers.CareerError):
            careers.choose_build(db, player, build, OPEN)
    careers.choose_build(db, player, "asset_manager", OPEN)
    assert careers.career(db, player)["level"] == 1
    # The database itself refuses any other build.
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE players SET build = 'ceo' WHERE id = %s", (player,))


def test_a_build_can_be_changed_once_in_a_real_month_and_each_keeps_its_own_level(db):
    player, _ = professional(db)
    quarters.close_due_quarters(db, OPEN + timedelta(days=29))
    with pytest.raises(careers.CareerError, match="once in a real month"):
        careers.choose_build(db, player, "risk_manager", OPEN + timedelta(days=29))
    careers.add_experience(db, player, "asset_manager", 200, OPEN)
    later = OPEN + timedelta(days=31)
    quarters.close_due_quarters(db, later)
    careers.choose_build(db, player, "risk_manager", later)
    assert careers.career(db, player, "risk_manager")["level"] == 1 and careers.current_job(db, player) is None      # changing build leaves the job
    quarters.close_due_quarters(db, later + timedelta(days=31))
    careers.choose_build(db, player, "asset_manager", later + timedelta(days=31))
    assert careers.career(db, player)["level"] == careers.level_for(200) > 1


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def test_an_employer_needs_to_know_where_to_pay_and_must_hire_that_build(db):
    player, _ = professional(db, build="asset_manager", employer=None, bank=None)
    with pytest.raises(careers.CareerError, match="bank first"):
        careers.take_job(db, player, "IKB", OPEN)
    careers.choose_bank(db, player, "IKB", OPEN)
    with pytest.raises(careers.CareerError, match="does not hire"):
        careers.take_job(db, player, "IDC", OPEN)                       # a cement company runs no investment desk
    assert careers.take_job(db, player, "AGA", OPEN)["ticker"] == "AGA"   # an insurer does
    tickers = {o["ticker"] for o in careers.openings(db, player, OPEN)}
    assert "IDC" not in tickers and {"IKB", "AGA"} <= tickers


def test_a_company_has_only_so_many_places(db):
    places = max(_dicts(db, "SELECT r.staff FROM company_results r JOIN companies c ON c.id = r.company_id"
                            " WHERE c.ticker = 'SCM' ORDER BY r.period DESC LIMIT 1")[0]["staff"] // data.STAFF_PER_OPENING, 1)
    for n in range(places):
        professional(db, f"player{n}", build="asset_manager", employer="SCM")
    late, _ = professional(db, "late", build="asset_manager", employer=None)
    with pytest.raises(careers.CareerError, match="no place open"):
        careers.take_job(db, late, "SCM", OPEN)
    assert next(o for o in careers.openings(db, late, OPEN) if o["ticker"] == "SCM")["places_left"] == 0


def test_two_people_cannot_take_the_last_place_at_the_same_moment(db):
    places = max(_dicts(db, "SELECT r.staff FROM company_results r JOIN companies c ON c.id = r.company_id"
                            " WHERE c.ticker = 'SCM' ORDER BY r.period DESC LIMIT 1")[0]["staff"] // data.STAFF_PER_OPENING, 1)
    for n in range(places - 1):
        professional(db, f"player{n}", build="asset_manager", employer="SCM")
    rivals = [professional(db, f"rival{n}", build="asset_manager", employer=None)[0] for n in range(6)]
    outcomes = []

    def apply(player):
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            try:
                careers.take_job(conn, player, "SCM", OPEN)
                outcomes.append("hired")
            except careers.CareerError:
                outcomes.append("refused")

    threads = [threading.Thread(target=apply, args=(p,)) for p in rivals]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("hired") == 1 and outcomes.count("refused") == 5


def test_nobody_can_hop_between_employers_within_a_quarter(db):
    player, _ = professional(db)
    with pytest.raises(careers.CareerError, match="after the quarter ends"):
        careers.take_job(db, player, "OTB", OPEN + timedelta(hours=1))
    careers.leave_job(db, player, OPEN + timedelta(hours=2))
    with pytest.raises(careers.CareerError, match="left a job this quarter"):
        careers.take_job(db, player, "OTB", OPEN + timedelta(hours=3))


# ---------------------------------------------------------------------------
# Pay day
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_pay_day_the_employer_pays_and_forty_percent_is_taken(db):
    player, account = professional(db, now=NOW9)
    assert pass_one(db, player, NOW9)["state"] == "passed"
    before = ledger.balance(db, account)
    employer = _dicts(db, "SELECT id, account_id FROM companies WHERE ticker = 'IKB'")[0]
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]

    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    wage_index = _dicts(db, "SELECT wage_index_bps FROM economy_results WHERE period = 8")[0]["wage_index_bps"]
    level = careers.career(db, player)["level"]            # the work passed has already taken them to Level 2
    full = careers.salary_per_quarter(level, wage_index)
    assert slip["worked"] and slip["company_id"] == employer["id"] and slip["level"] == level == 2
    assert slip["gross"] == full * slip["days_worked"] // 90 and 80 <= slip["days_worked"] <= 90
    assert slip["take_home"] * BPS // slip["gross"] == 6000 and slip["paid"] == slip["take_home"] and slip["owed"] == 0

    # The employer paid it, in one recorded payment with three receivers: the player, the
    # Government (tax) and the households of the city the player works in (living costs).
    legs = _dicts(db, "SELECT e.account_id, e.amount, a.kind, a.code FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                      " JOIN ledger_accounts a ON a.id = e.account_id WHERE t.kind = 'salary' AND t.period = 9 AND e.asset = 'NGN'")
    paid_by = [leg for leg in legs if leg["amount"] < 0]
    assert len(paid_by) == 1 and paid_by[0]["account_id"] == employer["account_id"]
    got = {leg["code"] or leg["kind"]: leg["amount"] for leg in legs if leg["amount"] > 0}
    assert got == {"player": slip["take_home"], "treasury": slip["tax"], "households:lagos": slip["living_costs"]}
    assert ledger.balance(db, account) - before >= slip["take_home"]
    sound(db)


@pytest.mark.world("eight")
def test_a_players_salary_comes_out_of_the_wage_bill_the_company_already_pays(db, connect):
    """The same quarter closed with and without a player on the staff costs the employer the same."""
    with psycopg.connect(TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres", autocommit=True) as admin:
        twin = TEST_DATABASE_URL.rsplit("/", 1)[1] + "_twin"
        admin.execute(f'DROP DATABASE IF EXISTS "{twin}" WITH (FORCE)')
        db.close()
        admin.execute(f'CREATE DATABASE "{twin}" TEMPLATE "{TEST_DATABASE_URL.rsplit("/", 1)[1]}"')
    try:
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as with_player, \
                psycopg.connect(TEST_DATABASE_URL.rsplit("/", 1)[0] + "/" + twin, autocommit=True) as without:
            player, _ = professional(with_player, now=NOW9)
            # Work that was tried and failed is still work, and carries no fee to disturb the comparison.
            taken = objectives.accept(with_player, player, "ac_ratios", NOW9)
            terms = _dicts(with_player, "SELECT terms FROM objectives WHERE id = %s", (taken["id"],))[0]["terms"]
            income = _dicts(with_player, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s ORDER BY version DESC LIMIT 1",
                            (terms["company_id"], terms["filed_period"]))[0]["figures"]["income_statement"]
            one_right = {"ebitda": (income["operating_profit"] + income["depreciation"]) / 1e8}
            assert objectives.submit(with_player, player, taken["id"], one_right, NOW9)["state"] == "failed"
            for conn in (with_player, without):
                quarters.close_due_quarters(conn, after_quarters(9))
            sql = ("SELECT r.operating_expenses, r.cost_of_sales, r.staff, r.wages, r.net_profit, r.cash FROM company_results r"
                   " JOIN companies c ON c.id = r.company_id WHERE c.ticker = 'IKB' AND r.period = 9")
            mine, theirs = _dicts(with_player, sql)[0], _dicts(without, sql)[0]
            assert _dicts(with_player, "SELECT count(*) AS n FROM payslips WHERE gross > 0")[0]["n"] == 1
            # Identical, but for the few kobo that sharing pay among five cities in whole kobo leaves over.
            assert mine["staff"] == theirs["staff"] and mine["wages"] == theirs["wages"] and mine["cost_of_sales"] == theirs["cost_of_sales"]
            for line in ("operating_expenses", "net_profit", "cash"):
                assert abs(mine[line] - theirs[line]) <= 10, line
    finally:
        with psycopg.connect(TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres", autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{twin}" WITH (FORCE)')


@pytest.mark.world("eight")
def test_no_work_no_pay(db):
    player, account = professional(db, now=NOW9)
    before = ledger.balance(db, account)
    quarters.close_due_quarters(db, after_quarters(9))
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    assert not slip["worked"] and slip["gross"] == 0 and "no piece of work" in slip["note"]
    assert not _dicts(db, "SELECT 1 FROM ledger_transactions WHERE kind = 'salary'")
    assert ledger.balance(db, account) - before == _dicts(
        db, "SELECT coalesce(sum(amount), 0) AS paid FROM deposit_interest WHERE player_id = %s", (player,))[0]["paid"]


@pytest.mark.world("eight")
def test_giving_work_up_or_leaving_it_undone_is_not_work(db):
    player, _ = professional(db, now=NOW9)
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    objectives.withdraw(db, player, taken["id"], NOW9)
    objectives.accept(db, player, "ac_cash_flow", NOW9)                 # taken on and never handed in
    quarters.close_due_quarters(db, after_quarters(9))
    assert _dicts(db, "SELECT gross, worked FROM payslips WHERE player_id = %s", (player,)) == [{"gross": 0, "worked": False}]
    assert {o["state"] for o in _dicts(db, "SELECT state FROM objectives")} == {"withdrawn", "not_done"}


@pytest.mark.world("eight")
def test_someone_who_starts_late_in_the_quarter_is_paid_for_the_days_worked(db):
    late = after_quarters(9) - timedelta(days=1, hours=2)               # about a day before the quarter ends
    player, _ = professional(db, now=late)
    pass_one(db, player, late)
    quarters.close_due_quarters(db, after_quarters(9))
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    assert 10 <= slip["days_worked"] <= 16 and "part-way" in slip["note"]
    full = careers.salary_per_quarter(slip["level"], _dicts(db, "SELECT wage_index_bps FROM economy_results WHERE period = 8")[0]["wage_index_bps"])
    assert slip["gross"] == full * slip["days_worked"] // 90 < full // 5


@pytest.mark.world("eight")
def test_nobody_is_paid_for_a_quarter_that_ended_before_they_were_hired(db):
    # The quarter has ended by the clock but has not been closed yet: nobody can be hired in that moment.
    after = after_quarters(9) - timedelta(minutes=30)
    with pytest.raises(careers.CareerError, match="books are being closed"):
        professional(db, now=after)
    quarters.close_due_quarters(db, after_quarters(9))
    assert not _dicts(db, "SELECT 1 FROM payslips") and not _dicts(db, "SELECT 1 FROM employments")


@pytest.mark.world("eight")
def test_an_employer_with_no_cash_owes_the_salary_and_pays_it_when_it_can(db):
    # Find an Accountant's employer that is out of cash.
    broke = _dicts(db, "SELECT c.ticker, c.account_id, c.id FROM companies c JOIN ledger_balances b ON b.account_id = c.account_id"
                       " AND b.asset = 'NGN' WHERE b.balance = 0 AND c.listed AND c.sector IN ('banking', 'insurance') LIMIT 1")          # players work for listed companies
    if not broke:
        company = _dicts(db, "SELECT ticker, account_id, id FROM companies WHERE ticker = 'IKB'")[0]
        ledger.transfer(db, payer=company["account_id"], receiver=ledger.account_id(db, ledger.TREASURY),
                        amount=ledger.balance(db, company["account_id"]), kind="test_drain", memo="Test: the company has no cash")
    else:
        company = broke[0]
    player, account = professional(db, employer=company["ticker"], now=NOW9)
    pass_one(db, player, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    owed = _dicts(db, "SELECT coalesce(sum(amount_outstanding), 0)::bigint AS owed FROM company_payables WHERE company_id = %s"
                      " AND payee_account_id = %s AND kind = 'salary'", (company["id"], account))[0]["owed"]
    assert slip["paid"] + slip["owed"] == slip["take_home"] and owed == slip["owed"]
    assert careers.profile(db, player, after_quarters(9))["job"]["owed"] == owed
    sound(db)


# ---------------------------------------------------------------------------
# The player's bank
# ---------------------------------------------------------------------------

def test_only_the_six_banks_can_be_chosen_and_a_player_moves_at_most_once_a_quarter(db):
    player, _ = professional(db, employer=None, bank=None)
    for wrong in ("SCM", "IDC", "XXX"):
        with pytest.raises(careers.CareerError):
            careers.choose_bank(db, player, wrong, OPEN)
    listed = careers.banks(db, player, OPEN)
    assert sorted(b["ticker"] for b in listed) == sorted(data.PLAYER_BANKS) and len(listed) == 6
    careers.choose_bank(db, player, "IKB", OPEN)
    with pytest.raises(careers.CareerError, match="after the quarter ends"):
        careers.choose_bank(db, player, "ZCB", OPEN + timedelta(days=2))
    quarters.close_due_quarters(db, after_quarters(1))
    assert careers.choose_bank(db, player, "ZCB", after_quarters(1))["ticker"] == "ZCB"


def test_a_weaker_bank_pays_more_on_savings():
    rates = [careers.savings_rate_bps(1300, rating) for rating in ("AAA", "AA", "A", "BBB", "BB", "B", "CCC")]
    assert rates == sorted(rates) and rates[0] < rates[-1] < 1300 and careers.savings_rate_bps(1300, "D") == 0


def test_the_bank_pays_interest_on_the_least_cash_kept_through_a_whole_quarter(db):
    player, account = professional(db, employer=None, cash_naira=400_000)
    bank = _dicts(db, "SELECT id, account_id FROM companies WHERE ticker = 'IKB'")[0]
    quarters.close_due_quarters(db, after_quarters(1))
    # The quarter they joined in earns nothing: interest is for a whole quarter with the bank.
    assert not _dicts(db, "SELECT 1 FROM deposit_interest WHERE player_id = %s", (player,))
    quarters.close_due_quarters(db, after_quarters(2))
    paid = _dicts(db, "SELECT * FROM deposit_interest WHERE player_id = %s", (player,))[0]
    assert paid["period"] == 2 and paid["lowest_balance"] == naira(400_000) and paid["company_id"] == bank["id"]
    assert paid["amount"] == (paid["lowest_balance"] * paid["rate_bps"] + 2 * BPS) // (4 * BPS) > 0
    leg = _dicts(db, "SELECT e.account_id, e.amount FROM ledger_entries e JOIN ledger_transactions t ON t.id = e.transaction_id"
                     " WHERE t.kind = 'deposit_interest' AND e.amount < 0")
    assert [(row["account_id"], -row["amount"]) for row in leg] == [(bank["account_id"], paid["amount"])]
    assert ledger.balance(db, account) == naira(400_000) + paid["amount"]
    sound(db)


def test_money_put_in_just_before_pay_day_earns_nothing(db):
    player, account = professional(db, employer=None)                     # no cash at all
    quarters.close_due_quarters(db, after_quarters(1))
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(50_000_000),
                    kind="test_cash", memo="Test: a large sum arrives on the last day")
    quarters.close_due_quarters(db, after_quarters(2))
    paid = _dicts(db, "SELECT lowest_balance, amount FROM deposit_interest WHERE player_id = %s", (player,))[0]
    assert paid == {"lowest_balance": 0, "amount": 0}


def test_lowest_balance_reads_every_movement(db):
    account = trader(db, "ada", cash_naira=500)
    treasury = ledger.account_id(db, ledger.TREASURY)
    ledger.transfer(db, payer=account, receiver=treasury, amount=naira(450), kind="test", memo="out")
    ledger.transfer(db, payer=treasury, receiver=account, amount=naira(9_000), kind="test", memo="in")
    assert careers.lowest_balance(db, account, None) == 0                 # it began at nothing
    start = _dicts(db, "SELECT min(created_at) AS at FROM ledger_transactions t JOIN ledger_entries e ON e.transaction_id = t.id"
                       " WHERE e.account_id = %s", (account,))[0]["at"]
    assert careers.lowest_balance(db, account, start) == naira(50)


# ---------------------------------------------------------------------------
# Retirement savings
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_part_of_every_salary_is_saved_and_the_employer_adds_more(db):
    player, account = professional(db, now=NOW9)
    pass_one(db, player, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    slip = _dicts(db, "SELECT * FROM payslips WHERE player_id = %s", (player,))[0]
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s", (player,))[0]
    assert entry["paid_in_by_you"] == slip["pension_yours"] == apply_bps(slip["gross"], 800)      # 8%, to the nearest kobo
    assert entry["paid_in_by_employer"] == slip["pension_employer"] == slip["gross"] // 10
    assert entry["closing"] == entry["paid_in_by_you"] + entry["paid_in_by_employer"] and entry["fund"] == "balanced"
    # It is a claim on the pension funds, not cash: the player cannot spend it.
    assert careers.profile(db, player, after_quarters(9))["retirement"]["value"] == entry["closing"]
    # Next quarter it grows by what the fund earned.
    quarters.close_due_quarters(db, after_quarters(10))
    second = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 10", (player,))[0]
    earned = _dicts(db, "SELECT return_bps FROM pension_fund_results WHERE period = 10 AND fund = 'balanced'")[0]["return_bps"]
    assert second["opening"] == entry["closing"] and second["growth"] == (entry["closing"] * earned + BPS // 2) // BPS
    sound(db)


def test_a_fund_is_changed_at_most_once_in_a_game_year(db):
    player, _ = professional(db, employer=None)
    with pytest.raises(careers.CareerError):
        careers.choose_fund(db, player, "everything", OPEN)
    careers.choose_fund(db, player, "growth", OPEN)
    with pytest.raises(careers.CareerError, match="once in a game year"):
        careers.choose_fund(db, player, "cautious", OPEN + timedelta(days=3))


def test_the_four_funds_divide_their_money_as_the_design_says():
    for fund in data.PENSION_FUNDS.values():
        assert fund["shares"] + fund["bonds"] + fund["cash"] == BPS
    order = [data.PENSION_FUNDS[f]["shares"] for f in ("growth", "balanced", "cautious", "income")]
    assert order == sorted(order, reverse=True)


# ---------------------------------------------------------------------------
# The Money Watch
# ---------------------------------------------------------------------------

@pytest.mark.world("eight")
def test_the_money_watch_records_what_players_were_paid_and_why(db):
    player, _ = professional(db, now=NOW9, cash_naira=200_000)
    done = pass_one(db, player, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    seen = _dicts(db, "SELECT paid_to_players FROM money_watch_results WHERE period = 9")[0]["paid_to_players"]
    slip = _dicts(db, "SELECT take_home FROM payslips WHERE player_id = %s", (player,))[0]
    assert seen["salary"] == {"total": slip["take_home"], "players": 1}
    assert seen["professional_fee"] == {"total": done["paid"], "players": 1}
    assert clock.period_label(9)
