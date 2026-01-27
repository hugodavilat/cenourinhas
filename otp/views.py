from django.shortcuts import render, redirect
from django.contrib import messages
from core.models import Guest
from django.utils import timezone
from datetime import timedelta

from .forms import PhoneForm, OTPForm
from .models import OTP
from .services import send_whatsapp_otp

def login_phone(request):
    if request.method == "POST":
        form = PhoneForm(request.POST)
        if form.is_valid():
            country_code = form.cleaned_data["country_code"]
            phone_number = form.cleaned_data["phone"]
            
            # Format phone number: remove spaces, dashes, parentheses and add country code
            phone_clean = "".join(filter(str.isdigit, phone_number))
            full_phone = f"+{country_code}{phone_clean}"

            try:
                user = Guest.objects.get(phone_number=full_phone)
            except Guest.DoesNotExist:
                form.add_error(None, "Este número de telefone não está na lista de convidados.")
                return render(request, "otp/login_phone.html", {"form": form})

            # Prevent login if this phone already has an active session
            if user.active_session_key and user.active_until and user.active_until > timezone.now():
                messages.error(request, "Este telefone já está logado em outro lugar.")
                return redirect("login_phone")

            # Generate OTP
            code = OTP.generate_code()

            # Attempt to send via WhatsApp; if sending fails, inform user
            sent = send_whatsapp_otp(full_phone, code)
            if not sent:
                messages.error(request, "Não foi possível enviar o OTP agora. Tente novamente mais tarde.")
                return redirect("login_phone")

            # Persist OTP record only after send succeeds
            OTP.objects.create(
                user=user,
                code=code,
                expires_at=timezone.now() + timedelta(minutes=5)
            )

            # Mark guest as awaiting verification: clear confirmed flag and mark message sent
            user.is_confirmed = False
            user.message_sent = True
            user.save()

            request.session["otp_user_id"] = user.id
            return redirect("verify_otp")

    return render(request, "otp/login_phone.html", {"form": PhoneForm()})

def verify_otp(request):
    if request.method == "POST":
        form = OTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            user_id = request.session.get("otp_user_id")

            if not user_id:
                messages.error(request, "Session expired")
                return redirect("login_phone")

            user = Guest.objects.get(id=user_id)

            otp = OTP.objects.filter(user=user, code=code).order_by("-created_at").first()
            if not otp:
                messages.error(request, "Invalid code")
                return redirect("verify_otp")

            if otp.is_expired():
                messages.error(request, "Code expired")
                return redirect("login_phone")

            # mark guest as confirmed and store authenticated flag in session
            user.is_confirmed = True
            # reset message_sent since verification succeeded
            user.message_sent = False
            user.save()

            # Set session expiry and mark guest as authenticated
            # Example: sessions expire in 1 hour (3600 seconds)
            request.session["guest_authenticated"] = True
            request.session.set_expiry(3600)
            # ensure session has a key
            request.session.save()
            session_key = request.session.session_key

            # Persist single-active-session info on the Guest
            user.active_session_key = session_key
            user.active_until = timezone.now() + timedelta(seconds=3600)
            user.save()

            return redirect("home")

    return render(request, "otp/verify_otp.html", {"form": OTPForm()})


def logout(request):
    # Clear guest active session info and flush session
    user_id = request.session.get("otp_user_id")
    if user_id:
        try:
            user = Guest.objects.get(id=user_id)
            user.active_session_key = None
            user.active_until = None
            user.save()
        except Guest.DoesNotExist:
            pass

    # Flush session completely
    request.session.flush()
    return redirect("home")
