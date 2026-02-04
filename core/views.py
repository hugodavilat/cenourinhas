import mercadopago
import requests
import json

from google import genai
from otp.services import send_whatsapp_message

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.urls import reverse

from .forms import WhatsAppMessageForm, PresenteForm, PagamentoForm, GuestForm, ExtraGuestForm
from .models import Presente, Pagamento, Guest, ExtraGuest, ConversationMessage
from .decorators import guest_required, wedding_admin_required
from .context import ASSISTANT_CONTEXT



# Simple conversation context storage (in-memory, replace with DB for production)
conversation_context = {}

@csrf_exempt
@require_POST
def whatsapp_gemini_api(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        jid = data.get('jid')
        message = data.get('message')
        if not jid or not message:
            return JsonResponse({'error': 'Missing jid or message'}, status=400)

        # Recupera ou cria contexto
        context = ConversationMessage.objects.filter(jid=jid).first()
        if not context:
            context = ConversationMessage.objects.create(jid=jid, messages=[])
        messages_list = context.messages or []

        # Mantém só as últimas 20 mensagens
        if len(messages_list) > 20:
            messages_list = messages_list[-20:]

        # Adiciona mensagem do usuário
        messages_list.append(ASSISTANT_CONTEXT.format(
            conversation_context="\n".join(messages_list),
            user_message=message
        ))

        # Chama Gemini
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=messages_list,
                config=genai.types.GenerateContentConfig(
                    temperature=0.4,
                    top_p=0.95,
                    top_k=20,
                ),
            )
            ai_message = response.candidates[0].content.parts[0].text
        except Exception as e:
            print(f"Erro ao chamar Gemini API: {str(e)}")
            return JsonResponse({'error': 'Failed to connect to Gemini API'}, status=500)

        # Adiciona mensagem do usuário e da IA ao contexto
        messages_list.append(message)
        messages_list.append(ai_message)
        # Mantém só as últimas 20 mensagens
        if len(messages_list) > 20:
            messages_list = messages_list[-20:]
        context.messages = messages_list
        context.save()

        # Envia resposta via WhatsApp
        try:
            print("Sending WhatsApp message to", jid)
            print("Message content:", ai_message)
            send_whatsapp_message_to_jid(jid, ai_message)
        except Exception as exc:
            print(f"Failed to send WhatsApp message to {jid}: {exc}")

        return JsonResponse({'reply': ai_message})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# New helper to send message to JID
def send_whatsapp_message_to_jid(jid, message):
    url = settings.WHATSAPP_SERVER_URL
    payload = {"jid": jid, "message": message}
    try:
        r = requests.post(url + "/send_jid_message", json=payload, timeout=15)
        r.raise_for_status()
        return True
    except requests.exceptions.RequestException as exc:
        print(f"Failed sending message to JID {jid}: {exc}")
        return False

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

@guest_required
def confirmacao_familia(request):
    from .models import ExtraGuest
    user_id = request.session.get("otp_user_id")
    is_extra = request.session.get("is_extra_guest_login", False)
    extra_guest_phone = request.session.get("extra_guest_phone")

    if is_extra and extra_guest_phone:
        main_guest = Guest.objects.get(id=user_id)
        extra_guest = ExtraGuest.objects.get(phone_number=extra_guest_phone, main_guest=main_guest)
    else:
        main_guest = Guest.objects.get(id=user_id)
        extra_guest = None

    # Sempre busca o estado atualizado do banco
    main_guest.refresh_from_db()
    extras = main_guest.extra_guests.all()
    msg = None
    success = False
    if request.method == "POST":
        updated = False
        # Principal
        if f"confirm_{main_guest.id}" in request.POST:
            confirm = request.POST.get(f"confirm_{main_guest.id}") == "1"
            if confirm:
                main_guest.is_confirmed = True
                main_guest.is_rejected = False
                main_guest.not_answered = False
                msg = f"Presença de {main_guest.name} confirmada!"
            else:
                main_guest.is_confirmed = False
                main_guest.is_rejected = True
                main_guest.not_answered = False
                msg = f"Presença de {main_guest.name} rejeitada!"
            main_guest.save()
            updated = True
        # Extras
        for extra in extras:
            if f"confirm_extra_{extra.id}" in request.POST:
                confirm = request.POST.get(f"confirm_extra_{extra.id}") == "1"
                if confirm:
                    extra.is_confirmed = True
                    extra.is_rejected = False
                    extra.not_answered = False
                    msg = f"Presença de {extra.name} confirmada!"
                else:
                    extra.is_confirmed = False
                    extra.is_rejected = True
                    extra.not_answered = False
                    msg = f"Presença de {extra.name} rejeitada!"
                extra.save()
                updated = True
        if updated:
            success = True
        # Atualiza os objetos após salvar
        main_guest.refresh_from_db()
        extras = main_guest.extra_guests.all()
    return render(request, "confirmacao_familia.html", {"main_guest": main_guest, "extras": extras, "success": success, "msg": msg})

# Admin dashboard view
@wedding_admin_required
def wedding_admin_dashboard(request):
    presentes = Presente.objects.all()
    pagamentos = Pagamento.objects.select_related('presente').all()
    guests = Guest.objects.all()
    return render(request, 'admin_dashboard.html', {
        'presentes': presentes,
        'pagamentos': pagamentos,
        'guests': guests,
    })

# CRUD for Presente
@wedding_admin_required
def admin_add_presente(request):
    if request.method == 'POST':
        form = PresenteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('wedding_admin')
    else:
        form = PresenteForm()
    return render(request, 'admin/form.html', {'form': form, 'title': 'Adicionar Presente'})

@wedding_admin_required
def admin_edit_presente(request, pk):
    presente = get_object_or_404(Presente, pk=pk)
    if request.method == 'POST':
        form = PresenteForm(request.POST, instance=presente)
        if form.is_valid():
            form.save()
            return redirect('wedding_admin')
    else:
        form = PresenteForm(instance=presente)
    return render(request, 'admin/form.html', {'form': form, 'title': 'Editar Presente'})

@wedding_admin_required
def admin_delete_presente(request, pk):
    presente = get_object_or_404(Presente, pk=pk)
    if request.method == 'POST':
        presente.delete()
        return redirect('wedding_admin')
    return render(request, 'admin/confirm_delete.html', {'object': presente, 'type': 'Presente'})

# CRUD for Pagamento (edit/delete only)
@wedding_admin_required
def admin_edit_pagamento(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    if request.method == 'POST':
        form = PagamentoForm(request.POST, instance=pagamento)
        if form.is_valid():
            form.save()
            return redirect('wedding_admin')
    else:
        form = PagamentoForm(instance=pagamento)
    return render(request, 'admin/form.html', {'form': form, 'title': 'Editar Pagamento'})

@wedding_admin_required
def admin_delete_pagamento(request, pk):
    pagamento = get_object_or_404(Pagamento, pk=pk)
    if request.method == 'POST':
        pagamento.delete()
        return redirect('wedding_admin')
    return render(request, 'admin/confirm_delete.html', {'object': pagamento, 'type': 'Pagamento'})

# CRUD for Guest
@wedding_admin_required
def admin_add_guest(request):
    if request.method == 'POST':
        form = GuestForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('wedding_admin')
    else:
        form = GuestForm()
    return render(request, 'admin/form.html', {'form': form, 'title': 'Adicionar Convidado'})

@wedding_admin_required
def admin_edit_guest(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    if request.method == 'POST':
        form = GuestForm(request.POST, instance=guest)
        if form.is_valid():
            form.save()
            return redirect('wedding_admin')
    else:
        form = GuestForm(instance=guest)
    return render(request, 'admin/form.html', {'form': form, 'title': 'Editar Convidado'})

@wedding_admin_required
def admin_delete_guest(request, pk):
    guest = get_object_or_404(Guest, pk=pk)
    if request.method == 'POST':
        guest.delete()
        return redirect('wedding_admin')
    return render(request, 'admin/confirm_delete.html', {'object': guest, 'type': 'Convidado'})

# CRUD for ExtraGuest
@wedding_admin_required
def admin_add_extra_guest(request, main_guest_id):
    main_guest = get_object_or_404(Guest, pk=main_guest_id)
    if request.method == 'POST':
        form = ExtraGuestForm(request.POST)
        if form.is_valid():
            extra = form.save(commit=False)
            extra.main_guest = main_guest
            extra.save()
            return redirect('admin_edit_guest', pk=main_guest.id)
    else:
        form = ExtraGuestForm()
    return render(request, 'admin/form.html', {'form': form, 'title': f'Adicionar Extra para {main_guest.name}'})

@wedding_admin_required
def admin_edit_extra_guest(request, pk):
    extra = get_object_or_404(ExtraGuest, pk=pk)
    if request.method == 'POST':
        form = ExtraGuestForm(request.POST, instance=extra)
        if form.is_valid():
            form.save()
            return redirect('admin_edit_guest', pk=extra.main_guest.id)
    else:
        form = ExtraGuestForm(instance=extra)
    return render(request, 'admin/form.html', {'form': form, 'title': f'Editar Extra de {extra.main_guest.name}'})

@wedding_admin_required
def admin_delete_extra_guest(request, pk):
    extra = get_object_or_404(ExtraGuest, pk=pk)
    main_guest_id = extra.main_guest.id
    if request.method == 'POST':
        extra.delete()
        return redirect('admin_edit_guest', pk=main_guest_id)
    return render(request, 'admin/confirm_delete.html', {'object': extra, 'type': 'Convidado Extra'})

@wedding_admin_required
def send_whatsapp_mass(request):
    selected_status = request.POST.get("status", request.GET.get("status", "all"))
    selected_guests = request.POST.getlist("selected_guests") if request.method == "POST" else []

    # Filter guests by status
    # Filtra apenas convidados com telefone preenchido
    guests = Guest.objects.exclude(phone_number__isnull=True).exclude(phone_number="")
    if selected_status == "confirmed":
        guests = guests.filter(is_confirmed=True)
    elif selected_status == "not_answered":
        guests = guests.filter(not_answered=True)
    elif selected_status == "rejected":
        guests = guests.filter(is_rejected=True)

    # Get ExtraGuests with phone numbers
    extra_guests = ExtraGuest.objects.exclude(phone_number__isnull=True).exclude(phone_number="")
    # Optionally filter extra guests by status
    if selected_status == "confirmed":
        extra_guests = extra_guests.filter(is_confirmed=True)
    elif selected_status == "not_answered":
        extra_guests = extra_guests.filter(not_answered=True)
    elif selected_status == "rejected":
        extra_guests = extra_guests.filter(is_rejected=True)

    # Combine guests and extra_guests into a single list
    all_guests = list(guests) + list(extra_guests)

    if request.method == "POST":
        form = WhatsAppMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message_template = form.cleaned_data["message"]
            image = form.cleaned_data.get("image")

            # Only send to selected guests
            selected_ids = set(int(gid) for gid in selected_guests)
            guests_to_send = [g for g in all_guests if g.id in selected_ids and getattr(g, "phone_number", None)] if selected_guests else [g for g in all_guests if getattr(g, "phone_number", None)]
            errors = []
            sent_guests = []
            if not guests_to_send:
                messages.error(request, "Nenhum convidado válido com telefone selecionado para envio.")
                return redirect(reverse("send_whatsapp_mass"))
            for guest in guests_to_send:
                phone = getattr(guest, "phone_number", None)
                name = getattr(guest, "name", str(guest))
                # Replace {{name}} in message template
                message = message_template.replace("{{name}}", name)
                try:
                    success = send_whatsapp_message(phone, message, image)
                except Exception as exc:
                    success = False
                if success:
                    sent_guests.append(guest)
                else:
                    errors.append(f"{name} ({phone})")
            if sent_guests:
                return render(request, "admin/whatsapp_feedback.html", {
                    "sent_guests": sent_guests
                })
            else:
                messages.error(request, f"Falha ao enviar para: {', '.join(errors)}")
                return redirect(reverse("send_whatsapp_mass"))
    else:
        form = WhatsAppMessageForm(initial={"status": selected_status})

    return render(request, "admin/send_whatsapp.html", {
        "form": form,
        "guests": all_guests,
        "selected_status": selected_status,
        "selected_guests": [int(gid) for gid in selected_guests],
    })