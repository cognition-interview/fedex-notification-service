"""Azure Function – Update Order Status

Replaces the PHP ``PATCH /api/orders/{id}/status`` endpoint.

Responsibilities (identical to the original PHP implementation):
1. Validate the incoming status value.
2. Update ``orders.status`` (set ``actual_delivery`` when Delivered).
3. Insert a ``shipment_events`` row with the mapped event type.
4. Insert a ``notifications`` row with the mapped notification type.
5. Send a branded email via Azure Communication Services.
6. Return the refreshed order (same shape as ``GET /api/orders/{id}``).
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

# ── Constants ────────────────────────────────────────────────────────────────

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


# ── Database helper ──────────────────────────────────────────────────────────

def _get_connection() -> psycopg2.extensions.connection:
    """Return a new psycopg2 connection using the same env var as the PHP backend."""
    dsn = os.environ["POSTGRES_CONNECTION_STRING"]
    return psycopg2.connect(dsn, sslmode="require")


# ── Email helper ─────────────────────────────────────────────────────────────

def _send_email(order: dict, business_name: str, contact_email: str,
                new_status: str, description: str) -> None:
    """Send a branded status-update email via Azure Communication Services SDK."""
    conn_str = os.environ.get("AZURE_EMAIL_CONNECTION_STRING", "")
    from_addr = os.environ.get("AZURE_EMAIL_FROM_ADDRESS", "")
    if not conn_str or not from_addr:
        logging.warning("Email env vars not set – skipping email send.")
        return

    now_utc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
    tracking = order["tracking_number"]
    origin = order["origin"]
    destination = order["destination"]

    subject = f"FedEx Update: Tracking #{tracking} — {new_status}"

    plain_text = (
        f"Hello {business_name},\n\n"
        "Your shipment status has been updated.\n\n"
        f"Tracking Number : {tracking}\n"
        f"Route           : {origin} → {destination}\n"
        f"New Status      : {new_status}\n"
        f"Description     : {description}\n"
        f"Updated At      : {now_utc}\n\n"
        "This is an automated message from FedEx Notification Service."
    )

    html = (
        "<div style='font-family:Arial,sans-serif;color:#333;max-width:600px'>"
        "  <div style='background:#4D148C;padding:16px 24px'>"
        "    <span style='color:#FF6200;font-size:24px;font-weight:bold'>Fed</span>"
        "    <span style='color:#fff;font-size:24px;font-weight:bold'>Ex</span>"
        "  </div>"
        "  <div style='padding:24px;border:1px solid #ddd'>"
        f"    <p>Hello <strong>{business_name}</strong>,</p>"
        "    <p>Your shipment status has been updated.</p>"
        "    <table style='width:100%;border-collapse:collapse;margin:16px 0'>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Tracking Number</td><td style='padding:8px'>{tracking}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Route</td><td style='padding:8px'>{origin} → {destination}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>New Status</td><td style='padding:8px;color:#4D148C;font-weight:bold'>{new_status}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Description</td><td style='padding:8px'>{description}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Updated At</td><td style='padding:8px'>{now_utc}</td></tr>"
        "    </table>"
        "    <p style='font-size:12px;color:#999'>This is an automated message from FedEx Notification Service. Do not reply.</p>"
        "  </div>"
        "</div>"
    )

    try:
        client = EmailClient.from_connection_string(conn_str)
        message = {
            "senderAddress": from_addr,
            "recipients": {"to": [{"address": contact_email}]},
            "content": {
                "subject": subject,
                "plainText": plain_text,
                "html": html,
            },
        }
        poller = client.begin_send(message)
        result = poller.result()
        logging.info("Email accepted – operation id: %s", result.id)
    except Exception:
        logging.exception("Email send failed (non-fatal)")


# ── Refresh helper ───────────────────────────────────────────────────────────

def _fetch_order_with_events(cur, order_id: str) -> dict | None:
    """Return the full order object with shipment_events (matches GET /api/orders/{id})."""
    cur.execute(
        """SELECT o.*, b.name AS business_name, b.contact_email, b.id AS business_id
           FROM orders o
           JOIN businesses b ON o.business_id = b.id
           WHERE o.id = %s""",
        (order_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None

    cur.execute(
        "SELECT * FROM shipment_events WHERE order_id = %s ORDER BY occurred_at DESC",
        (order_id,),
    )
    row["shipment_events"] = cur.fetchall()
    return row


# ── JSON serialiser ──────────────────────────────────────────────────────────

def _default_serialiser(obj: object) -> str | float:
    """Handle datetime / date / Decimal objects so json.dumps doesn't choke."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Main function ────────────────────────────────────────────────────────────

@app.route(route="orders/{order_id}/status", methods=["PATCH"])
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    """PATCH /api/orders/{order_id}/status — update shipment status."""
    try:
        return _handle_update_status(req)
    except Exception:
        logging.exception("Unhandled error in update_order_status")
        return func.HttpResponse(
            json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )


def _handle_update_status(req: func.HttpRequest) -> func.HttpResponse:
    """Inner handler so the top-level wrapper can catch all exceptions."""
    order_id = req.route_params.get("order_id", "")

    # ── Parse & validate body ────────────────────────────────────────────
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    new_status = (body.get("status") or "").strip()
    location = (body.get("location") or "Unknown").strip()
    description = (body.get("description") or "").strip()
    event_description = description or f"Status updated to {new_status}"

    if new_status not in VALID_STATUSES:
        return func.HttpResponse(
            json.dumps({"error": "Invalid status", "allowed": VALID_STATUSES}),
            status_code=422,
            mimetype="application/json",
        )

    # ── Database operations ──────────────────────────────────────────────
    conn = _get_connection()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Fetch order + business
                cur.execute(
                    """SELECT o.*, b.id AS business_id, b.name AS business_name,
                              b.contact_email
                       FROM orders o
                       JOIN businesses b ON o.business_id = b.id
                       WHERE o.id = %s""",
                    (order_id,),
                )
                order = cur.fetchone()
                if order is None:
                    return func.HttpResponse(
                        json.dumps({"error": "Order not found"}),
                        status_code=404,
                        mimetype="application/json",
                    )

                # 1. Update order status
                cur.execute(
                    """UPDATE orders
                       SET status = %s::order_status,
                           actual_delivery = CASE
                             WHEN %s = 'Delivered' THEN NOW()
                             ELSE actual_delivery
                           END,
                           updated_at = NOW()
                       WHERE id = %s""",
                    (new_status, new_status, order_id),
                )

                # 2. Insert shipment event
                event_type = STATUS_TO_EVENT.get(new_status, "In Transit")
                cur.execute(
                    """INSERT INTO shipment_events
                           (id, order_id, event_type, location, description, occurred_at)
                       VALUES (gen_random_uuid(), %s, %s::event_type, %s, %s, NOW())""",
                    (order_id, event_type, location, event_description),
                )

                # 3. Insert notification
                notif_type = STATUS_TO_NOTIFICATION.get(new_status, "Status Update")
                notif_message = (
                    f"Tracking #{order['tracking_number']}: "
                    f"status changed to {new_status}."
                )
                cur.execute(
                    """INSERT INTO notifications
                           (id, order_id, business_id, type, message, is_read, created_at)
                       VALUES (gen_random_uuid(), %s, %s, %s::notification_type,
                               %s, false, NOW())""",
                    (order_id, order["business_id"], notif_type, notif_message),
                )

                # 4. Fetch refreshed order for response
                refreshed = _fetch_order_with_events(cur, order_id)

        # 5. Send email (outside the DB transaction, non-blocking)
        _send_email(
            order=dict(order),
            business_name=order["business_name"],
            contact_email=order["contact_email"],
            new_status=new_status,
            description=event_description,
        )

    finally:
        conn.close()

    return func.HttpResponse(
        json.dumps(refreshed, default=_default_serialiser),
        status_code=200,
        mimetype="application/json",
    )
