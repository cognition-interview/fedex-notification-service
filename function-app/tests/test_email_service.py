"""Tests for the email service module."""

import base64
import hashlib
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from email_service import (
    _parse_email_connection_string,
    _build_signature,
    send_status_update_email,
)


class TestParseEmailConnectionString:
    def test_parses_valid_connection_string(self):
        conn_str = "endpoint=https://my-resource.communication.azure.com;accesskey=dGVzdGtleQ=="
        endpoint, key = _parse_email_connection_string(conn_str)
        assert endpoint == "https://my-resource.communication.azure.com"
        assert key == "dGVzdGtleQ=="

    def test_strips_trailing_slash(self):
        conn_str = "endpoint=https://my-resource.communication.azure.com/;accesskey=abc"
        endpoint, key = _parse_email_connection_string(conn_str)
        assert endpoint == "https://my-resource.communication.azure.com"

    def test_returns_empty_for_invalid_string(self):
        endpoint, key = _parse_email_connection_string("garbage")
        assert endpoint == ""
        assert key == ""


class TestBuildSignature:
    def test_signature_is_base64(self):
        # Use a known base64-encoded key
        access_key = base64.b64encode(b"test-secret-key").decode()
        sig = _build_signature(
            "POST",
            "/emails:send?api-version=2021-10-01-preview",
            "Mon, 07 Apr 2026 12:00:00 GMT",
            "my-resource.communication.azure.com",
            "content-hash-here",
            access_key,
        )
        # Verify it's valid base64
        decoded = base64.b64decode(sig)
        assert len(decoded) == 32  # SHA-256 produces 32 bytes

    def test_signature_deterministic(self):
        access_key = base64.b64encode(b"deterministic-key").decode()
        args = (
            "POST",
            "/path",
            "Mon, 07 Apr 2026 12:00:00 GMT",
            "host.example.com",
            "hash123",
            access_key,
        )
        sig1 = _build_signature(*args)
        sig2 = _build_signature(*args)
        assert sig1 == sig2

    def test_different_inputs_produce_different_signatures(self):
        access_key = base64.b64encode(b"key").decode()
        sig1 = _build_signature("POST", "/path1", "date", "host", "hash", access_key)
        sig2 = _build_signature("POST", "/path2", "date", "host", "hash", access_key)
        assert sig1 != sig2


class TestSendStatusUpdateEmail:
    ORDER = {
        "tracking_number": "TRK-001",
        "origin": "Memphis, TN",
        "destination": "New York, NY",
    }
    BUSINESS = {
        "contact_email": "test@example.com",
        "name": "Acme Corp",
    }

    def test_returns_false_when_no_config(self):
        with patch.dict(os.environ, {}, clear=True):
            result = send_status_update_email(
                self.ORDER, self.BUSINESS, "In Transit"
            )
            assert result is False

    def test_returns_false_when_invalid_connection_string(self):
        with patch.dict(os.environ, {
            "AZURE_EMAIL_CONNECTION_STRING": "garbage",
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@example.com",
        }):
            result = send_status_update_email(
                self.ORDER, self.BUSINESS, "In Transit"
            )
            assert result is False

    @patch("email_service.urllib.request.urlopen")
    def test_sends_email_successfully(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.read.return_value = b'{"id":"msg-123"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        access_key = base64.b64encode(b"test-key-for-email").decode()
        conn_str = f"endpoint=https://test.communication.azure.com;accesskey={access_key}"

        with patch.dict(os.environ, {
            "AZURE_EMAIL_CONNECTION_STRING": conn_str,
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@test.com",
        }):
            result = send_status_update_email(
                self.ORDER, self.BUSINESS, "Delivered", "Package delivered to front door"
            )
            assert result is True

        # Verify the request was made
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "emails:send" in req.full_url
        assert req.method == "POST"

        # Verify email body content
        body = json.loads(req.data.decode("utf-8"))
        assert body["content"]["subject"] == "FedEx Update: Tracking #TRK-001 — Delivered"
        assert "Acme Corp" in body["content"]["plainText"]
        assert body["recipients"]["to"][0]["email"] == "test@example.com"

    @patch("email_service.urllib.request.urlopen")
    def test_uses_default_description(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.read.return_value = b'{}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        access_key = base64.b64encode(b"test-key").decode()
        conn_str = f"endpoint=https://test.communication.azure.com;accesskey={access_key}"

        with patch.dict(os.environ, {
            "AZURE_EMAIL_CONNECTION_STRING": conn_str,
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@test.com",
        }):
            result = send_status_update_email(
                self.ORDER, self.BUSINESS, "In Transit"
            )
            assert result is True

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert "Status updated to In Transit" in body["content"]["plainText"]

    @patch("email_service.urllib.request.urlopen")
    def test_returns_false_on_http_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://test.com",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=MagicMock(read=MagicMock(return_value=b"error")),
        )

        access_key = base64.b64encode(b"key").decode()
        conn_str = f"endpoint=https://test.communication.azure.com;accesskey={access_key}"

        with patch.dict(os.environ, {
            "AZURE_EMAIL_CONNECTION_STRING": conn_str,
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@test.com",
        }):
            result = send_status_update_email(
                self.ORDER, self.BUSINESS, "In Transit"
            )
            assert result is False
