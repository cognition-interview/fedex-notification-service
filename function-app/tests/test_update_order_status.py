"""Tests for update_order_status Azure Function."""

import json
import unittest
from unittest.mock import MagicMock, patch

import azure.functions as func

from function_app import update_order_status


class TestUpdateOrderStatus(unittest.TestCase):
    """Tests for PATCH /api/orders/{order_id}/status."""

    def _make_request(self, order_id: str, body: dict | None = None) -> func.HttpRequest:
        return func.HttpRequest(
            method="PATCH",
            url=f"/api/orders/{order_id}/status",
            route_params={"order_id": order_id},
            body=json.dumps(body or {}).encode("utf-8"),
        )

    # ── Validation tests ─────────────────────────────────────────────────────

    def test_invalid_json_body_returns_400(self):
        req = func.HttpRequest(
            method="PATCH",
            url="/api/orders/ord-001/status",
            route_params={"order_id": "ord-001"},
            body=b"not-json",
        )
        resp = update_order_status(req)
        self.assertEqual(400, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertIn("error", data)

    def test_invalid_status_returns_422(self):
        req = self._make_request("ord-001", {"status": "Flying"})
        resp = update_order_status(req)
        self.assertEqual(422, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual("Invalid status", data["error"])
        self.assertIn("In Transit", data["allowed"])

    def test_empty_status_returns_422(self):
        req = self._make_request("ord-001", {"status": ""})
        resp = update_order_status(req)
        self.assertEqual(422, resp.status_code)

    # ── Order not found ──────────────────────────────────────────────────────

    @patch("function_app.get_connection")
    def test_order_not_found_returns_404(self, mock_get_conn):
        cur = MagicMock()
        cur.fetchone.return_value = None
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request("nonexistent", {"status": "In Transit"})
        resp = update_order_status(req)
        self.assertEqual(404, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual("Order not found", data["error"])

    # ── Successful status update ─────────────────────────────────────────────

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_successful_update_returns_refreshed_order(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-001",
            "tracking_number": "TRK-7489001",
            "origin": "Memphis, TN",
            "destination": "New York, NY",
            "status": "Picked Up",
            "business_id": "biz-001",
            "business_name": "Acme Corp",
            "contact_email": "ops@acme.com",
        }
        refreshed_order = {**order, "status": "In Transit"}
        events = [
            {
                "id": "evt-001",
                "event_type": "In Transit",
                "location": "Nashville, TN",
                "description": "Package departed hub",
            }
        ]

        cur = MagicMock()
        # 1st fetchone: fetch order, 2nd fetchone: refreshed order
        cur.fetchone.side_effect = [order, refreshed_order]
        cur.fetchall.return_value = events
        mock_get_conn.return_value.cursor.return_value = cur

        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request(
            "ord-001",
            {
                "status": "In Transit",
                "location": "Nashville, TN",
                "description": "Package departed hub",
            },
        )
        resp = update_order_status(req)
        self.assertEqual(200, resp.status_code)

        data = json.loads(resp.get_body())
        self.assertEqual("In Transit", data["status"])
        self.assertIn("shipment_events", data)
        self.assertEqual(1, len(data["shipment_events"]))

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_update_calls_correct_sql_sequence(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-002",
            "tracking_number": "TRK-002",
            "origin": "A",
            "destination": "B",
            "status": "In Transit",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Delivered"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-002", {"status": "Delivered", "location": "B"})
        resp = update_order_status(req)

        self.assertEqual(200, resp.status_code)
        # Verify 5 execute calls: fetch order, update, insert event, insert notif, fetch refreshed, fetch events
        self.assertEqual(6, cur.execute.call_count)

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_status_delivered_maps_to_delivery_confirmed_notification(
        self, mock_get_conn, mock_email_cls
    ):
        order = {
            "id": "ord-003",
            "tracking_number": "TRK-003",
            "origin": "A",
            "destination": "B",
            "status": "Out for Delivery",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Delivered"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-003", {"status": "Delivered", "location": "B"})
        update_order_status(req)

        # Check the notification insert call (4th execute call, index 3)
        notif_call = cur.execute.call_args_list[3]
        notif_args = notif_call[0][1]
        self.assertEqual("Delivery Confirmed", notif_args[2])

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_status_delayed_maps_to_delay_alert(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-004",
            "tracking_number": "TRK-004",
            "origin": "A",
            "destination": "B",
            "status": "In Transit",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Delayed"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-004", {"status": "Delayed", "location": "X"})
        update_order_status(req)

        notif_call = cur.execute.call_args_list[3]
        notif_args = notif_call[0][1]
        self.assertEqual("Delay Alert", notif_args[2])

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_status_exception_maps_to_exception_alert(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-005",
            "tracking_number": "TRK-005",
            "origin": "A",
            "destination": "B",
            "status": "In Transit",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Exception"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-005", {"status": "Exception", "location": "X"})
        update_order_status(req)

        notif_call = cur.execute.call_args_list[3]
        notif_args = notif_call[0][1]
        self.assertEqual("Exception Alert", notif_args[2])

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_status_out_for_delivery_maps_correctly(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-006",
            "tracking_number": "TRK-006",
            "origin": "A",
            "destination": "B",
            "status": "In Transit",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Out for Delivery"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-006", {"status": "Out for Delivery", "location": "B"})
        update_order_status(req)

        notif_call = cur.execute.call_args_list[3]
        notif_args = notif_call[0][1]
        self.assertEqual("Out for Delivery", notif_args[2])

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_picked_up_maps_to_status_update_notification(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-007",
            "tracking_number": "TRK-007",
            "origin": "A",
            "destination": "B",
            "status": "Exception",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Picked Up"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-007", {"status": "Picked Up", "location": "A"})
        update_order_status(req)

        notif_call = cur.execute.call_args_list[3]
        notif_args = notif_call[0][1]
        self.assertEqual("Status Update", notif_args[2])

    # ── Default description ──────────────────────────────────────────────────

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_default_description_when_not_provided(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-008",
            "tracking_number": "TRK-008",
            "origin": "A",
            "destination": "B",
            "status": "Picked Up",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "In Transit"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-008", {"status": "In Transit"})
        update_order_status(req)

        # Check the event insert call (3rd execute, index 2) for default description
        event_call = cur.execute.call_args_list[2]
        event_args = event_call[0][1]
        self.assertEqual("Status updated to In Transit", event_args[3])

    # ── Email failure does not fail the request ──────────────────────────────

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_email_failure_does_not_fail_request(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-009",
            "tracking_number": "TRK-009",
            "origin": "A",
            "destination": "B",
            "status": "Picked Up",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "In Transit"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.side_effect = Exception("SMTP fail")

        req = self._make_request("ord-009", {"status": "In Transit"})
        resp = update_order_status(req)

        # Request should succeed even though email failed
        self.assertEqual(200, resp.status_code)

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_email_returns_false_does_not_fail_request(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-010",
            "tracking_number": "TRK-010",
            "origin": "A",
            "destination": "B",
            "status": "Picked Up",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "In Transit"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = False

        req = self._make_request("ord-010", {"status": "In Transit"})
        resp = update_order_status(req)
        self.assertEqual(200, resp.status_code)

    # ── Event type mapping ───────────────────────────────────────────────────

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_event_type_mapping_for_delivered(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-011",
            "tracking_number": "TRK-011",
            "origin": "A",
            "destination": "B",
            "status": "Out for Delivery",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Delivered"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-011", {"status": "Delivered", "location": "B"})
        update_order_status(req)

        # Check event insert (3rd execute, index 2) for event_type
        event_call = cur.execute.call_args_list[2]
        event_args = event_call[0][1]
        self.assertEqual("Delivered", event_args[1])

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_event_type_mapping_for_delay_reported(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-012",
            "tracking_number": "TRK-012",
            "origin": "A",
            "destination": "B",
            "status": "In Transit",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "Delayed"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-012", {"status": "Delayed", "location": "X"})
        update_order_status(req)

        event_call = cur.execute.call_args_list[2]
        event_args = event_call[0][1]
        self.assertEqual("Delay Reported", event_args[1])

    # ── Default location ─────────────────────────────────────────────────────

    @patch("function_app.EmailService")
    @patch("function_app.get_connection")
    def test_default_location_is_unknown(self, mock_get_conn, mock_email_cls):
        order = {
            "id": "ord-013",
            "tracking_number": "TRK-013",
            "origin": "A",
            "destination": "B",
            "status": "Picked Up",
            "business_id": "biz-001",
            "business_name": "Acme",
            "contact_email": "a@b.com",
        }
        cur = MagicMock()
        cur.fetchone.side_effect = [order, {**order, "status": "In Transit"}]
        cur.fetchall.return_value = []
        mock_get_conn.return_value.cursor.return_value = cur
        mock_email_cls.return_value.send_status_update_email.return_value = True

        req = self._make_request("ord-013", {"status": "In Transit"})
        update_order_status(req)

        event_call = cur.execute.call_args_list[2]
        event_args = event_call[0][1]
        self.assertEqual("Unknown", event_args[2])


if __name__ == "__main__":
    unittest.main()
