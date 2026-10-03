"""Stage 5: professional objectives.

The stage test: "A new player is hired, completes an objective and is paid by a named payer."

Every objective is judged by the server from the game's own records, and every reward is
paid by a named payer out of that payer's own cash.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import psycopg
import pytest
from psycopg.rows import dict_row

from simulation import bonds, careers, clock, exchange, ledger, marketview, objectives, quarters
from simulation import world_data as data
from simulation.money import BPS, naira
from tests.conftest import ADULT, WORLD_START, after_quarters, join, money_accounted_for
from tests.test_careers import NOW9, pass_one, professional, sound

pytestmark = pytest.mark.world("eight")
START9 = WORLD_START + timedelta(weeks=8)             # the ninth quarter begins: a Monday at midnight in Lagos


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def bell(db, n: int) -> datetime:
    """Ring the nth Closing Bell of the ninth quarter (the first is on its Monday night)."""
    day = (clock.to_lagos(START9) + timedelta(days=n - 1)).date()
    now = datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)
    objectives.at_bell(db, now, day)
    return now


def give_shares(db, account, ticker: str, worth_naira: int) -> int:
    price = next(s["price"] for s in marketview._shares(db, exchange.session_of(NOW9)[0]) if s["ticker"] == ticker)
    shares = naira(worth_naira) // price + 1
    ledger.transfer(db, payer=ledger.account_id(db, ledger.INVESTORS_PUBLIC), receiver=account, amount=shares,
                    asset=f"SHR-{ticker}", kind="test_shares", memo="Test: shares")
    return shares


def give_cash(db, account, amount_naira: int) -> None:
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(amount_naira),
                    kind="test_cash", memo="Test: cash")


def government(db, kind: str, quarters_left: int | None = None) -> dict:
    lines = [b for b in bonds.listing(db, NOW9) if b["issuer"] == "Federal Government" and b["kind"] == kind]
    if quarters_left is None:
        return lines[0]
    return min(lines, key=lambda b: abs(b["quarters_left"] - quarters_left))


def state_of(db, objective_id) -> dict:
    return _dicts(db, "SELECT * FROM objectives WHERE id = %s", (objective_id,))[0]


def manager(db, name="ada", *, level=1, cash_naira=0, employer="IKB"):
    player, account = professional(db, name, build="asset_manager", employer=employer, now=NOW9, cash_naira=cash_naira)
    if level > 1:
        careers.add_experience(db, player, "asset_manager", careers.experience_for(level), NOW9)
    return player, account


def accountant(db, name="ada", *, level=1):
    player, account = professional(db, name, now=NOW9)
    if level > 1:
        careers.add_experience(db, player, "accountant", careers.experience_for(level), NOW9)
    return player, account


def figures_for(db, objective_id) -> dict:
    terms = state_of(db, objective_id)["terms"]
    return _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = %s ORDER BY version DESC LIMIT 1",
                  (terms["company_id"], terms["filed_period"]))[0]["figures"]


# ---------------------------------------------------------------------------
# THE STAGE TEST, through the website's own doors.
# ---------------------------------------------------------------------------

def test_a_new_player_is_hired_completes_an_objective_and_is_paid_by_a_named_payer(db, client):
    assert join(client, ADULT).status_code == 201
    # A new player has no build, no employer and no work.
    assert client.get("/api/me").json()["build"] is None
    assert client.get("/api/objectives").json()["ready"] is False

    # They choose a build, a bank and an employer.
    assert client.put("/api/career/build", json={"build": "accountant"}).status_code == 200
    assert client.put("/api/career/bank", json={"ticker": "IKB"}).status_code == 200
    employers = client.get("/api/career/employers").json()
    hiring = next(e for e in employers if e["places_left"] > 0 and not e["behind_on_bills"])
    career = client.put("/api/career/job", json={"ticker": hiring["ticker"]}).json()
    assert career["job"]["name"] == hiring["name"] and career["career"]["level"] == 1
    me = client.get("/api/me").json()
    assert (me["build_name"], me["level"], me["employer"]) == ("Accountant", 1, hiring["name"])

    # Work is on offer. They take a piece on: a client and a payer are named before they start.
    board = client.get("/api/objectives").json()
    offer = next(o for o in board["offers"] if o["template"] == "ac_ratios")
    assert offer["available"] and offer["payer"] == offer["client"]["name"]
    taken = client.post("/api/objectives", json={"template": "ac_ratios"})
    assert taken.status_code == 201
    work = taken.json()
    assert work["state"] == "active" and work["result"] is None and work["payer"] == offer["payer"]

    # They do the work from the figures they were given, and nothing else.
    given = {g["label"]: int(g["kobo"]) for g in work["terms"]["given"]}
    ebitda = given["Operating profit"] + given["Wear on buildings and machines (depreciation)"]
    answers = {
        "ebitda": round(ebitda / 1e8, 2),
        "margin": round(given["Profit after tax"] / given["Sales"] * 100, 1),
        "debt_to_ebitda": round(given["Total borrowings"] / (4 * ebitda), 1),
        "interest_cover": round(given["Operating profit"] / given["Interest paid on its debts"], 1),
    }
    cash_before = int(client.get("/api/me").json()["cash"]["amount_kobo"])
    done = client.post(f"/api/objectives/{work['id']}/hand-in", json={"answers": answers}).json()
    assert done["state"] == "passed" and done["result"]["score"] == 100
    assert int(done["paid_kobo"]) == int(done["reward_kobo"]) == naira(40_000) * _wage_index(db) // BPS // 100_000 * 100_000

    # They were paid by the named payer, out of the payer's own cash, and it is in the ledger.
    assert int(client.get("/api/me").json()["cash"]["amount_kobo"]) == cash_before + int(done["paid_kobo"])
    payment = _dicts(db, "SELECT t.kind, t.memo, payer.account_id AS payer, c.name FROM ledger_transactions t"
                         " JOIN ledger_entries payer ON payer.transaction_id = t.id AND payer.amount < 0"
                         " JOIN companies c ON c.account_id = payer.account_id WHERE t.reference = %s", (f"objective:{work['id']}",))
    assert len(payment) == 1 and payment[0]["kind"] == "professional_fee" and payment[0]["name"] == done["payer"]
    movement = client.get("/api/me/movements").json()[0]
    assert movement["counterparty"] == done["payer"] and int(movement["amount_kobo"]) == int(done["paid_kobo"])
    # They learn why: plain words, the method, then the arithmetic.
    assert all(done["result"]["debrief"][part] for part in ("plain", "method", "maths"))
    # Experience came with it; no money was made.
    after = client.get("/api/career").json()
    assert after["career"]["experience"] == 60 and after["career"]["level"] == 2 and after["reputation"] == 51
    assert ledger.audit(db) == [] and ledger.amount_in_existence(db) == money_accounted_for(db)

    # And on pay day the employer pays their salary.
    quarters.close_due_quarters(db, after_quarters(9))
    slip = client.get("/api/career").json()["payslips"][0]
    assert slip["employer"] == hiring["name"] and int(slip["paid_kobo"]) > 0 and slip["worked"]


def _wage_index(db) -> int:
    return _dicts(db, "SELECT wage_index_bps FROM economy_results ORDER BY period DESC LIMIT 1")[0]["wage_index_bps"]


# ---------------------------------------------------------------------------
# The rules around taking work on
# ---------------------------------------------------------------------------

def test_work_comes_through_an_employer_and_only_for_your_own_build(db):
    player, _ = professional(db, employer=None, now=NOW9)
    with pytest.raises(objectives.ObjectiveError, match="employer"):
        objectives.accept(db, player, "ac_ratios", NOW9)
    careers.take_job(db, player, "IDC", NOW9)
    for other in ("am_spread", "nothing", ""):
        with pytest.raises(objectives.ObjectiveError):
            objectives.accept(db, player, other, NOW9)


def test_harder_work_opens_with_level(db):
    player, _ = accountant(db)
    with pytest.raises(objectives.ObjectiveError, match="Level 4"):
        objectives.accept(db, player, "ac_rating", NOW9)
    locked = {o["template"]: o for o in objectives.board(db, player, NOW9)["offers"]}
    assert not locked["ac_rating"]["available"] and locked["ac_rating"]["why_not"] == "Opens at Level 4."
    careers.add_experience(db, player, "accountant", careers.experience_for(4), NOW9)
    assert objectives.accept(db, player, "ac_rating", NOW9)["state"] == "active"


def test_each_piece_of_work_once_a_quarter_and_three_in_hand_at_most(db):
    player, _ = accountant(db, level=5)
    for code in ("ac_ratios", "ac_cash_flow", "ac_income"):
        objectives.accept(db, player, code, NOW9)
    with pytest.raises(objectives.ObjectiveError, match="3 pieces of work"):
        objectives.accept(db, player, "ac_forecast", NOW9)
    first = _dicts(db, "SELECT id FROM objectives WHERE template = 'ac_ratios'")[0]["id"]
    objectives.submit(db, player, first, {"ebitda": 0}, NOW9)                        # handed in wrong: failed
    with pytest.raises(objectives.ObjectiveError, match="already taken"):
        objectives.accept(db, player, "ac_ratios", NOW9)                             # no second try this quarter
    # The database refuses a second one too, whatever the server is asked.
    row = state_of(db, first)
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO objectives (player_id, build, template, module, period, payer_account_id, payer_name, title, terms,"
                   " reward, experience, accepted_at) VALUES (%s, 'accountant', 'ac_ratios', 'x', %s, %s, 'x', 'x', '{}', 0, 0, now())",
                   (player, row["period"], row["payer_account_id"]))


def test_the_client_is_chosen_by_the_server_and_asking_again_changes_nothing(db):
    player, _ = accountant(db)
    seen = {objectives.board(db, player, NOW9 + timedelta(minutes=n))["offers"][0]["client"]["ticker"] for n in range(5)}
    assert len(seen) == 1
    other, _ = professional(db, "bola", now=NOW9)
    clients = set()
    for n in range(12):
        someone, _ = professional(db, f"player{n}", employer="GGM", now=NOW9)
        clients.add(objectives.board(db, someone, NOW9)["offers"][0]["client"]["ticker"])
    assert len(clients) > 3                                                          # different players, different clients


def test_work_is_handed_in_once_and_only_by_its_owner(db):
    player, _ = accountant(db)
    thief, _ = professional(db, "bola", now=NOW9)
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    with pytest.raises(objectives.ObjectiveError, match="no such piece of work"):
        objectives.submit(db, thief, taken["id"], {"ebitda": 1}, NOW9)
    with pytest.raises(objectives.ObjectiveError, match="no such piece of work"):
        objectives.withdraw(db, thief, taken["id"], NOW9)
    assert objectives.submit(db, player, taken["id"], {"ebitda": 1}, NOW9)["state"] == "failed"
    with pytest.raises(objectives.ObjectiveError, match="finished"):
        objectives.submit(db, player, taken["id"], {"ebitda": 2}, NOW9)


def test_the_terms_and_the_result_cannot_be_changed_in_the_database(db):
    player, _ = accountant(db)
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    for change in ("reward = reward * 100", "terms = '{}'", "experience = 9999", "payer_account_id = (SELECT id FROM ledger_accounts WHERE code = 'treasury')"):
        with pytest.raises(psycopg.errors.RestrictViolation):
            db.execute(f"UPDATE objectives SET {change} WHERE id = %s", (taken["id"],))
    objectives.submit(db, player, taken["id"], {"ebitda": 1}, NOW9)
    for change in ("state = 'passed'", "paid = reward", "result = '{}'"):
        with pytest.raises(psycopg.errors.RestrictViolation):
            db.execute(f"UPDATE objectives SET {change} WHERE id = %s", (taken["id"],))
    with pytest.raises(psycopg.errors.RestrictViolation):
        db.execute("DELETE FROM objectives WHERE id = %s", (taken["id"],))


def test_nothing_shown_before_judging_gives_the_answer_away(db):
    player, _ = accountant(db, level=5)
    for code in ("ac_ratios", "ac_cash_flow", "ac_income"):
        shown = objectives.accept(db, player, code, NOW9)
        assert shown["result"] is None and "company_id" not in shown["terms"]
        text = str(shown)
        assert "heading'" not in text and "answers" not in text
    cash = next(o for o in objectives.board(db, player, NOW9)["active"] if o["template"] == "ac_cash_flow")
    items = next(f for f in cash["terms"]["fields"] if f["kind"] == "classify")["items"]
    assert all(set(item) == {"key", "label", "kobo"} for item in items)


def test_a_payer_without_the_cash_is_not_offering_work_and_a_reward_never_exceeds_what_the_payer_has(db):
    player, account = manager(db)
    employer = _dicts(db, "SELECT account_id FROM companies WHERE ticker = 'IKB'")[0]["account_id"]
    taken = objectives.accept(db, player, "am_spread", NOW9)
    # The employer's cash goes, all but ₦10,000.
    ledger.transfer(db, payer=employer, receiver=ledger.account_id(db, ledger.TREASURY),
                    amount=ledger.balance(db, employer) - naira(10_000), kind="test_drain", memo="Test")
    offers = {o["template"]: o for o in objectives.board(db, player, NOW9)["offers"]}
    assert not offers["am_mandate"]["available"] or offers["am_mandate"]["level"] > 1
    assert not offers["am_idle"]["available"] and "cash to pay" in offers["am_idle"]["why_not"]
    for ticker in ("IDC", "ABA", "GGM", "EKC", "ADF"):
        give_shares(db, account, ticker, 25_000)
    bell(db, 1), bell(db, 2)
    done = state_of(db, taken["id"])
    assert done["state"] == "passed" and done["paid"] == naira(10_000) < done["reward"]
    assert "had only" in done["result"]["payment_note"] and ledger.balance(db, employer) == 0
    assert ledger.audit(db) == []


# ---------------------------------------------------------------------------
# ACCOUNTANT
# ---------------------------------------------------------------------------

def test_the_ratios_paper_is_marked_against_the_filed_accounts(db):
    player, _ = accountant(db)
    assert pass_one(db, player, NOW9)["result"]["score"] == 100
    other, _ = professional(db, "bola", now=NOW9)
    taken = objectives.accept(db, other, "ac_ratios", NOW9)
    f = figures_for(db, taken["id"])
    income = f["income_statement"]
    ebitda = income["operating_profit"] + income["depreciation"]
    # Two right, two wrong: not passed, and nothing paid.
    marked = objectives.submit(db, other, taken["id"], {
        "ebitda": ebitda / 1e8, "margin": income["net_profit"] / income["revenue"] * 100,
        "debt_to_ebitda": 99, "interest_cover": "nonsense"}, NOW9)
    assert marked["state"] == "failed" and marked["result"]["score"] == 50 and marked["paid"] == 0
    assert marked["result"]["answers"]["ebitda"] == round(ebitda / 1e8, 2)            # the right figures are shown afterwards


def test_sorting_the_cash_movements(db):
    player, account = accountant(db)
    taken = objectives.accept(db, player, "ac_cash_flow", NOW9)
    f = figures_for(db, taken["id"])
    truth = {item["key"]: item["heading"] for item in objectives._cash_items(f)}
    flow = f["cash_flow"]
    assert sum(i["kobo"] for i in objectives._cash_items(f)) == flow["cash_closing"] - flow["cash_opening"]
    done = objectives.submit(db, player, taken["id"], {
        "headings": truth, "operating": flow["cash_from_operations"] / 1e8, "investing": flow["cash_from_investing"] / 1e8,
        "financing": flow["cash_from_financing"] / 1e8, "closing": flow["cash_closing"] / 1e8}, NOW9)
    assert done["state"] == "passed" and done["paid"] == done["reward"] and done["payer"] == taken["terms"]["client"]["name"]

    other, _ = professional(db, "bola", now=NOW9)
    again = objectives.accept(db, other, "ac_cash_flow", NOW9)
    g = figures_for(db, again["id"])
    wrong = {item["key"]: "financing" for item in objectives._cash_items(g)}          # everything in one pile
    marked = objectives.submit(db, other, again["id"], {"headings": wrong, "closing": g["cash_flow"]["cash_closing"] / 1e8}, NOW9)
    assert marked["state"] == "failed" and marked["result"]["score"] == 20


def test_finishing_the_income_statement_and_the_tax(db):
    player, _ = accountant(db, level=2)
    taken = objectives.accept(db, player, "ac_income", NOW9)
    income = figures_for(db, taken["id"])["income_statement"]
    right = {k: income[k] / 1e8 for k in ("operating_profit", "profit_before_tax", "tax", "net_profit")}
    other, _ = professional(db, "bola", now=NOW9)
    careers.add_experience(db, other, "accountant", careers.experience_for(2), NOW9)
    theirs = objectives.accept(db, other, "ac_income", NOW9)
    their_income = figures_for(db, theirs["id"])["income_statement"]
    # Everything right but the tax: not passed. The tax is the point.
    no_tax = {k: their_income[k] / 1e8 for k in ("operating_profit", "profit_before_tax", "net_profit")} | {"tax": -5}
    assert objectives.submit(db, other, theirs["id"], no_tax, NOW9)["state"] == "failed"
    assert objectives.submit(db, player, taken["id"], right, NOW9)["state"] == "passed"


def test_a_sales_forecast_is_judged_by_what_the_company_then_files(db):
    good, _ = accountant(db, level=2)
    bad, _ = professional(db, "bola", now=NOW9)
    careers.add_experience(db, bad, "accountant", careers.experience_for(2), NOW9)
    silent, _ = professional(db, "chi", now=NOW9)
    careers.add_experience(db, silent, "accountant", careers.experience_for(2), NOW9)
    taken = {p: objectives.accept(db, p, "ac_forecast", NOW9) for p in (good, bad, silent)}
    assert objectives.submit(db, bad, taken[bad]["id"], {"revenue": 1.0}, NOW9)["state"] == "active"       # judged later
    with pytest.raises(objectives.ObjectiveError):
        objectives.submit(db, silent, taken[silent]["id"], {"revenue": "lots"}, NOW9)
    # The good forecaster is given the future for the purpose of the test: close a twin of the quarter first.
    company = state_of(db, taken[good]["id"])["terms"]["company_id"]
    with db.transaction(force_rollback=True):
        quarters.close_due_quarters(db, after_quarters(9))
        actual = _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = 9", (company,))[0]["figures"]["income_statement"]["revenue"]
    objectives.submit(db, good, taken[good]["id"], {"revenue": actual / 1e8 * 1.02}, NOW9)                 # 2% out
    quarters.close_due_quarters(db, after_quarters(9))
    results = {p: state_of(db, taken[p]["id"]) for p in taken}
    assert results[good]["state"] == "passed" and results[good]["result"]["score"] == 80 and results[good]["paid"] > 0
    assert results[bad]["state"] == "failed" and results[bad]["paid"] == 0
    assert results[silent]["state"] == "not_done"
    assert {r["judged_period"] for r in results.values()} == {10}                    # it counts towards the next pay day
    sound(db)


def test_the_auditors_call_on_whether_a_company_can_pay(db):
    players = [accountant(db, f"player{n}", level=3)[0] for n in range(6)]
    taken = {p: objectives.accept(db, p, "ac_bills", NOW9) for p in players}
    for index, p in enumerate(players):
        objectives.submit(db, p, taken[p]["id"], {"call": "pays" if index % 2 else "behind"}, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    for index, p in enumerate(players):
        row = state_of(db, taken[p]["id"])
        sheet = _dicts(db, "SELECT figures FROM company_reports WHERE company_id = %s AND period = 9",
                       (row["terms"]["company_id"],))[0]["figures"]
        behind = sheet["balance_sheet"]["payables"] > 0 or sheet["notes"]["principal_overdue"] > 0 or sheet["notes"].get("repayments_missed", 0) > 0
        assert (row["state"] == "passed") == (behind == (index % 2 == 0))
        assert row["result"]["answers"]["call"] == ("behind" if behind else "pays")


def test_calling_the_credit_rating(db):
    players = [accountant(db, f"player{n}", level=4)[0] for n in range(5)]
    taken = {p: objectives.accept(db, p, "ac_rating", NOW9) for p in players}
    for p in players:
        objectives.submit(db, p, taken[p]["id"], {"rating": taken[p]["terms"]["fields"][0]["options"][3]["code"]}, NOW9)    # everybody says BBB
    with pytest.raises(objectives.ObjectiveError):
        other = accountant(db, "zed", level=4)[0]
        objectives.submit(db, other, objectives.accept(db, other, "ac_rating", NOW9)["id"], {"rating": "A+"}, NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    for p in players:
        row = state_of(db, taken[p]["id"])
        rated = _dicts(db, "SELECT credit_rating FROM company_reports WHERE company_id = %s AND period = 9",
                       (row["terms"]["company_id"],))[0]["credit_rating"]
        assert (row["state"] == "passed") == (rated == "BBB")


def test_work_never_handed_in_is_recorded_as_not_done_when_the_quarter_ends(db):
    player, _ = accountant(db)
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    quarters.close_due_quarters(db, after_quarters(9))
    row = state_of(db, taken["id"])
    assert row["state"] == "not_done" and row["paid"] == 0
    with pytest.raises(objectives.ObjectiveError):
        objectives.submit(db, player, taken["id"], {"ebitda": 1}, after_quarters(9))


# ---------------------------------------------------------------------------
# ASSET MANAGER
# ---------------------------------------------------------------------------

def test_spreading_the_risk_is_judged_on_what_is_held_at_the_bell(db):
    player, account = manager(db)
    taken = objectives.accept(db, player, "am_spread", NOW9)
    for ticker in ("IDC", "ABA", "GGM", "EKC", "ADF"):                # five companies, three industries, 20% each
        give_shares(db, account, ticker, 25_000)
    bell(db, 1)
    assert state_of(db, taken["id"])["state"] == "active" and state_of(db, taken["id"])["progress"]["run"] == 1
    bell(db, 1)                                                       # the same bell rung twice counts once
    assert state_of(db, taken["id"])["progress"]["bells"] == 1
    before = ledger.balance(db, account)
    bell(db, 2)
    done = state_of(db, taken["id"])
    assert done["state"] == "passed" and done["result"]["score"] == 100
    employer = _dicts(db, "SELECT name FROM companies WHERE ticker = 'IKB'")[0]["name"]
    assert done["payer_name"] == employer and ledger.balance(db, account) == before + done["reward"]
    sound(db)


def test_one_big_holding_or_one_industry_does_not_pass(db):
    lopsided, account = manager(db)
    one_industry, second = manager(db, "bola")
    empty, _ = manager(db, "chi")
    taken = {p: objectives.accept(db, p, "am_spread", NOW9) for p in (lopsided, one_industry, empty)}
    give_shares(db, account, "IDC", 200_000)                          # one share is most of it
    for ticker in ("ABA", "GGM", "EKC", "ADF"):
        give_shares(db, account, ticker, 20_000)
    for ticker in ("IKB", "OTB", "HMB", "KCB", "ZCB"):                # five banks are one bet
        give_shares(db, second, ticker, 30_000)
    for n in range(1, 6):
        bell(db, n)
    assert state_of(db, taken[lopsided]["id"])["state"] == "failed"
    assert state_of(db, taken[one_industry]["id"])["state"] == "failed"
    assert state_of(db, taken[empty]["id"])["state"] == "not_done"


def test_shares_borrowed_for_the_moment_of_the_bell_must_still_be_there_at_the_next(db):
    player, account = manager(db)
    taken = objectives.accept(db, player, "am_spread", NOW9)
    given = {t: give_shares(db, account, t, 25_000) for t in ("IDC", "ABA", "GGM", "EKC", "ADF")}
    bell(db, 1)
    for ticker, shares in given.items():                              # gone again after the first bell
        ledger.transfer(db, payer=account, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC), amount=shares,
                        asset=f"SHR-{ticker}", kind="test_shares", memo="Test: handed back")
    bell(db, 2)
    assert state_of(db, taken["id"])["progress"]["run"] == 0 and state_of(db, taken["id"])["state"] == "active"


def test_idle_cash_in_government_bills(db):
    player, account = manager(db, cash_naira=120_000)
    late, late_account = manager(db, "bola", cash_naira=120_000)
    taken = objectives.accept(db, player, "am_idle", NOW9)
    late_taken = objectives.accept(db, late, "am_idle", NOW9)
    bill = government(db, "bill")
    bonds.trade(db, account=account, code=bill["code"], side="buy", units=60, now=NOW9)
    for n in range(1, 7):
        bell(db, n)
    # The latecomer buys only after the last-but-one bell: one bell is not enough.
    bonds.trade(db, account=late_account, code=bill["code"], side="buy", units=60, now=START9 + timedelta(days=5, hours=23))
    bell(db, 7)
    quarters.close_due_quarters(db, after_quarters(9))
    done, missed = state_of(db, taken["id"]), state_of(db, late_taken["id"])
    assert done["state"] == "passed" and done["progress"]["bells"] == 7 and done["paid"] == done["reward"]
    assert missed["state"] == "failed" and missed["progress"]["bells"] == 1
    sound(db)


def test_positioning_for_the_rate_decision(db):
    """Three managers, three calls. Whatever the Central Bank does, each is judged on their call
    and on how their bonds did against the five-year bond."""
    book = {"rise": ("bill", None), "hold": ("fixed", 20), "fall": ("fixed", 40)}
    taken, accounts = {}, {}
    for call, (kind, length) in book.items():
        player, account = manager(db, call, level=2, cash_naira=200_000)
        taken[call] = objectives.accept(db, player, "am_rates", NOW9)
        objectives.submit(db, player, taken[call]["id"], {"call": call}, NOW9)
        bonds.trade(db, account=account, code=government(db, kind, length)["code"], side="buy", units=100, now=NOW9)
        accounts[call] = account
    idle, _ = manager(db, "idle", level=2)
    idle_taken = objectives.accept(db, idle, "am_rates", NOW9)
    objectives.submit(db, idle, idle_taken["id"], {"call": "rise"}, NOW9)            # a call with no money on it
    for n in range(1, 8):
        bell(db, n)
    before = _dicts(db, "SELECT next_policy_rate_bps FROM economy_results WHERE period = 8")[0]["next_policy_rate_bps"]
    quarters.close_due_quarters(db, after_quarters(9))
    after = _dicts(db, "SELECT next_policy_rate_bps FROM economy_results WHERE period = 9")[0]["next_policy_rate_bps"]
    happened = "rise" if after > before else "fall" if after < before else "hold"
    for call in book:
        row = state_of(db, taken[call]["id"])
        called, kept_up = (m["earned"] for m in row["result"]["milestones"])
        assert called == (call == happened)
        assert (row["state"] == "passed") == (called and kept_up)
        assert row["progress"]["book"]["lines"][0]["units"] == 100
    # The manager who called it right did keep up with the five-year bond: that is what the right position does.
    assert state_of(db, taken[happened]["id"])["state"] == "passed"
    assert state_of(db, idle_taken["id"])["state"] == "failed" and state_of(db, idle_taken["id"])["paid"] == 0
    sound(db)


def test_a_long_bond_falls_further_than_a_bill_when_the_rate_rises(db):
    """The arithmetic the rate objective rests on, with the rate moved by hand."""
    state = bonds.market(db, NOW9)
    bill, long = (bonds.find(db, government(db, kind, length)["code"]) for kind, length in (("bill", None), ("fixed", 40)))
    higher = {**state, "policy": state["policy"] + 100}
    fall = lambda bond: (bonds.fair_value(bond, state) - bonds.fair_value(bond, higher)) * BPS // bonds.fair_value(bond, state)   # noqa: E731
    assert fall(long) > 10 * max(fall(bill), 1) and fall(bill) < 30


def test_running_a_balanced_mandate(db):
    player, account = manager(db, level=2, cash_naira=80_000)
    drifted, drifted_account = manager(db, "bola", level=2, cash_naira=80_000)
    taken = objectives.accept(db, player, "am_mandate", NOW9)
    other = objectives.accept(db, drifted, "am_mandate", NOW9)
    for who in (account, drifted_account):
        give_shares(db, who, "IDC", 40_000), give_shares(db, who, "GGM", 40_000)
        bonds.trade(db, account=who, code=government(db, "fixed", 8)["code"], side="buy", units=60, now=NOW9)
    have = objectives.wealth(db, account, NOW9)
    assert 4000 <= have["shares"] * BPS // have["total"] <= 6000 and 500 <= have["cash"] * BPS // have["total"] <= 2000
    bell(db, 1), bell(db, 2)
    give_shares(db, drifted_account, "IDC", 200_000)                  # shares become far too large a part
    for n in range(3, 7):
        bell(db, n)
    done, failed = state_of(db, taken["id"]), state_of(db, other["id"])
    assert done["state"] == "passed" and done["progress"]["bells"] == 3
    assert failed["state"] == "failed" and failed["progress"]["bells"] == 6 and failed["result"]["milestones"][0]["earned"]


def test_backing_a_valuation_through_the_results(db):
    holder, account = manager(db, level=3)
    seller, seller_account = manager(db, "bola", level=3)
    nobody, _ = manager(db, "chi", level=3)
    taken = {p: objectives.accept(db, p, "am_value", NOW9) for p in (holder, seller, nobody)}
    with pytest.raises(objectives.ObjectiveError, match="at least ₦50,000"):
        objectives.submit(db, holder, taken[holder]["id"], {"ticker": "IDC"}, NOW9)
    shares = give_shares(db, account, "IDC", 60_000)
    sold = give_shares(db, seller_account, "IDC", 60_000)
    with pytest.raises(objectives.ObjectiveError, match="no share"):
        objectives.submit(db, holder, taken[holder]["id"], {"ticker": "ZZZ"}, NOW9)
    assert objectives.submit(db, holder, taken[holder]["id"], {"ticker": "idc"}, NOW9)["state"] == "active"
    objectives.submit(db, seller, taken[seller]["id"], {"ticker": "IDC"}, NOW9)
    bell(db, 1)
    ledger.transfer(db, payer=seller_account, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC), amount=sold // 2,
                    asset="SHR-IDC", kind="test_shares", memo="Test: sold half before the results")
    bell(db, 2)
    assert state_of(db, taken[seller]["id"])["state"] == "failed"
    for n in range(3, 8):
        bell(db, n)
    assert state_of(db, taken[holder]["id"])["state"] == "active"     # nothing is decided before the results
    quarters.close_due_quarters(db, after_quarters(9))
    assert state_of(db, taken[nobody]["id"])["state"] == "not_done"
    pick = state_of(db, taken[holder]["id"])["progress"]["pick"]
    assert pick["shares"] == shares and state_of(db, taken[holder]["id"])["progress"]["results_in"] == 9
    # The first bell after the results decides it, on the share's price against the index.
    day = (clock.to_lagos(START9) + timedelta(days=7)).date()
    now = datetime.combine(day, time(22, 5), tzinfo=clock.LAGOS)
    objectives.at_bell(db, now, day)
    row = state_of(db, taken[holder]["id"])
    price = next(s["price"] for s in marketview._shares(db, exchange.session_of(now)[0]) if s["ticker"] == "IDC")
    share_bps = (price - pick["price"]) * BPS // pick["price"]
    index_bps = (objectives.index_now(db, now) - pick["index"]) * BPS // pick["index"]
    assert row["state"] == ("passed" if share_bps > index_bps else "failed") and row["judged_period"] == 10


def test_beating_the_index_leaves_out_money_paid_in(db):
    player, account = manager(db, level=4, cash_naira=100_000)
    cash_heavy, heavy_account = manager(db, "bola", level=4, cash_naira=100_000)
    poor, _ = manager(db, "chi", level=4, cash_naira=1_000)
    taken = {p: objectives.accept(db, p, "am_beat", NOW9) for p in (player, cash_heavy, poor)}
    for ticker in ("IDC", "GGM", "EKC"):
        give_shares(db, account, ticker, 60_000)
    give_shares(db, heavy_account, "IDC", 400_000)
    bell(db, 1)
    start = state_of(db, taken[player]["id"])["progress"]["start"]
    assert start["total"] == objectives.wealth(db, account, NOW9)["total"]
    # A large payment arrives from outside. It must not count as investment return.
    ledger.transfer(db, payer=ledger.account_id(db, ledger.TREASURY), receiver=account, amount=naira(100_000),
                    kind="starting_grant", memo="Test: money from outside", reference=str(account))
    # The second manager sells most of their shares: too little is left invested.
    ledger.transfer(db, payer=heavy_account, receiver=ledger.account_id(db, ledger.INVESTORS_PUBLIC),
                    amount=ledger.balance(db, heavy_account, "SHR-IDC") * 9 // 10, asset="SHR-IDC", kind="test_shares", memo="Test")
    give_shares(db, account, "IDC", 200_000)                          # the payment is invested, so 60% stays invested
    bell(db, 2)
    assert state_of(db, taken[cash_heavy]["id"])["state"] == "failed"
    assert state_of(db, taken[poor]["id"])["state"] == "not_done"     # never had the money to start
    for n in range(3, 9):
        bell(db, n)
    row = state_of(db, taken[player]["id"])
    assert row["state"] in ("passed", "failed") and row["progress"]["start"]["bells"] == 7
    # With prices unmoved, taking the payment out leaves a return of about nothing: it did not count.
    assert "paid in" in row["result"]["debrief"]["maths"] and "100,000 paid in" in row["result"]["debrief"]["maths"]


# ---------------------------------------------------------------------------
# Failure, and the performance review
# ---------------------------------------------------------------------------

def _finish(db, player, code: str, state: str, period: int) -> None:
    """Record one finished objective directly, for the tests of the record-keeping."""
    account = _dicts(db, "SELECT account_id FROM companies WHERE ticker = 'IDC'")[0]["account_id"]
    row = _dicts(db, "INSERT INTO objectives (player_id, build, template, module, period, payer_account_id, payer_name, title, terms,"
                     " reward, experience, accepted_at) VALUES (%s, 'accountant', %s, 'x', %s, %s, 'IDC', 'x', '{}', 0, 10, now()) RETURNING *",
                (player, code, period, account))[0]
    objectives._finish(db, row, objectives._verdict(state, "test", [], plain="", method="", maths=""), NOW9, 9)


def test_a_failed_objective_costs_the_reward_and_nothing_else(db):
    player, account = accountant(db)
    before = (ledger.balance(db, account), careers.career(db, player)["experience"],
              _dicts(db, "SELECT reputation FROM players WHERE id = %s", (player,))[0]["reputation"])
    taken = objectives.accept(db, player, "ac_ratios", NOW9)
    assert objectives.submit(db, player, taken["id"], {"ebitda": 1}, NOW9)["state"] == "failed"
    after = (ledger.balance(db, account), careers.career(db, player)["experience"],
             _dicts(db, "SELECT reputation FROM players WHERE id = %s", (player,))[0]["reputation"])
    assert after == before and not careers.career(db, player)["review_open"]


def test_five_failures_in_ten_open_a_review_and_three_passes_close_it(db):
    player, _ = accountant(db)
    for n, state in enumerate(["failed", "passed", "failed", "passed", "not_done", "passed", "withdrawn"]):
        _finish(db, player, "ac_ratios", state, 100 + n)
    assert not careers.career(db, player)["review_open"]              # four failures in seven
    _finish(db, player, "ac_ratios", "failed", 108)
    mine = careers.career(db, player)
    assert mine["review_open"]
    standing = careers.review_standing(db, player, mine)
    assert standing["finished"] == 0 and "Pass 3 of your next 5" in standing["how_to_recover"]
    words = _dicts(db, "SELECT words FROM career_events WHERE player_id = %s AND kind = 'review_opened'", (player,))[0]["words"]
    assert "5 of your last 8" in words
    level = mine["level"]
    for n, state in enumerate(["passed", "failed", "passed", "passed"]):
        _finish(db, player, "ac_ratios", state, 120 + n)
    mine = careers.career(db, player)
    assert not mine["review_open"] and mine["level"] >= level
    # The failures already answered for do not open a second review.
    _finish(db, player, "ac_ratios", "failed", 130)
    assert not careers.career(db, player)["review_open"]


def test_a_review_not_recovered_from_costs_one_level_and_no_money(db):
    player, account = accountant(db)
    careers.add_experience(db, player, "accountant", careers.experience_for(4) + 50, NOW9)
    cash = ledger.balance(db, account)
    for n in range(5):
        _finish(db, player, "ac_ratios", "failed", 100 + n)
    assert careers.career(db, player)["review_open"]
    for n, state in enumerate(["failed", "passed", "failed", "passed", "failed"]):
        _finish(db, player, "ac_ratios", state, 120 + n)
    mine = careers.career(db, player)
    assert not mine["review_open"] and mine["level"] == 3 and mine["experience"] == careers.experience_for(3)
    assert ledger.balance(db, account) == cash
    said = _dicts(db, "SELECT words FROM career_events WHERE player_id = %s AND kind = 'demoted'", (player,))[0]["words"]
    assert "Level 4 to Level 3" in said and "nothing else was lost" in said


def test_the_skill_tree_shows_what_has_been_learned_and_what_to_practise_again(db):
    player, _ = accountant(db)
    pass_one(db, player, NOW9)
    taken = objectives.accept(db, player, "ac_cash_flow", NOW9)
    objectives.submit(db, player, taken["id"], {"closing": 1}, NOW9)
    seen = objectives.board(db, player, NOW9)
    skills = {s["title"]: s for s in seen["skills"]}
    assert seen["coverage"] == {"learned": 1, "modules": 6} and len(skills) == 6
    assert skills["The lender's one-page view"]["stage"] == "learned" and not skills["The lender's one-page view"]["practise_again"]
    assert skills["Sort the quarter's cash"]["practise_again"] and skills["Sort the quarter's cash"]["stage"] == "not yet"
    assert not skills["Call the credit rating"]["open"]


def test_the_library_has_six_pieces_of_work_for_each_build_and_every_module_has_one():
    for build in careers.BUILDS:
        mine = [t for t in objectives.TEMPLATES.values() if t.build == build]
        assert len(mine) == 6 and len({t.module for t in mine}) == 6
        assert min(t.level for t in mine) == 1 and max(t.level for t in mine) <= 4
    names = " ".join(f"{t.module} {t.title} {t.idea}" for t in objectives.TEMPLATES.values()).upper()
    for body in ("CFA", "ACCA", "ICAN", "FRM", "CPA", "CRM"):       # exam bodies' names are never used in the game
        assert body not in names.replace("ICANT", "")


# ---------------------------------------------------------------------------
# The website's doors
# ---------------------------------------------------------------------------

def test_the_doors_are_shut_to_anybody_not_logged_in(client):
    for method, path in (("get", "/api/career"), ("get", "/api/objectives"), ("get", "/api/career/employers"),
                         ("get", "/api/career/banks"), ("get", "/api/desk/asset-manager"), ("get", "/api/desk/accountant")):
        assert getattr(client, method)(path).status_code == 401
    assert client.post("/api/objectives", json={"template": "ac_ratios"}).status_code == 401
    assert client.put("/api/career/build", json={"build": "accountant"}).status_code == 401


def test_the_website_cannot_send_extras_or_reach_another_players_work(db, client):
    other, _ = accountant(db, "bola")
    theirs = objectives.accept(db, other, "ac_ratios", NOW9)
    assert join(client, ADULT).status_code == 201
    assert client.put("/api/career/build", json={"build": "accountant", "level": 99}).status_code == 422
    assert client.put("/api/career/build", json={"build": "ceo"}).status_code == 422
    client.put("/api/career/build", json={"build": "accountant"})
    assert client.put("/api/career/job", json={"ticker": "IDC"}).status_code == 409           # no bank chosen yet
    assert client.post(f"/api/objectives/{theirs['id']}/hand-in", json={"answers": {"ebitda": 1}}).status_code == 409
    assert client.delete(f"/api/objectives/{theirs['id']}").status_code == 409
    assert state_of(db, theirs["id"])["state"] == "active"
    assert client.post("/api/objectives/1/hand-in", json={"answers": {"x" * 40: 1}}).status_code == 422
    assert all(o["id"] != theirs["id"] for o in client.get("/api/objectives").json()["active"])


def test_the_build_screens_have_their_figures(db, client):
    assert join(client, ADULT).status_code == 201
    client.put("/api/career/build", json={"build": "accountant"})
    client.put("/api/career/bank", json={"ticker": "IKB"})
    client.put("/api/career/job", json={"ticker": "IDC"})
    desk = client.get("/api/desk/accountant").json()
    assert desk["ticker"] == "IDC" and desk["is_employer"] and len(desk["quarters"]) == 8 and len(desk["companies"]) == 50
    latest = desk["quarters"][0]
    income = {k: int(v) for k, v in latest["income_statement"].items()}
    assert latest["ratios"]["Profit after tax ÷ sales (%)"] == round(income["net_profit"] * 100 / income["revenue"], 2)
    assert client.get("/api/desk/accountant?ticker=ZCB").json()["name"] == "Zuma Capital Bank"
    assert client.get("/api/desk/accountant?ticker=QQQ").status_code == 404
    mine = client.get("/api/desk/asset-manager").json()
    assert int(mine["total_kobo"]) == int(mine["cash_kobo"]) == naira(data.GRANT_ON_JOINING_NAIRA)
    assert [a["label"] for a in mine["allocation"]] == ["Cash"] and mine["allocation"][0]["share_bps"] == 10_000


def test_the_ticker_says_which_shares_have_not_traded_today(db, client):
    assert join(client, ADULT).status_code == 201
    seen = client.get("/api/market/ticker").json()
    assert seen["shares"] and all(s["traded_today"] is False for s in seen["shares"])
