"""Azure Function — Update Order Status

Replicates the PHP PATCH /api/orders/{id}/status endpoint.

Side effects (all within one request):
  1. Updates orders.status; sets actual_delivery = NOW() if Delivered.
  2. Inserts a shipment_events row with the mapped event_type.
  3. Inserts a notifications row with the mapped notification_type.
  4. Sends an email via Azure Communication Services.
  5. Returns the refreshed order (with shipment_events).
"""

import azure.functions as func
import json
import logging

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
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization",
            "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
        },
    )


@app.route(
    route="orders/{order_id}/status",
    methods=["PATCH", "OPTIONS"],
    auth_level=func.AuthLevel.FUNCTION,
)
def update_order_status(req: func.HttpRequest) -> func.HttpResponse:
    """PATCH /api/orders/{order_id}/status — Update order status."""

    # Handle CORS preflight
    if req.method == "OPTIONS":
        return _json_response({}, 200)

    order_id = req.route_params.get("order_id")
    if not order_id:
        return _json_response({"error": "Missing order_id"}, 400)

    # Parse request body
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Invalid JSON body"}, 400)

    new_status = (body.get("status") or "").strip()
    location = (body.get("location") or "Unknown").strip()
    description = (body.get("description") or "").strip()
    event_description = description or f"Status updated to {new_status}"

    if new_status not in VALID_STATUSES:
        return _json_response(
            {"error": "Invalid status", "allowed": VALID_STATUSES}, 422
        )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
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

            if not order:
                return _json_response({"error": "Order not found"}, 404)

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

            # Send email (non-blocking — failures are logged, not raised)
            try:
                business = {
                    "contact_email": order["contact_email"],
                    "name": order["business_name"],
                }
                send_status_update_email(order, business, new_status, event_description)
            except Exception as e:
                logging.error(f"[update_order_status] Email failed: {e}")

            # Return refreshed order with shipment events
            cur.execute(
                """SELECT o.*, b.name AS business_name, b.contact_email,
                          b.id AS business_id
                   FROM orders o
                   JOIN businesses b ON o.business_id = b.id
                   WHERE o.id = %s""",
                (order_id,),
            )
            refreshed_order = cur.fetchone()

            cur.execute(
                """SELECT * FROM shipment_events
                   WHERE order_id = %s
                   ORDER BY occurred_at DESC""",
                (order_id,),
            )
            refreshed_order["shipment_events"] = cur.fetchall()

            return _json_response(refreshed_order)
    except Exception as e:
        conn.rollback()
        logging.error(f"[update_order_status] DB error: {e}")
        return _json_response({"error": "Internal server error"}, 500)
    finally:
        conn.close()
