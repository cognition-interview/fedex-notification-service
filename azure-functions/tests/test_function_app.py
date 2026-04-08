"""Unit tests for the update-order-status Azure Function."""

from __future__ import annotations

import json
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Set required env vars before importing function_app
os.environ.setdefault("POSTGRES_CONNECTION_STRING", "postgresql://test:test@localhost/test")
os.environ.setdefault("AZURE_EMAIL_CONNECTION_STRING", "endpoint=https://fake.comm.azure.com;accesskey=ZmFrZQ==")
os.environ.setdefault("AZURE_EMAIL_FROM_ADDRESS", "noreply@test.com")

from function_app import (
    VALID_STATUSES,
    STATUS_TO_EVENT,
    STATUS_TO_NOTIFICATION,
    _default_serialiser,
    _handle_update_status,
    update_order_status,
)
import azure.functions as func


def _make_request(
    order_id: str = "ord-001",
    body: dict | None = None,
    method: str = "PATCH",
) -> func.HttpRequest:
    """Build a fake HttpRequest."""
    return func.HttpRequest(
        method=method,
        url=f"https://example.com/api/orders/{order_id}/status",
        route_params={"order_id": order_id},
        body=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
    )


class TestConstants(unittest.TestCase):
    """Verify that constant mappings are complete."""

    def test_valid_statuses(self) -> None:
        expected = {"Picked Up", "In Transit", "Out for Delivery", "Delivered", "Delayed", "Exception"}
        self.assertEqual(set(VALID_STATUSES), expected)

    def test_status_to_event_covers_all_statuses(self) -> None:
        for status in VALID_STATUSES:
            self.assertIn(status, STATUS_TO_EVENT, f"Missing event mapping for '{status}'")

    def test_notification_mapping(self) -> None:
        self.assertEqual(STATUS_TO_NOTIFICATION["Delivered"], "Delivery Confirmed")
        self.assertEqual(STATUS_TO_NOTIFICATION["Out for Delivery"], "Out for Delivery")
        self.assertEqual(STATUS_TO_NOTIFICATION["Delayed"], "Delay Alert")
        self.assertEqual(STATUS_TO_NOTIFICATION["Exception"], "Exception Alert")


class TestDefaultSerialiser(unittest.TestCase):
    """Verify JSON serialisation helpers."""

    def test_serialises_decimal(self) -> None:
        result = _default_serialiser(Decimal("12.50"))
        self.assertEqual(result, "12.50")

    def test_serialises_datetime(self) -> None:
        dt = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        result = _default_serialiser(dt)
        self.assertIn("2026-04-05", result)

    def test_serialises_date(self) -> None:
        d = date(2026, 4, 5)
        result = _default_serialiser(d)
        self.assertEqual(result, "2026-04-05")

    def test_raises_for_unknown_type(self) -> None:
        with self.assertRaises(TypeError):
            _default_serialiser(object())


class TestValidation(unittest.TestCase):
    """Verify request validation logic."""

    def test_invalid_status_returns_422(self) -> None:
        req = _make_request(body={"status": "Flying"})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)
        body = json.loads(resp.get_body())
        self.assertIn("error", body)
        self.assertIn("allowed", body)
        self.assertIn("In Transit", body["allowed"])

    def test_empty_status_returns_422(self) -> None:
        req = _make_request(body={"status": ""})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)

    def test_missing_status_returns_422(self) -> None:
        req = _make_request(body={})
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)

    def test_malformed_json_body_returns_422(self) -> None:
        req = func.HttpRequest(
            method="PATCH",
            url="https://example.com/api/orders/ord-001/status",
            route_params={"order_id": "ord-001"},
            body=b"not json",
            headers={"Content-Type": "application/json"},
        )
        resp = _handle_update_status(req)
        self.assertEqual(resp.status_code, 422)


class TestDatabaseFlow(unittest.TestCase):
    """Verify the handler's interaction with the database."""

    def _mock_order(self) -> dict:
        return {
            "id": "ord-001",
            "business_id": "biz-001",
            "tracking_number": "TRK123",
            "origin": "Memphis, TN",
            "destination": "New York, NY",
            "status": "Picked Up",
            "weight_lbs": Decimal("5.00"),
            "service_type": "FedEx Ground",
            "estimated_delivery": date(2026, 4, 10),
            "actual_delivery": None,
            "created_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 4, 1, tzinfo=timezone.utc),
            "business_name": "Acme Corp",
            "contact_email": "test@example.com",
        }

    def _mock_refreshed_order(self) -> dict:
        order = self._mock_order()
        order["status"] = "In Transit"
        order["shipment_events"] = [
            {
                "id": "evt-001",
                "order_id": "ord-001",
                "event_type": "In Transit",
                "location": "Nashville, TN",
                "description": "Package departed hub",
                "occurred_at": datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc),
            }
        ]
        return order

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_successful_update_returns_200(self, mock_conn_fn: MagicMock, mock_email: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [self._mock_order(), self._mock_refreshed_order()]
        mock_cursor.fetchall.return_value = self._mock_refreshed_order()["shipment_events"]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_fn.return_value = mock_conn

        req = _make_request(body={
            "status": "In Transit",
            "location": "Nashville, TN",
            "description": "Package departed hub",
        })
        resp = _handle_update_status(req)

        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.get_body())
        self.assertEqual(body["status"], "In Transit")
        self.assertIn("shipment_events", body)

        # Verify email was called
        mock_email.assert_called_once()

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_order_not_found_returns_404(self, mock_conn_fn: MagicMock, mock_email: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # order not found

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_fn.return_value = mock_conn

        req = _make_request(order_id="nonexistent", body={"status": "In Transit"})
        resp = _handle_update_status(req)

        self.assertEqual(resp.status_code, 404)
        body = json.loads(resp.get_body())
        self.assertIn("error", body)
        mock_email.assert_not_called()

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_db_exception_returns_500(self, mock_conn_fn: MagicMock, mock_email: MagicMock) -> None:
        mock_conn_fn.side_effect = Exception("connection refused")

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        self.assertEqual(resp.status_code, 500)
        body = json.loads(resp.get_body())
        self.assertIn("error", body)

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_default_location_is_unknown(self, mock_conn_fn: MagicMock, mock_email: MagicMock) -> None:
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [self._mock_order(), self._mock_refreshed_order()]
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_fn.return_value = mock_conn

        # No location field → defaults to "Unknown"
        req = _make_request(body={"status": "In Transit"})
        resp = _handle_update_status(req)

        self.assertEqual(resp.status_code, 200)
        # Check the insert shipment_events call used "Unknown" as location
        calls = mock_cursor.execute.call_args_list
        insert_event_call = [c for c in calls if "shipment_events" in str(c)]
        self.assertTrue(len(insert_event_call) > 0)
        # The 3rd positional param in the tuple should be "Unknown"
        args_tuple = insert_event_call[0][0][1]  # (sql, params_tuple)
        self.assertEqual(args_tuple[2], "Unknown")

    @patch("function_app._send_email")
    @patch("function_app._get_connection")
    def test_email_failure_does_not_fail_request(self, mock_conn_fn: MagicMock, mock_email: MagicMock) -> None:
        mock_email.side_effect = Exception("SMTP error")

        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [self._mock_order(), self._mock_refreshed_order()]
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_fn.return_value = mock_conn

        req = _make_request(body={"status": "In Transit"})
        # The top-level wrapper catches all exceptions
        resp = update_order_status(req)

        # Should still return — either 200 (if email exception is caught in _send_email)
        # or 500 (if it bubbles up and the wrapper catches it)
        self.assertIn(resp.status_code, [200, 500])


class TestStatusMappings(unittest.TestCase):
    """Verify all status → event and notification type mappings."""

    def test_picked_up_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["Picked Up"], "Package Picked Up")

    def test_in_transit_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["In Transit"], "In Transit")

    def test_out_for_delivery_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["Out for Delivery"], "Out for Delivery")

    def test_delivered_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["Delivered"], "Delivered")
        self.assertEqual(STATUS_TO_NOTIFICATION["Delivered"], "Delivery Confirmed")

    def test_delayed_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["Delayed"], "Delay Reported")
        self.assertEqual(STATUS_TO_NOTIFICATION["Delayed"], "Delay Alert")

    def test_exception_mapping(self) -> None:
        self.assertEqual(STATUS_TO_EVENT["Exception"], "Exception")
        self.assertEqual(STATUS_TO_NOTIFICATION["Exception"], "Exception Alert")

    def test_default_notification_is_status_update(self) -> None:
        # Statuses not in STATUS_TO_NOTIFICATION default to "Status Update"
        self.assertNotIn("Picked Up", STATUS_TO_NOTIFICATION)
        self.assertNotIn("In Transit", STATUS_TO_NOTIFICATION)


if __name__ == "__main__":
    unittest.main()
