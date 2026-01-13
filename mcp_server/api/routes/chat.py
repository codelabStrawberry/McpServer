# backend/api/routes/chat.py

from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from urllib.parse import urlparse
import re
import json
from uuid import uuid4

from api.db.redis import get_redis_client

from api.services.crawl import crawl_url
from api.services.extract import extract_pdf_text
from api.services.summarize import summarize_text
from ollama import ollama_chat

router = APIRouter()

TTL_SECONDS = 60 * 60  # 1 hour

PROMPT_KEY = "session:prompt:{sid}"
HISTORY_KEY = "session:history:{sid}"
STARTED_KEY = "session:started:{sid}"

READY_MESSAGE = "모의 면접 준비 완료! 아래에 '시작하기'라고 입력하면 면접을 시작합니다."

class MessageReq(BaseModel):
    sessionId: str
    message: str


class TerminateReq(BaseModel):
    sessionId: str


def _validate_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="URL 형식이 올바르지 않습니다.")


def _clean_text(text: str) -> str:
    # 과도한 공백 정리
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def _build_system_prompt(job_text: str, resume_text: str) -> str:
    job_text = _clean_text(job_text)
    resume_text = _clean_text(resume_text)

    return f"""
당신은 전문적인 면접관이다. 아래 규칙을 엄격히 따른다.

[역할]
- 사용자가 지원한 채용공고(job_text)와 자기소개서 요약(resume_text)을 기반으로 모의 면접을 진행한다.
- 질문은 1개씩만 한다.
- 사용자의 답변을 받으면 간단한 피드백과 더 나은 답변 예시를 제공한다.
- 그리고 추가질문이 필요하다고 판단되면 답변과 관련된 질문을 한다.
- 대답이 마무리가 되었다고 판단되면 새로운 질문을 1개 한다.
- 한국어로 대답한다.

[규칙]
- 질문은 현실적인 면접 질문으로 한다.
- 가능하면 채용공고의 요구사항과 자기소개서 내용을 연결해서 질문한다.
- 사용자의 답변에 대해 너무 길게 설명하지 않는다.

[채용공고]
{job_text}

[자기소개서 요약]
{resume_text}
""".strip()


def _format_history(history: list[dict[str, str]]) -> str:
    # Ollama에 넣기 쉬운 형태로 대화 로그를 평문으로 만듦
    # history item: {"role": "user"/"assistant", "content": "..."}
    lines = []
    for m in history:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines).strip()


def _is_start_trigger(text: str) -> bool:
    # "시작", "시작하기", "start" 등 유연 처리
    t = (text or "").strip().lower()
    return t in {"시작", "시작하기", "start", "begin"} or "시작" in t



class MessageReq(BaseModel):
    sessionId: str
    message: str


@router.post("/start")
async def start(
    url: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")

    sid = session_id or str(uuid4())

    _validate_url(url)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    # 1) 파일 bytes 먼저 읽기
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="업로드된 PDF가 비어 있습니다.")

    # 2) crawl
    job_text = await run_in_threadpool(crawl_url, url)

    # 3) extract
    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)

    # 4) summary
    resume_summary = await summarize_text(resume_text, language="ko", style="structured")

    # 5) system prompt 생성 + 저장
    system_prompt = _build_system_prompt(job_text=job_text, resume_text=resume_summary)
    await redis_client.set(PROMPT_KEY.format(sid=sid), system_prompt, ex=TTL_SECONDS)

    # 6) 세션 상태 초기화 (Redis)
    await redis_client.set(STARTED_KEY.format(sid=sid), "False", ex=TTL_SECONDS)
    history = [{"role": "assistant", "content": READY_MESSAGE}]
    await redis_client.set(HISTORY_KEY.format(sid=sid), json.dumps(history), ex=TTL_SECONDS)

    # 7) 프론트로 payload 반환 (Chatbot이 readyMessage를 첫 메시지로 띄움)
    return {
        "sessionId": sid,
        "readyMessage": READY_MESSAGE,
        "payload": {
            "systemPrompt": system_prompt,
            "jobText": job_text,
            "resumeText": resume_summary,
        },
    }

@router.get("/history")
async def history(sessionId: str = Query(...)):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")

    sid = (sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId가 필요합니다.")

    history_json = await redis_client.get(HISTORY_KEY.format(sid=sid))
    if not history_json:
        # 세션이 없거나 만료된 경우
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # bytes -> str
    if isinstance(history_json, (bytes, bytearray)):
        history_json = history_json.decode("utf-8")

    started_b = await redis_client.get(STARTED_KEY.format(sid=sid))
    started_s = ""
    if started_b is None:
        started_s = "False"
    elif isinstance(started_b, (bytes, bytearray)):
        started_s = started_b.decode("utf-8")
    else:
        started_s = str(started_b)

    return {
        "sessionId": sid,
        "started": started_s == "True",
        "history": json.loads(history_json),
    }

@router.post("/message")
async def message(req: MessageReq):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")

    sid = (req.sessionId or "").strip()
    user_text = (req.message or "").strip()

    if not sid:
        raise HTTPException(status_code=400, detail="sessionId가 필요합니다.")

    # Redis에서 prompt 확인 (세션 존재 여부)
    system_prompt_b = await redis_client.get(PROMPT_KEY.format(sid=sid))
    if not system_prompt_b:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다. 먼저 /chat/start를 호출하세요.")

# ✅ bytes -> str
    if isinstance(system_prompt_b, (bytes, bytearray)):
        system_prompt = system_prompt_b.decode("utf-8")
    else:
        system_prompt = str(system_prompt_b)

    # history 로드
    history_json = await redis_client.get(HISTORY_KEY.format(sid=sid))
    if history_json and isinstance(history_json, (bytes, bytearray)):
        history_json = history_json.decode("utf-8")
    history = json.loads(history_json) if history_json else []
    history.append({"role": "user", "content": user_text})

    # ✅ started bytes/string 안전 처리
    started_b = await redis_client.get(STARTED_KEY.format(sid=sid))
    if started_b is None:
        started = False
    else:
        started_s = started_b.decode("utf-8") if isinstance(started_b, (bytes, bytearray)) else str(started_b)
        started = started_s == "True"

    # Redis는 bytes를 반환할 수 있으므로 문자열로 변환
    system_prompt = system_prompt_b

    if not user_text:
        raise HTTPException(status_code=400, detail="message가 비어 있습니다.")

    # 세션 히스토리 로드 (Redis)
    history_json = await redis_client.get(HISTORY_KEY.format(sid=sid))
    history = json.loads(history_json) if history_json else []
    history.append({"role": "user", "content": user_text})

    # 시작 상태 로드 (Redis)
    started_b = await redis_client.get(STARTED_KEY.format(sid=sid))
    started = (started_b or b"False") == "True"

    # 시작 트리거 처리
    if not started:
        if _is_start_trigger(user_text):
            await redis_client.set(STARTED_KEY.format(sid=sid), "True", ex=TTL_SECONDS)

            # 첫 질문 생성
            prompt = f"""
{system_prompt}

지금부터 면접을 시작한다.
첫 질문 1개만, 한국어로, 바로 질문만 출력해라.

대화 로그:
{_format_history(history)}
""".strip()

            res = await ollama_chat(prompt)
            answer = (res.get("answer") or "").strip() or "좋습니다. 먼저 자기소개를 1분 정도로 해주세요."

            history.append({"role": "assistant", "content": answer})
            await redis_client.set(HISTORY_KEY.format(sid=sid), json.dumps(history), ex=TTL_SECONDS)

            return {"sessionId": sid, "answer": answer}

        # 아직 시작 전이면 안내만 반복
        answer = READY_MESSAGE
        history.append({"role": "assistant", "content": answer})
        await redis_client.set(HISTORY_KEY.format(sid=sid), json.dumps(history), ex=TTL_SECONDS)
        return {"sessionId": sid, "answer": answer}

    # 면접 진행 중: 시스템 프롬프트 + 히스토리 기반으로 응답 생성
    prompt = f"""
{system_prompt}

아래 대화 로그를 바탕으로 규칙에 맞게 응답해라.
- 사용자가 방금 답한 내용에 대해: (1) 짧은 피드백, (2) 더 나은 답변 예시, (3) 다음 질문 1개 순서로 작성한다.
- 한국어로 작성한다.

대화 로그:
{_format_history(history)}
""".strip()

    res = await ollama_chat(prompt)
    answer = res.get("answer", "").strip()

    if not answer:
        answer = "답변 감사합니다. 조금 더 구체적으로 어떤 상황(S), 과제(T), 행동(A), 결과(R)였는지 STAR 방식으로 설명해주실래요?"

    history.append({"role": "assistant", "content": answer})
    await redis_client.set(HISTORY_KEY.format(sid=sid), json.dumps(history), ex=TTL_SECONDS)

    return {"sessionId": sid, "answer": answer}


@router.post("/terminate")
async def terminate(req: TerminateReq):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")

    sid = (req.sessionId or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="sessionId가 필요합니다.")

    # Redis에서 세션 삭제
    await redis_client.delete(PROMPT_KEY.format(sid=sid))
    await redis_client.delete(HISTORY_KEY.format(sid=sid))
    await redis_client.delete(STARTED_KEY.format(sid=sid))

    return {"sessionId": sid, "status": "terminated"}

# @router.get("/ping")
# def ping():
#     return {"ok": True}