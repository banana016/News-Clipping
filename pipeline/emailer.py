"""
Step 12 of the pipeline: send the notification email via Gmail SMTP + app
password (Phase 3 decision — no separate email service to sign up for).

Failure here must never take down the pipeline run — the analysis results
are already in the DB by this point (spec: "뉴스 분석 결과는 발송 실패와
관계없이 저장"). Retries 3x, then just logs and returns False.
"""
from __future__ import annotations

import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from shared.config import settings

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
MAX_RETRIES = 3


def send_email(subject: str, html_body: str) -> bool:
    if settings.dry_run:
        logger.info("[DRY_RUN] would send email: %s", subject)
        return True

    if not (settings.gmail_address and settings.gmail_app_password and settings.briefing_recipient):
        logger.error("email not configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD / BRIEFING_RECIPIENT_EMAIL)")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.gmail_address
    msg["To"] = settings.briefing_recipient
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(settings.gmail_address, settings.gmail_app_password)
                server.sendmail(settings.gmail_address, [settings.briefing_recipient], msg.as_string())
            return True
        except smtplib.SMTPException as exc:
            logger.warning("email send failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2

    logger.error("email send failed after %d attempts", MAX_RETRIES)
    return False
