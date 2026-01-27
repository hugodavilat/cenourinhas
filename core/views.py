from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import mercadopago

from .models import Presente, Pagamento
from .decorators import guest_required


def get_sdk():
    """Obter SDK do Mercado Pago com token carregado"""
    token = settings.MERCADO_PAGO_ACCESS_TOKEN
    if not token:
        raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não está configurado")
    return mercadopago.SDK(token)


@guest_required
def home(request):
    """Render the wedding homepage for Aline and Hugo."""
    context = {
        'bride': 'Aline',
        'groom': 'Hugo',
        'wedding_date': 'Data a confirmar',
        'venue': 'Local a confirmar',
        'address': '',
        'message': 'Estamos preparando uma celebração especial — mais informações em breve.'
    }
    return render(request, 'index.html', context)


@guest_required
def presente(request):
    """Render the gift registry page."""
    presentes = Presente.objects.all()
    context = {
        'presentes': presentes,
        'message': 'Ajude esse casal que ama presentes! 💝'
    }
    return render(request, 'presente.html', context)


@guest_required
def iniciar_pagamento(request, presente_id):
    """
    Inicia o processo de pagamento criando uma preferência no Mercado Pago
    """
    presente = get_object_or_404(Presente, id=presente_id)
    
    # Verificar se token está configurado
    if not settings.MERCADO_PAGO_ACCESS_TOKEN:
        return render(request, 'pagamento/erro.html', {
            'mensagem': 'Access Token do Mercado Pago não está configurado. Verifique o arquivo .env'
        })
    
    # Criar registro de pagamento pendente
    pagamento = Pagamento.objects.create(
        presente=presente,
        valor=presente.valor
    )

    # Preparar dados da preference
    preference_data = {
        "items": [
            {
                "title": presente.nome,
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(presente.valor)
            }
        ],
        "external_reference": str(pagamento.id),
        "back_urls": {
            "success": f"{settings.SITE_URL}/pagamento/sucesso/",
            "failure": f"{settings.SITE_URL}/pagamento/erro/",
            "pending": f"{settings.SITE_URL}/pagamento/pendente/",
        },
        "notification_url": f"{settings.SITE_URL}/webhook/mercadopago/",
    }

    try:
        # Criar preference no Mercado Pago
        sdk = get_sdk()
        preference = sdk.preference().create(preference_data)
        
        # Verificar resposta
        if preference.get("status") == 201 and preference.get("response"):
            init_point = preference["response"].get("init_point")
            if init_point:
                return redirect(init_point)
            else:
                return render(request, 'pagamento/erro.html', {
                    'mensagem': 'Erro: Checkout URL não retornada pelo Mercado Pago'
                })
        else:
            error_msg = preference.get("response", {}).get("message", "Erro ao criar preferência")
            return render(request, 'pagamento/erro.html', {
                'mensagem': f'Erro: {error_msg}'
            })
    except Exception as e:
        import traceback
        print(f"Erro em iniciar_pagamento: {str(e)}")
        print(traceback.format_exc())
        return render(request, 'pagamento/erro.html', {
            'mensagem': f'Erro ao conectar com Mercado Pago: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook_mercadopago(request):
    """
    Webhook para receber notificações de pagamento do Mercado Pago
    """
    try:
        # Mercado Pago envia dados via GET ou POST
        data = request.GET if request.method == "GET" else request.POST
        
        payment_id = data.get("id")
        topic = data.get("topic")

        # Verificar se é notificação de pagamento
        if topic == "payment" and payment_id:
            try:
                # Obter informações do pagamento no Mercado Pago
                sdk = get_sdk()
                payment_info = sdk.payment().get(payment_id)
                info = payment_info["response"]

                # Extrair informações relevantes
                external_reference = info.get("external_reference")
                status = info.get("status")

                # Mapear status do Mercado Pago para nosso status
                status_map = {
                    'pending': 'pendente',
                    'approved': 'aprovado',
                    'authorized': 'aprovado',
                    'in_process': 'pendente',
                    'in_mediation': 'pendente',
                    'rejected': 'recusado',
                    'cancelled': 'cancelado',
                    'refunded': 'cancelado',
                    'charged_back': 'cancelado',
                }
                
                novo_status = status_map.get(status, 'pendente')

                # Atualizar pagamento no banco
                if external_reference:
                    try:
                        pagamento = Pagamento.objects.get(id=external_reference)
                        pagamento.mp_payment_id = payment_id
                        pagamento.status = novo_status
                        pagamento.save()
                    except Pagamento.DoesNotExist:
                        pass
            except Exception as e:
                print(f"Erro ao processar webhook: {str(e)}")

        return HttpResponse("OK", status=200)
    
    except Exception as e:
        print(f"Erro no webhook: {str(e)}")
        return HttpResponse("OK", status=200)


@guest_required
def pagamento_sucesso(request):
    """Página de sucesso após pagamento"""
    payment_id = request.GET.get('payment_id')
    context = {
        'titulo': 'Pagamento Realizado com Sucesso!',
        'mensagem': 'Obrigado pelo seu presente! Estamos muito felizes! 💝',
        'payment_id': payment_id
    }
    return render(request, 'pagamento/sucesso.html', context)


@guest_required
def pagamento_erro(request):
    """Página de erro após pagamento"""
    context = {
        'titulo': 'Erro no Pagamento',
        'mensagem': 'Ocorreu um erro ao processar seu pagamento. Tente novamente.'
    }
    return render(request, 'pagamento/erro.html', context)


@guest_required
def pagamento_pendente(request):
    """Página de pagamento pendente"""
    context = {
        'titulo': 'Pagamento Pendente',
        'mensagem': 'Seu pagamento está sendo processado. Você receberá uma confirmação em breve.'
    }
    return render(request, 'pagamento/pendente.html', context)