"""Limits on how often one visitor may try to log in or sign up.

Without them, a program could guess passwords all day, open accounts by the
thousand, or keep the server so busy that real players are shut out.

TEMPORARY SIMPLICITY (Stage 16 hardens this): the counts are kept in this one
server's memory. When the game runs on several servers they must be shared.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from server.config import get_settings

_lock = threading.Lock()
_attempts: dict[str, deque[float]] = defaultdict(deque)

# Working out a password check is deliberately slow. Only a few may run at once,
# so a flood of logins cannot use up the whole machine.
password_work = threading.BoundedSemaphore(4)


def visitor(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def allow(action: str, who: str, *, attempts: int, per_seconds: int) -> None:
    """Count one attempt. Refuses with "too many attempts" once the limit is passed."""
    if not get_settings().rate_limits:
        return
    now = time.monotonic()
    with _lock:
        if len(_attempts) > 50_000:                      # never let the notebook itself grow without end
            for key in [k for k, v in _attempts.items() if not v or now - v[-1] > 3600]:
                del _attempts[key]
        recent = _attempts[f"{action}:{who}"]
        while recent and now - recent[0] > per_seconds:
            recent.popleft()
        if len(recent) >= attempts:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Please wait a few minutes and try again."
            )
        recent.append(now)


def forget_all() -> None:
    with _lock:
        _attempts.clear()
