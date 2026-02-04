from django.db import models
from django.db.models import JSONField

class Presente(models.Model):
    nome = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    imagem_url = models.URLField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Presente"
        verbose_name_plural = "Presentes"


class Pagamento(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('aprovado', 'Aprovado'),
        ('recusado', 'Recusado'),
        ('cancelado', 'Cancelado'),
    ]

    presente = models.ForeignKey(Presente, on_delete=models.CASCADE, related_name='pagamentos')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    mp_payment_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    status = models.CharField(max_length=50, default='pendente', choices=STATUS_CHOICES)
    nome_pagador = models.CharField(max_length=255, blank=True, null=True)
    email_pagador = models.EmailField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pagamento {self.id} - {self.presente.nome} - {self.status}"

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ['-criado_em']

class Guest(models.Model):
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    jid = models.CharField(max_length=64, unique=True, blank=True, null=True, help_text="WhatsApp JID, e.g. 115831006589136@lid or 5511999999999@s.whatsapp.net")
    is_confirmed = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    not_answered = models.BooleanField(default=True)
    message_sent = models.BooleanField(default=False)
    # Track the session key currently associated with this guest (one active session)
    active_session_key = models.CharField(max_length=40, null=True, blank=True)
    # When the active session expires; used to allow new logins after timeout
    active_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


# Extra guests attached to a main guest
class ExtraGuest(models.Model):
    main_guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name='extra_guests')
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    jid = models.CharField(max_length=64, unique=True, blank=True, null=True, help_text="WhatsApp JID, e.g. 115831006589136@lid or 5511999999999@s.whatsapp.net")
    is_confirmed = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    not_answered = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (Extra of {self.main_guest.name})"


class ConversationMessage(models.Model):
    jid = models.CharField(max_length=64, help_text="WhatsApp JID, e.g. 115831006589136@lid or 5511999999999@s.whatsapp.net")
    messages = JSONField(default=list, blank=True, help_text="List of conversation messages")
