"""Quick fixes: the ten-question loophole check, one test (or more) for each question.

Players may commit crimes against each other's empires, but never against the game: no money from
nowhere, no seeing what is hidden, no acting as somebody else, no beating the clock.
"""

from __future__ import annotations

import threading
from datetime import timedelta

import pytest

from simulation import careers, empires, ledger, messages, news
from simulation import world_data as data
from tests.conftest import ADULT, join, money_accounted_for
from tests.test_careers import NOW9, professional
from tests.test_firm import firm_of
from tests.test_quick_fixes import _a_day_with_news, _dicts, person
from tests.test_savings import savings

pytestmark = pytest.mark.world("eight")


# 1. Can a player read messages between two other players?
def test_q1_nobody_reads_a_conversation_they_are_not_in(db, client):
    ada, bola = person(db, "adaeze"), person(db, "bola")
    messages.send(db, ada, "bola", "Our secret plan", NOW9)
    assert join(client, ADULT).status_code == 201                                # "Ada", a third player
    for name in ("adaeze", "bola"):
        seen = client.get("/api/messages/with", params={"name": name})
        assert seen.status_code == 200 and seen.json()["messages"] == [] and "secret" not in seen.text
    assert client.get("/api/messages").json()["conversations"] == []
    assert client.post("/api/messages/report", json={"message_id": 1}).status_code in (409,)
    assert messages.unread_count(db, bola) == 1                                  # reading as a stranger marked nothing read


# 2. Can a player find out who blocked or reported them?
def test_q2_a_block_or_a_report_is_never_shown_to_the_player_it_is_about(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    sent = messages.send(db, ada, "bola", "Hello", NOW9)
    messages.report(db, bola, sent["id"], "Spam", NOW9, and_block=True)
    seen = messages.thread(db, ada, "bola", NOW9)
    assert seen["blocked"] is False and seen["messages"][0]["reported"] is False
    assert messages.conversations(db, ada)["blocked"] == []
    with pytest.raises(messages.MessageError) as refused:
        messages.send(db, ada, "bola", "Hello?", NOW9)
    assert "block" not in str(refused.value).lower() and "report" not in str(refused.value).lower()


# 3. Can a player send a message as somebody else, or set its time, its reader or its state?
def test_q3_no_message_is_sent_as_anybody_else_or_with_its_own_time(db, client):
    assert join(client, ADULT).status_code == 201
    bola = person(db, "bola")
    for extra in ({"sender_id": str(bola)}, {"sent_at": "2020-01-01T00:00:00Z"}, {"read_at": "2020-01-01T00:00:00Z"}, {"hidden_for_receiver": True}):
        assert client.post("/api/messages", json={"to": "bola", "body": "hi", **extra}).status_code == 422
    assert client.post("/api/messages/block", json={"name": "bola", "blocker_id": str(bola)}).status_code == 422
    assert client.post("/api/messages/report", json={"message_id": 1, "reporter_id": str(bola)}).status_code == 422


# 4. Can a message, a block or a report move money, shares or anything else of value?
def test_q4_messages_move_nothing_of_value(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    before = (ledger.amount_in_existence(db), _dicts(db, "SELECT count(*) AS n FROM ledger_transactions")[0]["n"])
    m = messages.send(db, ada, "bola", "Send me 1,000,000 naira", NOW9)
    messages.thread(db, bola, "ada", NOW9)
    messages.report(db, bola, m["id"], None, NOW9, and_block=True)
    messages.unblock(db, bola, "ada")
    messages.hide_conversation(db, bola, "ada", NOW9)
    assert (ledger.amount_in_existence(db), _dicts(db, "SELECT count(*) AS n FROM ledger_transactions")[0]["n"]) == before
    assert ledger.audit(db) == [] and ledger.amount_in_existence(db) == money_accounted_for(db)


# 5. Can two sends at the same moment both slip under a limit?
def test_q5_two_sends_at_once_cannot_both_pass_a_limit(db, connect, monkeypatch):
    ada, bola = person(db, "ada"), person(db, "bola")
    monkeypatch.setattr(data, "UNANSWERED_IN_A_ROW", 1)
    first, second = connect(), connect()
    results = []
    gate = threading.Barrier(2)

    def go(conn):
        gate.wait()
        try:
            messages.send(conn, ada, "bola", "Hi", NOW9)
            results.append("sent")
        except messages.MessageError:
            results.append("refused")

    threads = [threading.Thread(target=go, args=(c,)) for c in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results) == ["refused", "sent"]
    assert _dicts(db, "SELECT count(*) AS n FROM player_messages WHERE sender_id = %s", (ada,))[0]["n"] == 1


# 6. Can a news pop-up show a story before its day (the running quarter's events stay hidden)?
def test_q6_no_pop_up_shows_a_story_before_its_day(db, client):
    day = _a_day_with_news(db)
    future = _dicts(db, "SELECT period, day FROM news_items WHERE (period, day) > (%s, %s) ORDER BY period, day LIMIT 1",
                    (day["period"], day["day"]))
    seen = news.alerts(db, day["period"], day["day"], (0, 1, 0))
    assert all((i["period"], i["day"]) <= (day["period"], day["day"]) for i in seen["items"])
    if future:
        f = future[0]
        assert news.alerts(db, day["period"], day["day"], (f["period"], f["day"], 0))["items"] == []
    # Through the website, a made-up mark far in the future, or a nonsense one, gives nothing away.
    assert join(client, ADULT).status_code == 201
    assert client.get("/api/news/alerts", params={"period": 99999, "day": 90, "top": 0}).json()["items"] == []
    for bad in ({"period": -1, "day": 1, "top": 0}, {"period": 1, "day": 91, "top": 0}, {"period": "x", "day": 1, "top": 0}):
        assert client.get("/api/news/alerts", params=bad).status_code == 422


# 7. Can a player change another player's settings, or begin somebody else's pension?
def test_q7_settings_and_pensions_are_only_ever_the_players_own(db, client, monkeypatch):
    other, _ = professional(db, "other", now=NOW9)
    savings(db, other, 1_000_000)
    assert join(client, ADULT).status_code == 201
    me = client.get("/api/me").json()
    assert client.patch("/api/me/news-alerts", json={"on": False, "player_id": str(other)}).status_code == 422
    assert client.patch("/api/me/news-alerts", json={"on": False}).status_code == 200
    assert _dicts(db, "SELECT news_alerts FROM players WHERE id = %s", (other,))[0]["news_alerts"] is True
    assert _dicts(db, "SELECT news_alerts FROM players WHERE id = %s", (me["id"],))[0]["news_alerts"] is False
    monkeypatch.setattr(data, "EARLY_RETIREMENT_AFTER_QUARTERS", 0)
    assert client.post("/api/career/retirement/pension", json={"early": True, "player_id": str(other)}).status_code == 422
    assert _dicts(db, "SELECT retired_period FROM retirement_accounts WHERE player_id = %s", (other,))[0]["retired_period"] is None


# 8. Can a player take the early pension and later move to the full one, or set their own rate?
def test_q8_the_early_pension_is_fixed_for_good_and_no_rate_is_chosen_by_the_player(db, monkeypatch):
    player, _ = professional(db, now=NOW9)
    savings(db, player, 1_000_000)
    monkeypatch.setattr(data, "EARLY_RETIREMENT_AFTER_QUARTERS", 0)
    careers.retire(db, player, NOW9, early=True)
    monkeypatch.setattr(data, "RETIREMENT_AFTER_QUARTERS", 0)
    with pytest.raises(careers.CareerError, match="already being paid"):
        careers.retire(db, player, NOW9)
    assert _dicts(db, "SELECT pension_bps FROM retirement_accounts WHERE player_id = %s", (player,))[0]["pension_bps"] == 150
    # The rate is checked by the database too: nothing outside 0.01% to 100% can be stored.
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE retirement_accounts SET pension_bps = 0 WHERE player_id = %s", (player,))


# 9. Can the "Trade for: My empire" switch let a member who may not trade for the empire use its money?
def test_q9_only_an_asset_manager_or_the_head_trades_with_the_empires_money(db):
    empire, team = firm_of(db)
    cash = ledger.balance(db, empire["account_id"])
    for build in ("lawyer", "risk_manager", "investment_banker", "accountant", "journalist"):
        with pytest.raises(empires.EmpireError, match="Only the empire's Asset Managers, and its head"):
            empires.trade_shares(db, team[build], ticker="IDC", side="buy", kind="limit", quantity=10, limit_price=10_000, now=NOW9)
        with pytest.raises(empires.EmpireError, match="Only the empire's Asset Managers, and its head"):
            empires.trade_bonds(db, team[build], code="NTB-1", side="buy", units=1, now=NOW9)
    assert ledger.balance(db, empire["account_id"]) == cash


# 10. Can a player push a dot or a count onto another player's screen that they cannot clear, or slip
#     hidden characters into a message?
def test_q10_no_count_that_cannot_be_cleared_and_no_hidden_characters(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    sent = messages.send(db, ada, "bola", "‮evil​\x00 text\r\n line", NOW9)
    assert sent["body"] == "evil text\n line"
    assert messages.unread_count(db, bola) == 1
    messages.block(db, bola, "ada", NOW9)
    assert messages.unread_count(db, bola) == 0                                  # blocking clears the count at once
    messages.unblock(db, bola, "ada")
    messages.hide_conversation(db, bola, "ada", NOW9)
    assert messages.unread_count(db, bola) == 0                                  # so does clearing the conversation
    later = NOW9 + timedelta(minutes=1)
    messages.send(db, bola, "ada", "Hi", later)
    messages.thread(db, ada, "bola", later)
    assert messages.unread_count(db, ada) == 0
