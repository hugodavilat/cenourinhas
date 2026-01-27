# decorators.py
import os
from django.shortcuts import redirect
from functools import wraps
from dotenv import load_dotenv
from django.shortcuts import redirect
from core.models import Guest

load_dotenv()

# Telefone dos que vão ter acesso irrestrito ao DB.
list_string = os.getenv("ADMINS")
ADMIN_PHONES = []
if list_string:
    ADMIN_PHONES = [item.strip() for item in list_string.split(',')]

def wedding_admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Assuming your OTP login stores the phone in the session or user object
        user_phone = request.user.phone_number 
        if user_phone in ADMIN_PHONES:
            return view_func(request, *args, **kwargs)
        return redirect('home') # Send intruders back to the main page
    return _wrapped_view


def guest_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Allow if session flag set after OTP verification
        if request.session.get("guest_authenticated"):
            return view_func(request, *args, **kwargs)

        # If we have an OTP user id in session, allow if that guest is confirmed
        guest_id = request.session.get("otp_user_id")
        if guest_id:
            try:
                guest = Guest.objects.get(id=guest_id)
                if guest.is_confirmed:
                    return view_func(request, *args, **kwargs)
                # allow admins by phone even if not confirmed
                if guest.phone_number in ADMIN_PHONES:
                    return view_func(request, *args, **kwargs)
            except Guest.DoesNotExist:
                pass

        # Not authenticated as guest -> redirect to OTP login
        return redirect('login_phone')
    return _wrapped_view