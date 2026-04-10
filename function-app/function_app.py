"""Azure Function App — PATCH API for FedEx Notification Service.

Mirrors the three PATCH endpoints from the PHP backend:
  - PATCH /api/orders/{id}/status
  - PATCH /api/notifications/{id}/read
  - PATCH /api/notifications/read-all
"""

import json
import logging

import azure.functions as func
import psycopg2.extras

from shared.database import get_connection

from shared.email_service import EmailService

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

VALID_STATUSES = [
    "Picked Up",
    "In Transit",
    "Out for Delivery",
    "Delivered",
    "Delayed",
    "Exception",
]

STATUS_TO_EVENT = {
    "Picked Up": "Package Picked Up",
    "In Transit": "In Transit",
    "Out for Delivery": "Out for Delivery",
    "Delivered": "Delivered",
    "Delayed": "Delay Reported",
    "Exception": "Exception",
}

STATUS_TO_NOTIFICATION = {
    "Delivered": "Delivery Confirmed",
    "Out for Delivery": "Out for Delivery",
    "Delayed": "Delay Alert",
    "Exception": "Exception Alert",
}


def _json_response(data: dict | list, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(data, default=str),
        status_code=status_code,
        mimetype="application/json",
    )


# ── PATCH /api/orders/{order_id}/status ──────────────────────────────────────


@app.route(
    route="orders/{order_id}/status",
    methods=["PATCH"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    """Update an order's status, insert shipment event + notification, send email."""
    order_id = req.route_params.get("order_id")
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body"}, 400)

    new_status = (body.get("status") or "").strip()
    location = (body.get("location") or "Unknown").strip()
    description = (body.get("description") or "").strip()
    event_description = description if description else f"Status updated to {new_status}"

    if new_status not in VALID_STATUSES:
        return _json_response(
            {"error": "Invalid status", "allowed": VALID_STATUSES}, 422
        )

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch order + business
    cur.execute(
        """SELECT o.*, b.id AS business_id, b.name AS business_name, b.contact_email
           FROM orders o
           JOIN businesses b ON o.business_id = b.id
           WHERE o.id = %s""",
        (order_id,),
    )
    order = cur.fetchone()

    if not order:
        return _json_response({"error": "Order not found"}, 404)

    # Update status
    cur.execute(
        """UPDATE orders
           SET status = %s::order_status,
               actual_delivery = CASE WHEN %s = 'Delivered' THEN NOW() ELSE actual_delivery END,
               updated_at = NOW()
           WHERE id = %s""",
        (new_status, new_status, order_id),
    )

    # Insert shipment event
    event_type = STATUS_TO_EVENT.get(new_status, "In Transit")
    cur.execute(
        """INSERT INTO shipment_events (id, order_id, event_type, location, description, occurred_at)
           VALUES (gen_random_uuid(), %s, %s::event_type, %s, %s, NOW())""",
        (order_id, event_type, location, event_description),
    )

    # Insert notification
    notif_type = STATUS_TO_NOTIFICATION.get(new_status, "Status Update")
    cur.execute(
        """INSERT INTO notifications (id, order_id, business_id, type, message, is_read, created_at)
           VALUES (gen_random_uuid(), %s, %s, %s::notification_type, %s, false, NOW())""",
        (
            order_id,
            order["business_id"],
            notif_type,
            f"Tracking #{order['tracking_number']}: status changed to {new_status}.",
        ),
    )

    # Send email (non-blocking — failures are caught)
    try:
        email_svc = EmailService()
        business = {
            "contact_email": order["contact_email"],
            "name": order["business_name"],
        }
        order_for_email = {
            "tracking_number": order["tracking_number"],
            "origin": order["origin"],
            "destination": order["destination"],
        }
        sent = email_svc.send_status_update_email(
            order_for_email, business, new_status, event_description
        )
        if not sent:
            logging.warning(
                "Email send returned False for order %s", order_id
            )
    except Exception as exc:
        logging.error("Email failed for order %s: %s", order_id, exc)

    # Return refreshed order (same as GET /api/orders/{id})
    cur.execute(
        """SELECT o.*, b.name AS business_name, b.contact_email, b.id AS business_id
           FROM orders o
           JOIN businesses b ON o.business_id = b.id
           WHERE o.id = %s""",
        (order_id,),
    )
    refreshed = cur.fetchone()

    cur.execute(
        "SELECT * FROM shipment_events WHERE order_id = %s ORDER BY occurred_at DESC",
        (order_id,),
    )
    refreshed["shipment_events"] = cur.fetchall()

    return _json_response(refreshed)


# ── PATCH /api/notifications/{notification_id}/read ──────────────────────────


@app.route(
    route="notifications/{notification_id}/read",
    methods=["PATCH"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def mark_notification_read(req: func.HttpRequest) -> func.HttpResponse:
    """Mark a single notification as read."""
    notification_id = req.route_params.get("notification_id")

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "UPDATE notifications SET is_read = true WHERE id = %s RETURNING *",
        (notification_id,),
    )
    notification = cur.fetchone()

    if not notification:
        return _json_response({"error": "Notification not found"}, 404)

    return _json_response(notification)


# ── PATCH /api/notifications/read-all ────────────────────────────────────────


@app.route(
    route="notifications/read-all",
    methods=["PATCH"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def mark_all_notifications_read(req: func.HttpRequest) -> func.HttpResponse:
    """Mark all (or business-scoped) notifications as read."""
    try:
        body = req.get_json()
    except ValueError:
        body = {}

    business_id = (body.get("businessId") or "").strip() if body else ""

    conn = get_connection()
    cur = conn.cursor()

    if business_id:
        cur.execute(
            "UPDATE notifications SET is_read = true WHERE business_id = %s AND is_read = false",
            (business_id,),
        )
    else:
        cur.execute("UPDATE notifications SET is_read = true WHERE is_read = false")

    return _json_response({"updated": cur.rowcount})
