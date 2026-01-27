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
            phone = form.cleaned_data["phone"]

            try:
                user = Guest.objects.get(phone_number=phone)
            except Guest.DoesNotExist:
                messages.error(request, "Phone not found")
                return redirect("login_phone")

            # Generate OTP
            code = OTP.generate_code()

            OTP.objects.create(
                user=user,
                code=code,
                expires_at=timezone.now() + timedelta(minutes=5)
            )

            # Send via WhatsApp
            send_whatsapp_otp(phone, code)

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
            user.save()
            request.session["guest_authenticated"] = True
            return redirect("home")

    return render(request, "otp/verify_otp.html", {"form": OTPForm()})
