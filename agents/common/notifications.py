"""Notification helpers for human-review alerts.

Provides Slack webhook and SMTP email notification utilities. Both are
best-effort: when no configuration present the functions are no-ops.
"""

import os
import smtplib
from email.message import EmailMessage

import requests

from common.observability import get_logger

logger = get_logger(__name__)


def notify_slack(text: str) -> dict:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        logger.debug("SLACK_WEBHOOK_URL not configured; skipping Slack notification")
        return {"status": "skipped", "reason": "no_slack_webhook"}

    payload = {"text": text}
    try:
        resp = requests.post(webhook, json=payload, timeout=(2, 5))
        resp.raise_for_status()
        return {"status": "sent", "provider": "slack"}
    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")
        return {"status": "error", "error": str(e)}


def notify_email(subject: str, body: str, to_addrs: list = None) -> dict:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    from_addr = os.environ.get("NOTIFY_FROM", "noreply@example.com")

    if not smtp_host or not smtp_user or not smtp_pass:
        logger.debug("SMTP not configured; skipping email notification")
        return {"status": "skipped", "reason": "no_smtp_config"}

    if not to_addrs:
        to_addrs = [os.environ.get("NOTIFY_TO", "editor@example.com")]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return {"status": "sent", "provider": "smtp"}
    except Exception as e:
        logger.warning(f"Email notification failed: {e}")
        return {"status": "error", "error": str(e)}
