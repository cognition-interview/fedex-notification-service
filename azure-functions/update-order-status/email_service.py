"""Azure Communication Services email helper.

Replicates the PHP EmailService — HMAC-SHA256 signed requests to the
Azure Communication Services REST API (2021-10-01-preview).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlparse

import urllib.request


def _parse_connection_string(conn_str: str) -> tuple[str, str]:
    """Extract (endpoint, access_key) from an Azure Communication Services
    connection string."""
    endpoint_match = re.search(r"endpoint=(https?://[^;]+)", conn_str, re.IGNORECASE)
    key_match = re.search(r"accesskey=([^;]+)", conn_str, re.IGNORECASE)
    endpoint = (endpoint_match.group(1) if endpoint_match else "").rstrip("/")
    access_key = key_match.group(1) if key_match else ""
    return endpoint, access_key


def _build_signature(
    method: str, path: str, date: str, host: str, content_hash: str, access_key: str
) -> str:
    string_to_sign = f"{method}\n{path}\n{date};{host};{content_hash}"
    decoded_key = base64.b64decode(access_key)
    signature = hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(signature.digest()).decode("utf-8")


def send_status_update_email(
    order: dict,
    business: dict,
    new_status: str,
    event_description: str | None = None,
) -> bool:
    """Send a status-update email via Azure Communication Services.

    Returns True on success, False on failure. Never raises.
    """
    conn_str = os.environ.get("AZURE_EMAIL_CONNECTION_STRING", "")
    from_address = os.environ.get("AZURE_EMAIL_FROM_ADDRESS", "")
    endpoint, access_key = _parse_connection_string(conn_str)

    if not endpoint or not access_key or not from_address:
        logging.warning("[EmailService] Missing email configuration — skipping send")
        return False

    to = business["contact_email"]
    tracking = order["tracking_number"]
    origin = order["origin"]
    destination = order["destination"]
    desc = (event_description or "").strip()
    desc_display = desc if desc else f"Status updated to {new_status}"
    now_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " UTC"
    subject = f"FedEx Update: Tracking #{tracking} — {new_status}"

    plain_text = "\n".join(
        [
            f"Hello {business['name']},",
            "",
            "Your shipment status has been updated.",
            "",
            f"Tracking Number : {tracking}",
            f"Route           : {origin} → {destination}",
            f"New Status      : {new_status}",
            f"Description     : {desc_display}",
            f"Updated At      : {now_str}",
            "",
            "This is an automated message from FedEx Notification Service.",
        ]
    )

    html = (
        "<div style='font-family:Arial,sans-serif;color:#333;max-width:600px'>"
        "  <div style='background:#4D148C;padding:16px 24px'>"
        "    <span style='color:#FF6200;font-size:24px;font-weight:bold'>Fed</span>"
        "    <span style='color:#fff;font-size:24px;font-weight:bold'>Ex</span>"
        "  </div>"
        "  <div style='padding:24px;border:1px solid #ddd'>"
        f"    <p>Hello <strong>{escape(business['name'])}</strong>,</p>"
        "    <p>Your shipment status has been updated.</p>"
        "    <table style='width:100%;border-collapse:collapse;margin:16px 0'>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Tracking Number</td><td style='padding:8px'>{escape(tracking)}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Route</td><td style='padding:8px'>{escape(origin)} &rarr; {escape(destination)}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>New Status</td><td style='padding:8px;color:#4D148C;font-weight:bold'>{escape(new_status)}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Description</td><td style='padding:8px'>{escape(desc_display)}</td></tr>"
        f"      <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Updated At</td><td style='padding:8px'>{now_str}</td></tr>"
        "    </table>"
        "    <p style='font-size:12px;color:#999'>This is an automated message from FedEx Notification Service. Do not reply.</p>"
        "  </div>"
        "</div>"
    )

    payload = json.dumps(
        {
            "sender": from_address,
            "recipients": {"to": [{"email": to}]},
            "content": {
                "subject": subject,
                "plainText": plain_text,
                "html": html,
            },
        }
    )

    path = "/emails:send?api-version=2021-10-01-preview"
    host = urlparse(endpoint).hostname
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " GMT"
    content_hash = base64.b64encode(
        hashlib.sha256(payload.encode("utf-8")).digest()
    ).decode("utf-8")
    signature = _build_signature("POST", path, date, host, content_hash, access_key)
    repeatability_id = str(uuid.uuid4())

    headers = {
        "Content-Type": "application/json",
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": (
            f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256"
            f"&Signature={signature}"
        ),
        "Repeatability-Request-ID": repeatability_id,
        "Repeatability-First-Sent": date,
    }

    try:
        req = urllib.request.Request(
            endpoint + path,
            data=payload.encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            resp_body = resp.read().decode("utf-8")
            logging.info(
                f"[EmailService] Azure accepted request HTTP {status}: {resp_body}"
            )
            return True
    except Exception as e:
        logging.error(f"[EmailService] Email send failed: {e}")
        return False
