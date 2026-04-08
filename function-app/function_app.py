"""Azure Function App for FedEx order status updates.

Mimics the PATCH /api/orders/{id}/status endpoint from the PHP backend:
1. Validates the new status
2. Fetches the order + business
3. Updates the order status (sets actual_delivery if Delivered)
4. Inserts a shipment_events row
5. Inserts a notifications row
6. Sends an email via Azure Communication Services
7. Returns the refreshed order with shipment events
"""

import azure.functions as func
import json
import logging
import os
import re
from datetime import datetime, timezone
from db import get_connection
from email_service import send_status_update_email

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

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


def _json_response(data: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(data, default=str),
        status_code=status_code,
        mimetype="application/json",
    )


def _fetch_order_with_business(conn, order_id: str) -> dict | None:
    """Fetch an order joined with its business details."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT o.id, o.tracking_number, o.origin, o.destination,
                      o.status, o.weight_lbs, o.service_type,
                      o.estimated_delivery, o.actual_delivery,
                      o.created_at, o.updated_at,
                      b.id AS business_id, b.name AS business_name,
                      b.contact_email
               FROM orders o
               JOIN businesses b ON o.business_id = b.id
               WHERE o.id = %s""",
            (order_id,),
        )
        row = cur.fetchone()
    return row


def _fetch_order_with_events(conn, order_id: str) -> dict | None:
    """Fetch an order with its business details and shipment events."""
    order = _fetch_order_with_business(conn, order_id)
    if order is None:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, order_id, event_type, location, description, occurred_at
               FROM shipment_events
               WHERE order_id = %s
               ORDER BY occurred_at DESC""",
            (order_id,),
        )
        events = cur.fetchall()

    order["shipment_events"] = events
    return order


@app.route(route="orders/{order_id}/status", methods=["PATCH"], auth_level=func.AuthLevel.FUNCTION)
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    """Update order status — mirrors PATCH /api/orders/{id}/status."""
    order_id = req.route_params.get("order_id")
    if not order_id:
        return _json_response({"error": "Missing order_id in route"}, 400)

    # Parse request body
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body"}, 400)

    new_status = (body.get("status") or "").strip()
    location = (body.get("location") or "Unknown").strip()
    description = (body.get("description") or "").strip()
    event_description = description or f"Status updated to {new_status}"

    # Validate status
    if new_status not in VALID_STATUSES:
        return _json_response(
            {"error": "Invalid status", "allowed": VALID_STATUSES}, 422
        )

    conn = get_connection()
    try:
        # Fetch order + business
        order = _fetch_order_with_business(conn, order_id)
        if order is None:
            return _json_response({"error": "Order not found"}, 404)

        with conn.cursor() as cur:
            # Update order status
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

            # Insert shipment event
            event_type = STATUS_TO_EVENT.get(new_status, "In Transit")
            cur.execute(
                """INSERT INTO shipment_events
                       (id, order_id, event_type, location, description, occurred_at)
                   VALUES (gen_random_uuid(), %s, %s::event_type, %s, %s, NOW())""",
                (order_id, event_type, location, event_description),
            )

            # Insert notification
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

        conn.commit()

        # Send email (non-blocking — failures are logged but don't fail the response)
        try:
            business = {
                "contact_email": order["contact_email"],
                "name": order["business_name"],
            }
            send_status_update_email(order, business, new_status, event_description)
        except Exception as e:
            logging.error(f"[update_order_status] Email failed: {e}")

        # Return refreshed order with events
        refreshed = _fetch_order_with_events(conn, order_id)
        return _json_response(refreshed)

    except Exception as e:
        conn.rollback()
        logging.error(f"[update_order_status] Error: {e}")
        return _json_response({"error": "Internal server error"}, 500)
