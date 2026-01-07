from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routes.chat import SESSION_PROMPTS   # start에서 저장한 프롬프트
from ollama import ollama_chat

router = APIRouter()

CHAT_HISTORY: dict[str, list[dict]] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

@router.post("/chat")
async def chat(req: ChatRequest):
    sid = req.session_id
    user_msg = (req.message or "").strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="message가 비어있습니다.")

    system_prompt = SESSION_PROMPTS.get(sid)
    if not system_prompt:
        raise HTTPException(status_code=400, detail="세션 프롬프트가 없습니다. 먼저 /start를 호출하세요.")

    history = CHAT_HISTORY.get(sid, [])
    last_turns = history[-10:]
    history_block = "\n".join(
        [f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}" for m in last_turns]
    ).strip()

    final_prompt = f"""
{system_prompt}

[CHAT HISTORY]
{history_block}

[USER]
{user_msg}

[ASSISTANT]
""".strip()

    result = await ollama_chat(final_prompt)
    assistant_text = result.get("answer", "")

    history.append({"role": "user", "content": user_msg})
    history.append({"role": "assistant", "content": assistant_text})
    CHAT_HISTORY[sid] = history

    return {"response": assistant_text}

@router.get("/chat-list/{session_id}")
async def chat_list(session_id: str):
    history = CHAT_HISTORY.get(session_id, [])
    return {"list": history}
