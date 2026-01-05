# api/routes/rag.py
from fastapi import APIRouter
from api.schemas import RagPayload
from rag import rag_chat

router = APIRouter()

@router.post("/rag_chat")
async def rag(payload: RagPayload):
    return {
        "result": await rag_chat(payload.question)
    }
