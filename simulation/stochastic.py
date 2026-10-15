"""Stage 9: the stochastic engine. Each quarter's surprises, drawn the way real ones fall.

Before Stage 9 every surprise was its own coin toss, spread evenly up to a limit. Now:

  * Surprises follow a bell curve with fat tails (a Student's t with four degrees of freedom):
    most quarters are ordinary, and a rare one is far worse (or better) than the usual limit.
  * Things that should move together do. Each quarter has a few common forces: the economy as
    a whole, energy, building, farming and money. Each industry, company, the oil price and the
    naira lean on the forces that move them, and add their own part.

Everything is still worked out from the world's secret seed: nobody outside the server can know
it in advance, and asking again for the same quarter gives the same answer. The common forces are
kept on the record (for checking), and are never sent to players.

A draw of size S here has the same typical spread as the old even draw of size S (its standard
deviation is S/sqrt(6)), but it can reach up to MOST_TIMES x S in a rare quarter.
"""

from __future__ import annotations

import hashlib
import math

from simulation import world_data as data

FACTORS = ("economy", "energy", "building", "farming", "money")
DEGREES_OF_FREEDOM = 4
SPREAD = 1 / math.sqrt(6)            # the old even draw's standard deviation, as a share of its size
MOST_TIMES = 2.5                     # a surprise never goes beyond 2.5 times the old limit


def _unit(seed: str, *key) -> float:
    """A number in (0, 1), fixed by its inputs."""
    digest = hashlib.sha256((seed + ":" + ":".join(str(k) for k in key)).encode()).digest()
    return (int.from_bytes(digest[:7], "big") + 0.5) / 2**56


def normal(seed: str, *key) -> float:
    """A draw from the standard bell curve (mean 0, spread 1)."""
    u1, u2 = _unit(seed, *key, "n1"), _unit(seed, *key, "n2")
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def fat_tailed(seed: str, *key, df: int = DEGREES_OF_FREEDOM) -> float:
    """A draw with fat tails (Student's t), scaled to a spread of 1."""
    z = normal(seed, *key, "z")
    chi2 = sum(normal(seed, *key, "c", n) ** 2 for n in range(df))
    t = z / math.sqrt(max(chi2, 1e-9) / df)
    return t * math.sqrt((df - 2) / df)


def factor(seed: str, name: str, period: int) -> float:
    """One of the quarter's common forces (spread 1)."""
    return fat_tailed(seed, "factor", name, period)


def factors(seed: str, period: int) -> dict[str, float]:
    return {name: factor(seed, name, period) for name in FACTORS}


def shock(seed: str, subject: str, period: int, what: str, loadings: dict[str, float] | None = None) -> float:
    """A surprise of spread 1: the common forces it leans on, and its own part."""
    loadings = loadings or {}
    shared = sum(weight * factor(seed, name, period) for name, weight in loadings.items())
    own_weight = math.sqrt(max(1 - sum(w * w for w in loadings.values()), 0))
    return shared + own_weight * fat_tailed(seed, subject, period, what)


def shock_bps(seed: str, subject: str, period: int, what: str, size_bps: int, loadings: dict[str, float] | None = None) -> int:
    """A surprise in hundredths of a percent, with the old draw's typical spread for the same size,
    and fat tails capped at MOST_TIMES the size."""
    if size_bps <= 0:
        return 0
    x = shock(seed, subject, period, what, loadings) * SPREAD
    x = min(max(x, -MOST_TIMES), MOST_TIMES)
    return round(size_bps * x)


def sector_loadings(sector: str) -> dict[str, float]:
    return dict(data.SECTOR_FACTOR_LOADINGS.get(sector, {"economy": 0.4}))


def company_loadings(sector: str) -> dict[str, float]:
    """A company shares part of its industry's forces; the rest of its luck is its own."""
    return {name: weight * data.COMPANY_SHARES_OF_SECTOR for name, weight in sector_loadings(sector).items()}


def record(conn, period: int, seed: str) -> None:
    """Keep the quarter's common forces on the record (never sent to players)."""
    for name, value in factors(seed, period).items():
        conn.execute("INSERT INTO stochastic_factors (period, name, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                     (period, name, value))
