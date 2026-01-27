import requests
from django.conf import settings

def send_whatsapp_otp(phone, code):
    url = settings.WHATSAPP_SERVER_URL  # set in settings
    phone = phone.lstrip("+")  # remove leading +
    payload = {"phone": phone, "code": code}

    r = requests.post(url + "/send_otp", json=payload, timeout=700)
    r.raise_for_status()
