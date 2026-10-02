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
    pool = ConnectionPool(
        get_settings().database_url, kwargs={"row_factory": dict_row, "autocommit": True}, open=False
    )
    pool.open()
    return pool


def get_connection() -> Iterator[Connection]:
    """Hands one request a database connection."""
    with _pool().connection() as conn:
        yield conn


def close_pool() -> None:
    if _pool.cache_info().currsize:
        _pool().close()
        _pool.cache_clear()
