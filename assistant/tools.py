# assistant/tools.py

from core.models import Guest, ExtraGuest, Presente, Pagamento
from core.mercadopago_sdk import get_sdk
from django.conf import settings


# ==========================================================
# 1) CONFIRMAR PRESENÇA
# ==========================================================


def tool_confirm_presence(phone: str, day1: bool = True, day2: bool = True):
    """
    Confirma ou rejeita a presença do convidado cujo telefone corresponde ao valor fornecido.
    Essa ferramenta confirma ou rejeita presença de todos os convidados extras. Caso queira confirmar de apenas um convidado, utilize o site https://cenourinhas.com.br.

    day1 e day2 são booleanos que indicam se a confirmação/rejeição deve ser aplicada ao dia 1 (10/10) e/ou ao dia 2 (11/10). Se ambos forem True, aplica-se a ambos os dias.
    Confirmar ou negar os dois dias é o comportamento padrão se day1 e day2 forem omitidos (ou ambos True).
    
    day1 é o pré casamento, 10 de outubro de 2026. Entenda qualquer referencia a dia 1, dia 10 ou pré.
    day2 é o casamento, 11 de outubro de 2026. Entenda qualquer referencia a dia 2, dia 11 ou casamento ou festa principal.

    Use esta ferramenta quando o usuário disser que deseja:
    - confirmar presença
    - negar presença
    - alterar resposta anterior

    Importante: O número de telefone deve ser fornecido no formato completo,
    incluindo código do país e DDD, para garantir a correspondência correta com os
    registros dos convidados.
    Exemplo de formato: "+5511999998888"

    Caso o usuário forneça um numero com o DDD, mas sem o código do país,
    tente adicionar o código do país padrão +55 antes de buscar. Caso fique na duvida,
    pergunte de que país é o usuário.


    Entrada:
      phone: número de telefone completo (string)
      day1: booleano (True = confirmar dia 10, False = rejeitar)
      day2: booleano (True = confirmar dia 11, False = rejeitar)

    Retorno:
      {
        "success": bool,
        "day1": bool,
        "day2": bool,
        "message": str
      }
    """

    # 1. Convidado principal
    guest = Guest.objects.filter(phone_number=phone).first()

    # 2. Convidado extra (redireciona para o convidado principal)
    if not guest:
        extra = ExtraGuest.objects.filter(phone_number=phone).first()
        if extra:
            return tool_confirm_presence(extra.main_guest.phone_number, day1=day1, day2=day2)

        return {
            "success": False,
            "message": "Não encontrei seu número na lista de convidados.",
        }

    # Helper to update per-person statuses
    def _set_status(person):
        setattr(person, 'day1_status', 'confirmed' if day1 else 'rejected')
        setattr(person, 'day2_status', 'confirmed' if day2 else 'rejected')

    # Update guest per-day fields
    print(f"Updating guest {guest.name} statuses: day1={day1}, day2={day2}")
    _set_status(guest)
    guest.save()

    # Atualizar convidados extras do mesmo grupo
    extras = ExtraGuest.objects.filter(main_guest=guest)
    for eg in extras:
        print(f"Updating extra guest {eg.name} statuses: day1={day1}, day2={day2}")
        _set_status(eg)
        eg.save()

    # Criar lista de nomes
    names = [guest.name] + [eg.name for eg in extras]
    formatted_names = "\n- " + "\n- ".join(names) if names else ""

    # Mensagem final humanizada
    yes_text = ''
    if day1 and not day2:
        yes_text = ' no dia 10 de outubro'
    elif day2 and not day1:
        yes_text = ' no dia 11 de outubro'
    elif day1 and day2:
        yes_text = ' nos dias 10 e 11 de outubro'
    no_text = ''
    if not day1 and day2:
        no_text = ' no dia 10 de outubro'
    elif not day2 and day1:
        no_text = ' no dia 11 de outubro'
    elif not day1 and not day2:
        no_text = ' nos dias 10 e 11 de outubro'
    
    msg = ""
    if yes_text:
        msg += f"Presença confirmada{yes_text} para:{formatted_names}"
    if no_text:
        msg += f"Presença rejeitada{no_text} para:{formatted_names}"

    return {
        "success": True,
        "day1": day1,
        "day2": day2,
        "message": msg,
    }


# ==========================================================
# 2) RETORNAR LISTA DE PRESENTES
# ==========================================================


def get_gift_options():
    """
    Retorna a lista completa de presentes disponíveis.

    Use esta ferramenta quando o usuário:
    - pedir opções de presentes
    - pedir lista de presentes
    - perguntar o que pode dar de presente

    Saída:
      [
        {
          "id": int,
          "name": str,
          "description": str,
          "price": str | None,
          "image_url": str | None
        },
        ...
      ]
    """
    presentes = Presente.objects.all()
    return [
        {
            "id": p.id,
            "name": p.nome,
            "description": p.descricao,
            "price": str(p.valor) if p.valor else None,
        }
        for p in presentes
    ]


# ==========================================================
# 3) INICIAR PAGAMENTO DE PRESENTE ESPECÍFICO
# ==========================================================


def tool_start_gift_payment(presente_id: int, message: str = None, guest_phone: str = None):
    """
    Cria um pagamento associado a um presente específico.

    Use esta ferramenta quando o usuário:
    - selecionar um presente da lista
    - disser “quero dar o presente X”
    - pedir o link de pagamento de um item específico

    Entrada:
      presente_id: inteiro correspondente ao ID do presente
      message: string opcional com mensagem do convidado para o casal
      guest_phone: string opcional com número de telefone do convidado para vincular ao pagamento

    Saída:
      {
        "success": bool,
        "message": str,
        "presente": str,
        "valor": str,
        "payment_url": str,
      }
    """

    presente = Presente.objects.filter(id=presente_id).first()

    if not presente:
        return {
            "success": False,
            "message": "Presente não encontrado.",
        }

    try:
        pagamento = Pagamento.objects.create(
            presente=presente,
            valor=presente.valor,
        )

        # If guest_phone provided, try to associate with a Guest
        if guest_phone:
            guest = Guest.objects.filter(phone_number=guest_phone).first()
            if guest:
                pagamento.guest = guest
                pagamento.nome_pagador = guest.name

        # Save optional message
        if message:
            pagamento.message = message

        pagamento.save()

        preference_data = {
            "items": [
                {
                    "title": presente.nome,
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": float(presente.valor),
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

        sdk = get_sdk()
        preference = sdk.preference().create(preference_data)

        init_point = preference["response"].get("init_point")

        return {
            "success": True,
            "presente": presente.nome,
            "valor": str(presente.valor),
            "payment_url": init_point,
            "message": f"Aqui está o link seguro para enviar o presente '{presente.nome}'.",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao criar link de pagamento: {e}",
        }


# ==========================================================
# 4) INICIAR PAGAMENTO DE VALOR PERSONALIZADO
# ==========================================================


def tool_start_custom_gift_payment(valor: float, message: str = None, guest_phone: str = None):
    """
    Cria um pagamento para um valor personalizado quando o usuário quer dar
    um valor específico sem escolher um presente por ID.

    Use esta ferramenta quando o usuário disser que quer dar um valor específico,
    mesmo sem ID.

    Exemplos de frases:
    • "Quero dar 200 reais."
    • "Quero ajudar com cem."
    • "Posso fazer um presente de 75?"

    Entrada:
      valor: número (float, decimal or int) representando o valor em BRL
      message: string opcional com mensagem do convidado para o casal
      guest_phone: string opcional com número de telefone do convidado para vincular ao pagamento

    Saída:
      {
        "success": bool,
        "message": str,
        "valor": str,
        "payment_url": str,
      }
    """

    try:
        # Criar um presente temporário para associar ao pagamento
        nome = f"Contribuição - R$ {valor:.2f}"
        # presente = Presente.objects.create(nome=nome, descricao="Contribuição personalizada", valor=valor)

        pagamento = Pagamento.objects.create(
            presente=None,
            valor=valor,
        )

        # Associate guest if phone provided
        if guest_phone:
            guest = Guest.objects.filter(phone_number=guest_phone).first()
            if guest:
                pagamento.guest = guest
                pagamento.nome_pagador = guest.name

        # Save optional message
        if message:
            pagamento.message = message

        pagamento.save()

        preference_data = {
            "items": [
                {
                    "title": nome,
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": float(valor),
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

        sdk = get_sdk()
        preference = sdk.preference().create(preference_data)

        init_point = preference["response"].get("init_point")

        return {
            "success": True,
            "valor": str(valor),
            "payment_url": init_point,
            "message": f"Aqui está o link seguro para contribuir com R$ {valor}.",
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Erro ao criar link de pagamento personalizado: {e}",
        }


# ==========================================================
# REGISTRO DE TOOLS
# ==========================================================

TOOLS = {
    "confirm_presence": tool_confirm_presence,
    "get_gift_options": get_gift_options,
    "start_gift_payment": tool_start_gift_payment,
    "start_custom_gift_payment": tool_start_custom_gift_payment,
}
