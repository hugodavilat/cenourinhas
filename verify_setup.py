#!/usr/bin/env python
"""
verify_setup.py - Verificador de Integridade da Integração Mercado Pago

Use: python verify_setup.py

Este script verifica se tudo foi configurado corretamente.
"""

import os
import sys
from pathlib import Path

def check_file_exists(path, name):
    """Verifica se um arquivo existe"""
    if os.path.exists(path):
        print(f"✅ {name}")
        return True
    else:
        print(f"❌ {name} - FALTANDO")
        return False

def check_env_variable(var_name):
    """Verifica se uma variável de ambiente está configurada"""
    if os.getenv(var_name):
        value = os.getenv(var_name)
        # Mascara a maioria do token para segurança
        if len(value) > 20:
            masked = value[:10] + "..." + value[-10:]
        else:
            masked = value
        print(f"✅ {var_name} = {masked}")
        return True
    else:
        print(f"❌ {var_name} - NÃO CONFIGURADO")
        return False

def check_import(module_name, display_name=None):
    """Verifica se um módulo pode ser importado"""
    if display_name is None:
        display_name = module_name
    try:
        __import__(module_name)
        print(f"✅ {display_name} importável")
        return True
    except ImportError:
        print(f"❌ {display_name} - INSTALE: pip install {module_name}")
        return False

def main():
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║        🔍 VERIFICADOR DE INTEGRAÇÃO MERCADO PAGO              ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")
    
    checks = []
    
    # 1. Verificar arquivos
    print("📁 ARQUIVOS NECESSÁRIOS:")
    checks.append(check_file_exists(".env", ".env com token"))
    checks.append(check_file_exists("core/models.py", "Models"))
    checks.append(check_file_exists("core/views.py", "Views"))
    checks.append(check_file_exists("core/admin.py", "Admin"))
    checks.append(check_file_exists("requirements.txt", "requirements.txt"))
    print()
    
    # 2. Verificar variáveis de ambiente
    print("🔐 VARIÁVEIS DE AMBIENTE:")
    # Carregar .env
    if os.path.exists(".env"):
        from dotenv import load_dotenv
        load_dotenv()
    checks.append(check_env_variable("MP_ACCESS_TOKEN"))
    print()
    
    # 3. Verificar imports
    print("📦 DEPENDÊNCIAS INSTALADAS:")
    checks.append(check_import("django", "Django"))
    checks.append(check_import("mercadopago", "Mercado Pago SDK"))
    checks.append(check_import("dotenv", "python-dotenv"))
    print()
    
    # 4. Verificar conteúdo dos arquivos
    print("✔️  CONTEÚDO DOS ARQUIVOS:")
    
    # Verificar se models.py tem Presente e Pagamento
    try:
        with open("core/models.py", "r") as f:
            models_content = f.read()
            if "class Presente" in models_content:
                print("✅ Model Presente definido")
                checks.append(True)
            else:
                print("❌ Model Presente NÃO encontrado")
                checks.append(False)
            
            if "class Pagamento" in models_content:
                print("✅ Model Pagamento definido")
                checks.append(True)
            else:
                print("❌ Model Pagamento NÃO encontrado")
                checks.append(False)
    except Exception as e:
        print(f"❌ Erro ao ler models.py: {e}")
        checks.append(False)
    
    # Verificar se views.py tem webhook
    try:
        with open("core/views.py", "r") as f:
            views_content = f.read()
            if "webhook_mercadopago" in views_content:
                print("✅ View webhook_mercadopago definida")
                checks.append(True)
            else:
                print("❌ View webhook_mercadopago NÃO encontrada")
                checks.append(False)
            
            if "mercadopago.SDK" in views_content:
                print("✅ SDK Mercado Pago importado")
                checks.append(True)
            else:
                print("❌ SDK Mercado Pago NÃO importado")
                checks.append(False)
    except Exception as e:
        print(f"❌ Erro ao ler views.py: {e}")
        checks.append(False)
    
    # Verificar urls.py
    try:
        with open("core/urls.py", "r") as f:
            urls_content = f.read()
            if "webhook" in urls_content:
                print("✅ Rota webhook configurada")
                checks.append(True)
            else:
                print("❌ Rota webhook NÃO encontrada")
                checks.append(False)
    except Exception as e:
        print(f"❌ Erro ao ler urls.py: {e}")
        checks.append(False)
    
    print()
    
    # 5. Verificar templates
    print("🎨 TEMPLATES:")
    checks.append(check_file_exists("templates/presente.html", "presente.html"))
    checks.append(check_file_exists("templates/pagamento/sucesso.html", "sucesso.html"))
    checks.append(check_file_exists("templates/pagamento/erro.html", "erro.html"))
    checks.append(check_file_exists("templates/pagamento/pendente.html", "pendente.html"))
    print()
    
    # 6. Resumo
    total = len(checks)
    passed = sum(checks)
    percentage = (passed / total) * 100 if total > 0 else 0
    
    print("═" * 64)
    print(f"📊 RESULTADO: {passed}/{total} verificações passaram ({percentage:.1f}%)")
    print("═" * 64)
    
    if percentage == 100:
        print("\n✨ TUDO ESTÁ OK! Você está pronto para começar!\n")
        print("Próximos passos:")
        print("  1. python manage.py migrate")
        print("  2. python manage.py createsuperuser")
        print("  3. python manage.py shell < seed_presentes.py")
        print("  4. python manage.py runserver")
        return 0
    elif percentage >= 80:
        print("\n⚠️  QUASE LÁ! Faltam pequenos ajustes.\n")
        return 1
    else:
        print("\n❌ PROBLEMAS ENCONTRADOS! Veja acima para detalhes.\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
