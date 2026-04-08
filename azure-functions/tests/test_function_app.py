"""Unit tests for the Azure Function – Update Order Status."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Set required env vars BEFORE importing function_app
os.environ.setdefault("POSTGRES_CONNECTION_STRING", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("AZURE_EMAIL_CONNECTION_STRING", "endpoint=https://fake.communication.azure.com/;accesskey=ZmFrZQ==")
os.environ.setdefault("AZURE_EMAIL_FROM_ADDRESS", "DoNotReply@fake.azurecomm.net")

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import function_app  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(body: dict | None = None, order_id: str = "abc-123") -> MagicMock:
    req = MagicMock()
    req.route_params = {"order_id": order_id}
    if body is not None:
        req.get_json.return_value = body
    else:
        req.get_json.side_effect = ValueError("no body")
    return req


ORDER_ROW = {
    "id": "abc-123",
    "tracking_number": "TRK 1234 5678 9012",
    "origin": "New York, NY",
    "destination": "Los Angeles, CA",
    "status": "In Transit",
    "weight_lbs": Decimal("12.50"),
    "service_type": "FedEx Express",
    "estimated_delivery": date(2026, 4, 10),
    "actual_delivery": None,
    "created_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    "updated_at": datetime(2026, 4, 5, 8, 30, 0, tzinfo=timezone.utc),
    "business_id": "biz-001",
    "business_name": "Acme Corp",
    "contact_email": "ops@acme.com",
    "business_account_number": "ACC-0001",
}


# ---------------------------------------------------------------------------
# Tests — Validation
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):
    def test_invalid_json_returns_400(self):
        req = _make_request(body=None)
        resp = function_app.update_order_status(req)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid JSON", resp.get_body().decode())

    def test_missing_status_returns_400(self):
        req = _make_request(body={"location": "Memphis"})
        resp = function_app.update_order_status(req)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid status", resp.get_body().decode())

    def test_bad_status_returns_400(self):
        req = _make_request(body={"status": "Lost Forever"})
        resp = function_app.update_order_status(req)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid status", resp.get_body().decode())

    def test_all_valid_statuses_accepted(self):
        for s in function_app.VALID_STATUSES:
            req = _make_request(body={"status": s})
            with patch.object(function_app, "_get_db_connection") as mock_conn:
                cur = MagicMock()
                cur.fetchone.return_value = None
                mock_conn.return_value.cursor.return_value = cur
                resp = function_app.update_order_status(req)
                # Should reach the DB lookup (404 = order not found, not 400)
                self.assertIn(resp.status_code, (200, 404))


# ---------------------------------------------------------------------------
# Tests — Order not found
# ---------------------------------------------------------------------------

class TestOrderNotFound(unittest.TestCase):
    @patch.object(function_app, "_get_db_connection")
    def test_returns_404(self, mock_conn):
        cur = MagicMock()
        cur.fetchone.return_value = None
        mock_conn.return_value.cursor.return_value = cur

        req = _make_request(body={"status": "In Transit"})
        resp = function_app.update_order_status(req)

        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.get_body().decode())


# ---------------------------------------------------------------------------
# Tests — Successful update
# ---------------------------------------------------------------------------

class TestSuccessfulUpdate(unittest.TestCase):
    def _run(self, new_status: str, **extra_body):
        body = {"status": new_status, "location": "Memphis, TN", **extra_body}
        req = _make_request(body=body)

        with patch.object(function_app, "_get_db_connection") as mock_conn, \
             patch.object(function_app, "_send_email") as mock_email:
            cur = MagicMock()
            # First fetchone → order row, second → refreshed order
            refreshed = dict(ORDER_ROW, status=new_status)
            cur.fetchone.side_effect = [ORDER_ROW, refreshed]
            cur.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = cur

            resp = function_app.update_order_status(req)
            return resp, cur, mock_email, mock_conn

    def test_returns_200(self):
        resp, *_ = self._run("Out for Delivery")
        self.assertEqual(resp.status_code, 200)

    def test_response_is_json(self):
        resp, *_ = self._run("Delivered")
        data = json.loads(resp.get_body())
        self.assertEqual(data["status"], "Delivered")

    def test_delivered_sets_actual_delivery(self):
        _, cur, *_ = self._run("Delivered")
        update_call = cur.execute.call_args_list[1]
        sql = update_call[0][0]
        self.assertIn("actual_delivery", sql)

    def test_non_delivered_no_actual_delivery(self):
        _, cur, *_ = self._run("In Transit")
        update_call = cur.execute.call_args_list[1]
        sql = update_call[0][0]
        self.assertNotIn("actual_delivery", sql)

    def test_shipment_event_inserted(self):
        _, cur, *_ = self._run("In Transit")
        insert_event = cur.execute.call_args_list[2]
        sql = insert_event[0][0]
        self.assertIn("shipment_events", sql)

    def test_notification_inserted(self):
        _, cur, *_ = self._run("Delayed")
        insert_notif = cur.execute.call_args_list[3]
        sql = insert_notif[0][0]
        self.assertIn("notifications", sql)

    def test_email_called(self):
        _, _, mock_email, _ = self._run("Exception")
        mock_email.assert_called_once()

    def test_conn_committed(self):
        _, _, _, mock_conn = self._run("In Transit")
        mock_conn.return_value.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests — Status mappings
# ---------------------------------------------------------------------------

class TestStatusMappings(unittest.TestCase):
    def test_event_mapping_complete(self):
        for s in function_app.VALID_STATUSES:
            self.assertIn(s, function_app.STATUS_TO_EVENT)

    def test_notification_delivered(self):
        self.assertEqual(function_app.STATUS_TO_NOTIFICATION["Delivered"], "Delivery Confirmed")

    def test_notification_delayed(self):
        self.assertEqual(function_app.STATUS_TO_NOTIFICATION["Delayed"], "Delay Alert")

    def test_notification_fallback(self):
        self.assertEqual(function_app.STATUS_TO_NOTIFICATION.get("Picked Up", "Status Update"),
                         "Status Update")


# ---------------------------------------------------------------------------
# Tests — JSON serialiser
# ---------------------------------------------------------------------------

class TestJsonSerialiser(unittest.TestCase):
    def test_decimal(self):
        self.assertEqual(function_app._json_serialiser(Decimal("12.50")), "12.50")

    def test_datetime(self):
        dt = datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.assertIn("2026", function_app._json_serialiser(dt))

    def test_date(self):
        d = date(2026, 4, 1)
        self.assertIn("2026-04-01", function_app._json_serialiser(d))

    def test_unsupported_raises(self):
        with self.assertRaises(TypeError):
            function_app._json_serialiser(object())


# ---------------------------------------------------------------------------
# Tests — Email non-blocking
# ---------------------------------------------------------------------------

class TestEmailNonBlocking(unittest.TestCase):
    @patch.object(function_app, "EmailClient")
    def test_email_exception_logged_not_raised(self, mock_client_cls):
        mock_client_cls.from_connection_string.side_effect = Exception("boom")
        # Should not raise
        function_app._send_email("TRK123", "Delivered", "desc", "a@b.com", "NY", "LA")


# ---------------------------------------------------------------------------
# Tests — DB connection closed
# ---------------------------------------------------------------------------

class TestDatabaseConnectionClosed(unittest.TestCase):
    @patch.object(function_app, "_get_db_connection")
    def test_conn_closed_on_success(self, mock_conn):
        cur = MagicMock()
        refreshed = dict(ORDER_ROW, status="In Transit")
        cur.fetchone.side_effect = [ORDER_ROW, refreshed]
        cur.fetchall.return_value = []
        mock_conn.return_value.cursor.return_value = cur

        with patch.object(function_app, "_send_email"):
            req = _make_request(body={"status": "In Transit", "location": "Memphis"})
            function_app.update_order_status(req)

        mock_conn.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
