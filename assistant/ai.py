import requests
import json
from django.conf import settings
from google import genai
from django.http import JsonResponse
from assistant.models import ConversationMessage
from assistant.context import ASSISTANT_CONTEXT_WITH_CONTEXT, ASSISTANT_CONTEXT_WITH_INPUT_AND_CONTEXT

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
                    )
                },
                {"role": "user", "content": message},
            ],
        }
    )
    return resp.json()

def call_gemini(message, previous_context=[]):
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=ASSISTANT_CONTEXT_WITH_INPUT_AND_CONTEXT.format(
            conversation_context="\n".join(previous_context),
            user_message=message
        ),
        config=genai.types.GenerateContentConfig(
            temperature=0.4,
            top_p=0.95,
            top_k=20,
        ),
    )
    return response.candidates[0].content.parts[0].text

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

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

@csrf_exempt
@require_POST
def whatsapp_gemini_api(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        jid = data.get('jid')
        message = data.get('message')
        if not jid or not message:
            return JsonResponse({'error': 'Missing jid or message'}, status=400)

        context = ConversationMessage.objects.filter(jid=jid).first()
        if not context:
            context = ConversationMessage.objects.create(jid=jid, messages=[])

        messages_list = [m for m in (context.messages or []) if isinstance(m, str)]
        if len(messages_list) > 10:
            messages_list = messages_list[-10:]

        try:
            ai_message = call_gemini(message, previous_context=messages_list)
        except Exception as exc:
            print(f"Error calling Gemini API: {exc}")
            ai_message = f"Nossa IA está com alguma instabilidade no momento. Tente novamente mais tarde ou nos ajude a consertar o problema https://github.com/hugodavilat/cenourinhas/blob/main/core/views.py#L64. Error: {exc}"

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

        return JsonResponse({'reply': ai_message})
    except Exception as e:
        print("DEBUG: Exception in whatsapp_gemini_api", str(e))
        return JsonResponse({'error': str(e)}, status=500)
