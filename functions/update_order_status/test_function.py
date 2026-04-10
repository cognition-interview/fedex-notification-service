"""Tests for the Update Order Status Azure Function.

Uses unittest.mock to stub out the PostgreSQL connection and email service,
mirroring the approach used in the PHP backend's OrderControllerTest.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch, call

import azure.functions as func

# Ensure dummy env vars are set before importing function modules
os.environ.setdefault(
    "POSTGRES_CONNECTION_STRING", "postgresql://user:pass@localhost:5432/testdb"
)
os.environ.setdefault(
    "AZURE_EMAIL_CONNECTION_STRING",
    "endpoint=https://test.communication.azure.com;accesskey=dGVzdC1rZXk=",
)
os.environ.setdefault("AZURE_EMAIL_FROM_ADDRESS", "noreply@test.com")

from function_app import (
    update_order_status,
    VALID_STATUSES,
    STATUS_TO_EVENT,
    STATUS_TO_NOTIFICATION,
)


def _make_request(
    order_id: str = "ord-001",
    body: dict | None = None,
    method: str = "PATCH",
) -> func.HttpRequest:
    """Build a mock HttpRequest matching the function's route."""
    return func.HttpRequest(
        method=method,
        url=f"https://fedex-update-status.azurewebsites.net/api/orders/{order_id}/status",
        route_params={"order_id": order_id},
        body=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def _sample_order(status: str = "Picked Up", **overrides) -> dict:
    """Return a realistic order row as returned by psycopg2 RealDictCursor."""
    order = {
        "id": "ord-001",
        "tracking_number": "TRK 7489 0001",
        "origin": "Memphis, TN",
        "destination": "New York, NY",
        "status": status,
        "weight_lbs": "12.50",
        "service_type": "FedEx Express",
        "estimated_delivery": "2026-04-15",
        "actual_delivery": None,
        "created_at": "2026-04-01T12:00:00+00:00",
        "updated_at": "2026-04-05T08:30:00+00:00",
        "business_id": "biz-001",
        "business_name": "Acme Corp",
        "contact_email": "ops@acme.com",
    }
    order.update(overrides)
    return order


def _sample_order_with_events(status: str = "In Transit") -> dict:
    """Order dict with nested shipment_events for the refresh response."""
    order = _sample_order(status=status)
    order["shipment_events"] = [
        {
            "id": "evt-001",
            "order_id": "ord-001",
            "event_type": "In Transit",
            "location": "Memphis, TN",
            "description": "Package en route",
            "occurred_at": "2026-04-05T10:00:00+00:00",
        }
    ]
    return order


class TestUpdateOrderStatus(unittest.TestCase):
    """Tests for the update_order_status HTTP trigger."""

    def _mock_cursor(self, fetchone_values=None, fetchall_values=None):
        """Create a mock cursor that returns pre-configured values."""
        cursor = MagicMock()
        if fetchone_values is not None:
            cursor.fetchone = MagicMock(side_effect=fetchone_values)
        else:
            cursor.fetchone = MagicMock(return_value=None)
        if fetchall_values is not None:
            cursor.fetchall = MagicMock(side_effect=fetchall_values)
        else:
            cursor.fetchall = MagicMock(return_value=[])
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)
        return cursor

    def _mock_connection(self, cursor):
        """Create a mock connection that returns the given cursor."""
        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.closed = False
        return conn

    # ── Validation tests ─────────────────────────────────────────────────

    @patch("function_app.get_connection")
    def test_invalid_status_returns_422(self, mock_get_conn):
        req = _make_request(body={"status": "Flying"})
        resp = update_order_status(req)

        self.assertEqual(422, resp.status_code)
        body = json.loads(resp.get_body())
        self.assertIn("error", body)
        self.assertEqual("Invalid status", body["error"])
        self.assertEqual(VALID_STATUSES, body["allowed"])

    @patch("function_app.get_connection")
    def test_empty_status_returns_422(self, mock_get_conn):
        req = _make_request(body={"status": ""})
        resp = update_order_status(req)

        self.assertEqual(422, resp.status_code)

    @patch("function_app.get_connection")
    def test_missing_status_returns_422(self, mock_get_conn):
        req = _make_request(body={})
        resp = update_order_status(req)

        self.assertEqual(422, resp.status_code)

    def test_invalid_json_body_returns_400(self):
        req = func.HttpRequest(
            method="PATCH",
            url="https://fedex-update-status.azurewebsites.net/api/orders/ord-001/status",
            route_params={"order_id": "ord-001"},
            body=b"not json",
            headers={"Content-Type": "application/json"},
        )
        resp = update_order_status(req)
        self.assertEqual(400, resp.status_code)
        body = json.loads(resp.get_body())
        self.assertEqual("Invalid JSON body", body["error"])

    # ── Order not found ──────────────────────────────────────────────────

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_order_not_found_returns_404(self, mock_get_conn, mock_email):
        cursor = self._mock_cursor(fetchone_values=[None])
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(order_id="nonexistent", body={"status": "In Transit"})
        resp = update_order_status(req)

        self.assertEqual(404, resp.status_code)
        body = json.loads(resp.get_body())
        self.assertEqual("Order not found", body["error"])

    # ── Successful status updates ────────────────────────────────────────

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_in_transit_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("Picked Up")
        refreshed = _sample_order_with_events("In Transit")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "In Transit",
            "location": "Nashville, TN",
            "description": "Package departed hub",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)
        body = json.loads(resp.get_body())
        self.assertIn("shipment_events", body)
        conn.commit.assert_called_once()

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_delivered_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("Out for Delivery")
        refreshed = _sample_order_with_events("Delivered")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "Delivered",
            "location": "New York, NY",
            "description": "Left at front door",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)
        conn.commit.assert_called_once()

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_delayed_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("In Transit")
        refreshed = _sample_order_with_events("Delayed")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "Delayed",
            "location": "Nashville, TN",
            "description": "Weather delay",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_exception_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("In Transit")
        refreshed = _sample_order_with_events("Exception")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "Exception",
            "location": "Nashville, TN",
            "description": "Address issue",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_out_for_delivery_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("In Transit")
        refreshed = _sample_order_with_events("Out for Delivery")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "Out for Delivery",
            "location": "New York, NY",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_to_picked_up_returns_200(self, mock_get_conn, mock_email):
        order = _sample_order("Exception")
        refreshed = _sample_order_with_events("Picked Up")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "Picked Up",
            "location": "Memphis, TN",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)

    # ── Default description ──────────────────────────────────────────────

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_update_without_description_uses_default(self, mock_get_conn, mock_email):
        order = _sample_order("Picked Up")
        refreshed = _sample_order_with_events("In Transit")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)

    # ── Email behaviour ──────────────────────────────────────────────────

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_email_is_called_on_success(self, mock_get_conn, mock_email):
        order = _sample_order("Picked Up")
        refreshed = _sample_order_with_events("In Transit")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={
            "status": "In Transit",
            "location": "Nashville, TN",
            "description": "Package departed hub",
        })
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)
        mock_email.assert_called_once()
        call_args = mock_email.call_args
        self.assertEqual(call_args[0][2], "In Transit")

    @patch("function_app.send_status_update_email", side_effect=Exception("SMTP down"))
    @patch("function_app.get_connection")
    def test_email_failure_does_not_fail_request(self, mock_get_conn, mock_email):
        """Email failures are caught — the HTTP response should still be 200."""
        order = _sample_order("Picked Up")
        refreshed = _sample_order_with_events("In Transit")

        cursor = self._mock_cursor(
            fetchone_values=[order, refreshed],
            fetchall_values=[refreshed["shipment_events"]],
        )
        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)
        mock_email.assert_called_once()

    # ── DB error handling ────────────────────────────────────────────────

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_db_error_returns_500_and_rolls_back(self, mock_get_conn, mock_email):
        order = _sample_order("Picked Up")

        cursor = self._mock_cursor(fetchone_values=[order])
        # Make cursor.execute raise on the UPDATE statement (second call inside the with block)
        call_count = 0
        original_execute = cursor.execute

        def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # The UPDATE statement
                raise Exception("Connection lost")

        cursor.execute = MagicMock(side_effect=execute_side_effect)

        conn = self._mock_connection(cursor)
        mock_get_conn.return_value = conn

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        self.assertEqual(500, resp.status_code)
        conn.rollback.assert_called_once()

    # ── Status-to-event and status-to-notification mapping ───────────────

    def test_status_to_event_mapping_complete(self):
        """Every valid status has a corresponding event type."""
        for status in VALID_STATUSES:
            self.assertIn(status, STATUS_TO_EVENT)

    def test_status_to_notification_mapping_has_special_statuses(self):
        """Delivered, Out for Delivery, Delayed, Exception have custom types."""
        self.assertEqual("Delivery Confirmed", STATUS_TO_NOTIFICATION["Delivered"])
        self.assertEqual("Out for Delivery", STATUS_TO_NOTIFICATION["Out for Delivery"])
        self.assertEqual("Delay Alert", STATUS_TO_NOTIFICATION["Delayed"])
        self.assertEqual("Exception Alert", STATUS_TO_NOTIFICATION["Exception"])

    def test_default_notification_type_for_other_statuses(self):
        """Statuses not in the map should default to 'Status Update'."""
        self.assertNotIn("Picked Up", STATUS_TO_NOTIFICATION)
        self.assertNotIn("In Transit", STATUS_TO_NOTIFICATION)


class TestEmailService(unittest.TestCase):
    """Tests for the email_service module."""

    @patch("email_service.requests.post")
    def test_send_email_success(self, mock_post):
        from email_service import send_status_update_email

        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        order = _sample_order()
        business = {"contact_email": "ops@acme.com", "name": "Acme Corp"}

        result = send_status_update_email(order, business, "In Transit", "Package en route")

        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("email_service.requests.post")
    def test_send_email_failure_returns_false(self, mock_post):
        from email_service import send_status_update_email

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        order = _sample_order()
        business = {"contact_email": "ops@acme.com", "name": "Acme Corp"}

        result = send_status_update_email(order, business, "In Transit")

        self.assertFalse(result)

    @patch("email_service.requests.post", side_effect=__import__("requests").RequestException("Network error"))
    def test_send_email_request_exception_returns_false(self, mock_post):
        from email_service import send_status_update_email

        order = _sample_order()
        business = {"contact_email": "ops@acme.com", "name": "Acme Corp"}

        result = send_status_update_email(order, business, "In Transit")

        self.assertFalse(result)

    def test_send_email_missing_connection_string_returns_false(self):
        from email_service import send_status_update_email

        original = os.environ.get("AZURE_EMAIL_CONNECTION_STRING")
        os.environ["AZURE_EMAIL_CONNECTION_STRING"] = ""

        order = _sample_order()
        business = {"contact_email": "ops@acme.com", "name": "Acme Corp"}

        result = send_status_update_email(order, business, "In Transit")

        self.assertFalse(result)

        if original:
            os.environ["AZURE_EMAIL_CONNECTION_STRING"] = original


class TestDatabaseModule(unittest.TestCase):
    """Tests for the db module."""

    @patch("db.psycopg2.connect")
    def test_get_connection_creates_connection(self, mock_connect):
        import db

        # Reset module-level connection
        db._conn = None

        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_connect.return_value = mock_conn

        conn = db.get_connection()

        mock_connect.assert_called_once()
        self.assertEqual(conn, mock_conn)

    @patch("db.psycopg2.connect")
    def test_get_connection_reuses_existing(self, mock_connect):
        import db

        mock_conn = MagicMock()
        mock_conn.closed = False
        db._conn = mock_conn

        conn = db.get_connection()

        mock_connect.assert_not_called()
        self.assertEqual(conn, mock_conn)

    @patch("db.psycopg2.connect")
    def test_get_connection_reconnects_if_closed(self, mock_connect):
        import db

        # Simulate a closed connection
        old_conn = MagicMock()
        old_conn.closed = True
        db._conn = old_conn

        new_conn = MagicMock()
        new_conn.closed = False
        mock_connect.return_value = new_conn

        conn = db.get_connection()

        mock_connect.assert_called_once()
        self.assertEqual(conn, new_conn)


if __name__ == "__main__":
    unittest.main()
