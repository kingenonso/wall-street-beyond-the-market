"""Private equity stage, part 1: the firm's requests, as a player would make them."""

from __future__ import annotations

import pytest
from psycopg.rows import dict_row

from simulation import empires, firm
from tests.conftest import ADULT, join
from tests.test_builds import pro
from tests.test_careers import NOW9

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def test_a_member_sees_the_firm_does_a_duty_and_never_sees_a_colleagues_player_number_or_an_answer(db, client):
    assert client.get("/api/firm").status_code == 401
    assert join(client, ADULT).status_code == 201
    outside = client.get("/api/firm").json()
    assert outside["firm"] is None and isinstance(outside["stake_offers"], list)
    assert client.put("/api/career/build", json={"build": "asset_manager"}).status_code == 200
    first = client.get("/api/empires").json()["directory"]["league"][0]
    assert client.post(f"/api/empires/{first['id']}/applications").status_code == 201
    # A colleague in the same empire.
    other, _ = pro(db, "investment_banker", "colleague")
    empires.apply(db, other, first["id"], NOW9)
    seen = client.get("/api/firm").json()["firm"]
    assert seen["name"] == first["name"] and not seen["is_head"] and not seen["player_run"]
    assert str(other) not in str(seen)                               # colleagues are named by seat, never by player number
    assert any(r["build"] == "investment_banker" and not r["you"] for r in seen["roster"])
    desk = next(d for d in seen["duties"]["desks"] if d["build"] == "asset_manager")
    assert desk["yours"] and desk["duties"]
    duty = next(d for d in desk["duties"] if d["yours"] and d["title"] == "Close the books")
    opened = client.post(f"/api/firm/duties/{duty['id']}/open")
    assert opened.status_code == 200, opened.text
    shown = opened.json()["firm"]
    assert "_truth" not in str(shown)
    mine = next(d for d in next(d for d in shown["duties"]["desks"] if d["build"] == "asset_manager")["duties"] if d["id"] == duty["id"])
    assert mine["opened"] and mine["terms"]["asks"]
    # Answers of the wrong shape are refused before they reach the desk.
    assert client.post(f"/api/firm/duties/{duty['id']}/hand-in", json={"answers": {"costs": "x" * 700}}).status_code == 422
    assert client.post(f"/api/firm/duties/{duty['id']}/hand-in", json={"answers": {}, "score": 100}).status_code == 422
    done = client.post(f"/api/firm/duties/{duty['id']}/hand-in", json={"answers": {"costs": 0, "profit": 0}})
    assert done.status_code == 200 and 0 <= done.json()["result"]["score"] <= 100
    again = client.post(f"/api/firm/duties/{duty['id']}/hand-in", json={"answers": {"costs": 0, "profit": 0}})
    assert again.status_code == 409
    # A duty of another desk, or a duty in another empire, is refused in words.
    lawyer_duty = _dicts(db, "SELECT id FROM desk_duties WHERE empire_id = %s AND build = 'investment_banker' LIMIT 1", (first["id"],))
    if lawyer_duty:
        assert client.post(f"/api/firm/duties/{lawyer_duty[0]['id']}/open").status_code == 409
    elsewhere = _dicts(db, "SELECT id FROM desk_duties WHERE empire_id <> %s LIMIT 1", (first["id"],))
    assert client.post(f"/api/firm/duties/{elsewhere[0]['id']}/open").status_code == 409
    # A computer-run empire's members do not vote; requests by player number are not accepted at all.
    assert client.post("/api/firm/votes", json={"kind": "treasury", "cash_least_bps": 0, "shares_most_bps": 10000}).status_code == 409
    assert client.put("/api/firm/titles", json={"member_id": str(other), "title": "deputy"}).status_code == 422
    assert client.put("/api/firm/titles", json={"seat_id": 1, "title": "deputy"}).status_code == 409
    # Everybody's public record can be read; it holds only what they signed and how it turned out.
    record = client.get(f"/api/people/{other}/record").json()
    assert set(record) == {"signed", "as_head"}


def test_the_firm_screen_lists_its_writes_and_each_refuses_a_stranger(db, client):
    assert join(client, ADULT).status_code == 201
    for method, path, body in (("put", "/api/firm/requests/1", {"approve": True}), ("post", "/api/firm/raisings", {"kind": "loan", "amount_kobo": 100, "quarters": 4}),
                               ("put", "/api/firm/budgets", {"budgets": {"head": 1}}), ("post", "/api/firm/tasks", {"kind": "rescue", "priority": 1}),
                               ("put", "/api/firm/trade-limit", {"limit_naira": 5}), ("post", "/api/firm/cover", {"kind": "inspection", "insurer_id": "00000000-0000-0000-0000-000000000000", "cover_kobo": 100}),
                               ("post", "/api/firm/events/1", {"desk": "head", "choice": "accept"}), ("put", "/api/firm/strategy", {"choice": "grow", "growth_bps": 0, "payout_kobo": 0, "tasks": 0})):
        answer = getattr(client, method)(path, json=body)
        assert answer.status_code == 409, (path, answer.text)
    assert client.post("/api/stake-offers/1", json={"amount_kobo": 100}).status_code == 409
