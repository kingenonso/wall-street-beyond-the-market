"""The world on day one: the institutions, the 40 companies and the opening money.

Stage 2 checklist items 4, 6, 7 and 8.
"""

from __future__ import annotations

from collections import Counter

import pytest

import psycopg
from psycopg.rows import dict_row

from simulation import genesis, ledger
from simulation import world_data as data
from simulation.money import million_naira, naira
from tests.conftest import WORLD_START

# The company list from the design document, section 4.
BLUEPRINT = {
    "Commercial banks": {"Ikenga Bank", "Olumo Trust Bank", "Harmattan Bank", "Kainji Commercial Bank", "Zuma Capital Bank", "Obudu Bank",
                         "Sahel Crest Microfinance Bank"},
    "Consumer goods, food and drinks": {"Adunni Foods", "Tamuno Breweries", "Zobo Royal Beverages", "Garki Flour Mills", "Ayo Dairy", "Amaka Household Products"},
    "Oil and gas": {"Opobo Petroleum", "Brass River Energy", "Delta Creek Gas", "Okrika Refining & Marketing"},
    "Telecoms": {"Gangan Mobile", "Ekwe Communications", "Sango Networks", "Lekki Fibre Networks"},
    "Cement and building materials": {"Idanre Cement", "Kogi Ridge Cement", "Aso Blocks & Aggregates"},
    "Agriculture": {"Ofada Farms", "Sokoto Plains Agro", "Ikom Cocoa Estates", "Benue Harvest Foods"},
    "Real estate and construction": {"Eyo Properties", "Gidan Construction", "Ulo Estates", "Zuma Rock Hotels"},
    "Manufacturing and industrial": {"Ariaria Industries", "Dala Steel Works", "Onitsha Packaging", "Kainji Textiles", "Calabar Paper Mills",
                                     "Niger Bridge Steel"},
    "Media houses": {"The Lagoon Herald", "Ogene News Network", "The Naira Ledger"},
    "Insurance": {"Agbada Assurance", "Kuka Insurance"},
    "Power and utilities": {"Amadioha Power", "Jos Plateau Electric", "Ibom Solar Power"},
    "Transport and logistics": {"Danfo Logistics", "Lokoja Freight & Shipping", "Bonny Tide Shipping", "Oguta Airways"},
}


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def test_all_50_companies_exist_with_the_blueprint_names_and_sectors(db):
    rows = db.execute("SELECT s.name, c.name FROM companies c JOIN sectors s ON s.code = c.sector").fetchall()
    found: dict[str, set] = {}
    for sector, company in rows:
        found.setdefault(sector, set()).add(company)
    assert len(rows) == 50
    assert found == BLUEPRINT


def test_accounts_exist_for_companies_banks_government_and_the_prize_pool(db):
    kinds = Counter(k for (k,) in db.execute("SELECT kind FROM ledger_accounts").fetchall())
    assert kinds["company"] == 50                 # includes the banks
    assert kinds["government"] == 1
    assert kinds["prize_pool"] == 1
    assert kinds["central_bank"] == 1
    banks = db.execute(
        "SELECT count(*) FROM companies c JOIN ledger_accounts a ON a.id = c.account_id WHERE c.sector = 'banking'"
    ).fetchone()[0]
    assert banks == 7                             # six commercial banks and one microfinance bank
    for code in (ledger.TREASURY, ledger.PRIZE_POOL, ledger.CENTRAL_BANK, ledger.PUBLIC):
        assert ledger.account_id(db, code)


def test_every_naira_at_the_start_was_issued_by_the_central_bank(db):
    issued = ledger.amount_in_existence(db)
    held = db.execute(
        "SELECT sum(balance) FROM ledger_balances b JOIN ledger_accounts a ON a.id = b.account_id"
        " WHERE b.asset = 'NGN' AND a.code IS DISTINCT FROM 'central_bank'"
    ).fetchone()[0]
    assert issued == held > 0
    assert ledger.balance(db, ledger.account_id(db, ledger.TREASURY)) == million_naira(data.TREASURY_OPENING_M)
    assert ledger.balance(db, ledger.account_id(db, ledger.PRIZE_POOL)) == 0


def test_every_opening_balance_sheet_balances(db):
    for r in _dicts(db, "SELECT r.*, c.name, c.account_id FROM company_results r JOIN companies c ON c.id = r.company_id WHERE r.period = 0"):
        assert r["total_assets"] == r["cash"] + r["customer_loans"] + r["loans_to_companies"] + r["fixed_assets"], r["name"]
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"], r["name"]
        assert r["total_equity"] > 0, r["name"]
        assert r["cash"] == ledger.balance(db, r["account_id"]), r["name"]       # cash is what the ledger says


def test_every_company_has_statements_shares_owners_debts_and_a_rating(db):
    for c in _dicts(db, "SELECT * FROM companies"):
        report = _dicts(db, "SELECT * FROM company_reports WHERE company_id = %s AND period = 0", (c["id"],))[0]
        assert set(report["figures"]) == {"income_statement", "cash_flow", "balance_sheet", "notes"}
        assert report["credit_rating"] in ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")
        assert report["rating_reasons"]

        # Shares in issue equal what the owners hold between them.
        in_issue = ledger.amount_in_existence(db, c["share_asset"])
        held = db.execute(
            "SELECT sum(balance), count(*) FROM ledger_balances WHERE asset = %s AND balance > 0", (c["share_asset"],)
        ).fetchone()
        assert in_issue == held[0] > 0, c["name"]
        assert held[1] == 3                        # founders, institutions, small investors
        assert report["figures"]["notes"]["shares_in_issue"] == in_issue


def test_debts_have_a_lender_a_rate_and_a_repayment_date(db):
    debts = _dicts(
        db,
        "SELECT d.*, c.sector, a.kind AS lender_kind, lc.sector AS lender_sector FROM company_debts d"
        " JOIN companies c ON c.id = d.company_id JOIN ledger_accounts a ON a.id = d.lender_account_id"
        " LEFT JOIN companies lc ON lc.account_id = d.lender_account_id",
    )
    assert len(debts) > 30
    for d in debts:
        assert d["annual_rate_bps"] > 0
        # Two companies begin with a loan already past its repayment date (period 0).
        assert d["maturity_period"] > 0 or d["name"].startswith("overdue loan")
        if d["kind"] == "bank_loan":
            assert d["lender_sector"] == "banking"          # bank loans are owed to one of the six banks
        else:
            assert d["lender_kind"] == "npc_investors"       # bonds are held by investors
    borrowers = {d["company_id"] for d in debts}
    non_financial = db.execute("SELECT count(*) FROM companies WHERE sector NOT IN ('banking', 'insurance')").fetchone()[0]
    assert len(borrowers) == non_financial

    # What the banks say they have lent equals what the companies say they owe them.
    lent = db.execute("SELECT sum(loans_to_companies) FROM company_results WHERE period = 0").fetchone()[0]
    owed = db.execute("SELECT sum(principal_outstanding) FROM company_debts WHERE kind = 'bank_loan'").fetchone()[0]
    assert lent == owed


def test_creating_the_world_twice_changes_nothing(db):
    before = db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0], ledger.amount_in_existence(db)
    assert genesis.create_world(db, WORLD_START) is False
    assert (db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0], ledger.amount_in_existence(db)) == before
    assert db.execute("SELECT count(*) FROM companies").fetchone()[0] == 50


def test_a_player_from_before_the_ledger_existed_is_given_an_account_and_starting_cash(db):
    player_id = db.execute(
        "INSERT INTO players (email, email_key, display_name, display_name_key, password_hash, adult_confirmed_at)"
        " VALUES ('early@example.com', 'early@example.com', 'Early', 'early', 'x', now()) RETURNING id"
    ).fetchone()[0]
    money_before = ledger.amount_in_existence(db)

    genesis.create_world(db, WORLD_START)
    genesis.create_world(db, WORLD_START)          # running it again must not pay twice

    account = ledger.player_account_id(db, player_id)
    assert ledger.balance(db, account) == naira(500_000)
    assert ledger.amount_in_existence(db) == money_before     # paid by the Treasury, not created


# ---------------------------------------------------------------------------
# The ten weaker companies and the five head-office locations (owner, 2 October 2026).
# ---------------------------------------------------------------------------

def test_head_offices_are_spread_over_five_locations_including_aba_and_kano(db):
    by_city = dict(db.execute("SELECT headquarters, count(*) FROM companies GROUP BY headquarters").fetchall())
    assert set(by_city) == {"Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"}
    assert by_city["Aba"] == 2 and by_city["Kano"] == 3
    homes = dict(db.execute("SELECT name, headquarters FROM companies").fetchall())
    assert homes["Kainji Textiles"] == "Kano" and homes["Sahel Crest Microfinance Bank"] == "Kano"
    assert homes["Niger Bridge Steel"] == "Aba" and homes["Calabar Paper Mills"] == "Aba"


def test_two_companies_begin_the_game_already_in_default(db):
    rated = dict(db.execute(
        "SELECT c.name, r.credit_rating FROM company_reports r JOIN companies c ON c.id = r.company_id WHERE r.period = 0"
    ).fetchall())
    assert rated["Bonny Tide Shipping"] == "D" and rated["Kainji Textiles"] == "D"
    assert sorted(name for name, rating in rated.items() if rating == "D") == ["Bonny Tide Shipping", "Kainji Textiles"]


def test_three_companies_begin_the_game_behind_on_their_bills(db):
    rated = dict(db.execute(
        "SELECT c.name, r.credit_rating FROM company_reports r JOIN companies c ON c.id = r.company_id WHERE r.period = 0"
    ).fetchall())
    for name in ("Zuma Rock Hotels", "Oguta Airways", "Calabar Paper Mills"):
        assert rated[name] == "CCC", name


def test_a_troubled_start_still_balances_and_explains_itself(db):
    for r in _dicts(db, "SELECT r.*, c.name FROM company_results r JOIN companies c ON c.id = r.company_id"
                        " WHERE r.period = 0 AND (r.principal_overdue > 0 OR r.payables > 0)"):
        assert r["total_assets"] == r["total_liabilities"] + r["total_equity"], r["name"]
        assert r["total_equity"] > 0, r["name"]
        assert r["drivers"]["notes"], r["name"]              # the filing says why it is in trouble


def test_the_worlds_secret_is_set_and_can_never_be_changed(db):
    assert db.execute("SELECT fortune_seed FROM world_state").fetchone()[0] == "a-fixed-seed-so-tests-repeat"
    with pytest.raises(Exception) as refused:
        db.execute("UPDATE world_state SET fortune_seed = 'one-i-chose'")
    assert refused.value.diag.constraint_name == "world_is_permanent"
