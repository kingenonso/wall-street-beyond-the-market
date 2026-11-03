"""The talent and funds stage, Part 4c: six new industries.

Medicines and healthcare, groceries and retail, technology and payments, film and entertainment, solid
minerals and mining, and fertilisers and agro-chemicals: twenty-four companies, six baskets on the exchange,
eight new kinds of event, and one new piece of work for each of the players' builds.

Every test here is named as the item in `docs/PART_4C_CHECKLIST.md` names it, so the stage report can tick
each item against its test. The sections follow the checklist's own: A the world, B how the economy moves
them, C news and events, D the exchange, E work for the builds, F what the player sees, G trouble, H the
loophole check.
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import abroad, careers, corporate, events
from simulation import indexes, insight, ledger, marketview, news, objectives, objectives_industries, objectives_more
from simulation import private
from simulation import world_data as data
from simulation.money import BPS
from tests.conftest import after_quarters, money_accounted_for
from tests.test_careers import NOW9, professional
from tests.test_market import OPEN

NEW = ("pharma", "retail", "technology", "entertainment", "mining", "fertiliser")

# The twenty-four companies, exactly as the owner approved them on 3 November 2026 in
# `docs/PART_4C_NEW_INDUSTRIES_PROPOSAL.md`: ticker -> (name, industry, headquarters, opening revenue in
# millions, listed). This is the stage's contract with the owner, so it is written out rather than read
# back from the catalogue the code builds from.
APPROVED = {
    "OGP": ("Ogbomoso Pharma", "pharma", "Lagos", 95_000, True),
    "OVP": ("Osun Valley Pharmaceuticals", "pharma", "Lagos", 210_000, True),
    "YBM": ("Yaba Medicare", "pharma", "Abuja", 140_000, True),
    "ILD": ("Ilesa Diagnostics", "pharma", "Port Harcourt", 28_000, False),
    "WSG": ("Wuse Grocers", "retail", "Abuja", 260_000, True),
    "GBF": ("Gboko Fresh Markets", "retail", "Kano", 75_000, True),
    "ADK": ("Aduke Stores", "retail", "Lagos", 22_000, False),
    "OTG": ("Otukpo Grocers", "retail", "Aba", 45_000, True),
    "ZGP": ("Zanga Pay", "technology", "Lagos", 180_000, True),
    "OJD": ("Oja Digital", "technology", "Lagos", 120_000, True),
    "NMS": ("Nembe Softworks", "technology", "Abuja", 38_000, True),
    "IKS": ("Ikere Cloud Services", "technology", "Lagos", 26_000, False),
    "GDS": ("Gidi Screen", "entertainment", "Lagos", 88_000, True),
    "ILP": ("Ilorin Pictures", "entertainment", "Abuja", 34_000, True),
    "UFS": ("Uyo Film Studios", "entertainment", "Port Harcourt", 15_000, True),
    "OTS": ("Otun Sounds", "entertainment", "Lagos", 9_000, False),
    "KDG": ("Kaduna Goldfields", "mining", "Abuja", 145_000, True),
    "BTM": ("Bauchi Tin Mines", "mining", "Kano", 62_000, True),
    "ECM": ("Enugu Coal Mines", "mining", "Aba", 40_000, True),
    "OMM": ("Omu Minerals", "mining", "Lagos", 18_000, False),
    "WRU": ("Warri Urea", "fertiliser", "Port Harcourt", 195_000, True),
    "GMF": ("Gombe Fertilisers", "fertiliser", "Kano", 110_000, True),
    "KAC": ("Katsina Agro-Chemicals", "fertiliser", "Abuja", 30_000, True),
    "ICS": ("Ijebu Crop Science", "fertiliser", "Aba", 21_000, False),
}

# The eight kinds of event this part adds, and what each is allowed to touch.
NEW_EVENTS = {
    "drug_shortage": ("sector", ("pharma",)),
    "payments_outage": ("sector", ("technology",)),
    "bumper_harvest": ("sector", ("fertiliser",)),
    "bad_batch": ("company", ("pharma",)),
    "mine_accident": ("company", ("mining",)),
    "seam_runs_out": ("company", ("mining",)),
    "film_flops": ("company", ("entertainment",)),
    "film_hit": ("company", ("entertainment",)),
}


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
    return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def _company(db, ticker):
    return _one(db, "SELECT * FROM companies WHERE ticker = %s", (ticker,))


def whole(db):
    """The books balance and no naira is unaccounted for: the check every test in this file ends with."""
    assert ledger.audit(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


def imported_share_of_sales(sector: str) -> int:
    """What a kind of company ends up paying abroad each quarter, as a share of its sales: the same two
    tables the engine reads, added up the same way it adds them (`abroad` and `economy.companies_buy_inputs`)."""
    goods = sum(bps for supplier, bps in data.INPUTS.get(sector, {}).items() if supplier in data.IMPORTABLE_SUPPLIES)
    return data.IMPORT_SHARE_BPS.get(sector, 0) * goods // BPS


# ---------------------------------------------------------------------------
# A. The world
# ---------------------------------------------------------------------------

@pytest.mark.world("fresh")
def test_the_world_has_the_six_new_industries(db):
    """Item 1: six industries in the catalogue, each with its own balance-sheet shape."""
    codes = [s.code for s in data.SECTORS]
    assert set(NEW) <= set(codes) and len(codes) == len(set(codes)) == 21
    shapes = {s.code: s for s in data.SECTORS}

    # Each is a real shape, not a copy of another: the six differ from one another and from the twelve
    # industries that were already there.
    fingerprints = {(s.cost_of_sales_bps, s.opex_bps, s.fixed_assets_x, s.debt_x, s.payout_bps) for s in data.SECTORS}
    assert len(fingerprints) == len(data.SECTORS)

    # What each shape says, in the terms the proposal gave the owner.
    assert shapes["retail"].cost_of_sales_bps == max(s.cost_of_sales_bps for s in data.SECTORS)   # the thinnest margin
    assert shapes["technology"].revenue_growth_bps == max(s.revenue_growth_bps for s in data.SECTORS)   # the fastest growing
    assert shapes["technology"].payout_bps == min(s.payout_bps for s in data.SECTORS)             # and pays out least
    assert shapes["mining"].fixed_assets_x == max(shapes[c].fixed_assets_x for c in NEW)          # machines and ground
    assert shapes["fertiliser"].fixed_assets_x > shapes["retail"].fixed_assets_x                  # a plant against a shop
    for code in NEW:
        sector = shapes[code]
        assert 0 < sector.cost_of_sales_bps < 10_000, code
        assert sector.opex_bps > 0 and sector.debt_x >= 0, code
        assert len(sector.season_bps) == 4, code                  # a year's four quarters

    # And the world was made with them: a row in the database, in the same order the catalogue gives.
    in_db = _rows(db, "SELECT code, name FROM sectors ORDER BY sort_order")
    assert [r["code"] for r in in_db] == codes
    assert {r["code"]: r["name"] for r in in_db}["technology"] == "Technology and payments"


@pytest.mark.world("fresh")
def test_the_new_companies_are_counted_and_placed(db):
    """Item 2: twenty-four companies, each with a headquarters, an opening revenue, a bank, and listed or private."""
    catalogue = {c.ticker: c for c in data.COMPANIES if c.sector in NEW}
    assert len(catalogue) == 24
    assert sum(1 for c in catalogue.values() if c.listed) == 18
    assert sum(1 for c in catalogue.values() if not c.listed) == 6

    for ticker, (name, sector, headquarters, revenue, listed) in APPROVED.items():
        company = catalogue[ticker]
        assert (company.name, company.sector, company.headquarters, company.yearly_revenue_m, company.listed) \
            == (name, sector, headquarters, revenue, listed), ticker
        # One private company in each industry, no more and no less: a buyer who digs has one target a trade.
        assert any(c.listed for c in catalogue.values() if c.sector == sector), sector
    assert sorted(c.sector for c in catalogue.values() if not c.listed) == sorted(NEW)

    # Each has a bank that holds its loan, and the bank is one of the listed banks.
    banks = {c.ticker for c in data.COMPANIES if c.sector == "banking" and c.listed}
    assert all(c.lender in banks for c in catalogue.values())

    # Every one is in the world, at its headquarters, trading, with its own account.
    for ticker, (name, sector, headquarters, revenue, listed) in APPROVED.items():
        row = _company(db, ticker)
        assert row and row["name"] == name and row["sector"] == sector, ticker
        assert row["headquarters"] == headquarters and row["listed"] is listed, ticker
        assert row["status"] == "trading" and row["account_id"] and row["share_asset"] == f"SHR-{ticker}", ticker

    # No ticker or name anywhere in the catalogue repeats: a duplicate would make one company shadow another.
    tickers = [c.ticker for c in data.COMPANIES]
    names = [c.name for c in data.COMPANIES]
    assert len(tickers) == len(set(tickers)) == 104
    assert len(names) == len(set(names))


@pytest.mark.world("fresh")
def test_the_new_companies_books_balance(db):
    """Item 3: every new company's opening accounts balance, its loan sits with a named bank, and no naira
    appears without a recorded payer."""
    for ticker in APPROVED:
        row = _one(db, "SELECT r.* FROM company_results r JOIN companies c ON c.id = r.company_id"
                       " WHERE c.ticker = %s AND r.period = 0", (ticker,))
        assert row, ticker
        assert row["total_assets"] == row["total_liabilities"] + row["total_equity"], ticker
        assert row["total_assets"] == row["cash"] + row["customer_loans"] + row["loans_to_companies"] \
            + row["fixed_assets"] + row["investments"], ticker
        assert row["total_liabilities"] == row["borrowings"] + row["payables"] + row["customer_funds"], ticker
        assert row["total_equity"] == row["share_capital"] + row["retained_earnings"], ticker
        assert row["revenue"] > 0 and row["cash"] > 0, ticker

        # Its loan is owed to a named bank, and the bank's books show the other side of it.
        debts = _rows(db, "SELECT d.*, a.name AS lender FROM company_debts d JOIN ledger_accounts a ON a.id = d.lender_account_id"
                          " JOIN companies c ON c.id = d.company_id WHERE c.ticker = %s AND d.kind = 'bank_loan'", (ticker,))
        assert debts, ticker
        for debt in debts:
            assert debt["principal_outstanding"] > 0 and debt["lender"]
            assert _one(db, "SELECT 1 AS x FROM companies WHERE name = %s", (debt["lender"],)), (ticker, debt["lender"])

    whole(db)


@pytest.mark.world("fresh")
def test_the_new_industries_sell_into_the_economy(db):
    """Item 4: medicines and groceries to households, fertiliser to farms, mining abroad for dollars,
    technology to everyone."""
    sales = {r["sector"]: r for r in _rows(db, "SELECT * FROM sector_demand")}
    assert set(NEW) <= set(sales)

    # The shops and the medicine makers live off households: no other industry buys from them, so nearly
    # everything they sell is sold to people.
    for code in ("pharma", "retail", "technology"):
        assert sales[code]["household_bps"] > 0, code
        assert sales[code]["household_bps"] > sales[code]["government_bps"], code

    # The farms buy the fertiliser: a real buyer, recorded in the same table every other industry uses.
    farm = _one(db, "SELECT bps FROM sector_inputs WHERE buyer = 'agriculture' AND supplier = 'fertiliser'")
    assert farm and farm["bps"] > 0
    farms_spend = _one(db, "SELECT sum(bps) AS n FROM sector_inputs WHERE buyer = 'agriculture'")["n"]
    assert farm["bps"] * 4 >= farms_spend                       # about a quarter of what a farm spends on supplies

    # The miners sell for dollars: they are on the list of what the country sells abroad, beside farms and factories.
    assert data.NON_OIL_EXPORTS.get("mining", 0) > 0
    assert sum(data.NON_OIL_EXPORTS.values()) == BPS

    # Every one of the six has somebody to sell to: a share of its sales reaches households, however small.
    for code in NEW:
        assert sales[code]["household_bps"] > 0, code


@pytest.mark.world("fresh")
def test_a_new_world_starts_with_the_new_industries(db):
    """Item 5: a fresh world begins with the new companies already trading."""
    trading = _rows(db, "SELECT ticker, listed FROM companies WHERE status = 'trading'")
    tickers = {r["ticker"] for r in trading}
    assert set(APPROVED) <= tickers

    # The eighteen listed ones have a share to buy on the exchange; the six private ones have none.
    instruments = {r["ticker"] for r in _rows(db, "SELECT c.ticker FROM market_instruments m JOIN companies c ON c.id = m.company_id")}
    assert {t for t, row in APPROVED.items() if row[4]} <= instruments
    assert not ({t for t, row in APPROVED.items() if not row[4]} & instruments)

    # The six baskets are live on the exchange from the first day.
    live = {r["code"] for r in _rows(db, "SELECT code FROM market_indexes WHERE status = 'live' AND owner_id IS NULL")}
    assert {"PHARMA", "RETAIL", "TECH", "FILM", "MINING", "FERT"} <= live
    whole(db)


# ---------------------------------------------------------------------------
# B. How the economy moves them
# ---------------------------------------------------------------------------

def test_the_new_industries_lean_on_the_right_forces():
    """Item 6: each leans on the forces its business answers to."""
    lean = data.SECTOR_FACTOR_LOADINGS
    assert lean["retail"]["economy"] >= max(v.get("economy", 0) for v in lean.values())
    assert lean["fertiliser"]["energy"] >= 0.6 and lean["fertiliser"]["farming"] > 0     # gas, and the farms
    assert lean["mining"]["energy"] > 0                                                 # machines run on fuel
    assert lean["technology"]["economy"] > 0
    # And no industry claims more than the whole of its own luck: the squares of a row add up to less than one.
    for code in NEW:
        assert sum(v * v for v in lean[code].values()) < 1, code


def test_a_weak_naira_costs_the_medicine_makers():
    """Item 7: the medicine makers buy their ingredients abroad, so a weak naira raises their costs."""
    shares = {code: imported_share_of_sales(code) for code in data.INPUTS}
    assert shares["pharma"] == max(shares.values())
    assert shares["pharma"] >= shares["manufacturing"] * 2                     # not a little more: the most of any industry
    # And the machinery is the one that already exists: the usual share, the switch that makes them buy less
    # when goods abroad are dear, and the price they pay for what they cannot do without.
    usual = data.IMPORT_SHARE_BPS["pharma"]
    assert usual == max(data.IMPORT_SHARE_BPS.values())
    at_par = abroad.import_share_bps("pharma", BPS)
    assert at_par == BPS // 2                                                   # the most any industry may buy abroad
    dear = abroad.import_share_bps("pharma", 13_000)                            # goods abroad 30% dearer
    assert 0 < dear < at_par                                                    # they buy less of it, and pay more for the rest


def test_a_weak_naira_helps_the_miners():
    """Item 8: the miners sell for dollars and pay in naira."""
    assert data.NON_OIL_EXPORTS["mining"] > 0
    # A weak naira raises what a dollar buys at home, so a miner's dollar sales are worth more naira, while
    # its wages and its fuel are still paid in naira. The same switch the farms and factories already use.
    assert data.EXPORT_SWITCH_BPS > 0
    assert imported_share_of_sales("mining") < imported_share_of_sales("pharma")   # it buys less abroad than it sells


def test_the_fertiliser_makers_follow_the_gas_price():
    """Item 9: gas is most of the fertiliser makers' cost, which ties them to oil and gas."""
    inputs = data.INPUTS["fertiliser"]
    assert inputs["oil_gas"] == max(inputs.values())
    assert inputs["oil_gas"] * 2 > sum(inputs.values())                  # more than everything else put together
    # It is a customer of the oil and gas industry, in the same table every other buyer uses.
    paid_to_gas = {code: data.INPUTS.get(code, {}).get("oil_gas", 0) for code in data.INPUTS}
    assert paid_to_gas["fertiliser"] == max(paid_to_gas.values())
    # And its fortune follows the same force the oil price moves (energy), not a new one of its own.
    assert data.SECTOR_FACTOR_LOADINGS["fertiliser"]["energy"] >= data.SECTOR_FACTOR_LOADINGS["oil_gas"]["energy"] * 0.7


def test_the_shops_follow_household_money():
    """Item 10: the shops' sales follow wages and household spending."""
    assert data.SECTOR_FACTOR_LOADINGS["retail"]["economy"] >= max(v.get("economy", 0) for v in data.SECTOR_FACTOR_LOADINGS.values())
    # A shop buys the goods it sells and pays to move them: its costs are other industries' sales, not wages.
    assert data.INPUTS["retail"]["consumer"] + data.INPUTS["retail"]["agriculture"] >= sum(data.INPUTS["retail"].values()) * 3 // 4


def test_rising_rates_hurt_the_technology_shares_most():
    """Item 11: technology leans hardest on the long interest rate of any industry."""
    money = {code: lean.get("money", 0) for code, lean in data.SECTOR_FACTOR_LOADINGS.items()}
    assert money["technology"] == max(money.values())
    assert money["technology"] > money["banking"]                     # dear money hurts the borrower, not the lender
    assert money["technology"] >= 2 * sorted(money.values())[-2]      # and by more than the runner-up


def test_each_new_industry_has_a_home_city():
    """Item 12: each runs cheaper in its natural city, on the table the existing industries already use."""
    for code in NEW:
        favours = {city: cost for (sector, city), cost in data.SECTOR_FIT.items() if sector == code}
        assert favours, code
        cheapest = min(favours.values())
        assert cheapest < 0, code                                     # a saving, not a penalty
        home = min(favours, key=favours.get)
        assert home in {loc.name for loc in data.LOCATIONS}, code
    # The medicines settle by the ports, the shops in the biggest market, the miners on tin country.
    assert min((cost, city) for (sector, city), cost in data.SECTOR_FIT.items() if sector == "pharma")[1] == "Lagos"
    assert min((cost, city) for (sector, city), cost in data.SECTOR_FIT.items() if sector == "mining")[1] == "Kano"
    assert min((cost, city) for (sector, city), cost in data.SECTOR_FIT.items() if sector == "fertiliser")[1] == "Port Harcourt"


def test_the_miners_may_borrow_in_dollars():
    """Item 13: the miners may borrow in dollars through Eurobonds, as the largest oil and telecoms companies do."""
    borrowers = dict(data.FX_COMPANY_EUROBONDS)
    assert borrowers.get("mining") == 2
    assert set(borrowers) == {"oil_gas", "telecoms", "mining"}
    # Only the largest of a kind borrow this way, which is what keeps a small miner out of the dollar market.
    assert data.FX_EUROBOND_TERM_QUARTERS > 0 and data.FX_EUROBOND_SPREAD_BPS > 0


def test_the_new_industries_can_hedge_fuel():
    """Item 14: the miners and fertiliser makers can hedge fuel, as transport and power already do."""
    assert {"mining", "fertiliser"} <= set(data.HEDGE_BUYERS_SECTORS)
    assert {"aviation", "transport", "shipping", "power"} <= set(data.HEDGE_BUYERS_SECTORS)   # the older ones unchanged
    assert data.HEDGE_BUY_SHARE_BPS > 0 and data.HEDGE_MOST_CONTRACTS > 0


def test_who_may_issue_preferred_shares():
    """Item 15: technology may issue preferred shares."""
    assert "technology" in data.PREFERRED_SECTORS
    assert {"banking", "insurance", "telecoms", "power", "real_estate"} <= set(data.PREFERRED_SECTORS)
    # A miner may not: nothing in this part opened that door.
    for code in ("mining", "fertiliser", "retail", "entertainment", "pharma"):
        assert code not in data.PREFERRED_SECTORS, code


# --- END OF PART ONE ---
