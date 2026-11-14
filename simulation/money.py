"""Money arithmetic.

All money in the game is a whole number of kobo (1 naira = 100 kobo). Whole
numbers never pick up the tiny rounding errors that decimal fractions do, so
the books always add up exactly.

Rates are written in "basis points" (bps): hundredths of a percent.
100 bps = 1%, 3000 bps = 30%, 10000 bps = 100%.
"""

from __future__ import annotations

KOBO_PER_NAIRA = 100
BPS = 10_000

# PostgreSQL's whole-number column (bigint) cannot hold more than this.
MAX_AMOUNT = 9_223_372_036_854_775_807


def naira(amount: int) -> int:
    """Whole naira, as kobo."""
    return amount * KOBO_PER_NAIRA


def million_naira(amount: int) -> int:
    """Millions of naira, as kobo."""
    return amount * 1_000_000 * KOBO_PER_NAIRA


def apply_bps(amount: int, bps: int) -> int:
    """`amount` times a rate in basis points, rounded to the nearest kobo (halves round up)."""
    return (amount * bps + BPS // 2) // BPS


def is_whole_amount(value: object) -> bool:
    """True only for a real whole number. Rejects fractions, text, and True/False."""
    return isinstance(value, int) and not isinstance(value, bool)


zero_kobo = 0
