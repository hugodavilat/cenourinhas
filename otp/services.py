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

def send_whatsapp_message(jid, message, image=None):
    url = settings.WHATSAPP_SERVER_URL  # set in settings
    if image:
        # Send as multipart/form-data (not supported for JID endpoint yet)
        files = {"image": image}
        data = {"jid": jid, "message": message}
        try:
            r = requests.post(url + "/send_jid_message", data=data, files=files, timeout=15)
            r.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            logger.exception("Failed sending message to WhatsApp service: %s", exc)
            return False
    else:
        # Send as JSON
        payload = {"jid": jid, "message": message}
        try:
            r = requests.post(url + "/send_jid_message", json=payload, timeout=15)
            r.raise_for_status()
            return True
        except requests.exceptions.RequestException as exc:
            logger.exception("Failed sending message to WhatsApp service: %s", exc)
            return False
