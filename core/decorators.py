# decorators.py
import os
from django.shortcuts import redirect
from functools import wraps
from dotenv import load_dotenv
from django.shortcuts import redirect
from core.models import Guest
from django.utils import timezone

load_dotenv()

# Telefone dos que vão ter acesso irrestrito ao DB.
list_string = os.getenv("ADMINS")
ADMIN_PHONES = []
if list_string:
    ADMIN_PHONES = [item.strip() for item in list_string.split(',')]

def wedding_admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        guest_id = request.session.get("otp_user_id")
        if not guest_id:
            return redirect('login_phone')
        try:
            guest = Guest.objects.get(id=guest_id)
        except Guest.DoesNotExist:
            return redirect('login_phone')
        user_phone = guest.phone_number
        print("ADMIN_PHONES:", ADMIN_PHONES)
        print(f"wedding_admin_required: checking access for phone {user_phone}")
        if user_phone in ADMIN_PHONES:
            return view_func(request, *args, **kwargs)
        return redirect('home') # Send intruders back to the main page
    return _wrapped_view


def guest_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Require the verified session flag set after OTP verification
        if not request.session.get("guest_authenticated"):
            return redirect('login_phone')

        # Require otp_user_id in session
        guest_id = request.session.get("otp_user_id")
        if not guest_id:
            return redirect('login_phone')

        try:
            guest = Guest.objects.get(id=guest_id)
        except Guest.DoesNotExist:
            return redirect('login_phone')

        # Allow admins by phone even if not confirmed
        # if guest.phone_number in ADMIN_PHONES:
        #     return view_func(request, *args, **kwargs)

        # Permite acesso à página de confirmação mesmo se não confirmado
        # if not guest.is_confirmed:
        #     if request.resolver_match and request.resolver_match.url_name == "confirmacao_familia":
        #         return view_func(request, *args, **kwargs)
        #     return redirect('login_phone')

        # Ensure session key matches the guest's active session and is still valid
        session_key = request.session.session_key
        if not session_key:
            # create/save session to obtain a key
            request.session.save()
            session_key = request.session.session_key

        if guest.active_session_key and guest.active_until:
            if guest.active_until > timezone.now() and session_key == guest.active_session_key:
                return view_func(request, *args, **kwargs)

        # fallback: not authenticated or session mismatch
        return redirect('login_phone')
    return _wrapped_view