import mercadopago
from django.conf import settings

def get_sdk():
    """Obter SDK do Mercado Pago com token carregado"""
    token = settings.MERCADO_PAGO_ACCESS_TOKEN
    if not token:
        raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não está configurado")
    return mercadopago.SDK(token)
