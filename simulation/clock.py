"""The world clock.

One clock for the whole game, set to Lagos time (design document, section 5).
It answers two questions:

1. Is the stock exchange open right now?
2. What is the date in the game's own calendar?

This file owns "time and market hours". No other part of the game is allowed
to work these out for itself (design document, section 19, "one owner per value").

Everything here is plain calculation. It reads no database and no system
clock: the caller passes in the current time. That makes it easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

LAGOS = ZoneInfo("Africa/Lagos")

# Exchange hours, Lagos time, every day of the week.
AUCTION_START = time(11, 30)
MARKET_OPEN = time(12, 0)
MARKET_CLOSE = time(22, 0)

# The business calendar is compressed:
# one real week is one game quarter, four real weeks are one game year.
REAL_DAYS_PER_QUARTER = 7
QUARTERS_PER_YEAR = 4
GAME_DAYS_PER_QUARTER = 90


class MarketState(str, Enum):
    OPENING_AUCTION = "opening_auction"
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True)
class GameDate:
    """A date in the game's calendar. Years, quarters and days all start at 1."""

    year: int
    quarter: int
    day_of_quarter: int


@dataclass(frozen=True)
class ClockSnapshot:
    lagos_time: datetime
    market_state: MarketState
    next_state: MarketState
    next_change_at: datetime
    world_started: bool
    game_date: GameDate | None


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("The clock needs a time that carries its time zone.")


def to_lagos(moment: datetime) -> datetime:
    _require_aware(moment)
    return moment.astimezone(LAGOS)


def market_state(moment: datetime) -> MarketState:
    """Whether the exchange is in its opening auction, open, or closed."""
    now = to_lagos(moment).time()
    if AUCTION_START <= now < MARKET_OPEN:
        return MarketState.OPENING_AUCTION
    if MARKET_OPEN <= now < MARKET_CLOSE:
        return MarketState.OPEN
    return MarketState.CLOSED


def next_change(moment: datetime) -> tuple[MarketState, datetime]:
    """The next market state, and the Lagos time at which it begins."""
    now = to_lagos(moment)
    today = now.date()

    def at(day, clock_time: time) -> datetime:
        return datetime.combine(day, clock_time, tzinfo=LAGOS)

    state = market_state(moment)
    if state is MarketState.OPENING_AUCTION:
        return MarketState.OPEN, at(today, MARKET_OPEN)
    if state is MarketState.OPEN:
        return MarketState.CLOSED, at(today, MARKET_CLOSE)
    # Closed: the next auction is later today, or tomorrow if today's has passed.
    if now.time() < AUCTION_START:
        return MarketState.OPENING_AUCTION, at(today, AUCTION_START)
    return MarketState.OPENING_AUCTION, at(today + timedelta(days=1), AUCTION_START)


def game_date(moment: datetime, world_start: datetime) -> GameDate | None:
    """The game-calendar date, or None if the world has not started yet."""
    _require_aware(moment)
    _require_aware(world_start)
    elapsed = moment - world_start
    if elapsed < timedelta(0):
        return None

    quarter_length = timedelta(days=REAL_DAYS_PER_QUARTER)
    quarters_elapsed = elapsed // quarter_length
    into_quarter = elapsed - quarters_elapsed * quarter_length
    day_of_quarter = int(into_quarter / quarter_length * GAME_DAYS_PER_QUARTER) + 1

    return GameDate(
        year=quarters_elapsed // QUARTERS_PER_YEAR + 1,
        quarter=quarters_elapsed % QUARTERS_PER_YEAR + 1,
        day_of_quarter=min(day_of_quarter, GAME_DAYS_PER_QUARTER),
    )


def snapshot(moment: datetime, world_start: datetime) -> ClockSnapshot:
    """Everything a screen needs to show the time and the market's status."""
    upcoming_state, upcoming_at = next_change(moment)
    date = game_date(moment, world_start)
    return ClockSnapshot(
        lagos_time=to_lagos(moment),
        market_state=market_state(moment),
        next_state=upcoming_state,
        next_change_at=upcoming_at,
        world_started=date is not None,
        game_date=date,
    )
