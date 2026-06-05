from django import forms
from .models import Presente, Pagamento, Guest, ExtraGuest, SiteContent

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


class SiteContentForm(forms.ModelForm):
    class Meta:
        model = SiteContent
        fields = [
            'otp_page_photo', 'hero_photo', 'hero_text',
            'cenourinhas_title', 'cenourinhas_text', 'cenourinhas_photo',
            'sobre_title', 'sobre_subtitle', 'sobre_text',
            'jornada_title', 'jornada_text', 'jornada_photo',
            'assistant_context',
        ]
        widgets = {
            'hero_text': forms.Textarea(attrs={'rows': 3}),
            'cenourinhas_text': forms.Textarea(attrs={'rows': 5}),
            'sobre_text': forms.Textarea(attrs={'rows': 5}),
            'jornada_text': forms.Textarea(attrs={'rows': 5}),
            'assistant_context': forms.Textarea(attrs={'rows': 8}),
        }
