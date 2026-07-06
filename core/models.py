from django.db import models
from django.db.models import JSONField

DAY_STATUS_CHOICES = [
    ('pending', 'Pendente'),
    ('confirmed', 'Confirmado'),
    ('rejected', 'Rejeitado'),
]

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

    presente = models.ForeignKey(Presente, on_delete=models.CASCADE, related_name='pagamentos', null=True, blank=True)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    # Link to the guest who initiated the payment (optional)
    guest = models.ForeignKey('Guest', on_delete=models.SET_NULL, null=True, blank=True, related_name='pagamentos')
    # Optional message provided by the guest when giving the present
    message = models.TextField(blank=True, null=True)
    mp_payment_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    status = models.CharField(max_length=50, default='pendente', choices=STATUS_CHOICES)
    nome_pagador = models.CharField(max_length=255, blank=True, null=True)
    email_pagador = models.EmailField(blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        nome_do_present = self.presente.nome if self.presente else "Contribuição Personalizada"
        id_do_pagamento = self.id if self.id else "Personalizado"
        return f"Pagamento {id_do_pagamento} - {nome_do_present} - {self.status}"

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ['-criado_em']

class Guest(models.Model):
    name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    jid = models.CharField(max_length=64, unique=True, blank=True, null=True, help_text="WhatsApp JID, e.g. 115831006589136@lid or 5511999999999@s.whatsapp.net")
    day1_status = models.CharField(max_length=10, choices=DAY_STATUS_CHOICES, default='pending')
    day2_status = models.CharField(max_length=10, choices=DAY_STATUS_CHOICES, default='pending')
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
    day1_status = models.CharField(max_length=10, choices=DAY_STATUS_CHOICES, default='pending')
    day2_status = models.CharField(max_length=10, choices=DAY_STATUS_CHOICES, default='pending')
    is_confirmed = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    not_answered = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} (Extra of {self.main_guest.name})"


class SiteContent(models.Model):
    """Singleton model for admin-editable site content."""

    otp_page_photo = models.ImageField(upload_to='site_content/', blank=True, null=True)
    hero_photo = models.ImageField(upload_to='site_content/', blank=True, null=True)
    hero_text = models.TextField(default="Quase um carnaval fora de época. Estamos preparando uma comemoração inesquecível e contamos com você!")

    cenourinhas_title = models.CharField(max_length=255, default='Por que "Cenourinhas"?')
    cenourinhas_text = models.TextField(default='Muitos perguntam: "Por que vocês se chamam de Cenourinhas?" Tudo começou com o nosso lema oficial em cada treino de corrida: To Bem Não...')
    cenourinhas_photo = models.ImageField(upload_to='site_content/', blank=True, null=True)

    sobre_title = models.CharField(max_length=255, default='Sobre o Casal')
    sobre_subtitle = models.CharField(max_length=255, default='Duas metades que se completam')
    sobre_text = models.TextField(default='Ela é uma paulista raiz, dona de uma tatuagem do Banespa no braço e apaixonada por prédios antigos e corridas no asfalto. Ele é tricolor doente pelo Fluminense, fã de moqueca, do mar e de correr com o pé na areia.')

    jornada_title = models.CharField(max_length=255, default='Nossa Jornada')
    jornada_text = models.TextField(default='Um encontro casual no Tinder que virou uma linda história: em pouco tempo já dividíamos o mesmo teto e as aventuras pelo Brasil.')
    jornada_photo = models.ImageField(upload_to='site_content/', blank=True, null=True)

    assistant_context = models.TextField(blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conteúdo do Site"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


