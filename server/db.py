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
    pool = ConnectionPool(get_settings().database_url, kwargs={"row_factory": dict_row}, open=False)
    pool.open()
    return pool


def get_connection() -> Iterator[Connection]:
    """Hands one request a database connection. Its work is saved if the request
    succeeds and undone if it fails."""
    with _pool().connection() as conn:
        yield conn


def close_pool() -> None:
    if _pool.cache_info().currsize:
        _pool().close()
        _pool.cache_clear()
