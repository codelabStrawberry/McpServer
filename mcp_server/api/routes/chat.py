# api/routes/chat.py
from fastapi import APIRouter
from api.schemas import ChatPayload
from ollama import ollama_chat

router = APIRouter()

@router.post("/chat")
async def chat(payload: ChatPayload):
    return {
        "result": await ollama_chat(payload.prompt)
    }
