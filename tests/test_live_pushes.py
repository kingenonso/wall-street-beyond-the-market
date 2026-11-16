"""Live events, part 2 (owner, 16 November 2026: "build"): updates that appear the moment something changes, and the
empire's chat on the Live events page.

Promises: a bell, a sealed prediction, a chat message, a new standing plan and the scores each send a ping, once the
change is saved; the server's listener hears it and tells the open pages that should hear it; a logged-in player's line
says hello, passes the ping on, says it is still there when quiet, and closes after a while for the browser to reopen;
the Live events page carries the empire's chat for its members.

Loopholes: a ping that carries a figure or a message (it carries only the kind of change); a rival empire's chat or plan
reaching another empire's screens; a ping heard before the change is saved (a change undone sends nothing); a line opened
without logging in; one player opening line after line; anything but a known ping read off the database's channel;
a rival or a player in no empire seeing an empire's chat on the page.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import timedelta

import psycopg
import pytest

from server import live_stream
from simulation import empires, liveevents, pings
from tests.conftest import TEST_DATABASE_URL
from tests.test_empires import founded
from tests.test_live_events import BELL, ring

pytestmark = pytest.mark.world("eight")


def heard_after(action) -> list[dict]:
    """Every ping the database carries while `action` runs, as a screen's server would hear it."""
    with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as ear:
        ear.execute(f"LISTEN {pings.CHANNEL}")
        action()
        return [json.loads(n.payload) for n in ear.notifies(timeout=0.5)]


def test_each_change_sends_a_ping_with_only_the_kind_of_change_and_never_a_figure_or_words(db, monkeypatch):
    empire, (head, _), partners = founded(db)
    banker = partners["investment_banker"][0]
    assert heard_after(lambda: liveevents.set_plan(db, head, "cut", 0, BELL - timedelta(hours=1))) == [
        {"what": "plan", "empire": empire["id"]}]
    event = {}
    assert {"what": "event", "empire": None} in heard_after(lambda: event.update(ring(db, monkeypatch, "fraud")))
    assert heard_after(lambda: liveevents.predict(db, banker, event["id"], -420, BELL + timedelta(minutes=2))) == [
        {"what": "prediction", "empire": empire["id"]}]
    said = heard_after(lambda: empires.say(db, banker, "Sell before the institutions read it", BELL + timedelta(minutes=3)))
    assert said == [{"what": "chat", "empire": empire["id"]}]
    assert "-420" not in json.dumps(said) and "institutions" not in json.dumps(said)
    assert heard_after(lambda: liveevents.score(db, event["id"], BELL + timedelta(minutes=30))) == [{"what": "event", "empire": None}]
    # Scored already: nothing changes, so nothing is sent.
    assert heard_after(lambda: liveevents.score(db, event["id"], BELL + timedelta(minutes=31))) == []


def test_a_change_that_is_undone_sends_nothing_and_a_refused_one_neither(db, monkeypatch):
    _empire, (head, _), _partners = founded(db)
    event = ring(db, monkeypatch, "oil_spike")

    def undone():
        with db.transaction(force_rollback=True):
            empires.say(db, head, "never said", BELL + timedelta(minutes=1))
    assert heard_after(undone) == []

    def refused():
        with pytest.raises(liveevents.LiveEventError):
            liveevents.predict(db, head, event["id"], 100, BELL + timedelta(minutes=12))     # after the ten minutes
    assert heard_after(refused) == []


def test_only_known_pings_are_read_off_the_channel():
    assert pings.read('{"what": "chat", "empire": 4}') == {"what": "chat", "empire": 4}
    assert pings.read('{"what": "event", "empire": null}') == {"what": "event", "empire": None}
    for bad in ('{"what": "chat"}', '{"what": "plan", "empire": "4"}', '{"what": "secret"}', "[1]", "not json",
                '{"what": "event", "empire": true}'):
        assert pings.read(bad) is None
    with pytest.raises(ValueError):
        pings.ping(None, "secret")


def test_an_empires_chat_and_plan_reach_only_its_own_members_screens():
    hub = live_stream.Hub()

    async def run():
        loop = asyncio.get_running_loop()
        ours, rivals, loner = hub.open("a", 7, loop), hub.open("b", 8, loop), hub.open("c", None, loop)
        assert hub.deliver({"what": "chat", "empire": 7}) == 1
        assert hub.deliver({"what": "plan", "empire": 7}) == 1
        assert hub.deliver({"what": "prediction", "empire": 8}) == 3          # how many have predicted is public
        assert hub.deliver({"what": "event", "empire": None}) == 3
        await asyncio.sleep(0.05)
        drained = {name: [line.queue.get_nowait() for _ in range(line.queue.qsize())]
                   for name, line in (("ours", ours), ("rivals", rivals), ("loner", loner))}
        assert drained == {"ours": ["chat", "plan", "prediction", "event"], "rivals": ["prediction", "event"],
                           "loner": ["prediction", "event"]}
        hub.close(ours)
        assert hub.deliver({"what": "chat", "empire": 7}) == 0
    asyncio.run(run())


def test_one_player_cannot_open_line_after_line(monkeypatch):
    hub = live_stream.Hub()
    monkeypatch.setattr(live_stream, "MOST_LINES", 6)

    async def run():
        loop = asyncio.get_running_loop()
        mine = [hub.open("a", None, loop) for _ in range(live_stream.MOST_LINES_EACH)]
        assert all(mine) and hub.open("a", None, loop) is None and not hub.has_room("a")
        assert hub.open("b", None, loop) and hub.open("c", None, loop)
        assert hub.open("d", None, loop) is None                              # the whole server is full too
        hub.close(mine[0])
        assert hub.has_room("a")
    asyncio.run(run())


def test_the_listener_hears_the_database_and_tells_the_open_lines(db):
    live_stream.listener.start()
    try:
        assert live_stream.listener.listening.wait(10)

        async def run():
            line = live_stream.hub.open("tester", 77, asyncio.get_running_loop())
            try:
                await asyncio.to_thread(pings.ping, db, "chat", 77)
                assert await asyncio.wait_for(line.queue.get(), timeout=5) == "chat"
                db.execute("SELECT pg_notify(%s, %s)", (pings.CHANNEL, "not a ping"))
                await asyncio.to_thread(pings.ping, db, "chat", 78)          # another empire's
                await asyncio.to_thread(pings.ping, db, "event")
                assert await asyncio.wait_for(line.queue.get(), timeout=5) == "event"
            finally:
                live_stream.hub.close(line)
        asyncio.run(run())
    finally:
        live_stream.listener.stop()


def test_a_line_needs_a_login_and_passes_on_what_it_hears(client, monkeypatch):
    from tests.conftest import ADULT, join
    assert client.get("/api/live/stream").status_code == 401
    assert join(client, ADULT).status_code == 201
    monkeypatch.setattr(live_stream, "KEEPALIVE_SECONDS", 0.4)
    monkeypatch.setattr(live_stream, "LINE_SECONDS", 1.5)

    def send():
        ends = time.monotonic() + 5
        while live_stream.hub.size() == 0 and time.monotonic() < ends:
            time.sleep(0.02)
        live_stream.hub.deliver({"what": "chat", "empire": 999_999})           # not this player's empire
        live_stream.hub.deliver({"what": "prediction", "empire": 3})
    sender = threading.Thread(target=send)
    sender.start()
    answer = client.get("/api/live/stream")
    sender.join()
    assert answer.status_code == 200 and answer.headers["content-type"].startswith("text/event-stream")
    body = answer.text
    assert body.startswith("retry: 3000") and "event: hello" in body and ": still here" in body
    changed = [json.loads(chunk.split("data: ", 1)[1]) for chunk in body.split("\n\n") if chunk.startswith("event: changed")]
    assert changed == [{"what": ["prediction"]}]
    assert live_stream.hub.size() == 0                                          # closed after its time, for the browser to reopen


def test_the_live_page_carries_the_empires_chat_for_its_members_only(db, monkeypatch):
    _empire, (head, _), partners = founded(db)
    banker = partners["investment_banker"][0]
    empires.say(db, banker, "Fraud at the bell: cut the stake?", BELL - timedelta(minutes=5))
    empires.say(db, head, "Yes, half", BELL - timedelta(minutes=4))
    page = liveevents.view(db, banker, BELL - timedelta(minutes=3))
    assert [(m["who"], m["body"], m["yours"]) for m in page["chat"]] == [
        (page["chat"][0]["who"], "Fraud at the bell: cut the stake?", True), (page["chat"][1]["who"], "Yes, half", False)]
    from tests.test_builds import pro
    loner, _ = pro(db, "asset_manager", "loner", level=10)
    assert liveevents.view(db, loner, BELL - timedelta(minutes=3))["chat"] == []
