"""PostgreSQL database connectivity for the Azure Function App."""

import os
from urllib.parse import urlparse, unquote

import psycopg2
import psycopg2.extras

_connection = None


def get_connection():
    """Return a reusable PostgreSQL connection (created on first call)."""
    global _connection
    if _connection is None or _connection.closed:
        conn_str = os.environ["POSTGRES_CONNECTION_STRING"]
        parsed = urlparse(conn_str)
        _connection = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=unquote(parsed.password or ""),
            sslmode="require",
        )
        _connection.autocommit = True
    return _connection


def reset_connection():
    """Close and discard the current connection (useful for tests)."""
    global _connection
    if _connection is not None and not _connection.closed:
        _connection.close()
    _connection = None


def set_test_connection(conn):
    """Inject a mock/test connection."""
    global _connection
    _connection = conn
