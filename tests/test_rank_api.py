"""Stage 7: the website's requests about ranks, rank cases, reports and the league, as a player would make them."""

from __future__ import annotations

import pytest

from simulation import careers, ledger, objectives
from simulation.money import naira
from tests.conftest import ADULT, join, money_accounted_for
from tests.test_mastery import master
from tests.test_careers import NOW9
from tests.test_objectives import give_cash

pytestmark = pytest.mark.world("eight")


def test_a_player_sees_the_gate_ahead_sits_a_case_and_reports_marking(db, client):
    assert client.get("/api/ranks").status_code == 401
    assert join(client, ADULT).status_code == 201
    assert client.get("/api/ranks").json()["tracks"] == []                      # no build yet
    assert client.put("/api/career/build", json={"build": "asset_manager"}).status_code == 200
    seen = client.get("/api/ranks").json()
    track = seen["tracks"][0]
    assert track["gate"] == 20 and not track["can_begin"] and "Reach Level 20" in track["why_not"] and int(track["fee_kobo"]) > 0
    assert seen["active"] is None and [t["track"] for t in seen["tracks"]] == ["asset_manager"]
    refused = client.post("/api/ranks/cases", json={"track": "asset_manager"})
    assert refused.status_code == 409 and "Reach Level 20" in refused.json()["detail"]
    # Another build's case, a track that does not exist, and extra fields are refused.
    assert client.post("/api/ranks/cases", json={"track": "investment_banker"}).status_code == 409
    assert client.post("/api/ranks/cases", json={"track": "ceo"}).status_code == 409
    assert client.post("/api/ranks/cases", json={"track": "admin"}).status_code == 422
    assert client.post("/api/ranks/cases", json={"track": "asset_manager", "fee_kobo": 0}).status_code == 422

    # The work board now carries the three settings, the map and the tracker.
    board = client.get("/api/objectives").json()
    # (Eight modules in the first band, each three ways; the gap stage's higher bands are listed too, locked until their level.)
    first = [o for o in board["offers"] if objectives.TEMPLATES[o["template"]].level <= 4]
    assert {o["setting"] for o in board["offers"]} == {"solo", "empire", "live"} and len(first) == 24
    total = len(objectives.modules("asset_manager"))
    assert board["tracks"][0]["name"] == "Accountant" and board["tracks"][0]["modules"] == total
    assert set(board["weekend"]) == {"open", "opens", "closes", "hours"} and len(board["skills"]) == total

    player = client.get("/api/me").json()
    account = ledger.player_account_id(db, player["id"])
    careers.add_experience(db, player["id"], "asset_manager", careers.experience_for(20), NOW9)
    master(db, player["id"], "asset_manager")
    give_cash(db, account, 1_000_000)
    cash = ledger.balance(db, account)
    begun = client.post("/api/ranks/cases", json={"track": "asset_manager"})
    assert begun.status_code == 201, begun.text
    case = begun.json()["active"]
    assert ledger.balance(db, account) == cash - int(case["fee_kobo"]) and len(case["parts"]) == 3
    # Nothing in what the website receives gives an answer away, or says how the case was drawn.
    text = begun.text
    assert "answers" not in text and "salt" not in text and "filed_period" not in text and "company_id" not in text
    # A company figure travels as text.
    assert all(isinstance(line.get("kobo", ""), str) for part in case["parts"] for line in part["terms"]["given"])
    # Badly shaped papers are refused before they are looked at.
    for bad in ({"answers": []}, {"answers": {"ac_ratios": {"ebitda": float("1e999")}}} if False else {"answers": {"ac_ratios": "x"}},
                {"answers": {"ac_ratios": {"k" * 40: 1}}}, {"answers": {}, "score": 100}):
        assert client.post(f"/api/ranks/cases/{case['id']}/hand-in", json=bad).status_code == 422
    assert client.post("/api/ranks/cases/999999/hand-in", json={"answers": {}}).status_code == 409
    marked = client.post(f"/api/ranks/cases/{case['id']}/hand-in", json={"answers": {"ac_ratios": {"ebitda": 1.0}}})
    assert marked.status_code == 200
    past = marked.json()["past"][0]
    assert marked.json()["active"] is None and past["state"] == "failed" and past["result"]["score"] < 80
    assert client.post(f"/api/ranks/cases/{case['id']}/hand-in", json={"answers": {}}).status_code == 409
    again = client.get("/api/ranks").json()["tracks"][0]
    assert not again["can_begin"] and again["retry_at"] and "after 3 real days" in again["why_not"]

    # Reporting the marking: once, in words.
    assert client.post("/api/reports", json={"case_id": past["id"], "words": "short"}).status_code == 422
    assert client.post("/api/reports", json={"case_id": past["id"], "objective_id": 1, "words": "Both at once is not allowed."}).status_code == 422
    assert client.post("/api/reports", json={"case_id": past["id"], "words": "The interest cover looks wrong to me."}).status_code == 201
    assert client.post("/api/reports", json={"case_id": past["id"], "words": "The interest cover looks wrong to me."}).status_code == 409
    assert client.post("/api/reports", json={"case_id": 424242, "words": "This is not a case of mine at all."}).status_code == 409

    # The league: divisions, and every player ranked within their build.
    directory = client.get("/api/empires").json()["directory"]
    assert len(directory["divisions"]) == 1 and len(directory["divisions"][0]["empires"]) == 5
    assert directory["build_table"]["top"][0]["you"] and directory["build_table"]["your_place"] == 1
    table = client.get("/api/league/builds/accountant").json()
    assert table["top"][0]["level"] == 20 and "id" not in table["top"][0]
    assert client.get("/api/league/builds/ceo").status_code == 422
    assert ledger.audit(db) == [] and ledger.amount_in_existence(db) == money_accounted_for(db)


def test_resignation_and_the_vote_are_refused_in_words_when_they_do_not_apply(db, client):
    assert join(client, ADULT).status_code == 201
    for method, path, body in (("post", "/api/empire/resignation", {"letter": "Goodbye."}), ("delete", "/api/empire/resignation", None),
                               ("post", "/api/empire/resignation/acceptance", None),
                               ("put", "/api/empire/resignations/1/offer", {"bonus_kobo": naira(1_000)}),
                               ("delete", "/api/empire/resignations/1", None),
                               ("post", "/api/empire/head-votes", {"build": "investment_banker", "slot": 1})):
        answer = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
        assert answer.status_code == 409, (path, answer.text)
    for bad in ({"letter": "x" * 601}, {"letter": "bad\x07bell"}, {"letter": "fine", "leaves_at": "now"}):
        assert client.post("/api/empire/resignation", json=bad).status_code == 422
    for bad in ({"bonus_kobo": -1}, {"bonus_kobo": 1.5}, {"bonus_kobo": "9"}, {"bonus_kobo": 1, "to": "me"}):
        assert client.put("/api/empire/resignations/1/offer", json=bad).status_code == 422
