from fastapi import APIRouter, Request
from gemini.client import call_gemini_with_rotation

router = APIRouter()

@router.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    message = data.get("message")
    channel = data.get("channel", "web")
    print(f"📩 Mensaje recibido: {message}")
    respuesta = call_gemini_with_rotation(message)

    return {
        "mensaje_recibido": message,
        "respuesta_bot": respuesta
    }
    