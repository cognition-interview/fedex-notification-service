"""Tests for the database connection module."""

import os
import pytest
from unittest.mock import patch, MagicMock
from db import _parse_connection_string, get_connection, set_test_connection


class TestParseConnectionString:
    def test_parses_standard_url(self):
        url = "postgresql://user:pass@host.example.com:5432/mydb"
        result = _parse_connection_string(url)
        assert result["host"] == "host.example.com"
        assert result["port"] == 5432
        assert result["dbname"] == "mydb"
        assert result["user"] == "user"
        assert result["password"] == "pass"
        assert result["sslmode"] == "require"

    def test_parses_url_with_encoded_password(self):
        url = "postgresql://user:p%40ss%23word@host:5432/db"
        result = _parse_connection_string(url)
        assert result["password"] == "p@ss#word"

    def test_default_port(self):
        url = "postgresql://user:pass@host/db"
        result = _parse_connection_string(url)
        assert result["port"] == 5432

    def test_parses_url_with_no_password(self):
        url = "postgresql://user@host:5432/db"
        result = _parse_connection_string(url)
        assert result["password"] == ""


class TestSetTestConnection:
    def test_set_test_connection(self):
        mock_conn = MagicMock()
        mock_conn.closed = 0  # psycopg2 uses 0 for open connections
        set_test_connection(mock_conn)
        # After setting, get_connection should return the mock
        result = get_connection()
        assert result is mock_conn

    def teardown_method(self):
        set_test_connection(None)


class TestGetConnection:
    def test_raises_when_no_connection_string(self):
        set_test_connection(None)
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="POSTGRES_CONNECTION_STRING is not set"):
                get_connection()

    def teardown_method(self):
        set_test_connection(None)
