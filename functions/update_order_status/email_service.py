"""Azure Communication Services email sender.

Replicates the HMAC-SHA256 authenticated email sending from the PHP
backend's EmailService.php, targeting the same ACS REST API.
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

import requests


def _parse_connection_string(conn_str: str) -> tuple[str, str]:
    """Extract (endpoint, access_key) from an ACS connection string."""
    endpoint_match = re.search(r"endpoint=(https?://[^;]+)", conn_str, re.IGNORECASE)
    key_match = re.search(r"accesskey=([^;]+)", conn_str, re.IGNORECASE)
    endpoint = (endpoint_match.group(1) if endpoint_match else "").rstrip("/")
    access_key = key_match.group(1) if key_match else ""
    return endpoint, access_key


def _build_signature(
    method: str, path: str, date: str, host: str, content_hash: str, access_key: str
) -> str:
    """Build HMAC-SHA256 signature matching the PHP implementation."""
    string_to_sign = f"{method}\n{path}\n{date};{host};{content_hash}"
    decoded_key = base64.b64decode(access_key)
    signature = hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256)
    return base64.b64encode(signature.digest()).decode("utf-8")


def send_status_update_email(
    order: dict, business: dict, new_status: str, event_description: str | None = None
) -> bool:
    """Send a status-update email via Azure Communication Services.

    Parameters match the PHP EmailService::sendStatusUpdateEmail() signature.
    """
    conn_str = os.environ.get("AZURE_EMAIL_CONNECTION_STRING", "")
    from_address = os.environ.get("AZURE_EMAIL_FROM_ADDRESS", "")

    endpoint, access_key = _parse_connection_string(conn_str)
    if not endpoint or not access_key:
        logging.error("[EmailService] Missing or invalid AZURE_EMAIL_CONNECTION_STRING")
        return False

    to = business["contact_email"]
    subject = f"FedEx Update: Tracking #{order['tracking_number']} — {new_status}"
    desc = (event_description or "").strip()

    now_utc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S")

    # Plain text body
    desc_line = (
        f"Description     : {desc}"
        if desc
        else f"Description     : Status updated to {new_status}"
    )
    plain_text = "\n".join(
        [
            f"Hello {business['name']},",
            "",
            "Your shipment status has been updated.",
            "",
            f"Tracking Number : {order['tracking_number']}",
            f"Route           : {order['origin']} → {order['destination']}",
            f"New Status      : {new_status}",
            desc_line,
            f"Updated At      : {now_utc} UTC",
            "",
            "This is an automated message from FedEx Notification Service.",
        ]
    )

    # HTML body (FedEx branded, matching PHP implementation)
    desc_html = escape(desc) if desc else f"Status updated to {new_status}"
    html = f"""
        <div style='font-family:Arial,sans-serif;color:#333;max-width:600px'>
            <div style='background:#4D148C;padding:16px 24px'>
                <span style='color:#FF6200;font-size:24px;font-weight:bold'>Fed</span><span style='color:#fff;font-size:24px;font-weight:bold'>Ex</span>
            </div>
            <div style='padding:24px;border:1px solid #ddd'>
                <p>Hello <strong>{escape(business['name'])}</strong>,</p>
                <p>Your shipment status has been updated.</p>
                <table style='width:100%;border-collapse:collapse;margin:16px 0'>
                    <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Tracking Number</td><td style='padding:8px'>{escape(order['tracking_number'])}</td></tr>
                    <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Route</td><td style='padding:8px'>{escape(order['origin'])} → {escape(order['destination'])}</td></tr>
                    <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>New Status</td><td style='padding:8px;color:#4D148C;font-weight:bold'>{escape(new_status)}</td></tr>
                    <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Description</td><td style='padding:8px'>{desc_html}</td></tr>
                    <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Updated At</td><td style='padding:8px'>{now_utc} UTC</td></tr>
                </table>
                <p style='font-size:12px;color:#999'>This is an automated message from FedEx Notification Service. Do not reply.</p>
            </div>
        </div>"""

    email_body = json.dumps(
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
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    content_hash = base64.b64encode(
        hashlib.sha256(email_body.encode("utf-8")).digest()
    ).decode("utf-8")
    signature = _build_signature("POST", path, date, host, content_hash, access_key)

    headers = {
        "Content-Type": "application/json",
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": (
            f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256"
            f"&Signature={signature}"
        ),
        "Repeatability-Request-ID": str(uuid.uuid4()),
        "Repeatability-First-Sent": date,
    }

    try:
        resp = requests.post(
            f"{endpoint}{path}", headers=headers, data=email_body, timeout=15
        )
        if 200 <= resp.status_code < 300:
            logging.info(
                f"[EmailService] Azure accepted request HTTP {resp.status_code}"
            )
            return True
        else:
            logging.error(
                f"[EmailService] Azure returned HTTP {resp.status_code}: {resp.text}"
            )
            return False
    except requests.RequestException as e:
        logging.error(f"[EmailService] Request error: {e}")
        return False
