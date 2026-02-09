# assistant/tools.py

from core.models import Guest, ExtraGuest, Presente, Pagamento
from core.mercadopago_sdk import get_sdk
from django.conf import settings


# ==========================================================
# 1) CONFIRMAR PRESENÇA
# ==========================================================


def tool_confirm_presence(phone: str, confirm: bool):
    """
    Confirma ou rejeita a presença do convidado cujo telefone corresponde ao valor fornecido.

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
      confirm: booleano (True = confirmar, False = rejeitar)

    Retorno:
      {
        "success": bool,
        "message": str,
        "guest_name": str,
        "confirmed": bool,
      }
    """

    # 1. Convidado principal
    guest = Guest.objects.filter(phone_number=phone).first()

    # 2. Convidado extra (redireciona para o convidado principal)
    if not guest:
        extra = ExtraGuest.objects.filter(phone_number=phone).first()
        if extra:
            return tool_confirm_presence(extra.main_guest.phone_number, confirm)

        return {
            "success": False,
            "message": "Não encontrei seu número na lista de convidados.",
        }

    # Atualizar convidado principal
    guest.is_confirmed = confirm
    guest.is_rejected = not confirm
    guest.not_answered = False
    guest.save()

    # Atualizar convidados extras do mesmo grupo
    extras = ExtraGuest.objects.filter(main_guest=guest)
    for eg in extras:
        eg.is_confirmed = confirm
        eg.is_rejected = not confirm
        eg.not_answered = False
        eg.save()

    # Criar lista de nomes
    names = [guest.name] + [eg.name for eg in extras]
    formatted_names = "\n- " + "\n- ".join(names) if names else ""

    # Mensagem final humanizada
    if confirm:
        msg = f"Presença confirmada para:{formatted_names}"
    else:
        msg = f"Registramos que não comparecerão:{formatted_names}"

    return {
        "success": True,
        "guest_name": guest.name,
        "confirmed": confirm,
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


def tool_start_gift_payment(presente_id: int):
    """
    Cria um pagamento associado a um presente específico.

    Use esta ferramenta quando o usuário:
    - selecionar um presente da lista
    - disser “quero dar o presente X”
    - pedir o link de pagamento de um item específico

    Entrada:
      presente_id: inteiro correspondente ao ID do presente

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
# REGISTRO DE TOOLS
# ==========================================================

TOOLS = {
    "confirm_presence": tool_confirm_presence,
    "get_gift_options": get_gift_options,
    "start_gift_payment": tool_start_gift_payment,
}
