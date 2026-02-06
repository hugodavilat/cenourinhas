
from django.db import models
from django.db.models import JSONField

# Modelo para armazenar contexto de conversas do assistente virtual
class ConversationMessage(models.Model):
	jid = models.CharField(max_length=64, help_text="WhatsApp JID, e.g. 115831006589136@lid or 5511999999999@s.whatsapp.net")
	messages = JSONField(default=list, blank=True, help_text="List of conversation messages")

# Create your models here.
