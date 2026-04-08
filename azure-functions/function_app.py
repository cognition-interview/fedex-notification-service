"""Azure Function – Update Order Status

Replaces the PHP ``PATCH /api/orders/{id}/status`` endpoint.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import azure.functions as func
import psycopg2
import psycopg2.extras
from azure.communication.email import EmailClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Constants matching PHP backend
VALID_STATUSES = [
    "Picked Up",
    "In Transit",
    "Out for Delivery",
    "Delivered",
    "Delayed",
    "Exception",
]

STATUS_TO_EVENT: dict[str, str] = {
    "Picked Up": "Package Picked Up",
    "In Transit": "In Transit",
    "Out for Delivery": "Out for Delivery",
    "Delivered": "Delivered",
    "Delayed": "Delay Reported",
    "Exception": "Exception",
}

STATUS_TO_NOTIFICATION: dict[str, str] = {
    "Delivered": "Delivery Confirmed",
    "Out for Delivery": "Out for Delivery",
    "Delayed": "Delay Alert",
    "Exception": "Exception Alert",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_serialiser(obj: object) -> str:
    """Handle Decimal, datetime and date for json.dumps."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _get_db_connection():
    conn_str = os.environ["POSTGRES_CONNECTION_STRING"]
    return psycopg2.connect(conn_str, sslmode="require")


def _send_email(tracking_number: str, new_status: str, description: str,
                contact_email: str, origin: str, destination: str) -> None:
    """Send a branded status-update email via Azure Communication Services."""
    try:
        conn_string = os.environ.get("AZURE_EMAIL_CONNECTION_STRING", "")
        from_address = os.environ.get("AZURE_EMAIL_FROM_ADDRESS", "")
        if not conn_string or not from_address:
            logging.warning("Email config missing – skipping email send")
            return

        client = EmailClient.from_connection_string(conn_string)
        subject = f"FedEx Update: Tracking #{tracking_number} — {new_status}"
        plain = (
            f"Tracking #{tracking_number}\n"
            f"Route: {origin} → {destination}\n"
            f"New Status: {new_status}\n"
            f"Details: {description or 'N/A'}\n"
            f"Updated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}\n"
        )
        html = (
            '<div style="font-family:Arial,sans-serif;max-width:600px">'
            '<div style="background:#4D148C;padding:16px 24px">'
            '<span style="color:#fff;font-size:20px;font-weight:bold">FedEx</span></div>'
            '<div style="padding:24px">'
            f'<h2 style="color:#4D148C">Shipment Update</h2>'
            '<table style="width:100%;border-collapse:collapse">'
            f'<tr><td style="padding:8px;border-bottom:1px solid #eee"><strong>Tracking #</strong></td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{tracking_number}</td></tr>'
            f'<tr><td style="padding:8px;border-bottom:1px solid #eee"><strong>Route</strong></td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{origin} → {destination}</td></tr>'
            f'<tr><td style="padding:8px;border-bottom:1px solid #eee"><strong>Status</strong></td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">'
            f'<span style="background:#FF6200;color:#fff;padding:4px 12px;border-radius:4px">'
            f'{new_status}</span></td></tr>'
            f'<tr><td style="padding:8px;border-bottom:1px solid #eee"><strong>Details</strong></td>'
            f'<td style="padding:8px;border-bottom:1px solid #eee">{description or "N/A"}</td></tr>'
            '</table></div></div>'
        )

        message = {
            "senderAddress": from_address,
            "recipients": {"to": [{"address": contact_email}]},
            "content": {
                "subject": subject,
                "plainText": plain,
                "html": html,
            },
        }
        poller = client.begin_send(message)
        poller.result()
        logging.info("Email sent to %s for %s", contact_email, tracking_number)
    except Exception:
        logging.exception("Email send failed (non-blocking)")


# ---------------------------------------------------------------------------
# HTTP Trigger
# ---------------------------------------------------------------------------

@app.route(route="orders/{order_id}/status", methods=["PATCH"])
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    order_id = req.route_params.get("order_id", "")

    # ── Parse body ──────────────────────────────────────────────────────
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
        )

    new_status = body.get("status", "")
    location = body.get("location", "")
    description = body.get("description", "")

    if new_status not in VALID_STATUSES:
        return func.HttpResponse(
            json.dumps({
                "error": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}"
            }),
            status_code=400,
            mimetype="application/json",
        )

    # ── Database work (single connection) ───────────────────────────────
    conn = None
    try:
        conn = _get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Fetch order
        cur.execute(
            "SELECT o.*, b.name AS business_name, b.contact_email, "
            "b.account_number AS business_account_number "
            "FROM orders o JOIN businesses b ON o.business_id = b.id "
            "WHERE o.id = %s",
            (order_id,),
        )
        order = cur.fetchone()
        if not order:
            return func.HttpResponse(
                json.dumps({"error": "Order not found"}),
                status_code=404,
                mimetype="application/json",
            )

        # 2. Update order status
        if new_status == "Delivered":
            cur.execute(
                "UPDATE orders SET status = %s, actual_delivery = NOW() "
                "WHERE id = %s",
                (new_status, order_id),
            )
        else:
            cur.execute(
                "UPDATE orders SET status = %s WHERE id = %s",
                (new_status, order_id),
            )

        # 3. Insert shipment event
        event_type = STATUS_TO_EVENT.get(new_status, "In Transit")
        cur.execute(
            "INSERT INTO shipment_events (order_id, event_type, location, description) "
            "VALUES (%s, %s, %s, %s)",
            (order_id, event_type, location, description),
        )

        # 4. Insert notification
        notification_type = STATUS_TO_NOTIFICATION.get(new_status, "Status Update")
        message_text = (
            f"Tracking #{order['tracking_number']}: "
            f"status changed to {new_status}."
        )
        cur.execute(
            "INSERT INTO notifications (order_id, business_id, type, message) "
            "VALUES (%s, %s, %s, %s)",
            (order_id, order["business_id"], notification_type, message_text),
        )

        conn.commit()

        # 5. Re-fetch order with events
        cur.execute(
            "SELECT o.*, b.name AS business_name, b.contact_email "
            "FROM orders o JOIN businesses b ON o.business_id = b.id "
            "WHERE o.id = %s",
            (order_id,),
        )
        refreshed = dict(cur.fetchone())

        cur.execute(
            "SELECT * FROM shipment_events WHERE order_id = %s "
            "ORDER BY occurred_at DESC",
            (order_id,),
        )
        refreshed["shipment_events"] = [dict(e) for e in cur.fetchall()]

        cur.close()

        # 6. Send email (non-blocking — failures are logged only)
        contact_email = order.get("contact_email", "")
        if contact_email:
            _send_email(
                order["tracking_number"],
                new_status,
                description,
                contact_email,
                order["origin"],
                order["destination"],
            )

        return func.HttpResponse(
            json.dumps(refreshed, default=_json_serialiser),
            status_code=200,
            mimetype="application/json",
        )

    except Exception:
        logging.exception("Error updating order status")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )
    finally:
        if conn:
            conn.close()
