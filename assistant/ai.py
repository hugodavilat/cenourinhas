import requests
import json
from google import genai

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse

from assistant.models import ConversationMessage
from assistant.context import ASSISTANT_CONTEXT_WITH_CONTEXT
from assistant.tools import (
    tool_confirm_presence,
    get_gift_options,
    tool_start_gift_payment,
    TOOLS,
)


def call_llama(message, previous_context=[]):
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.OPEN_ROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "meta-llama/llama-3.1-8b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": ASSISTANT_CONTEXT_WITH_CONTEXT.format(
                        conversation_context="\n".join(previous_context)
                    ),
                },
                {"role": "user", "content": message},
            ],
        },
    )
    return resp.json()


def call_gemini(client, message, previous_context=[]):
    system_prompt = ASSISTANT_CONTEXT_WITH_CONTEXT.format(
        conversation_context="\n".join(previous_context)
    )
    return client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {
                "role": "user",
                "parts": [{"text": system_prompt}],
            },
            {
                "role": "user",
                "parts": [{"text": message}],
            },
        ],
        config=genai.types.GenerateContentConfig(
            temperature=0.4,
            tools=[
                genai.types.Tool(
                    function_declarations=[
                        genai.types.FunctionDeclaration(
                            name="confirm_presence",
                            description=tool_confirm_presence.__doc__,
                            parameters=genai.types.Schema(
                                type="object",
                                properties={
                                    "phone": genai.types.Schema(type="string"),
                                    "confirm": genai.types.Schema(type="boolean"),
                                },
                                required=["phone", "confirm"],
                            ),
                        ),
                        genai.types.FunctionDeclaration(
                            name="get_gift_options",
                            description=get_gift_options.__doc__,
                            parameters=genai.types.Schema(
                                type="object",
                                properties={},
                                required=[],
                            ),
                        ),
                        genai.types.FunctionDeclaration(
                            name="start_gift_payment",
                            description=tool_start_gift_payment.__doc__,
                            parameters=genai.types.Schema(
                                type="object",
                                properties={
                                    "presente_id": genai.types.Schema(type="integer"),
                                },
                                required=["presente_id"],
                            ),
                        ),
                    ]
                )
            ],
            tool_config=genai.types.ToolConfig(
                function_calling_config=genai.types.FunctionCallingConfig(mode="AUTO")
            ),
        ),
    )


#############################################
# SEGUNDA CHAMADA UNIVERSAL AO GEMINI
#############################################
def generate_final_response(client, tool_name, tool_result):
    """
    Gera uma resposta amigável para o usuário a partir do resultado de uma ferramenta.
    Compatível 100% com Gemini 2.5 (sem INVALID_ARGUMENT).
    """

    # -------------------------------
    # Escolher instrução por tool:
    # -------------------------------
    basic_instruction = """
    Essas respostas serão enviadas via WhatsApp, então seja breve e evite
    formatações complexas (markdown deve ser evitado). Não mande liks
    formatados como markdown, apenas texto simples.
    """
    if tool_name == "get_gift_options":
        instruction = basic_instruction + (
            "Transforme a lista de presentes abaixo em uma lista para o usuário escolher um. "
            "Mostre nome, descrição, ID e valor se existir. Não mostre JSON."
        )
    elif tool_name == "confirm_presence":
        instruction = basic_instruction + (
            "Gere uma mensagem informando o resultado da confirmação de presença. "
            "Não mostre JSON."
        )
    elif tool_name == "start_gift_payment":
        instruction = basic_instruction + (
            "O JSON contém link e infos de pagamento. Monte uma resposta humana com o link. "
            "Não mostre JSON."
        )
    elif tool_name == "start_custom_gift_payment":
        instruction = basic_instruction + (
            "O JSON contém link e valor. Gere uma resposta para o usuário mostrando esses dados. "
            "Não mostre JSON."
        )
    else:
        instruction = "Transforme o resultado abaixo em uma resposta para o usuário, nunca mostrando JSON."

    # -------------------------------
    # SEGUNDA CHAMADA — formato mínimo
    # -------------------------------
    final = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            {
                "role": "model",
                "parts": [{"text": instruction}],
            },
            {
                "role": "user",
                "parts": [{"text": json.dumps(tool_result, ensure_ascii=False)}],
            },
        ],
    )

    return final.candidates[0].content.parts[0].text


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


@csrf_exempt
@require_POST
def whatsapp_gemini_api(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        jid = data.get("jid")
        message = data.get("message")
        if not jid or not message:
            return JsonResponse({"error": "Missing jid or message"}, status=400)

        # Gemini Client with correct API key.
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # Retrieve past messages from JID.
        context = ConversationMessage.objects.filter(jid=jid).first()
        if not context:
            context = ConversationMessage.objects.create(jid=jid, messages=[])
        messages_list = [m for m in (context.messages or []) if isinstance(m, str)]
        if len(messages_list) > 10:
            messages_list = messages_list[-10:]

        # First call to Gemini API.
        # --- CHAMA GEMINI ---
        gemini_response = call_gemini(client, message, previous_context=messages_list)
        result = gemini_response.candidates[0]

        ai_message = ""

        # Verificar se há tool call
        tool_call = None
        part0 = result.content.parts[0]

        if hasattr(part0, "function_call") and part0.function_call:
            tool_call = part0.function_call

        if tool_call:
            tool_name = tool_call.name
            tool_args = dict(tool_call.args)

            if tool_name in TOOLS:
                tool_result = TOOLS[tool_name](**tool_args)
                print("DEBUG: Tool result for", tool_name, ":", tool_result)

                # Segunda chamada para gerar resposta final natural
                final = generate_final_response(client, tool_name, tool_result)
                print("DEBUG: Tool result for", tool_name, ":", tool_result)
                # ai_message = final.candidates[0].content.parts[0].text
                ai_message = final

            else:
                ai_message = f"[ERRO] Tool '{tool_name}' não registrada."

        else:
            # Resposta normal (sem tools)
            ai_message = part0.text

        # Atualiza o contexto da conversa e salva a mensagem do usuário e a resposta da IA.
        messages_list.append(message)
        messages_list.append(ai_message)
        context.messages = messages_list
        context.save()

        try:
            print("Sending WhatsApp message to", jid)
            print("Message content:", ai_message)
            send_whatsapp_message_to_jid(jid, ai_message)
        except Exception as exc:
            print(f"Failed to send WhatsApp message to {jid}: {exc}")

        return JsonResponse({"reply": ai_message})
    except Exception as e:
        print("DEBUG: Exception in whatsapp_gemini_api", str(e))
        return JsonResponse({"error": str(e)}, status=500)
