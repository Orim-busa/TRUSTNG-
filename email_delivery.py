"""TrustNG email verification delivery through configured SMTP."""

import os
import smtplib
from email.message import EmailMessage


def smtp_mode_enabled():
    return os.getenv("TRUSTNG_EMAIL_DELIVERY_MODE", "sandbox").strip().lower() == "smtp"


def send_verification_email(recipient_email, code):
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("EMAIL_FROM")

    if not all((host, port, username, password, sender)):
        raise RuntimeError("SMTP email configuration is incomplete.")

    message = EmailMessage()
    message["Subject"] = "Your TrustNG verification code"
    message["From"] = sender
    message["To"] = recipient_email
    message.set_content(
        f"""Your TrustNG email verification code is:

{code}

This code expires in 10 minutes and can only be used once.

If you did not request this code, you can ignore this email.

TrustNG
"""
    )

    use_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"

    if use_ssl:
        with smtplib.SMTP_SSL(host, int(port), timeout=15) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, int(port), timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.send_message(message)

    return True
