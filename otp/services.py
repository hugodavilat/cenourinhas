import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

def send_whatsapp_otp(phone, code):
    """Send OTP to WhatsApp service. Returns True on success, False on failure.

    This function catches request errors instead of raising, so callers can
    handle failures gracefully and show user-friendly messages.
    """
    url = settings.WHATSAPP_SERVER_URL  # set in settings
    phone = phone.lstrip("+")  # remove leading +
    payload = {"phone": phone, "code": code}

    try:
        r = requests.post(url + "/send_otp", json=payload, timeout=10)
        r.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        logger.exception("Failed sending OTP to WhatsApp service: %s", exc)
        return False
