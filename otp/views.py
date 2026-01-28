from django.shortcuts import render, redirect
from django.contrib import messages
from core.models import Guest, ExtraGuest
from django.utils import timezone
from datetime import timedelta

from .forms import PhoneForm, OTPForm
from .models import OTP
from .services import send_whatsapp_otp

from core.decorators import ADMIN_PHONES
from core.settings import DEBUG

def login_phone(request):
    if request.method == "POST":
        form = PhoneForm(request.POST)
        if form.is_valid():
            country_code = form.cleaned_data["country_code"]
            phone_number = form.cleaned_data["phone"]
            # Format phone number: remove spaces, dashes, parentheses and add country code
            phone_clean = "".join(filter(str.isdigit, phone_number))
            full_phone = f"+{country_code}{phone_clean}"


            # Try to find Guest by phone, or ExtraGuest by phone
            user = None
            is_extra = False

            try:
                user = Guest.objects.get(phone_number=full_phone)
            except Guest.DoesNotExist:
                extra = None
                if full_phone:
                    try:
                        extra = ExtraGuest.objects.get(phone_number=full_phone)
                    except ExtraGuest.DoesNotExist:
                        pass
                if extra:
                    user = extra.main_guest
                    is_extra = True
                else:
                    print(f"Redirect: phone not in guest list ({full_phone})")
                    form.add_error(None, "Este número de telefone não está na lista de convidados.")
                    return render(request, "otp/login_phone.html", {"form": form})

            # Mark in session if this is an extra guest login
            request.session["is_extra_guest_login"] = is_extra
            if is_extra:
                request.session["extra_guest_phone"] = full_phone
            else:
                request.session.pop("extra_guest_phone", None)
            request.session["otp_user_id"] = user.id


            if user.active_session_key and user.active_until and user.active_until > timezone.now():
                # Clear the active session so user can request a new OTP
                print(f"Clearing active session for {full_phone} (was: {user.active_session_key}, until: {user.active_until})")
                user.active_session_key = None
                user.active_until = None
                user.save()
                # Optionally, you can also log out the previous session if needed

            code = OTP.generate_code()
            if DEBUG:
                print(f"DEBUG: OTP para {full_phone} é {code}")

            try:
                sent = send_whatsapp_otp(full_phone, code)
            except Exception as exc:
                print(f"Redirect: erro ao tentar enviar OTP para {full_phone}: {exc}")
                messages.error(request, f"Erro técnico ao tentar enviar OTP: {exc}")
                return redirect("login_phone")

            if not sent:
                print(f"Redirect: não foi possível enviar OTP para {full_phone}")
                messages.error(request, f"Não foi possível enviar o OTP para {full_phone}. Verifique o número ou tente novamente mais tarde.")
                return redirect("login_phone")

            OTP.objects.create(
                user=user,
                code=code,
                expires_at=timezone.now() + timedelta(minutes=5)
            )

            user.is_confirmed = False
            user.message_sent = True
            user.save()

            request.session["otp_user_id"] = user.id
            return redirect("verify_otp")

    return render(request, "otp/login_phone.html", {"form": form if 'form' in locals() else PhoneForm()})

def verify_otp(request):
    if request.method == "POST":
        form = OTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            user_id = request.session.get("otp_user_id")

            if not user_id:
                messages.error(request, "Session expired")
                return redirect("login_phone")


            try:
                user = Guest.objects.get(id=user_id)
            except Guest.DoesNotExist:
                messages.error(request, "Convidado não encontrado.")
                return redirect("login_phone")

            is_extra = request.session.get("is_extra_guest_login", False)
            extra_guest_phone = request.session.get("extra_guest_phone")
            if is_extra and extra_guest_phone:
                # Find the extra guest
                try:
                    extra = ExtraGuest.objects.get(phone_number=extra_guest_phone, main_guest_id=user_id)
                except ExtraGuest.DoesNotExist:
                    messages.error(request, "Convidado extra não encontrado.")
                    return redirect("login_phone")
                # OTP is always tied to the main guest, so check OTP for user
                otp = OTP.objects.filter(user=user, code=code).order_by("-created_at").first()
                if not otp:
                    messages.error(request, "Invalid code")
                    return redirect("verify_otp")
                if otp.is_expired():
                    messages.error(request, "Code expired")
                    return redirect("login_phone")
                # Confirm the extra guest
                extra.is_confirmed = True
                extra.save()
                # Optionally, mark main guest as confirmed if you want
                # user.is_confirmed = True
                # user.save()
            else:
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
            # Set is_admin flag in session if phone is in ADMIN_PHONES
            request.session["is_admin"] = user.phone_number in ADMIN_PHONES
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
