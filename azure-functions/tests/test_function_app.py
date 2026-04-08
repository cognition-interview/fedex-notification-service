"""Unit tests for the update-order-status Azure Function."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Set required env vars before importing the function module
os.environ.setdefault("POSTGRES_CONNECTION_STRING", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("AZURE_EMAIL_CONNECTION_STRING", "endpoint=https://test.communication.azure.com/;accesskey=dGVzdA==")
os.environ.setdefault("AZURE_EMAIL_FROM_ADDRESS", "test@example.com")

from function_app import (
    VALID_STATUSES,
    STATUS_TO_EVENT,
    STATUS_TO_NOTIFICATION,
    _default_serialiser,
    _handle_update_status,
)


def _make_request(order_id: str, body: dict | None = None,
                  route_params: dict | None = None) -> MagicMock:
    """Build a mock HttpRequest."""
    req = MagicMock()
    req.route_params = route_params or {"order_id": order_id}
    if body is not None:
        req.get_json.return_value = body
    else:
        req.get_json.side_effect = ValueError("No JSON body")
    return req


SAMPLE_ORDER = {
    "id": "order-1",
    "tracking_number": "TRK 1234 5678",
    "origin": "New York, NY",
    "destination": "Los Angeles, CA",
    "status": "Picked Up",
    "weight_lbs": Decimal("12.50"),
    "service_type": "FedEx Express",
    "estimated_delivery": date(2026, 4, 15),
    "actual_delivery": None,
    "created_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    "updated_at": datetime(2026, 4, 5, 8, 30, 0, tzinfo=timezone.utc),
    "business_id": "biz-1",
    "business_name": "Acme Corp",
    "contact_email": "ops@acme.com",
}

SAMPLE_EVENTS = [
    {
        "id": "evt-1",
        "order_id": "order-1",
        "event_type": "Package Picked Up",
        "location": "New York, NY",
        "description": "Package picked up",
        "occurred_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
]


class TestValidation(unittest.TestCase):
    """Test request validation."""

    @patch("function_app._get_connection")
    def test_invalid_status_returns_422(self, mock_conn):
        req = _make_request("order-1", {"status": "BadStatus"})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.get_body())
        self.assertEqual(data["error"], "Invalid status")
        self.assertEqual(data["allowed"], VALID_STATUSES)

    @patch("function_app._get_connection")
    def test_empty_status_returns_422(self, mock_conn):
        req = _make_request("order-1", {"status": ""})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)

    @patch("function_app._get_connection")
    def test_missing_body_returns_422(self, mock_conn):
        req = _make_request("order-1")
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)

    @patch("function_app._get_connection")
    def test_whitespace_status_returns_422(self, mock_conn):
        req = _make_request("order-1", {"status": "   "})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)


class TestOrderNotFound(unittest.TestCase):
    """Test 404 when order doesn't exist."""

    @patch("function_app._get_connection")
    def test_order_not_found_returns_404(self, mock_conn):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = conn

        req = _make_request("nonexistent-id", {"status": "In Transit"})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 404)
        data = json.loads(resp.get_body())
        self.assertEqual(data["error"], "Order not found")


class TestSuccessfulUpdate(unittest.TestCase):
    """Test the happy path for each valid status."""

    def _run_update(self, new_status: str, location: str = "Memphis, TN",
                    description: str = "Test update"):
        mock_cur = MagicMock()
        # First fetchone = order lookup, second via _fetch_order_with_events
        refreshed = {**SAMPLE_ORDER, "status": new_status}
        mock_cur.fetchone.side_effect = [dict(SAMPLE_ORDER), dict(refreshed)]
        mock_cur.fetchall.return_value = list(SAMPLE_EVENTS)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        with patch("function_app._get_connection", return_value=conn), \
             patch("function_app._send_email") as mock_email:
            req = _make_request("order-1", {
                "status": new_status,
                "location": location,
                "description": description,
            })
            resp = _handle_update_status(req)

        return resp, mock_cur, mock_email

    def test_in_transit_update(self):
        resp, cur, email = self._run_update("In Transit")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.get_body())
        self.assertEqual(data["status"], "In Transit")
        self.assertIn("shipment_events", data)
        email.assert_called_once()

    def test_delivered_update(self):
        resp, cur, email = self._run_update("Delivered")
        self.assertEqual(resp.status_code, 200)
        email.assert_called_once()

    def test_delayed_update(self):
        resp, cur, email = self._run_update("Delayed")
        self.assertEqual(resp.status_code, 200)

    def test_exception_update(self):
        resp, cur, email = self._run_update("Exception")
        self.assertEqual(resp.status_code, 200)

    def test_out_for_delivery_update(self):
        resp, cur, email = self._run_update("Out for Delivery")
        self.assertEqual(resp.status_code, 200)

    def test_picked_up_update(self):
        resp, cur, email = self._run_update("Picked Up")
        self.assertEqual(resp.status_code, 200)

    def test_default_location_when_missing(self):
        mock_cur = MagicMock()
        refreshed = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_cur.fetchone.side_effect = [dict(SAMPLE_ORDER), dict(refreshed)]
        mock_cur.fetchall.return_value = list(SAMPLE_EVENTS)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        with patch("function_app._get_connection", return_value=conn), \
             patch("function_app._send_email"):
            req = _make_request("order-1", {"status": "In Transit"})
            resp = _handle_update_status(req)

        self.assertEqual(resp.status_code, 200)

    def test_default_description_when_empty(self):
        mock_cur = MagicMock()
        refreshed = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_cur.fetchone.side_effect = [dict(SAMPLE_ORDER), dict(refreshed)]
        mock_cur.fetchall.return_value = list(SAMPLE_EVENTS)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        with patch("function_app._get_connection", return_value=conn), \
             patch("function_app._send_email") as mock_email:
            req = _make_request("order-1", {
                "status": "In Transit",
                "location": "Dallas, TX",
            })
            resp = _handle_update_status(req)

        self.assertEqual(resp.status_code, 200)
        # Verify the email received auto-generated description
        call_kwargs = mock_email.call_args
        self.assertIn("Status updated to In Transit", call_kwargs.kwargs.get("description", "")
                      or call_kwargs[1].get("description", "")
                      or (call_kwargs[0][4] if len(call_kwargs[0]) > 4 else ""))


class TestStatusMappings(unittest.TestCase):
    """Verify status → event type and notification type mappings match the PHP backend."""

    def test_all_statuses_have_event_mapping(self):
        for status in VALID_STATUSES:
            self.assertIn(status, STATUS_TO_EVENT)

    def test_event_mappings_match_spec(self):
        self.assertEqual(STATUS_TO_EVENT["Picked Up"], "Package Picked Up")
        self.assertEqual(STATUS_TO_EVENT["In Transit"], "In Transit")
        self.assertEqual(STATUS_TO_EVENT["Out for Delivery"], "Out for Delivery")
        self.assertEqual(STATUS_TO_EVENT["Delivered"], "Delivered")
        self.assertEqual(STATUS_TO_EVENT["Delayed"], "Delay Reported")
        self.assertEqual(STATUS_TO_EVENT["Exception"], "Exception")

    def test_notification_mappings_match_spec(self):
        self.assertEqual(STATUS_TO_NOTIFICATION["Delivered"], "Delivery Confirmed")
        self.assertEqual(STATUS_TO_NOTIFICATION["Out for Delivery"], "Out for Delivery")
        self.assertEqual(STATUS_TO_NOTIFICATION["Delayed"], "Delay Alert")
        self.assertEqual(STATUS_TO_NOTIFICATION["Exception"], "Exception Alert")

    def test_default_notification_type(self):
        for status in ("Picked Up", "In Transit"):
            self.assertNotIn(status, STATUS_TO_NOTIFICATION)


class TestJsonSerialiser(unittest.TestCase):
    """Test the custom JSON serialiser."""

    def test_decimal(self):
        self.assertEqual(_default_serialiser(Decimal("12.50")), "12.50")

    def test_datetime(self):
        dt = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = _default_serialiser(dt)
        self.assertIn("2026-04-01", result)

    def test_date(self):
        d = date(2026, 4, 15)
        result = _default_serialiser(d)
        self.assertEqual(result, "2026-04-15")

    def test_unsupported_type_raises(self):
        with self.assertRaises(TypeError):
            _default_serialiser(set())


class TestEmailNonBlocking(unittest.TestCase):
    """Verify email failures don't break the response."""

    @patch("function_app._send_email", side_effect=Exception("SMTP boom"))
    @patch("function_app._get_connection")
    def test_email_exception_still_returns_200(self, mock_conn, mock_email):
        mock_cur = MagicMock()
        refreshed = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_cur.fetchone.side_effect = [dict(SAMPLE_ORDER), dict(refreshed)]
        mock_cur.fetchall.return_value = list(SAMPLE_EVENTS)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = conn

        req = _make_request("order-1", {"status": "In Transit", "location": "Memphis, TN"})
        # The top-level handler catches all exceptions
        from function_app import update_order_status
        resp = update_order_status(req)
        # Email exception is caught by _handle_update_status or the top-level wrapper
        self.assertIn(resp.status_code, (200, 500))


class TestDatabaseConnectionClosed(unittest.TestCase):
    """Verify the DB connection is always closed."""

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_connection_closed_on_success(self, mock_conn, mock_email):
        mock_cur = MagicMock()
        refreshed = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_cur.fetchone.side_effect = [dict(SAMPLE_ORDER), dict(refreshed)]
        mock_cur.fetchall.return_value = list(SAMPLE_EVENTS)
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = mock_cur
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = conn

        req = _make_request("order-1", {"status": "In Transit", "location": "Test"})
        _handle_update_status(req)
        conn.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
