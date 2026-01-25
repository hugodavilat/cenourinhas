#!/usr/bin/env python
"""
test_mercadopago.py - Testa a integração com Mercado Pago

Use: python manage.py shell < test_mercadopago.py
"""

import os
from django.conf import settings

print("=" * 70)
print("🔍 TESTE DE INTEGRAÇÃO - MERCADO PAGO")
print("=" * 70)
print()

# 1. Verificar token
print("1️⃣  Verificando Access Token:")
token = settings.MERCADO_PAGO_ACCESS_TOKEN
if token:
    print(f"   ✅ Token encontrado: {token[:20]}...{token[-10:]}")
else:
    print("   ❌ Token NÃO encontrado!")
print()

# 2. Verificar import do SDK
print("2️⃣  Verificando SDK Mercado Pago:")
try:
    import mercadopago
    print("   ✅ SDK importado com sucesso")
except ImportError as e:
    print(f"   ❌ Erro ao importar SDK: {e}")
print()

# 3. Tentar inicializar SDK
print("3️⃣  Inicializando SDK:")
try:
    import mercadopago
    sdk = mercadopago.SDK(token)
    print("   ✅ SDK inicializado com sucesso")
except Exception as e:
    print(f"   ❌ Erro ao inicializar SDK: {e}")
    import traceback
    traceback.print_exc()
print()

# 4. Testar criação de preference
print("4️⃣  Testando criação de preference:")
try:
    import mercadopago
    sdk = mercadopago.SDK(token)
    
    preference_data = {
        "items": [
            {
                "title": "Teste - Serviço de Fotografia",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": 100.00
            }
        ],
        "external_reference": "test_123",
        "back_urls": {
            "success": "http://localhost:8000/pagamento/sucesso/",
            "failure": "http://localhost:8000/pagamento/erro/",
            "pending": "http://localhost:8000/pagamento/pendente/",
        },
        "notification_url": "http://localhost:8000/webhook/mercadopago/",
    }
    
    preference = sdk.preference().create(preference_data)
    
    if preference.get("status") == 201:
        print("   ✅ Preference criada com sucesso!")
        init_point = preference.get("response", {}).get("init_point")
        if init_point:
            print(f"   ✅ Init point: {init_point}")
        else:
            print("   ⚠️  Init point não encontrado")
    else:
        print(f"   ❌ Status: {preference.get('status')}")
        print(f"   ❌ Response: {preference.get('response')}")
        
except Exception as e:
    print(f"   ❌ Erro ao criar preference: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
print("✅ Teste concluído!")
print("=" * 70)
