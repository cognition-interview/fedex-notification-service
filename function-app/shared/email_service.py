"""Azure Communication Services email sender — Python port of EmailService.php."""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)


class EmailService:
    """Send branded status-update emails via Azure Communication Services."""

    def __init__(self):
        conn_str = os.environ.get("AZURE_EMAIL_CONNECTION_STRING", "")
        self._parse_connection_string(conn_str)
        self.from_address = os.environ.get("AZURE_EMAIL_FROM_ADDRESS", "")

    def _parse_connection_string(self, conn_str: str) -> None:
        ep_match = re.search(r"endpoint=(https?://[^;]+)", conn_str, re.IGNORECASE)
        key_match = re.search(r"accesskey=([^;]+)", conn_str, re.IGNORECASE)
        self.endpoint = (ep_match.group(1) if ep_match else "").rstrip("/")
        self.access_key = key_match.group(1) if key_match else ""

    def send_status_update_email(
        self,
        order: dict,
        business: dict,
        new_status: str,
        event_description: str | None = None,
    ) -> bool:
        to = business["contact_email"]
        subject = f"FedEx Update: Tracking #{order['tracking_number']} — {new_status}"
        desc = (event_description or "").strip()
        desc_display = desc if desc else f"Status updated to {new_status}"
        now_utc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " UTC"

        plain_text = "\n".join([
            f"Hello {business['name']},",
            "",
            "Your shipment status has been updated.",
            "",
            f"Tracking Number : {order['tracking_number']}",
            f"Route           : {order['origin']} → {order['destination']}",
            f"New Status      : {new_status}",
            f"Description     : {desc_display}",
            f"Updated At      : {now_utc}",
            "",
            "This is an automated message from FedEx Notification Service.",
        ])

        html = f"""
            <div style='font-family:Arial,sans-serif;color:#333;max-width:600px'>
                <div style='background:#4D148C;padding:16px 24px'>
                    <span style='color:#FF6200;font-size:24px;font-weight:bold'>Fed</span><span style='color:#fff;font-size:24px;font-weight:bold'>Ex</span>
                </div>
                <div style='padding:24px;border:1px solid #ddd'>
                    <p>Hello <strong>{business['name']}</strong>,</p>
                    <p>Your shipment status has been updated.</p>
                    <table style='width:100%;border-collapse:collapse;margin:16px 0'>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Tracking Number</td><td style='padding:8px'>{order['tracking_number']}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Route</td><td style='padding:8px'>{order['origin']} → {order['destination']}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>New Status</td><td style='padding:8px;color:#4D148C;font-weight:bold'>{new_status}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Description</td><td style='padding:8px'>{desc_display}</td></tr>
                        <tr><td style='padding:8px;background:#f5f5f5;font-weight:bold'>Updated At</td><td style='padding:8px'>{now_utc}</td></tr>
                    </table>
                    <p style='font-size:12px;color:#999'>This is an automated message from FedEx Notification Service. Do not reply.</p>
                </div>
            </div>"""

        body = json.dumps({
            "sender": self.from_address,
            "recipients": {"to": [{"email": to}]},
            "content": {
                "subject": subject,
                "plainText": plain_text,
                "html": html,
            },
        })

        return self._post("/emails:send?api-version=2021-10-01-preview", body)

    def _post(self, path: str, body: str) -> bool:
        try:
            host = re.sub(r"https?://", "", self.endpoint)
            date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " GMT"
            content_hash = base64.b64encode(
                hashlib.sha256(body.encode("utf-8")).digest()
            ).decode("utf-8")
            signature = self._build_signature("POST", path, date, host, content_hash)

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

            resp = requests.post(
                self.endpoint + path, data=body, headers=headers, timeout=15
            )

            if resp.status_code < 200 or resp.status_code >= 300:
                logger.error(
                    "[EmailService] Azure returned HTTP %d: %s",
                    resp.status_code,
                    resp.text,
                )
                return False

            logger.info(
                "[EmailService] Azure accepted request HTTP %d: %s",
                resp.status_code,
                resp.text,
            )
            return True
        except Exception as exc:
            logger.error("[EmailService] request error: %s", exc)
            return False

    def _build_signature(
        self,
        method: str,
        path: str,
        date: str,
        host: str,
        content_hash: str,
    ) -> str:
        string_to_sign = f"{method}\n{path}\n{date};{host};{content_hash}"
        decoded_key = base64.b64decode(self.access_key)
        signature = hmac.new(
            decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode("utf-8")
