"""The world clock: market hours in Lagos time, and the game calendar."""

from datetime import datetime, timedelta, timezone

import pytest

from simulation import clock
from simulation.clock import LAGOS, GameDate, MarketState

WORLD_START = datetime(2026, 10, 5, 0, 0, tzinfo=LAGOS)


def lagos(hour: int, minute: int = 0, day: int = 6) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=LAGOS)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (lagos(0, 0), MarketState.CLOSED),
        (lagos(11, 29), MarketState.CLOSED),
        (lagos(11, 30), MarketState.OPENING_AUCTION),
        (lagos(11, 59), MarketState.OPENING_AUCTION),
        (lagos(12, 0), MarketState.OPEN),
        (lagos(21, 59), MarketState.OPEN),
        (lagos(22, 0), MarketState.CLOSED),
        (lagos(23, 59), MarketState.CLOSED),
    ],
)
def test_market_state_at_each_boundary(moment, expected):
    assert clock.market_state(moment) is expected


def test_market_hours_follow_lagos_time_not_the_callers_time_zone():
    # 11:00 UTC is 12:00 in Lagos, so the market is open wherever the player is.
    assert clock.market_state(datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)) is MarketState.OPEN
    # 10:00 in Regina (UTC-6) is 17:00 in Lagos.
    regina = timezone(timedelta(hours=-6))
    assert clock.market_state(datetime(2026, 10, 6, 10, 0, tzinfo=regina)) is MarketState.OPEN


def test_market_opens_every_day_including_weekends():
    saturday = datetime(2026, 10, 10, 15, 0, tzinfo=LAGOS)
    assert saturday.weekday() == 5
    assert clock.market_state(saturday) is MarketState.OPEN


@pytest.mark.parametrize(
    ("moment", "next_state", "next_at"),
    [
        (lagos(9, 0), MarketState.OPENING_AUCTION, lagos(11, 30)),
        (lagos(11, 45), MarketState.OPEN, lagos(12, 0)),
        (lagos(15, 0), MarketState.CLOSED, lagos(22, 0)),
        (lagos(22, 30), MarketState.OPENING_AUCTION, lagos(11, 30, day=7)),
    ],
)
def test_next_change(moment, next_state, next_at):
    assert clock.next_change(moment) == (next_state, next_at)


def test_a_time_without_a_time_zone_is_rejected():
    with pytest.raises(ValueError):
        clock.market_state(datetime(2026, 10, 6, 12, 0))


def test_game_calendar_before_the_world_starts():
    assert clock.game_date(WORLD_START - timedelta(seconds=1), WORLD_START) is None
    assert clock.snapshot(WORLD_START - timedelta(days=1), WORLD_START).world_started is False


def test_game_calendar_first_moment():
    assert clock.game_date(WORLD_START, WORLD_START) == GameDate(1, 1, 1)


def test_one_real_week_is_one_game_quarter():
    assert clock.game_date(WORLD_START + timedelta(days=7), WORLD_START) == GameDate(1, 2, 1)
    just_before = WORLD_START + timedelta(days=7) - timedelta(seconds=1)
    assert clock.game_date(just_before, WORLD_START) == GameDate(1, 1, 90)


def test_four_real_weeks_are_one_game_year():
    assert clock.game_date(WORLD_START + timedelta(days=28), WORLD_START) == GameDate(2, 1, 1)
    assert clock.game_date(WORLD_START + timedelta(days=27), WORLD_START).quarter == 4


def test_day_of_quarter_moves_evenly_through_the_week():
    # Halfway through the real week is game day 46 of 90.
    midweek = WORLD_START + timedelta(days=3, hours=12)
    assert clock.game_date(midweek, WORLD_START) == GameDate(1, 1, 46)
