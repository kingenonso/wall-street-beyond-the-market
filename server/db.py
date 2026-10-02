"""The connection to the database."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from server.config import get_settings


@lru_cache
def _pool() -> ConnectionPool:
    # autocommit: a single statement is saved at once. Anything that takes several
    # statements must be wrapped in `with conn.transaction():`, which saves all of it
    # or none of it, and has saved it by the time the block ends.
    settings = get_settings()
    pool = ConnectionPool(
        settings.database_url,
        kwargs={"row_factory": dict_row, "autocommit": True},
        min_size=2,
        max_size=settings.database_pool_size,
        timeout=5,          # when every connection is busy, give up quickly and say "busy"
        open=False,
    )
    pool.open()
    return pool


def get_connection() -> Iterator[Connection]:
    """Hands one request a database connection."""
    with _pool().connection() as conn:
        yield conn


def connection():
    """A connection for a short piece of work: `with connection() as conn:`."""
    return _pool().connection()


def close_pool() -> None:
    if _pool.cache_info().currsize:
        _pool().close()
        _pool.cache_clear()
