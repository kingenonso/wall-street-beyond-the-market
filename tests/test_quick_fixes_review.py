"""Quick fixes: the problems the independent reviewer found, each with a test.

(The website's own fixes, the trade-for switch falling back, a failed send emptying the box, the
fair-dealing price, a bad address and the menu and pop-up for keyboards and screen readers, are checked
in the browser run and in web/src/messages.test.ts.)
"""

from __future__ import annotations

import pytest

from simulation import careers, messages, ranks
from tests.test_careers import NOW9, professional
from tests.test_mastery import master
from tests.test_quick_fixes import _dicts, person

pytestmark = pytest.mark.world("eight")


# R1. A block was given away: "can_write" was false only when the other player had blocked you.
def test_r01_a_block_is_never_given_away_by_the_conversation_or_the_refusal(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "Hi", NOW9)
    before = messages.thread(db, ada, "bola", NOW9)
    messages.block(db, bola, "ada", NOW9)
    after = messages.thread(db, ada, "bola", NOW9)
    assert {k: v for k, v in before.items() if k != "messages"} == {k: v for k, v in after.items() if k != "messages"}
    messages.send(db, ada, "bola", "Still there?", NOW9)                         # no refusal at all
    assert messages.unread_count(db, bola) == 0                                   # nothing from a blocked player is counted
    assert [m["body"] for m in messages.thread(db, bola, "ada", NOW9)["messages"]] == ["Hi"]


# R2. Opening a conversation marked read a message that arrived after the page was read.
def test_r02_only_the_messages_shown_are_marked_read(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "One", NOW9)
    shown = messages.thread(db, bola, "ada", NOW9)
    assert [m["body"] for m in shown["messages"]] == ["One"]
    messages.send(db, ada, "bola", "Two", NOW9)
    assert messages.unread_count(db, bola) == 1
    assert [m["body"] for m in messages.thread(db, bola, "ada", NOW9)["messages"]] == ["One", "Two"]
    assert messages.unread_count(db, bola) == 0


# R6. The list counted unread messages from a blocked player while the dot did not.
def test_r06_the_list_and_the_dot_agree_after_a_block(db):
    ada, bola = person(db, "ada"), person(db, "bola")
    messages.send(db, ada, "bola", "One", NOW9)
    messages.block(db, bola, "ada", NOW9)
    listed = messages.conversations(db, bola)["conversations"][0]
    assert listed["unread"] == 0 == messages.unread_count(db, bola)


# R10. The dot ignored the CEO case.
def test_r10_the_dot_shows_when_the_ceo_case_can_be_begun(db):
    player, _ = professional(db, now=NOW9)
    db.execute("UPDATE careers SET rank = 2 WHERE player_id = %s", (player,))
    careers.add_experience(db, player, "accountant", careers.experience_for(45), NOW9)
    mine = careers.career(db, player)
    assert mine["level"] == 45 and mine["level"] < careers.level_cap(mine["rank"])      # short of the build's next gate
    assert ranks.waiting(db, player, mine, NOW9) is False
    master(db, player, "ceo")
    assert ranks.waiting(db, player, careers.career(db, player), NOW9) is True


# R11. A loophole test reported a message number that might not exist; it now uses a real message
#      (tests/test_quick_fixes_loopholes.py, q1). Here: a stranger cannot report a real message either way.
def test_r11_a_stranger_cannot_report_a_real_message(db):
    ada, bola, chidi = person(db, "ada"), person(db, "bola"), person(db, "chidi")
    sent = messages.send(db, ada, "bola", "Hi", NOW9)
    with pytest.raises(messages.MessageError, match="no such message"):
        messages.report(db, chidi, sent["id"], None, NOW9)
    assert _dicts(db, "SELECT count(*) AS n FROM message_reports")[0]["n"] == 0
