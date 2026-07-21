import logging
import mercadopago
import threading
import time
from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.utils import timezone
from assistant.ai import whatsapp_gemini_api
from otp.services import send_whatsapp_message

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.db.models import Q
from core.mercadopago_sdk import get_sdk
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.urls import reverse

from .forms import WhatsAppMessageForm, PresenteForm, PagamentoForm, GuestForm, ExtraGuestForm, SiteContentForm
from .models import Presente, Pagamento, Guest, ExtraGuest, SiteContent
from .decorators import guest_required, wedding_admin_required
from .models import WhatsAppBatch, WhatsAppBatchItem


def get_sdk():
    """Obter SDK do Mercado Pago com token carregado"""
    token = settings.MERCADO_PAGO_ACCESS_TOKEN
    if not token:
        raise ValueError("MERCADO_PAGO_ACCESS_TOKEN não está configurado")
    return mercadopago.SDK(token)


@guest_required
def home(request):
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

        def _save_rsvp_person(person, day, action, person_name):
            status_field = f"day{day}_status"
            setattr(person, status_field, 'confirmed' if action == 'confirmed' else 'rejected')
            person.is_confirmed = person.day1_status == 'confirmed' and person.day2_status == 'confirmed'
            person.is_rejected = person.day1_status == 'rejected' and person.day2_status == 'rejected'
            person.not_answered = person.day1_status == 'pending' and person.day2_status == 'pending'
            person.save()
            return f"Presença de {person_name} no dia {day} {'confirmada' if action == 'confirmed' else 'rejeitada'}!"

        # Principal
        if f"day1_guest_{main_guest.id}" in request.POST:
            action = request.POST.get(f"day1_guest_{main_guest.id}")
            msg = _save_rsvp_person(main_guest, 1, action, main_guest.name)
            updated = True
        elif f"day2_guest_{main_guest.id}" in request.POST:
            action = request.POST.get(f"day2_guest_{main_guest.id}")
            msg = _save_rsvp_person(main_guest, 2, action, main_guest.name)
            updated = True

        # Extras
        for extra in extras:
            if f"day1_extra_{extra.id}" in request.POST:
                action = request.POST.get(f"day1_extra_{extra.id}")
                msg = _save_rsvp_person(extra, 1, action, extra.name)
                updated = True
            elif f"day2_extra_{extra.id}" in request.POST:
                action = request.POST.get(f"day2_extra_{extra.id}")
                msg = _save_rsvp_person(extra, 2, action, extra.name)
                updated = True

        if updated:
            success = True
        # Atualiza os objetos após salvar
        main_guest.refresh_from_db()
        extras = main_guest.extra_guests.all()

    presentes = Presente.objects.all()
    site_content = SiteContent.load()
    context = {
        'main_guest': main_guest,
        'extras': extras,
        'success': success,
        'msg': msg,
        'presentes': presentes,
        'site_content': site_content,
        'bride': 'Aline',
        'groom': 'Hugo',
        'wedding_date': '10 e 11 de outubro de 2026',
        'venue': 'Quintal Pra Festas / Templo Cervejeiro',
        'address': '',
        'message': 'Estamos preparando uma celebração especial — mais informações abaixo.'
    }

    # For fetch-based RSVP submissions, return only the RSVP section so the
    # client can swap it in place without a full-page reload (which was
    # scrolling the user to the top and back down to the RSVP section).
    if request.method == "POST" and request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, 'partials/_rsvp.html', context)

    return render(request, 'index.html', context)


@wedding_admin_required
def admin_edit_content(request):
    content = SiteContent.load()
    if request.method == 'POST':
        form = SiteContentForm(request.POST, request.FILES, instance=content)

        # Handle remove checkboxes for images
        if form.is_valid():
            # If admin requested removal of images, clear them before saving
            if request.POST.get('remove_hero_photo') == '1' and content.hero_photo:
                content.hero_photo.delete(save=False)
                content.hero_photo = None
            if request.POST.get('remove_cenourinhas_photo') == '1' and content.cenourinhas_photo:
                content.cenourinhas_photo.delete(save=False)
                content.cenourinhas_photo = None
            if request.POST.get('remove_jornada_photo') == '1' and content.jornada_photo:
                content.jornada_photo.delete(save=False)
                content.jornada_photo = None
            if request.POST.get('remove_otp_page_photo') == '1' and content.otp_page_photo:
                content.otp_page_photo.delete(save=False)
                content.otp_page_photo = None

            form.save()
            messages.success(request, 'Conteúdo salvo com sucesso.')
            return redirect('admin_edit_content')
    else:
        form = SiteContentForm(instance=content)
    return render(request, 'admin/edit_content.html', {'form': form, 'content': content})


@guest_required
def presente(request):
    """Redirect to presents section on single home page."""
    return redirect(reverse('home') + '#presentes')

def notificar_present(pagamento: Pagamento):
    admin_numbers = getattr(settings, 'WEDDING_ADMINS_WHATSAPP', '') or ''
    admin_list = [n.strip() for n in admin_numbers.split(',') if n.strip()]
    # Build message with details
    present_name = pagamento.presente.nome if pagamento.presente else 'Presente'
    amount = f"R$ {pagamento.valor:.2f}" if pagamento.valor is not None else '-' 
    guest_name = pagamento.nome_pagador or (pagamento.guest.name if pagamento.guest else '-')
    guest_phone = pagamento.guest.phone_number if pagamento.guest else '-'
    guest_msg = pagamento.message or '-'
    text = (
        f"Novo presente recebido (ou iniciado)!\nPresente: {present_name}\nValor: {amount}\nPor: {guest_name} ({guest_phone})\nMensagem: {guest_msg}"
        f"\nStatus atual: {pagamento.status}"
        f"\nCheque na conta do MercadoPago para confirmação"
    )
    for admin_phone in admin_list:
        try:
            success, error = send_whatsapp_message(admin_phone, text)
            if not success:
                logger = logging.getLogger(__name__)
                logger.warning("Failed to notify admin %s via WhatsApp: %s", admin_phone, error)
        except Exception:
            # swallow errors to keep webhook resilient
            pass

logger = logging.getLogger(__name__)


WHATSAPP_SEND_DELAY_SECONDS = getattr(settings, 'WHATSAPP_SEND_DELAY_SECONDS', 1.0)


def _send_whatsapp_batch_in_background(batch_id, items_data, message_template, image_bytes, image_name):
    """
    Roda em uma thread separada, fora do request-response cycle.
    Loop sequencial com pausa entre envios para evitar timeouts e rate limits.
    """
    close_old_connections()

    try:
        batch = WhatsAppBatch.objects.get(id=batch_id)
    except WhatsAppBatch.DoesNotExist:
        return

    image_file = None
    if image_bytes:
        image_file = ContentFile(image_bytes, name=image_name)

    for item_data in items_data:
        try:
            item = WhatsAppBatchItem.objects.get(id=item_data['item_id'])
        except WhatsAppBatchItem.DoesNotExist:
            continue

        message = message_template.replace("{{name}}", item_data['name'])

        try:
            if image_file:
                image_file.seek(0)
            success, error = send_whatsapp_message(item_data['phone'], message, image_file)
        except Exception as exc:
            success = False
            error = str(exc)

        if success:
            item.status = 'sent'
            item.sent_at = timezone.now()
            batch.sent_count = batch.sent_count + 1
        else:
            item.status = 'failed'
            item.error_message = (error or 'Erro desconhecido')[:2000]
            batch.failed_count = batch.failed_count + 1
            logger.warning(
                "Falha ao enviar WhatsApp para %s (%s): %s",
                item.guest_name, item.phone_number, item.error_message
            )

        item.save(update_fields=['status', 'error_message', 'sent_at'])
        batch.save(update_fields=['sent_count', 'failed_count'])

        guest_id = item_data.get('guest_id')
        guest_type = item_data.get('guest_type')
        if guest_type == 'guest' and guest_id:
            try:
                guest = Guest.objects.get(id=guest_id)
                guest.message_sent = success
                guest.save(update_fields=['message_sent'])
            except Guest.DoesNotExist:
                pass
        elif guest_type == 'extra' and guest_id:
            try:
                extra_guest = ExtraGuest.objects.get(id=guest_id)
                extra_guest.message_sent = success
                extra_guest.save(update_fields=['message_sent'])
            except ExtraGuest.DoesNotExist:
                pass

        time.sleep(WHATSAPP_SEND_DELAY_SECONDS)

    batch.mark_completed()
    close_old_connections()

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

    # If guest is logged in, associate the payment and optionally store a message
    try:
        user_id = request.session.get("otp_user_id")
        if user_id:
            from .models import Guest
            try:
                guest = Guest.objects.get(id=user_id)
                pagamento.guest = guest
                pagamento.nome_pagador = guest.name
            except Guest.DoesNotExist:
                guest = None
        # Accept an optional message param from the website or AI tools
        message = request.POST.get('message') or request.GET.get('message')
        if message:
            pagamento.message = message
        pagamento.save()
    except Exception:
        # Do not interrupt the payment flow for non-critical issues
        pass

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
                try:
                    notificar_present(pagamento)  # Notify admins of new present
                except Exception as exc:
                    print(f"Erro ao notificar admins: {str(exc)}")
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

                payer = info.get('payer', {}) or {}
                payer_email = payer.get('email')
                payer_name = None
                if payer.get('first_name') or payer.get('last_name'):
                    payer_name = (payer.get('first_name','') + ' ' + payer.get('last_name','')).strip()
                elif payer.get('nickname'):
                    payer_name = payer.get('nickname')

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
                        # populate payer info when available
                        if payer_email:
                            pagamento.email_pagador = payer_email
                        if payer_name:
                            pagamento.nome_pagador = pagamento.nome_pagador or payer_name
                        previous_status = pagamento.status
                        pagamento.status = novo_status
                        pagamento.save()

                        # If payment just became approved, notify admins via WhatsApp
                        try:
                            if previous_status != 'aprovado' and novo_status == 'aprovado':
                                notificar_present(pagamento)
                        except Exception as exc:
                            print(f"Erro ao notificar admins via WhatsApp: {str(exc)}")
                    except Pagamento.DoesNotExist:
                        pass
            except Exception as e:
                print(f"Erro ao processar webhook: {str(e)}")

        return HttpResponse("OK", status=200)
    
    except Exception as e:
        print(f"Erro no webhook: {str(e)}")
        return HttpResponse("OK", status=200)


def pagamento_sucesso(request):
    """Página de sucesso após pagamento"""
    payment_id = request.GET.get('payment_id')
    context = {
        'titulo': 'Pagamento Realizado com Sucesso!',
        'mensagem': 'Obrigado pelo seu presente! Estamos muito felizes! 💝',
        'payment_id': payment_id
    }
    return render(request, 'pagamento/sucesso.html', context)


def pagamento_erro(request):
    """Página de erro após pagamento"""
    context = {
        'titulo': 'Erro no Pagamento',
        'mensagem': 'Ocorreu um erro ao processar seu pagamento. Tente novamente.'
    }
    return render(request, 'pagamento/erro.html', context)


def pagamento_pendente(request):
    """Página de pagamento pendente"""
    context = {
        'titulo': 'Pagamento Pendente',
        'mensagem': 'Seu pagamento está sendo processado. Você receberá uma confirmação em breve.'
    }
    return render(request, 'pagamento/pendente.html', context)

@guest_required
def confirmacao_familia(request):
    """Redirect to RSVP section on single home page."""
    return redirect(reverse('home') + '#rsvp')

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
    presente = get_object_or_400(Presente, pk=pk)
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
    selected_day = request.POST.get("day", request.GET.get("day", "all"))
    
    # In GET requests, selected_guests comes from the URL (if any).
    # In POST requests, it comes from form submissions.
    # We expect 'guest-ID' or 'extra-ID' format.
    selected_guests_from_request = request.POST.getlist("selected_guests") if request.method == "POST" else request.GET.getlist("selected_guests")
    selected_guest_identifiers = set(selected_guests_from_request)

    # Filtra apenas convidados com telefone preenchido
    guests_queryset = Guest.objects.exclude(phone_number__isnull=True).exclude(phone_number="")
    extra_guests_queryset = ExtraGuest.objects.exclude(phone_number__isnull=True).exclude(phone_number="")

    status_map = {
        'confirmed': 'confirmed',
        'not_answered': 'pending',
        'rejected': 'rejected',
    }

    if selected_status == 'not_sent':
        guests_queryset = guests_queryset.filter(message_sent=False)
        extra_guests_queryset = extra_guests_queryset.filter(message_sent=False)
    else:
        if selected_status in status_map:
            if selected_day in ("day1", "day2"):
                field = 'day1_status' if selected_day == 'day1' else 'day2_status'
                guests_queryset = guests_queryset.filter(**{field: status_map[selected_status]})
                extra_guests_queryset = extra_guests_queryset.filter(**{field: status_map[selected_status]})
            else:
                if selected_status == "confirmed":
                    guests_queryset = guests_queryset.filter(Q(day1_status='confirmed') | Q(day2_status='confirmed'))
                    extra_guests_queryset = extra_guests_queryset.filter(Q(day1_status='confirmed') | Q(day2_status='confirmed'))
                elif selected_status == "not_answered":
                    guests_queryset = guests_queryset.filter(Q(day1_status='pending') | Q(day2_status='pending'))
                    extra_guests_queryset = extra_guests_queryset.filter(Q(day1_status='pending') | Q(day2_status='pending'))
                elif selected_status == "rejected":
                    guests_queryset = guests_queryset.filter(Q(day1_status='rejected') | Q(day2_status='rejected'))
                    extra_guests_queryset = extra_guests_queryset.filter(Q(day1_status='rejected') | Q(day2_status='rejected'))

    # Add 'identifier' attribute to each guest for unique identification
    all_guests_with_identifiers = []
    for guest in guests_queryset:
        guest.identifier = f"guest-{guest.id}"
        all_guests_with_identifiers.append(guest)
    for extra_guest in extra_guests_queryset:
        extra_guest.identifier = f"extra-{extra_guest.id}"
        all_guests_with_identifiers.append(extra_guest)

    if request.method == "POST":
        form = WhatsAppMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message_template = form.cleaned_data["message"]
            image = form.cleaned_data.get("image")

            # Filter guests based on selected_guest_identifiers
            guests_to_send = [
                g for g in all_guests_with_identifiers
                if getattr(g, "phone_number", None) and g.identifier in selected_guest_identifiers
            ]

            if not guests_to_send:
                messages.error(request, "Nenhum convidado válido com telefone selecionado para envio.")
                return redirect(reverse("send_whatsapp_mass"))

            batch_ja_rodando = WhatsAppBatch.objects.filter(status='running').first()
            if batch_ja_rodando:
                messages.error(
                    request,
                    "Já existe um envio em andamento (iniciado em "
                    f"{batch_ja_rodando.created_at.strftime('%d/%m %H:%M')}). "
                    "Aguarde ele terminar antes de iniciar outro."
                )
                return redirect(reverse("whatsapp_batch_status", args=[batch_ja_rodando.id]))

            image_bytes = None
            image_name = None
            if image:
                image.seek(0)
                image_bytes = image.read()
                image_name = image.name

            batch = WhatsAppBatch.objects.create(
                created_by=getattr(request.user, 'username', '') if request.user.is_authenticated else '',
                message_template=message_template,
                total=len(guests_to_send),
            )

            items_data = []
            for guest in guests_to_send:
                # Extract guest_id and guest_type from the identifier
                guest_type, guest_id = guest.identifier.split('-')
                item = WhatsAppBatchItem.objects.create(
                    batch=batch,
                    guest_name=getattr(guest, "name", str(guest)),
                    phone_number=guest.phone_number,
                )
                items_data.append({
                    'item_id': item.id,
                    'name': item.guest_name,
                    'phone': item.phone_number,
                    'guest_id': guest_id, # Use the extracted ID
                    'guest_type': guest_type, # Use the extracted type
                })

            thread = threading.Thread(
                target=_send_whatsapp_batch_in_background,
                args=(batch.id, items_data, message_template, image_bytes, image_name),
                daemon=True,
            )
            thread.start()

            return redirect(reverse("whatsapp_batch_status", args=[batch.id]))
    else:
        form = WhatsAppMessageForm(initial={"status": selected_status})

    return render(request, "admin/send_whatsapp.html", {
        "form": form,
        "guests": all_guests_with_identifiers, # Pass the list with identifiers
        "selected_status": selected_status,
        "selected_day": selected_day,
        "selected_guest_identifiers": selected_guest_identifiers, # Pass the set of identifiers for checking 'checked' state
    })


@wedding_admin_required
def whatsapp_batch_status(request, batch_id):
    batch = get_object_or_404(WhatsAppBatch, id=batch_id)
    return render(request, "admin/whatsapp_batch_status.html", {"batch": batch})


@wedding_admin_required
def whatsapp_batch_status_json(request, batch_id):
    batch = get_object_or_404(WhatsAppBatch, id=batch_id)
    items = batch.items.all()

    return JsonResponse({
        "status": batch.status,
        "total": batch.total,
        "sent_count": batch.sent_count,
        "failed_count": batch.failed_count,
        "items": [
            {
                "name": i.guest_name,
                "phone": i.phone_number,
                "status": i.status,
                "error": i.error_message,
            }
            for i in items
        ],
    })