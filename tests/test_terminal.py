"""The terminal (owner, 15 November 2026): what the readout and the money map send.

Promises: every indicator carries its own record, a scale, where it stands on it, its usual range and what its move
means in words; inflation's range is what the Central Bank accepts; the money map is the published record of the last
closed quarter, city by city.

Loopholes: neither answer is given without a login; neither holds anything of a player's (the map is the quarter's
published totals; the readout's own-money chart is the reader's alone).
"""

from __future__ import annotations

import pytest

from simulation import world_data as data
from tests.conftest import ADULT, join

pytestmark = pytest.mark.world("eight")


def test_every_indicator_carries_its_record_its_scale_and_what_the_move_means(client):
    assert client.get("/api/readout").status_code == 401
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/readout").json()
    lines = {i["name"]: i for g in body["groups"] for i in g["indicators"]}
    assert set(lines) == {"Oil and gas", "Farm produce", "Metals", "Building materials", "Jobs", "Policy rate", "Inflation", "Confidence"}
    for name, line in lines.items():
        assert len(line["history"]) == 8, name                                  # eight quarters have closed
        assert line["low"] and line["high"], name
        assert 0 <= line["band_from_pct"] <= line["band_to_pct"] <= 100, name
        assert 0 <= line["position_pct"] <= 100, name
        # A figure that moved says what the move means; one that did not says nothing.
        assert bool(line["means"]) == bool(line["change_bps"]), name
        assert "kobo" not in str(line)
    # Inflation is set against what the Central Bank accepts, not against its own record.
    inflation = lines["Inflation"]
    assert inflation["band_words"] == "what the Central Bank accepts"
    low, high = float(inflation["low"].rstrip("%")), float(inflation["high"].rstrip("%"))
    accepted = ((data.INFLATION_TARGET_BPS - data.INFLATION_BAND_BPS) / 100, (data.INFLATION_TARGET_BPS + data.INFLATION_BAND_BPS) / 100)
    assert low <= accepted[0] and high >= accepted[1]
    assert lines["Metals"]["band_words"] == "the middle half of its own record"


def test_the_money_map_is_the_last_closed_quarters_published_record(client, db):
    assert client.get("/api/economy/flows").status_code == 401
    assert join(client, ADULT).status_code == 201
    body = client.get("/api/economy/flows").json()
    assert body["period"] == 8 and body["period_label"] == "Year 2 Q4" and body["capital"] == "Abuja"
    assert [c["name"] for c in body["cities"]] == ["Lagos", "Abuja", "Port Harcourt", "Aba", "Kano"]
    spent, taxed = db.execute("SELECT sum(spending)::bigint FROM household_results WHERE period = 8").fetchone()[0], \
        db.execute("SELECT sum(tax)::bigint FROM company_results WHERE period = 8").fetchone()[0]
    assert sum(int(c["spending_kobo"]) for c in body["cities"]) == spent
    assert sum(int(c["taxes_kobo"]) for c in body["cities"]) == taxed          # every company's head office is in one of the five
    assert all(int(c["government_kobo"]) >= 0 and c["jobs"] > 0 for c in body["cities"])
    # Nothing of a player's is in it: the player's own name and money appear nowhere.
    assert "Ada" not in str(body)
