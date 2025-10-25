from fastapi import APIRouter, Request
from .client import call_gemini_with_rotation

router = APIRouter()

@router.post("/chat")
async def chat(request: Request):
    data = await request.json()
    prompt = data.get("message", "")
    response = call_gemini_with_rotation(prompt)
    return {"response": response}