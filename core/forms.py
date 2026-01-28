from django import forms
from .models import Presente, Pagamento, Guest, ExtraGuest

class PresenteForm(forms.ModelForm):
    class Meta:
        model = Presente
        fields = ['nome', 'descricao', 'valor', 'imagem_url']

class PagamentoForm(forms.ModelForm):
    class Meta:
        model = Pagamento
        fields = ['presente', 'valor', 'status', 'nome_pagador', 'email_pagador']

class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = ['name', 'phone_number', 'is_confirmed', 'message_sent', 'active_session_key', 'active_until']

class ExtraGuestForm(forms.ModelForm):
    class Meta:
        model = ExtraGuest
        fields = ['name', 'phone_number', 'is_confirmed']

class WhatsAppMessageForm(forms.Form):
    message = forms.CharField(widget=forms.Textarea, required=True, label="Mensagem WhatsApp")
    image = forms.ImageField(required=False, label="Imagem (opcional)")
