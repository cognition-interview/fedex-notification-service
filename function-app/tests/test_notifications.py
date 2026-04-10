"""Tests for mark_notification_read and mark_all_notifications_read."""

import json
import unittest
from unittest.mock import MagicMock, patch

import azure.functions as func

from function_app import mark_all_notifications_read, mark_notification_read


class TestMarkNotificationRead(unittest.TestCase):
    """Tests for PATCH /api/notifications/{notification_id}/read."""

    def _make_request(self, notification_id: str) -> func.HttpRequest:
        return func.HttpRequest(
            method="PATCH",
            url=f"/api/notifications/{notification_id}/read",
            route_params={"notification_id": notification_id},
            body=b"",
        )

    @patch("function_app.get_connection")
    def test_marks_notification_as_read(self, mock_get_conn):
        updated = {
            "id": "notif-001",
            "order_id": "ord-001",
            "business_id": "biz-001",
            "type": "Status Update",
            "message": "Package in transit",
            "is_read": True,
            "created_at": "2026-04-05T14:00:00Z",
        }
        cur = MagicMock()
        cur.fetchone.return_value = updated
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request("notif-001")
        resp = mark_notification_read(req)

        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertTrue(data["is_read"])
        self.assertEqual("notif-001", data["id"])

    @patch("function_app.get_connection")
    def test_notification_not_found_returns_404(self, mock_get_conn):
        cur = MagicMock()
        cur.fetchone.return_value = None
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request("ghost")
        resp = mark_notification_read(req)

        self.assertEqual(404, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual("Notification not found", data["error"])

    @patch("function_app.get_connection")
    def test_executes_correct_sql(self, mock_get_conn):
        cur = MagicMock()
        cur.fetchone.return_value = {"id": "notif-002", "is_read": True}
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request("notif-002")
        mark_notification_read(req)

        cur.execute.assert_called_once()
        sql = cur.execute.call_args[0][0]
        self.assertIn("UPDATE notifications", sql)
        self.assertIn("RETURNING", sql)


class TestMarkAllNotificationsRead(unittest.TestCase):
    """Tests for PATCH /api/notifications/read-all."""

    def _make_request(self, body: dict | None = None) -> func.HttpRequest:
        return func.HttpRequest(
            method="PATCH",
            url="/api/notifications/read-all",
            route_params={},
            body=json.dumps(body or {}).encode("utf-8"),
        )

    @patch("function_app.get_connection")
    def test_marks_all_notifications_read_without_business_id(self, mock_get_conn):
        cur = MagicMock()
        cur.rowcount = 42
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request({})
        resp = mark_all_notifications_read(req)

        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual(42, data["updated"])

    @patch("function_app.get_connection")
    def test_marks_business_scoped_notifications(self, mock_get_conn):
        cur = MagicMock()
        cur.rowcount = 5
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request({"businessId": "biz-001"})
        resp = mark_all_notifications_read(req)

        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual(5, data["updated"])

        # Verify the SQL includes business_id filter
        sql = cur.execute.call_args[0][0]
        self.assertIn("business_id", sql)

    @patch("function_app.get_connection")
    def test_all_without_business_id_uses_global_update(self, mock_get_conn):
        cur = MagicMock()
        cur.rowcount = 100
        mock_get_conn.return_value.cursor.return_value = cur

        req = self._make_request({})
        mark_all_notifications_read(req)

        sql = cur.execute.call_args[0][0]
        self.assertIn("is_read = false", sql)
        # Should NOT include business_id parameter binding
        args = cur.execute.call_args[0]
        self.assertEqual(1, len(args))  # Only SQL, no params tuple

    @patch("function_app.get_connection")
    def test_empty_body_treated_as_global(self, mock_get_conn):
        cur = MagicMock()
        cur.rowcount = 0
        mock_get_conn.return_value.cursor.return_value = cur

        req = func.HttpRequest(
            method="PATCH",
            url="/api/notifications/read-all",
            route_params={},
            body=b"",
        )
        resp = mark_all_notifications_read(req)
        self.assertEqual(200, resp.status_code)
        data = json.loads(resp.get_body())
        self.assertEqual(0, data["updated"])


if __name__ == "__main__":
    unittest.main()
