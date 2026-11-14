"""Quick fixes after the private equity stage (owner, 8 and 9 October 2026).

1. A "Trade for: Me / My empire" switch on the trading screens (the website; the empire's routes are
   tested in test_empire_api). 2. Legal Counsel is silver (test_builds). 3. Quiet news pop-ups for every
   story, which a player can mute. 4. Messages between players, with blocking, reporting and limits.
5. Rank moves under the profile picture, with a dot when a case is waiting. 6. Early retirement.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from simulation import careers, messages, news, quarters
from simulation import world_data as data
from simulation.money import apply_bps
from tests.conftest import ADULT, after_quarters, join
from tests.test_careers import NOW9, pass_one, professional, sound
from tests.test_market import trader
from tests.test_mastery import master
from tests.test_savings import savings

pytestmark = pytest.mark.world("eight")


def _dicts(db, sql, params=()):
    with db.cursor(row_factory=dict_row) as cur:
        return cur.execute(sql, params).fetchall()


def person(db, name: str):
    account = trader(db, name)
    return _dicts(db, "SELECT player_id FROM ledger_accounts WHERE id = %s", (account,))[0]["player_id"]


# ---------------------------------------------------------------------------
# 6. Early retirement
# ---------------------------------------------------------------------------

def test_early_retirement_opens_at_twenty_quarters_or_level_35_and_pays_less_for_good(db, monkeypatch):
    player, account = professional(db, now=NOW9)
    savings(db, player, 4_000_000)
    assert (data.EARLY_RETIREMENT_AFTER_QUARTERS, data.EARLY_RETIREMENT_LEVEL, data.EARLY_PENSION_PAID_BPS) == (20, 35, 150)
    assert (data.RETIREMENT_AFTER_QUARTERS, data.RETIREMENT_LEVEL, data.PENSION_PAID_BPS) == (40, 50, 250)
    shown = careers.profile(db, player, NOW9)["retirement"]
    assert shown["can_retire_early"] is False and shown["early_quarters_to_go"] == 20 and shown["early_pension_bps"] == 150
    with pytest.raises(careers.CareerError, match="Early retirement opens at Level 35"):
        careers.retire(db, player, NOW9, early=True)
    pass_one(db, player, NOW9)
    assert quarters.close_due_quarters(db, after_quarters(9)) == [9]
    now = after_quarters(9) + timedelta(hours=12)
    monkeypatch.setattr(data, "EARLY_RETIREMENT_AFTER_QUARTERS", 1)              # as if five years had passed
    shown = careers.profile(db, player, now)["retirement"]
    assert shown["can_retire_early"] is True and shown["can_retire"] is False
    with pytest.raises(careers.CareerError, match="Retirement opens at Level 50"):
        careers.retire(db, player, now)                                          # the full pension is not open yet
    careers.retire(db, player, now, early=True)
    assert _dicts(db, "SELECT pension_bps FROM retirement_accounts WHERE player_id = %s", (player,))[0]["pension_bps"] == 150
    # Fixed for good: neither kind of pension can be begun again, even once the full one would have opened.
    monkeypatch.setattr(data, "RETIREMENT_AFTER_QUARTERS", 1)
    for early in (False, True):
        with pytest.raises(careers.CareerError, match="already being paid"):
            careers.retire(db, player, now, early=early)
    assert quarters.close_due_quarters(db, after_quarters(10)) == [10]
    entry = _dicts(db, "SELECT * FROM retirement_entries WHERE player_id = %s AND period = 10", (player,))[0]
    base = entry["opening"] + entry["growth"] + entry["paid_in_by_you"] + entry["paid_in_by_employer"]
    assert entry["paid_out"] == apply_bps(base, 150) > 0 and entry["paid_out"] < apply_bps(base, 250)
    assert careers.profile(db, player, after_quarters(10) + timedelta(hours=1))["retirement"]["pension_bps"] == 150
    sound(db)


def test_someone_who_qualifies_for_the_full_pension_is_not_let_take_the_smaller_one(db, monkeypatch):
    player, _ = professional(db, now=NOW9)
    savings(db, player, 1_000_000)
    careers.add_experience(db, player, "asset_manager", careers.experience_for(20), NOW9)
    monkeypatch.setattr(data, "RETIREMENT_LEVEL", 20)
    with pytest.raises(careers.CareerError, match="already qualify for the full pension"):
        careers.retire(db, player, NOW9, early=True)
    careers.retire(db, player, NOW9)
    assert _dicts(db, "SELECT pension_bps FROM retirement_accounts WHERE player_id = %s", (player,))[0]["pension_bps"] == 250


def test_early_retirement_through_the_website(db, client, monkeypatch):
    assert join(client, ADULT).status_code == 201
    assert client.put("/api/career/build", json={"build": "asset_manager"}).status_code == 200
    me = client.get("/api/me").json()
    savings(db, me["id"], 1_000_000)
    refused = client.post("/api/career/retirement/pension", json={"early": True})
    assert refused.status_code == 409 and "Early retirement opens at Level 35" in refused.json()["detail"]
    careers.add_experience(db, me["id"], "asset_manager", careers.experience_for(20), NOW9)
    master(db, me["id"], "asset_manager")
    monkeypatch.setattr(data, "EARLY_RETIREMENT_LEVEL", 20)
    seen = client.get("/api/career").json()["retirement"]
    assert seen["can_retire_early"] is True and seen["early_pension_bps"] == 150 and seen["full_pension_bps"] == 250
    assert client.post("/api/career/retirement/pension", json={"early": True, "pension_bps": 10000}).status_code == 422
    done = client.post("/api/career/retirement/pension", json={"early": True})
    assert done.status_code == 200, done.text
    assert done.json()["retirement"]["pension_bps"] == 150
    assert client.post("/api/career/retirement/pension", json={}).status_code == 409


# ---------------------------------------------------------------------------
# 5. Rank under the profile picture, with a dot when a case is waiting
# ---------------------------------------------------------------------------

def test_the_dot_shows_when_a_rank_case_can_be_begun_or_is_in_hand(db, client):
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    assert me["rank_waiting"] is False and me["unread_messages"] == 0 and me["news_alerts"] is True
    assert client.put("/api/career/build", json={"build": "asset_manager"}).status_code == 200
    assert client.get("/api/me").json()["rank_waiting"] is False                 # short of the gate
    careers.add_experience(db, me["id"], "asset_manager", careers.experience_for(20), NOW9)
    assert client.get("/api/me").json()["rank_waiting"] is False                 # at the gate, modules not yet mastered
    master(db, me["id"], "asset_manager")
    assert client.get("/api/me").json()["rank_waiting"] is True                  # the case can be begun
    from tests.test_objectives import give_cash
    from simulation import ledger
    give_cash(db, ledger.player_account_id(db, me["id"]), 1_000_000)
    assert client.post("/api/ranks/cases", json={"track": "asset_manager"}).status_code == 201
    assert client.get("/api/me").json()["rank_waiting"] is True                  # a case in hand


# ---------------------------------------------------------------------------
# 3. Quiet news pop-ups
# ---------------------------------------------------------------------------

def _a_day_with_news(db):
    return _dicts(db, "SELECT period, day, count(*) AS n FROM news_items GROUP BY period, day HAVING count(*) >= 4"
                      " ORDER BY period DESC, day DESC LIMIT 1")[0]


def test_news_alerts_show_only_new_stories_never_future_ones_and_start_with_none(db):
    day = _a_day_with_news(db)
    first = news.alerts(db, day["period"], day["day"] - 1, None)
    assert first["items"] == [] and first["mark"][:2] == (day["period"], day["day"] - 1)
    # The next day: that day's stories, most important first, three at most and a count of the rest.
    seen = news.alerts(db, day["period"], day["day"], first["mark"])
    assert len(seen["items"]) == 3 and seen["more"] == day["n"] - 3
    assert all((i["period"], i["day"]) <= (day["period"], day["day"]) for i in seen["items"])
    # Looking again the same day shows nothing new; a story added later that day is shown.
    again = news.alerts(db, day["period"], day["day"], seen["mark"])
    assert again["items"] == [] and again["more"] == 0
    db.execute("INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body)"
               " SELECT period, day, outlet, kind, story, importance, 'A late story', body FROM news_items"
               " WHERE period = %s AND day = %s LIMIT 1", (day["period"], day["day"]))
    late = news.alerts(db, day["period"], day["day"], seen["mark"])
    assert [i["headline"] for i in late["items"]] == ["A late story"]
    # A story dated tomorrow is never shown today, and a mark from the future shows nothing.
    db.execute("INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body)"
               " SELECT period, day + 1, outlet, kind, story, importance, 'Tomorrow', body FROM news_items"
               " WHERE period = %s AND day = %s LIMIT 1", (day["period"], day["day"]))
    assert "Tomorrow" not in [i["headline"] for i in news.alerts(db, day["period"], day["day"], first["mark"])["items"]]
    assert news.alerts(db, day["period"], day["day"], (day["period"], day["day"] + 5, 0))["items"] == []


def test_news_alerts_can_be_muted_and_the_route_gives_only_headlines(db, client):
    assert client.get("/api/news/alerts").status_code == 401
    assert join(client, ADULT).status_code == 201
    first = client.get("/api/news/alerts")
    assert first.status_code == 200 and first.json()["items"] == []
    body = first.text
    assert "body" not in body and "facts" not in body
    off = client.patch("/api/me/news-alerts", json={"on": False})
    assert off.status_code == 200 and off.json()["news_alerts"] is False
    mark = first.json()["mark"]
    assert mark is not None
    db.execute("INSERT INTO news_items (period, day, outlet, kind, story, importance, headline, body)"
               " SELECT %s, %s, outlet, kind, story, importance, 'Fresh', body FROM news_items LIMIT 1", (mark["period"], mark["day"]))
    muted = client.get("/api/news/alerts", params=mark).json()
    assert muted["items"] == []
    assert client.patch("/api/me/news-alerts", json={"on": True}).json()["news_alerts"] is True
    assert [i["headline"] for i in client.get("/api/news/alerts", params=mark).json()["items"]] == ["Fresh"]
    assert client.patch("/api/me/news-alerts", json={"on": "yes please"}).status_code == 422
    assert client.patch("/api/me/news-alerts", json={"on": True, "player_id": "x"}).status_code == 422


# ---------------------------------------------------------------------------
# 4. Messages between players
# ---------------------------------------------------------------------------

def test_two_players_write_to_each_other_and_only_they_see_it(db):
    ada, bola, chidi = person(db, "ada"), person(db, "bola"), person(db, "chidi")
    sent = messages.send(db, ada, "BOLA", "  Hello Bola \x07", NOW9)
    assert sent["body"] == "Hello Bola"
    assert messages.unread_count(db, bola) == 1 and messages.unread_count(db, ada) == 0
    listed = messages.conversations(db, bola)["conversations"]
    assert [(c["name"], c["unread"], c["mine"]) for c in listed] == [("ada", 1, False)]
    thread = messages.thread(db, bola, "ada", NOW9)
    assert [m["body"] for m in thread["messages"]] == ["Hello Bola"] and thread["can_write"]
    assert messages.unread_count(db, bola) == 0                                   # opening it marks it read
    messages.send(db, bola, "ada", "Hi Ada", NOW9)
    assert [m["mine"] for m in messages.thread(db, ada, "bola", NOW9)["messages"]] == [True, False]
    assert messages.conversations(db, chidi)["conversations"] == []
    assert messages.thread(db, chidi, "ada", NOW9)["messages"] == []
    for bad, words in (("", "Write something"), ("x" * 1001, "at most 1000")):
        with pytest.raises(messages.MessageError, match=words):
            messages.send(db, ada, "bola", bad, NOW9)
    with pytest.raises(messages.MessageError, match="no player of that name"):
        messages.send(db, ada, "nobody", "hi", NOW9)
    with pytest.raises(messages.MessageError, match="yourself"):
        messages.send(db, ada, "ada", "hi", NOW9)


def test_a_block_stops_messages_reaching_the_blocker_and_the_blocked_player_is_never_told(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "One", NOW9)
    messages.block(db, bola, "ada", NOW9)
    # Ada writes as usual: nothing tells her she is blocked, and nothing reaches Bola.
    messages.send(db, ada, "bola", "Two", NOW9)
    seen_by_ada = messages.thread(db, ada, "bola", NOW9)
    assert seen_by_ada["blocked"] is False and seen_by_ada["can_write"] is True
    assert [m["body"] for m in seen_by_ada["messages"]] == ["One", "Two"]
    assert [m["body"] for m in messages.thread(db, bola, "ada", NOW9)["messages"]] == ["One"]
    assert messages.unread_count(db, bola) == 0
    # Bola, who blocked her, is told plainly that it is his own block.
    with pytest.raises(messages.MessageError, match="You have blocked this player"):
        messages.send(db, bola, "ada", "Hi", NOW9)
    assert messages.thread(db, bola, "ada", NOW9)["blocked"] is True and messages.thread(db, bola, "ada", NOW9)["can_write"] is False
    assert messages.conversations(db, bola)["blocked"] == ["ada"] and messages.conversations(db, ada)["blocked"] == []
    # Lifting the block lets new messages through; what was sent during the block stays unseen.
    messages.unblock(db, bola, "ada")
    messages.send(db, bola, "ada", "Hello again", NOW9)
    messages.send(db, ada, "bola", "Three", NOW9)
    assert [m["body"] for m in messages.thread(db, bola, "ada", NOW9)["messages"]] == ["One", "Hello again", "Three"]


def test_a_message_that_arrives_while_a_conversation_is_open_stays_unread(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "First", NOW9)
    shown = messages.thread(db, bola, "ada", NOW9)
    late = messages.send(db, ada, "bola", "Second", NOW9)
    # Marking read touches only what was shown: run the marking again with the first look's ids.
    db.execute("UPDATE player_messages SET read_at = %s WHERE id = ANY(%s) AND read_at IS NULL",
               (NOW9, [m["id"] for m in shown["messages"]]))
    assert messages.unread_count(db, bola) == 1
    assert _dicts(db, "SELECT read_at FROM player_messages WHERE id = %s", (late["id"],))[0]["read_at"] is None
    # Clearing a conversation does not mark anything read for the sender to see.
    messages.hide_conversation(db, bola, "ada", NOW9)
    assert _dicts(db, "SELECT read_at FROM player_messages WHERE id = %s", (late["id"],))[0]["read_at"] is None
    assert messages.unread_count(db, bola) == 0


def test_limits_keep_anyone_from_flooding_others(db, monkeypatch):
    ada, bola = person(db, "ada"), person(db, "bola")
    for i in range(data.UNANSWERED_IN_A_ROW):
        messages.send(db, ada, "bola", f"Hello {i}", NOW9)
    with pytest.raises(messages.MessageError, match="has not answered"):
        messages.send(db, ada, "bola", "Hello again", NOW9)
    messages.send(db, bola, "ada", "Hi", NOW9)
    messages.send(db, ada, "bola", "At last", NOW9)                               # an answer opens the way again
    # New people a day.
    others = [person(db, f"p{i}") for i in range(data.NEW_PEOPLE_PER_DAY + 1)]
    for i in range(data.NEW_PEOPLE_PER_DAY):
        messages.send(db, ada, f"p{i}", "Hello", NOW9)
    with pytest.raises(messages.MessageError, match="new players today"):
        messages.send(db, ada, f"p{data.NEW_PEOPLE_PER_DAY}", "Hello", NOW9)
    messages.send(db, ada, "p0", "Still allowed: we have spoken", NOW9 + timedelta(minutes=1))
    messages.send(db, ada, f"p{data.NEW_PEOPLE_PER_DAY}", "A day later", NOW9 + timedelta(days=1, minutes=1))
    assert others
    # Messages an hour.
    monkeypatch.setattr(data, "MESSAGES_PER_HOUR", 2)
    later = NOW9 + timedelta(days=3)
    messages.send(db, bola, "ada", "a", later)
    messages.send(db, bola, "ada", "b", later)
    with pytest.raises(messages.MessageError, match="last hour"):
        messages.send(db, bola, "ada", "c", later)
    messages.send(db, bola, "ada", "c", later + timedelta(hours=1, minutes=1))


def test_reports_go_to_the_receiver_only_once_and_three_reporters_limit_the_sender(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    reporters = [person(db, f"r{i}") for i in range(3)]
    sent = messages.send(db, ada, "bola", "Rude", NOW9)
    with pytest.raises(messages.MessageError, match="no such message"):
        messages.report(db, ada, sent["id"], "mine", NOW9)                       # not the sender
    with pytest.raises(messages.MessageError, match="no such message"):
        messages.report(db, reporters[0], sent["id"], "not mine", NOW9)          # not a stranger
    messages.report(db, bola, sent["id"], "Rude", NOW9, and_block=True)
    with pytest.raises(messages.MessageError, match="already reported"):
        messages.report(db, bola, sent["id"], "again", NOW9)
    assert messages.conversations(db, bola)["blocked"] == ["ada"]
    for i, r in enumerate(reporters[:2]):
        m = messages.send(db, ada, f"r{i}", "Rude", NOW9)
        messages.report(db, r, m["id"], None, NOW9)
    # Three different players in a week: ada may only answer people who wrote first.
    stranger = person(db, "stranger")
    assert stranger
    with pytest.raises(messages.MessageError, match="only answer"):
        messages.send(db, ada, "stranger", "Hi", NOW9)
    messages.send(db, reporters[2], "ada", "Hello ada", NOW9)
    messages.send(db, ada, "r2", "Hello back", NOW9)
    messages.send(db, ada, "stranger", "A week on", NOW9 + timedelta(days=data.REPORT_WINDOW_DAYS, minutes=1))


def test_clearing_a_conversation_hides_it_for_one_side_only(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "One", NOW9)
    messages.send(db, bola, "ada", "Two", NOW9)
    messages.hide_conversation(db, ada, "bola", NOW9)
    assert messages.conversations(db, ada)["conversations"] == []
    assert [m["body"] for m in messages.thread(db, bola, "ada", NOW9)["messages"]] == ["One", "Two"]
    messages.send(db, bola, "ada", "Three", NOW9)
    assert [m["body"] for m in messages.thread(db, ada, "bola", NOW9)["messages"]] == ["Three"]


def test_messages_through_the_website(db, client):
    assert client.get("/api/messages").status_code == 401
    assert join(client, ADULT).status_code == 201
    bola = person(db, "bola")
    sent = client.post("/api/messages", json={"to": "bola", "body": "Hello"})
    assert sent.status_code == 201, sent.text
    assert client.post("/api/messages", json={"to": "bola", "body": "x", "sender_id": str(bola)}).status_code == 422
    assert client.post("/api/messages", json={"to": "Ada", "body": "me"}).status_code == 409
    messages.send(db, bola, "ada", "Hi Ada", NOW9)
    assert client.get("/api/me").json()["unread_messages"] == 1
    listed = client.get("/api/messages").json()
    assert listed["unread"] == 1 and listed["conversations"][0]["name"] == "bola" and listed["limits"]["max_chars"] == 1000
    thread = client.get("/api/messages/with", params={"name": "bola"}).json()
    assert [m["body"] for m in thread["messages"]] == ["Hello", "Hi Ada"] and "sender_id" not in str(thread)
    assert client.get("/api/me").json()["unread_messages"] == 0
    theirs = thread["messages"][1]["id"]
    assert client.post("/api/messages/report", json={"message_id": thread["messages"][0]["id"]}).status_code == 409
    assert client.post("/api/messages/report", json={"message_id": theirs, "reason": "Rude", "block": True}).json()["blocked"] == ["bola"]
    blocked = client.post("/api/messages", json={"to": "bola", "body": "again"})
    assert blocked.status_code == 409 and "You have blocked" in blocked.json()["detail"]
    assert client.post("/api/messages/unblock", json={"name": "bola"}).json()["blocked"] == []
    assert client.post("/api/messages/clear", json={"name": "bola"}).json()["conversations"] == []
    assert client.get("/api/messages/with", params={"name": "nobody"}).status_code == 404
