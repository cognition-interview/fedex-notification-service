"""Azure Function — Update Order Status

Replicates the PATCH /api/orders/{id}/status endpoint from the on-prem
PHP backend as a standalone Azure Function (HTTP trigger).

Side effects (identical to the PHP endpoint):
1. Updates orders.status; sets actual_delivery = NOW() if Delivered
2. Inserts a shipment_events row with mapped event_type
3. Inserts a notifications row with mapped notification_type
4. Sends an email via Azure Communication Services
5. Returns the refreshed order with shipment events
"""

import azure.functions as func
import json
import logging
import os

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


def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(body, default=str),
        status_code=status_code,
        mimetype="application/json",
    )


def _fetch_order_with_business(conn, order_id: str) -> dict | None:
    """Fetch an order joined with its business info."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT o.*, b.name AS business_name,
                      b.contact_email, b.id AS business_id
               FROM orders o
               JOIN businesses b ON o.business_id = b.id
               WHERE o.id = %s""",
            (order_id,),
        )
        return cur.fetchone()


def _fetch_order_with_events(conn, order_id: str) -> dict | None:
    """Fetch a full order with nested shipment_events (for the response)."""
    order = _fetch_order_with_business(conn, order_id)
    if not order:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM shipment_events
               WHERE order_id = %s
               ORDER BY occurred_at DESC""",
            (order_id,),
        )
        order["shipment_events"] = cur.fetchall()

    return order


@app.route(route="orders/{order_id}/status", methods=["PATCH"])
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger that updates an order's status.

    Route: PATCH /api/orders/{order_id}/status
    Body:  { "status": "In Transit", "location": "Memphis, TN",
             "description": "Package arrived at sorting facility" }
    """
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
        if not order:
            return _json_response({"error": "Order not found"}, 404)

        with conn.cursor() as cur:
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
            message = (
                f"Tracking #{order['tracking_number']}: "
                f"status changed to {new_status}."
            )
            cur.execute(
                """INSERT INTO notifications
                   (id, order_id, business_id, type, message, is_read, created_at)
                   VALUES (gen_random_uuid(), %s, %s, %s::notification_type,
                           %s, false, NOW())""",
                (order_id, order["business_id"], notif_type, message),
            )

        conn.commit()

        # 4. Send email (non-blocking — errors are logged but don't fail the request)
        try:
            business = {
                "contact_email": order["contact_email"],
                "name": order["business_name"],
            }
            send_status_update_email(order, business, new_status, event_description)
        except Exception as e:
            logging.error(f"[update_order_status] Email failed: {e}")

        # 5. Return refreshed order
        refreshed = _fetch_order_with_events(conn, order_id)
        if not refreshed:
            return _json_response({"error": "Order not found after update"}, 500)

        return _json_response(refreshed)

    except Exception as e:
        conn.rollback()
        logging.error(f"[update_order_status] DB error: {e}")
        return _json_response({"error": "Internal server error"}, 500)
