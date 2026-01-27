from django import forms

class PhoneForm(forms.Form):
    phone = forms.CharField(label="Telefone")

class OTPForm(forms.Form):
    code = forms.CharField(label="Código")
