"""PostgreSQL connection helper for the Azure Function App.

Parses the POSTGRES_CONNECTION_STRING environment variable and returns a
psycopg2 connection with RealDictCursor for dict-style row access.
"""

import os
import re
from urllib.parse import urlparse, unquote

import psycopg2
import psycopg2.extras

_connection = None


def _parse_connection_string(conn_str: str) -> dict:
    """Parse a postgresql:// connection URL into connect() kwargs."""
    parsed = urlparse(conn_str)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": unquote(parsed.password or ""),
        "sslmode": "require",
    }


def get_connection():
    """Return a reusable psycopg2 connection (singleton per function instance).

    The connection uses RealDictCursor so rows are returned as dicts.
    """
    global _connection
    if _connection is None or _connection.closed:
        conn_str = os.environ.get("POSTGRES_CONNECTION_STRING", "")
        if not conn_str:
            raise RuntimeError("POSTGRES_CONNECTION_STRING is not set")
        params = _parse_connection_string(conn_str)
        _connection = psycopg2.connect(
            **params,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return _connection


def set_test_connection(conn):
    """Inject a test connection (used by unit tests)."""
    global _connection
    _connection = conn
