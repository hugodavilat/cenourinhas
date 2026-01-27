from django.db import models
from core.models import Guest
from django.utils import timezone
from datetime import timedelta
import random

class OTP(models.Model):
    user = models.ForeignKey(Guest, on_delete=models.CASCADE)
    code = models.CharField(max_length=5)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    @staticmethod
    def generate_code():
        return str(random.randint(10000, 99999))

    def is_expired(self):
        return timezone.now() > self.expires_at
