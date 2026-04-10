"""Database connection helper for the Azure Function.

Uses psycopg2 to connect to PostgreSQL via the same
POSTGRES_CONNECTION_STRING env var used by the PHP backend.
"""

import os
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

_conn = None


def get_connection():
    """Return a reusable psycopg2 connection (created on first call).

    The connection string is expected in the POSTGRES_CONNECTION_STRING
    environment variable, e.g.:
        postgresql://user:pass@host:5432/dbname
    """
    global _conn
    if _conn is None or _conn.closed:
        conn_str = os.environ["POSTGRES_CONNECTION_STRING"]
        parsed = urlparse(conn_str)
        _conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            dbname=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
            sslmode="require",
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        _conn.autocommit = False
    return _conn
