"""Good and bad fortune.

Each world has a secret chosen at random when it is created. Every quarter's
fortune, for every company and every sector, is worked out from that secret.
Nobody outside the server can know it in advance, yet asking again for the
same quarter always gives the same answer.
"""

from __future__ import annotations

import hashlib


def fortune_bps(seed: str, subject: str, period: int, what: str, size_bps: int) -> int:
    """This quarter's good or bad fortune, between -size and +size.

    Most quarters land near the middle; big swings are rare.
    """
    if size_bps <= 0:
        return 0
    digest = hashlib.sha256(f"{seed}:{subject}:{period}:{what}".encode()).digest()
    first = int.from_bytes(digest[:4], "big") / 2**32
    second = int.from_bytes(digest[4:8], "big") / 2**32
    return round(size_bps * (first + second - 1))
