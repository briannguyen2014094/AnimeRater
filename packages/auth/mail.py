"""Password recovery email via the deployment's SMTP server."""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode, urlsplit


def reset_mail_settings():
    base_url = os.getenv("APP_BASE_URL", "").rstrip("/")
    parsed = urlsplit(base_url)
    host = os.getenv("SMTP_HOST", "")
    sender = os.getenv("SMTP_FROM", "")
    if (not host or not sender or parsed.scheme not in ("http", "https")
            or not parsed.netloc or parsed.query or parsed.fragment or parsed.username):
        raise ValueError("Configure APP_BASE_URL, SMTP_HOST, and SMTP_FROM")
    return base_url, host, sender


def send_password_reset(email, token):
    try:
        base_url, host, sender = reset_mail_settings()
        message = EmailMessage()
        message["Subject"] = "Reset your AnimeRater password"
        message["From"] = sender
        message["To"] = email
        link = f"{base_url}/#{urlencode({'reset_token': token})}"
        message.set_content(
            f"Use this link to choose a new AnimeRater password:\n\n{link}\n\n"
            "This link expires in 30 minutes and can be used once. "
            "If you did not request this, you can ignore this email."
        )
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            username = os.getenv("SMTP_USERNAME")
            if username:
                smtp.login(username, os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    except Exception:
        # Do not log recipients, credentials, reset URLs, or SMTP exception text.
        logging.getLogger(__name__).error("Password recovery email delivery failed; check SMTP configuration")
