from django.urls import path
from .views import login_phone, verify_otp, logout

urlpatterns = [
    path("login/", login_phone, name="login_phone"),
    path("verify/", verify_otp, name="verify_otp"),
    path("logout/", logout, name="logout"),
]
