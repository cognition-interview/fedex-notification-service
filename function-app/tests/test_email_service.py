"""Tests for the EmailService Python port."""

import base64
import json
import unittest
from unittest.mock import patch

from shared.email_service import EmailService


class TestEmailService(unittest.TestCase):
    """Tests for shared/email_service.py."""

    def _make_order(self, **overrides):
        defaults = {
            "tracking_number": "748923014456",
            "origin": "Memphis, TN",
            "destination": "New York, NY",
        }
        defaults.update(overrides)
        return defaults

    def _make_business(self, **overrides):
        defaults = {
            "contact_email": "ops@acme.com",
            "name": "Acme Electronics",
        }
        defaults.update(overrides)
        return defaults

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    def test_constructor_parses_connection_string(self):
        svc = EmailService()
        self.assertEqual("https://test.communication.azure.com", svc.endpoint)
        self.assertEqual(
            base64.b64encode(b"test-access-key").decode(), svc.access_key
        )
        self.assertEqual("noreply@fedex-test.com", svc.from_address)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "",
            "AZURE_EMAIL_FROM_ADDRESS": "",
        },
    )
    def test_empty_connection_string_does_not_crash(self):
        svc = EmailService()
        self.assertEqual("", svc.endpoint)
        self.assertEqual("", svc.access_key)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_send_email_calls_correct_endpoint(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        result = svc.send_status_update_email(
            self._make_order(), self._make_business(), "In Transit"
        )

        self.assertTrue(result)
        call_url = mock_post.call_args[0][0]
        self.assertIn("test.communication.azure.com", call_url)
        self.assertIn("/emails:send", call_url)
        self.assertIn("api-version=", call_url)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_email_body_contains_tracking_number(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(tracking_number="999888777"), self._make_business(), "Delayed"
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertIn("999888777", body["content"]["subject"])
        self.assertIn("999888777", body["content"]["plainText"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_email_body_has_correct_structure(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(), self._make_business(), "Out for Delivery"
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertIn("recipients", body)
        self.assertIn("content", body)
        self.assertIn("to", body["recipients"])
        self.assertIn("subject", body["content"])
        self.assertIn("plainText", body["content"])
        self.assertIn("html", body["content"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_email_addresses_correct_recipient(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(),
            self._make_business(contact_email="logistics@example.com"),
            "Delivered",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertEqual("logistics@example.com", body["recipients"]["to"][0]["email"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "shipping@fedex.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_sender_is_configured_from_address(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(), self._make_business(), "Delivered"
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertEqual("shipping@fedex.com", body["sender"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_event_description_appears_in_email(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(),
            self._make_business(),
            "Delayed",
            "Weather delay in Memphis area",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertIn("Weather delay in Memphis area", body["content"]["plainText"])
        self.assertIn("Weather delay in Memphis area", body["content"]["html"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_empty_description_uses_default(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(), self._make_business(), "In Transit", ""
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertIn("Status updated to In Transit", body["content"]["plainText"])

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_returns_false_on_http_error(self, mock_post):
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "Internal Server Error"

        svc = EmailService()
        result = svc.send_status_update_email(
            self._make_order(), self._make_business(), "In Transit"
        )
        self.assertFalse(result)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_returns_false_on_request_exception(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")

        svc = EmailService()
        result = svc.send_status_update_email(
            self._make_order(), self._make_business(), "In Transit"
        )
        self.assertFalse(result)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    def test_build_signature_is_deterministic(self):
        svc = EmailService()
        sig1 = svc._build_signature(
            "POST", "/emails:send", "Mon, 01 Jan 2026 00:00:00 GMT",
            "test.communication.azure.com", "abc123"
        )
        sig2 = svc._build_signature(
            "POST", "/emails:send", "Mon, 01 Jan 2026 00:00:00 GMT",
            "test.communication.azure.com", "abc123"
        )
        self.assertEqual(sig1, sig2)

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    def test_build_signature_returns_valid_base64(self):
        svc = EmailService()
        sig = svc._build_signature(
            "POST",
            "/emails:send?api-version=2021-10-01-preview",
            "Mon, 01 Jan 2026 00:00:00 GMT",
            "test.communication.azure.com",
            base64.b64encode(b"test-hash").decode(),
        )
        self.assertIsNotNone(base64.b64decode(sig, validate=True))

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_auth_header_contains_hmac_sha256(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(), self._make_business(), "In Transit"
        )

        headers = mock_post.call_args[1]["headers"]
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("HMAC-SHA256"))

    @patch.dict(
        "os.environ",
        {
            "AZURE_EMAIL_CONNECTION_STRING": "endpoint=https://test.communication.azure.com;accesskey="
            + base64.b64encode(b"test-access-key").decode(),
            "AZURE_EMAIL_FROM_ADDRESS": "noreply@fedex-test.com",
        },
    )
    @patch("shared.email_service.requests.post")
    def test_plain_text_contains_route(self, mock_post):
        mock_post.return_value.status_code = 202
        mock_post.return_value.text = "{}"

        svc = EmailService()
        svc.send_status_update_email(
            self._make_order(origin="Louisville, KY", destination="Dallas, TX"),
            self._make_business(),
            "In Transit",
        )

        body = json.loads(mock_post.call_args[1]["data"])
        self.assertIn("Louisville, KY", body["content"]["plainText"])
        self.assertIn("Dallas, TX", body["content"]["plainText"])


if __name__ == "__main__":
    unittest.main()
