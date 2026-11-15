"""The world's health check (simulation.check_world): it only reads, and it finds what is out of place."""

from __future__ import annotations

import pytest

from simulation import check_world
from tests.test_empires import founded

pytestmark = pytest.mark.world("eight")


def test_a_sound_world_with_an_empire_passes(db):
    founded(db)
    assert check_world.check(db) == []


def test_a_head_left_in_an_ordinary_seat_is_found_and_the_books_still_pass(db):
    empire, (head, _), partners = founded(db)
    # As an empire looked before the head's chair (migration 052): the head in their build's first seat.
    db.execute("DELETE FROM empire_seats WHERE empire_id = %s AND slot = 0", (empire["id"],))
    db.execute("UPDATE empire_seats SET player_id = NULL WHERE empire_id = %s AND build = 'asset_manager' AND slot = 2",
               (empire["id"],))
    db.execute("UPDATE empire_seats SET player_id = %s WHERE empire_id = %s AND build = 'asset_manager' AND slot = 2",
               (head, empire["id"]))
    faults = check_world.check(db)
    assert any("not the head's chair" in f for f in faults), faults
    assert not any("does not add up" in f or "do not add up" in f for f in faults)
