"""The talent and funds stage, Part 4c: new industries at home.

Ten new industries (technology, fintech, healthcare, mining, retail,
entertainment, education, solar, pharmaceuticals, e-commerce) and 35 new
Nigerian companies. New worlds are born with them; worlds already running
gain them later, once the funding for that is built (a later part).
"""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import exchange, ledger
from simulation import world_data as data
from tests.conftest import after_quarters, money_accounted_for

HOME_SECTORS = ("tech", "fintech", "healthcare", "mining", "retail",
                "entertainment", "education", "solar", "pharma", "ecommerce")


def _one(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(sql, params).fetchall()
        return rows[0] if rows else None


def _rows(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def sound(db) -> None:
    assert exchange.check_books(db) == []
    assert ledger.audit(db) == []
    assert ledger.amount_in_existence(db) == money_accounted_for(db)


def test_new_worlds_are_born_with_the_ten_new_industries(db):
    assert {s.code for s in data.SECTORS} >= set(HOME_SECTORS)
    assert _one(db, "SELECT count(*) AS n FROM sectors")["n"] == len(data.SECTORS) == 25
    assert _one(db, "SELECT count(*) AS n FROM companies")["n"] == len(data.COMPANIES) == 115
    assert _one(db, "SELECT count(*) AS n FROM companies WHERE listed")["n"] == 70
    for code in HOME_SECTORS:
        assert _one(db, "SELECT 1 AS x FROM sectors WHERE code = %s", (code,)) is not None
        assert _one(db, "SELECT count(*) AS n FROM companies WHERE sector = %s", (code,))["n"] > 0
    sound(db)


@pytest.mark.world("eight")
def test_the_new_industries_trade_close_and_report_like_the_old_ones(db):
    from simulation import private, quarters
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    for code in HOME_SECTORS:
        companies = _rows(db, "SELECT * FROM companies WHERE sector = %s", (code,))
        assert companies
        for company in companies:
            result = _one(db, "SELECT * FROM company_results WHERE company_id = %s AND period = 9", (company["id"],))
            assert result["revenue"] > 0
            assert result["total_assets"] == result["total_liabilities"] + result["total_equity"]
            if company["listed"]:
                assert _one(db, "SELECT 1 AS x FROM market_instruments WHERE company_id = %s", (company["id"],)) is not None
            else:
                assert private.profile(db, company["id"]) is not None
    sound(db)


@pytest.mark.world("eight")
def test_the_new_industries_have_their_place_in_the_economy(db):
    for code in HOME_SECTORS:
        assert _one(db, "SELECT household_bps FROM sector_demand WHERE sector = %s", (code,))["household_bps"] > 0
        assert _one(db, "SELECT count(*) AS n FROM sector_inputs WHERE buyer = %s", (code,))["n"] >= 5
    sound(db)


def test_every_new_company_points_at_something_real(db):
    """The catalogue's cross-references hold: sectors, lenders, locations and wordings.
    (The news and company pages look sectors up by code and would crash on a missing one.)"""
    from simulation import news, private
    codes = {s.code for s in data.SECTORS}
    tickers = {c.ticker for c in data.COMPANIES}
    places = {loc.name for loc in data.LOCATIONS}
    assert len(codes) == 25 and len(tickers) == 115
    for company in data.COMPANIES:
        assert company.sector in codes, company.ticker
        assert company.headquarters in places, company.ticker
        assert company.lender is None or company.lender in tickers, company.ticker
    for code in HOME_SECTORS:
        assert code in news.SECTOR_WORDS, code
        assert code in private.ASSETS, code
        assert code in data.INPUTS, code
    sound(db)
