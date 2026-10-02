"""What players can see of the companies: the list and each company's filed reports.

Stage 2 checklist items 11 and 12.
"""

from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

from simulation.money import naira

pytestmark = pytest.mark.world("eight")


def test_the_list_shows_all_50_companies_in_their_12_sectors(client, player):
    sectors = client.get("/api/companies").json()["sectors"]
    assert [s["name"] for s in sectors][:3] == ["Commercial banks", "Consumer goods, food and drinks", "Oil and gas"]
    assert len(sectors) == 12
    assert sum(len(s["companies"]) for s in sectors) == 50
    assert [len(s["companies"]) for s in sectors] == [7, 6, 4, 4, 3, 4, 4, 6, 3, 2, 3, 4]

    ikenga = next(c for c in sectors[0]["companies"] if c["ticker"] == "IKB")
    assert ikenga["name"] == "Ikenga Bank"
    assert ikenga["period_label"] == "Year 2 Q4"
    assert ikenga["credit_rating"] in ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "D")
    assert int(ikenga["revenue_kobo"]) > 0 and isinstance(ikenga["revenue_kobo"], str)
    assert isinstance(ikenga["revenue_change_bps"], int)


def test_a_company_page_shows_its_accounts_quarter_by_quarter(client, player):
    body = client.get("/api/companies/IDC").json()
    assert (body["name"], body["sector"], body["headquarters"]) == ("Idanre Cement", "Cement and building materials", "Lagos")

    reports = body["reports"]
    assert [r["period_label"] for r in reports] == [
        "Year 1 Q1", "Year 1 Q2", "Year 1 Q3", "Year 1 Q4", "Year 2 Q1", "Year 2 Q2", "Year 2 Q3", "Year 2 Q4",
    ]
    latest = reports[-1]
    assert set(latest["figures"]) == {"income_statement", "cash_flow", "balance_sheet", "notes"}
    sheet = {k: int(v) for k, v in latest["figures"]["balance_sheet"].items()}
    assert sheet["total_assets"] == sheet["total_liabilities"] + sheet["total_equity"]
    assert latest["rating_reasons"] and latest["version"] == 1 and latest["amended"] is False
    assert latest["figures"]["notes"]["why_revenue"][0].startswith("Idanre Cement's sales have been growing about")
    income = {k: int(v) for k, v in latest["figures"]["income_statement"].items()}
    assert income["ebitda"] == income["operating_profit"] + income["depreciation"]          # EBITDA is filed

    # Shares, owners and debts.
    assert int(body["shares_in_issue"]) == sum(int(o["shares"]) for o in body["owners"])
    assert sum(o["share_bps"] for o in body["owners"]) in range(9_998, 10_001)
    debts = latest["figures"]["notes"]["borrowings"]
    assert {d["kind"] for d in debts} == {"bank_loan", "bond"}
    assert all(d["annual_rate_bps"] > 0 and d["maturity_period"] > 8 for d in debts)


def test_more_or_fewer_quarters_can_be_asked_for(client, player):
    assert len(client.get("/api/companies/IDC?periods=3").json()["reports"]) == 3
    assert len(client.get("/api/companies/IDC?periods=40").json()["reports"]) == 9      # includes the opening position


def test_every_amount_crosses_as_whole_kobo_in_text(client, player):
    figures = client.get("/api/companies/GGM").json()["reports"][-1]["figures"]
    for section in ("income_statement", "cash_flow", "balance_sheet"):
        for line, value in figures[section].items():
            assert isinstance(value, str) and int(value) == int(value), line


def test_an_unknown_company_is_not_found(client, player):
    assert client.get("/api/companies/ZZZ").status_code == 404
    assert client.get("/api/companies/' OR 1=1 --").status_code == 404


@pytest.mark.parametrize("periods", ["0", "-1", "41", "999999999999", "1.5", "abc"])
def test_a_silly_number_of_quarters_is_refused(client, player, periods):
    """Loophole question 7 (bad numbers)."""
    assert client.get(f"/api/companies/IDC?periods={periods}").status_code == 422


def test_companies_need_a_login(client):
    """Loophole question 5 (permissions)."""
    assert client.get("/api/companies").status_code == 401
    assert client.get("/api/companies/IDC").status_code == 401
    assert client.get("/api/world/status").status_code == 401
    assert client.get("/api/me/movements").status_code == 401


def test_world_status_names_the_latest_closed_quarter(client, player):
    assert client.get("/api/world/status").json() == {
        "companies": 50, "last_closed_period": 8, "last_closed_label": "Year 2 Q4",
    }


def test_players_are_shown_the_reported_record_never_the_true_one(client, player, db):
    """Loophole question 6 (hidden information), and the base for fraud in Stage 11.

    A false, amended report is filed. The page must show the filing, while the
    true record stays untouched and unseen.
    """
    company_id, = db.execute("SELECT id FROM companies WHERE ticker = 'ONP'").fetchone()
    honest = db.execute("SELECT figures FROM company_reports WHERE company_id = %s AND period = 8", (company_id,)).fetchone()[0]
    true_revenue = honest["income_statement"]["revenue"]
    false = {**honest, "income_statement": {**honest["income_statement"], "revenue": true_revenue + naira(310_000_000)}}
    db.execute(
        "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
        " VALUES (%s, 8, 2, %s, 'A', %s, 'Company management')",
        (company_id, Jsonb(false), Jsonb(["Restated"])),
    )

    latest = client.get("/api/companies/ONP").json()["reports"][-1]

    assert int(latest["figures"]["income_statement"]["revenue"]) == true_revenue + naira(310_000_000)
    assert latest["amended"] is True and latest["version"] == 2
    assert db.execute("SELECT revenue FROM company_results WHERE company_id = %s AND period = 8", (company_id,)).fetchone()[0] == true_revenue


def test_nothing_private_leaks_through_the_company_pages(client, player):
    text = client.get("/api/companies").text + client.get("/api/companies/IKB").text
    for secret in ("ledger_totals", "base_revenue", "base_opex", "account_id", "password", "@example.com", "drivers"):
        assert secret not in text


def test_a_filing_from_before_ebitda_was_filed_still_shows_it(client, player, db):
    from psycopg.types.json import Jsonb
    company_id = db.execute("SELECT id FROM companies WHERE ticker = 'IDC'").fetchone()[0]
    figures = db.execute("SELECT figures FROM company_reports WHERE company_id = %s AND period = 8", (company_id,)).fetchone()[0]
    expected = figures["income_statement"].pop("ebitda")
    db.execute(
        "INSERT INTO company_reports (company_id, period, version, figures, credit_rating, rating_reasons, filed_by)"
        " VALUES (%s, 8, 2, %s, 'A', %s, 'Company management')", (company_id, Jsonb(figures), Jsonb(["Old style"])),
    )
    latest = client.get("/api/companies/IDC").json()["reports"][-1]
    assert latest["version"] == 2 and latest["figures"]["income_statement"]["ebitda"] == str(expected)
    listed = [c for s in client.get("/api/companies").json()["sectors"] for c in s["companies"] if c["ticker"] == "IDC"][0]
    assert listed["ebitda_kobo"] == str(expected)
