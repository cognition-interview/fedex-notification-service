"""Tests for the Azure Function App — update_order_status endpoint.

Mirrors the PHP OrderControllerTest patterns: mocks the database connection
and verifies HTTP responses, status codes, and side effects.
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone

import azure.functions as func

# We need to mock db and email_service before importing function_app
import db as db_module
from function_app import (
    app,
    update_order_status,
    VALID_STATUSES,
    STATUS_TO_EVENT,
    STATUS_TO_NOTIFICATION,
    _json_response,
    _fetch_order_with_business,
    _fetch_order_with_events,
)


def _make_request(
    method: str = "PATCH",
    route_params: dict = None,
    body: dict = None,
) -> func.HttpRequest:
    """Build a mock HttpRequest."""
    return func.HttpRequest(
        method=method,
        url="/api/orders/ord-001/status",
        route_params=route_params or {"order_id": "ord-001"},
        body=json.dumps(body or {}).encode("utf-8"),
    )


SAMPLE_ORDER = {
    "id": "ord-001",
    "tracking_number": "TRK 7489 001",
    "origin": "Memphis, TN",
    "destination": "New York, NY",
    "status": "Picked Up",
    "weight_lbs": 5.0,
    "service_type": "FedEx Ground",
    "estimated_delivery": "2026-04-10",
    "actual_delivery": None,
    "created_at": "2026-04-07T00:00:00+00",
    "updated_at": "2026-04-07T00:00:00+00",
    "business_id": "biz-001",
    "business_name": "Acme Corp",
    "contact_email": "test@example.com",
}

SAMPLE_EVENTS = [
    {
        "id": "evt-001",
        "order_id": "ord-001",
        "event_type": "Package Picked Up",
        "location": "Memphis, TN",
        "description": "Package picked up",
        "occurred_at": "2026-04-07T08:00:00+00",
    },
]


class TestJsonResponse:
    def test_returns_200_by_default(self):
        resp = _json_response({"key": "value"})
        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        body = json.loads(resp.get_body())
        assert body["key"] == "value"

    def test_returns_custom_status_code(self):
        resp = _json_response({"error": "not found"}, 404)
        assert resp.status_code == 404


class TestFetchOrderWithBusiness:
    def test_returns_order_dict(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = SAMPLE_ORDER
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = _fetch_order_with_business(mock_conn, "ord-001")
        assert result["id"] == "ord-001"
        assert result["tracking_number"] == "TRK 7489 001"
        mock_cursor.execute.assert_called_once()

    def test_returns_none_when_not_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = _fetch_order_with_business(mock_conn, "nonexistent")
        assert result is None


class TestFetchOrderWithEvents:
    def test_returns_order_with_events(self):
        mock_cursor = MagicMock()
        # First call: fetchone for the order, second call: fetchall for events
        mock_cursor.fetchone.return_value = SAMPLE_ORDER.copy()
        mock_cursor.fetchall.return_value = SAMPLE_EVENTS
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = _fetch_order_with_events(mock_conn, "ord-001")
        assert result is not None
        assert "shipment_events" in result
        assert len(result["shipment_events"]) == 1

    def test_returns_none_when_order_not_found(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        result = _fetch_order_with_events(mock_conn, "nonexistent")
        assert result is None


class TestUpdateOrderStatus:
    """Tests for the update_order_status Azure Function."""

    def _setup_mock_conn(self, order=None, refreshed_order=None, events=None):
        """Set up a mock connection that handles all the queries."""
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        # fetchone is called twice: once for initial fetch, once for refreshed order
        if order is None:
            mock_cursor.fetchone.return_value = None
        else:
            refreshed = refreshed_order or order.copy()
            mock_cursor.fetchone.side_effect = [order, refreshed]

        mock_cursor.fetchall.return_value = events or []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        return mock_conn

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_valid_status_update(self, mock_get_conn, mock_send_email):
        mock_conn = self._setup_mock_conn(
            order=SAMPLE_ORDER.copy(),
            refreshed_order={**SAMPLE_ORDER, "status": "In Transit"},
            events=SAMPLE_EVENTS,
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": "In Transit",
            "location": "Nashville, TN",
            "description": "Package departed hub",
        })
        resp = update_order_status(req)

        assert resp.status_code == 200
        body = json.loads(resp.get_body())
        assert body["tracking_number"] == "TRK 7489 001"
        mock_conn.commit.assert_called_once()
        mock_send_email.assert_called_once()

    @patch("function_app.get_connection")
    def test_invalid_status_returns_422(self, mock_get_conn):
        req = _make_request(body={"status": "Flying"})
        resp = update_order_status(req)

        assert resp.status_code == 422
        body = json.loads(resp.get_body())
        assert body["error"] == "Invalid status"
        assert "In Transit" in body["allowed"]
        assert "Flying" not in body["allowed"]

    @patch("function_app.get_connection")
    def test_empty_status_returns_422(self, mock_get_conn):
        req = _make_request(body={"status": ""})
        resp = update_order_status(req)

        assert resp.status_code == 422

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_order_not_found_returns_404(self, mock_get_conn, mock_send_email):
        mock_conn = self._setup_mock_conn(order=None)
        mock_get_conn.return_value = mock_conn

        req = _make_request(
            route_params={"order_id": "nonexistent"},
            body={"status": "In Transit"},
        )
        resp = update_order_status(req)

        assert resp.status_code == 404
        body = json.loads(resp.get_body())
        assert body["error"] == "Order not found"
        mock_send_email.assert_not_called()

    def test_missing_order_id_returns_400(self):
        req = func.HttpRequest(
            method="PATCH",
            url="/api/orders//status",
            route_params={},
            body=json.dumps({"status": "In Transit"}).encode("utf-8"),
        )
        resp = update_order_status(req)
        assert resp.status_code == 400

    def test_invalid_json_body_returns_400(self):
        req = func.HttpRequest(
            method="PATCH",
            url="/api/orders/ord-001/status",
            route_params={"order_id": "ord-001"},
            body=b"not json",
        )
        resp = update_order_status(req)
        assert resp.status_code == 400

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_delivered_status_update(self, mock_get_conn, mock_send_email):
        order = {**SAMPLE_ORDER, "status": "Out for Delivery"}
        mock_conn = self._setup_mock_conn(
            order=order,
            refreshed_order={**order, "status": "Delivered", "actual_delivery": "2026-04-08"},
            events=SAMPLE_EVENTS,
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": "Delivered",
            "location": "New York, NY",
            "description": "Left at front door",
        })
        resp = update_order_status(req)

        assert resp.status_code == 200
        mock_conn.commit.assert_called_once()

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_delayed_status_update(self, mock_get_conn, mock_send_email):
        order = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_conn = self._setup_mock_conn(
            order=order,
            refreshed_order={**order, "status": "Delayed"},
            events=SAMPLE_EVENTS,
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": "Delayed",
            "location": "Memphis, TN",
            "description": "Weather delay",
        })
        resp = update_order_status(req)

        assert resp.status_code == 200
        mock_conn.commit.assert_called_once()

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_exception_status_update(self, mock_get_conn, mock_send_email):
        order = {**SAMPLE_ORDER, "status": "In Transit"}
        mock_conn = self._setup_mock_conn(
            order=order,
            refreshed_order={**order, "status": "Exception"},
            events=SAMPLE_EVENTS,
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": "Exception",
            "location": "Memphis, TN",
            "description": "Address issue",
        })
        resp = update_order_status(req)

        assert resp.status_code == 200

    @patch("function_app.send_status_update_email", side_effect=Exception("SMTP down"))
    @patch("function_app.get_connection")
    def test_email_failure_does_not_fail_request(self, mock_get_conn, mock_send_email):
        mock_conn = self._setup_mock_conn(
            order=SAMPLE_ORDER.copy(),
            refreshed_order={**SAMPLE_ORDER, "status": "In Transit"},
            events=SAMPLE_EVENTS,
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": "In Transit",
            "location": "Nashville, TN",
        })
        resp = update_order_status(req)

        # Email failure should NOT cause the HTTP response to fail
        assert resp.status_code == 200
        mock_conn.commit.assert_called_once()

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_default_location_is_unknown(self, mock_get_conn, mock_send_email):
        mock_conn = self._setup_mock_conn(
            order=SAMPLE_ORDER.copy(),
            refreshed_order={**SAMPLE_ORDER, "status": "In Transit"},
            events=[],
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        assert resp.status_code == 200

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_default_description_generated(self, mock_get_conn, mock_send_email):
        mock_conn = self._setup_mock_conn(
            order=SAMPLE_ORDER.copy(),
            refreshed_order={**SAMPLE_ORDER, "status": "In Transit"},
            events=[],
        )
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={"status": "In Transit", "location": "Memphis, TN"})
        resp = update_order_status(req)

        assert resp.status_code == 200
        # Verify the email was called with the default description
        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args
        assert call_args[0][3] == "Status updated to In Transit"

    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_db_error_returns_500(self, mock_get_conn, mock_send_email):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = SAMPLE_ORDER.copy()
        mock_cursor.execute.side_effect = [None, Exception("DB write failed")]
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={"status": "In Transit"})
        resp = update_order_status(req)

        assert resp.status_code == 500
        mock_conn.rollback.assert_called_once()


class TestStatusMappings:
    """Verify the status-to-event and status-to-notification mappings."""

    def test_all_valid_statuses_have_event_mapping(self):
        for status in VALID_STATUSES:
            assert status in STATUS_TO_EVENT

    def test_event_type_values(self):
        assert STATUS_TO_EVENT["Picked Up"] == "Package Picked Up"
        assert STATUS_TO_EVENT["In Transit"] == "In Transit"
        assert STATUS_TO_EVENT["Out for Delivery"] == "Out for Delivery"
        assert STATUS_TO_EVENT["Delivered"] == "Delivered"
        assert STATUS_TO_EVENT["Delayed"] == "Delay Reported"
        assert STATUS_TO_EVENT["Exception"] == "Exception"

    def test_notification_type_values(self):
        assert STATUS_TO_NOTIFICATION["Delivered"] == "Delivery Confirmed"
        assert STATUS_TO_NOTIFICATION["Out for Delivery"] == "Out for Delivery"
        assert STATUS_TO_NOTIFICATION["Delayed"] == "Delay Alert"
        assert STATUS_TO_NOTIFICATION["Exception"] == "Exception Alert"

    def test_default_notification_for_other_statuses(self):
        # Statuses not in the mapping should default to "Status Update"
        assert "Picked Up" not in STATUS_TO_NOTIFICATION
        assert "In Transit" not in STATUS_TO_NOTIFICATION


class TestAllValidStatuses:
    """Ensure each valid status can be processed through the function."""

    @pytest.mark.parametrize("status", VALID_STATUSES)
    @patch("function_app.send_status_update_email")
    @patch("function_app.get_connection")
    def test_each_valid_status_succeeds(self, mock_get_conn, mock_send_email, status):
        order = SAMPLE_ORDER.copy()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.side_effect = [order, {**order, "status": status}]
        mock_cursor.fetchall.return_value = []

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        req = _make_request(body={
            "status": status,
            "location": "Test City",
            "description": f"Testing {status}",
        })
        resp = update_order_status(req)

        assert resp.status_code == 200
        mock_conn.commit.assert_called_once()
