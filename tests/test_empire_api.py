"""Stage 6: the website's requests about empires and pension funds, as a player would make them."""

from __future__ import annotations

import pytest

from simulation import ledger
from simulation.money import naira
from tests.conftest import ADULT, join, money_accounted_for

pytestmark = pytest.mark.world("eight")


def test_a_new_player_joins_an_empire_from_the_first_day_and_uses_the_war_room(db, client):
    assert client.get("/api/empires").status_code == 401
    assert join(client, ADULT).status_code == 201
    seen = client.get("/api/empires").json()
    assert seen["room"] is None and len(seen["directory"]["league"]) == 5 and not seen["directory"]["can_found"]
    first = seen["directory"]["league"][0]
    assert int(first["worth_kobo"]) > 0 and "cash_kobo" not in first and "holdings" not in first
    # Without a build there is no seat to take.
    refused = client.post(f"/api/empires/{first['id']}/applications")
    assert refused.status_code == 409 and "build" in refused.json()["detail"]
    assert client.put("/api/career/build", json={"build": "accountant"}).status_code == 200
    joined = client.post(f"/api/empires/{first['id']}/applications")
    assert joined.status_code == 201
    room = joined.json()["room"]
    assert room["name"] == first["name"] and room["your_build"] == "accountant" and room["run_by_computer"] and not room["is_head"]
    assert len(room["seats"]) == 12 and sum(1 for s in room["seats"] if s["you"]) == 1
    assert room["can_audit"] and not room["can_trade"]

    # The chat.
    assert client.post("/api/empire/messages", json={"body": "Good morning."}).json()["room"]["messages"][-1]["body"] == "Good morning."
    assert client.post("/api/empire/messages", json={"body": ""}).status_code == 422
    # What a member cannot do is refused in words, not with a fault.
    for method, path, body in (("post", "/api/empire/tasks", None), ("put", "/api/empire/limits", {"trade_limit_bps": 9000}),
                               ("post", "/api/empire/bonds", {"code": "FGN3M", "side": "buy", "units": 1}),
                               ("post", "/api/empire/ai-audit", None), ("post", "/api/empire/opening", None),
                               ("put", "/api/empire/cases/1", {"punish": True})):
        answer = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert answer.status_code == 409, (path, answer.text)

    # The shadow feature: sign for a cost. The money moves through the ledger and is in the books.
    cash = int(client.get("/api/me").json()["cash"]["amount_kobo"])
    taken = client.post("/api/empire/expenses", json={"amount_kobo": naira(50_000)})
    assert taken.status_code == 201
    assert int(client.get("/api/me").json()["cash"]["amount_kobo"]) == cash + naira(50_000)
    room = taken.json()["room"]
    assert int(room["signing_used_kobo"]) == naira(50_000) and int(room["your_entries"][0]["amount_kobo"]) == naira(50_000)
    assert "genuine" not in str(room) and "entered_by" not in str(room) and "thief_level" not in str(room)
    for bad in ({"amount_kobo": -1}, {"amount_kobo": 1.5}, {"amount_kobo": "5"}, {"amount_kobo": naira(50_000), "to": "me"},
                {"amount_kobo": naira(10_000_000)}):
        assert client.post("/api/empire/expenses", json=bad).status_code in (409, 422)
    assert ledger.audit(db) == [] and ledger.amount_in_existence(db) == money_accounted_for(db)

    # An audit: the Accountant sees what the audit found, their own entry included.
    audit = client.post("/api/empire/audits")
    assert audit.status_code == 201
    opened = audit.json()["room"]["open_audit"]
    assert client.put(f"/api/empire/audits/{opened['id']}", json={"report": []}).status_code == 200

    # Savings choices, and the pension funds.
    career = client.put("/api/career/extra-saving", json={"extra_bps": 500}).json()
    assert career["retirement"]["extra_bps"] == 500 and len(career["retirement"]["funds"]) == 4
    assert all(f["bad"] for f in career["retirement"]["funds"])
    assert client.put("/api/career/extra-saving", json={"extra_bps": 550}).status_code == 422
    assert client.post("/api/career/retirement/pension").status_code == 409
    funds = client.get("/api/pension-funds").json()
    assert funds["funds"] == [] and funds["can_open"] is False and funds["managing"] is None
    assert client.post("/api/pension-funds", json={"name": "Quick Pensions", "fee_bps": 10}).status_code == 409

    # Leaving.
    left = client.delete("/api/empire/seat")
    assert left.status_code == 200 and left.json()["room"] is None
    assert client.post("/api/empire/messages", json={"body": "Still here?"}).status_code == 409


def test_one_players_requests_never_reach_another_empires_room(db, client):
    assert join(client, ADULT).status_code == 201
    client.put("/api/career/build", json={"build": "lawyer"})
    league = client.get("/api/empires").json()["directory"]["league"]
    client.post(f"/api/empires/{league[0]['id']}/applications")
    client.post("/api/empire/messages", json={"body": "Our secret plan."})
    client.post("/api/auth/logout")
    assert join(client, {**ADULT, "email": "ben@example.com", "display_name": "Ben"}).status_code == 201
    client.put("/api/career/build", json={"build": "lawyer"})
    assert "Our secret plan." not in client.get("/api/empires").text
    client.post(f"/api/empires/{league[1]['id']}/applications")
    seen = client.get("/api/empires").json()
    assert seen["room"]["name"] == league[1]["name"] and "Our secret plan." not in str(seen)
    # There is no way to name another empire in a request about "my empire".
    assert client.get(f"/api/empires/{league[0]['id']}").status_code in (404, 405)
