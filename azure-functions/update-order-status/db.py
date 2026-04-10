"""Database connection helper for the Azure Function.

Reads POSTGRES_CONNECTION_STRING from environment / app settings and returns a
psycopg2 connection with SSL required and RealDictCursor as the default.
"""

import os
from urllib.parse import urlparse, unquote

import psycopg2
import psycopg2.extras


def get_connection():
    """Create and return a new psycopg2 connection to PostgreSQL."""
    conn_str = os.environ["POSTGRES_CONNECTION_STRING"]
    parsed = urlparse(conn_str)

    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=unquote(parsed.password or ""),
        sslmode="require",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )
