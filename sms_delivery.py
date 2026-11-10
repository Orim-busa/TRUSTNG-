"""TrustNG transactional SMS delivery through Sendozi."""

import json
import os
from urllib.request import Request, urlopen


SENDOZI_URL = "https://api.sendozi.com/v1/sms/send"


def sendozi_mode_enabled():
    return (
        os.getenv("TRUSTNG_PHONE_DELIVERY_MODE", "").strip().lower()
        == "sendozi"
    )


def send_verification_sms(phone_number, code, idempotency_key):
    """Submit one OTP to the recipient's previously assigned phone."""
    api_key = os.getenv("SENDOZI_API_KEY", "").strip()
    sender = os.getenv("SENDOZI_TRANSACTIONAL_SENDER", "").strip()
    environment = os.getenv("TRUSTNG_ENV", "").strip().lower()

    if not api_key or not sender:
        raise RuntimeError("Sendozi credentials are incomplete.")

    if environment == "sandbox":
        if not api_key.startswith("sk_test_"):
            raise RuntimeError("Sandbox requires a Sendozi test API key.")
        mode = "SENDOZI_SANDBOX"
    elif environment == "production":
        if not api_key.startswith("sk_live_"):
            raise RuntimeError("Production requires a Sendozi live API key.")
        mode = "SENDOZI_LIVE"
    else:
        raise RuntimeError("SMS environment is not configured.")

    if not idempotency_key or len(idempotency_key) > 255:
        raise RuntimeError("A valid SMS idempotency key is required.")

    message = (
        f"Your TrustNG phone verification code is {code}. "
        "It expires in 10 minutes and can only be used once. "
        "Do not share this code."
    )

    payload = {
        "sender": sender,
        "recipient": phone_number,
        "message": message,
        "route": "transactional",
    }

    request = Request(
        SENDOZI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # Never expose provider credentials or raw response bodies.
        raise RuntimeError("Sendozi SMS request failed.") from exc

    if not isinstance(body, dict) or body.get("success") is not True:
        raise RuntimeError("Sendozi did not accept the SMS request.")

    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Sendozi returned an invalid response.")

    return {
        "accepted": True,
        "mode": mode,
        "message_id": data.get("message_id"),
        "batch_id": data.get("batch_id"),
    }
