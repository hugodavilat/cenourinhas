import logging
import requests
from django.conf import settings

from core.models import ExtraGuest, Guest

logger = logging.getLogger(__name__)


def extract_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def normalize_phone_number(value: str, country_code: str = None) -> str:
    digits = extract_digits(value)
    if digits.startswith("00"):
        digits = digits[2:]

    if country_code:
        country_code = extract_digits(country_code)
        if not digits.startswith(country_code):
            if digits.startswith("0"):
                digits = country_code + digits.lstrip("0")
            elif len(digits) <= 11:
                digits = country_code + digits

    return f"+{digits}" if digits else ""


def normalize_whatsapp_phone(value: str, country_code: str = None) -> str:
    digits = extract_digits(value)
    if digits.startswith("00"):
        digits = digits[2:]

    if country_code:
        country_code = extract_digits(country_code)
        if not digits.startswith(country_code):
            if digits.startswith("0"):
                digits = country_code + digits.lstrip("0")
            elif len(digits) <= 11:
                digits = country_code + digits

    return digits


def phone_candidate_variants(phone: str) -> list[str]:
    variants = []
    if phone and phone not in variants:
        variants.append(phone)

    if phone.startswith("+"):
        no_plus = phone[1:]
        if no_plus and no_plus not in variants:
            variants.append(no_plus)

    digits = extract_digits(phone)
    if digits and digits not in variants:
        variants.append(digits)

    if len(digits) == 13 and digits.startswith("55") and digits[4] == '9':
        alt = digits[:4] + digits[5:]
        if alt not in variants:
            variants.append(alt)
    elif len(digits) == 12 and digits.startswith("55"):
        alt = digits[:4] + "9" + digits[4:]
        if alt not in variants:
            variants.append(alt)

    return variants


def find_user_by_phone(phone: str, country_code: str = None):
    normalized = normalize_phone_number(phone, country_code)
    variants = phone_candidate_variants(normalized)

    for candidate in variants:
        try:
            return Guest.objects.get(phone_number=candidate), False, candidate
        except Guest.DoesNotExist:
            pass

    for candidate in variants:
        try:
            extra = ExtraGuest.objects.get(phone_number=candidate)
            return extra.main_guest, True, candidate
        except ExtraGuest.DoesNotExist:
            pass

    return None, False, ""


def send_whatsapp_otp(phone, code):
    """Send OTP to WhatsApp service. Returns (success, error_message)."""
    url = settings.WHATSAPP_SERVER_URL  # set in settings
    phone = normalize_whatsapp_phone(phone)
    payload = {"phone": phone, "code": code}

    try:
        r = requests.post(url + "/send_otp", json=payload, timeout=10)
        if r.ok:
            return True, ""
        logger.error("WhatsApp OTP service returned %s: %s", r.status_code, r.text)
        return False, r.text
    except requests.exceptions.RequestException as exc:
        logger.exception("Failed sending OTP to WhatsApp service: %s", exc)
        return False, str(exc)


def send_whatsapp_message(phone, message, attachment=None):
    url = settings.WHATSAPP_SERVER_URL  # set in settings
    phone = normalize_whatsapp_phone(phone)
    if attachment:
        # Send as multipart/form-data (supports image or PDF)
        files = {"image": attachment}
        data = {"phone": phone, "message": message}
        try:
            r = requests.post(url + "/send_message", data=data, files=files, timeout=15)
            if r.ok:
                return True, ""
            logger.error("WhatsApp message service returned %s: %s", r.status_code, r.text)
            return False, r.text
        except requests.exceptions.RequestException as exc:
            logger.exception("Failed sending message to WhatsApp service: %s", exc)
            return False, str(exc)
    else:
        # Send as JSON
        payload = {"phone": phone, "message": message}
        try:
            r = requests.post(url + "/send_message", json=payload, timeout=15)
            if r.ok:
                return True, ""
            logger.error("WhatsApp message service returned %s: %s", r.status_code, r.text)
            return False, r.text
        except requests.exceptions.RequestException as exc:
            logger.exception("Failed sending message to WhatsApp service: %s", exc)
            return False, str(exc)
