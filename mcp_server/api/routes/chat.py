# backend/api/routes/chat.py

from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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

redis_client = None


# ----------------------------
# Redis 키 Prefix
# ----------------------------
PROMPT_KEY = "session:prompt:{sid}"
HISTORY_KEY = "session:history:{sid}"
STARTED_KEY = "session:started:{sid}"
TTL_SECONDS = 7200  # 2시간 만료

READY_MESSAGE = "<면접 준비완료> 준비가 되면 '시작하기'라고 입력해주세요."


def _validate_url(url: str) -> None:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        raise HTTPException(status_code=400, detail="URL 형식이 올바르지 않습니다.")


def _build_system_prompt(job_text: str, resume_text: str) -> str:
    # (최소 구현) - 너의 서비스 목적에 맞는 시스템 프롬프트
    return f"""
너는 한국어로 진행하는 '면접관'이다.
아래 채용공고(job_text)와 자기소개서(resume_text)를 바탕으로, 지원자에게 '대화형 면접'을 진행하라.

규칙:
- 사용자가 '시작하기'라고 입력하기 전에는 면접 질문을 시작하지 않는다.
- 면접이 시작되면, 한 번에 질문 1개만 한다.
- 사용자가 답하면: (1) 짧은 피드백 2~4줄, (2) 더 나은 답변 예시 3~6줄, (3) 다음 질문 1개 순서로 진행한다.
- 질문은 채용공고 요구역량과 자기소개서 경험을 연결해 검증하는 형태로 만든다.
- 과도하게 길지 않게, 실전 면접 톤으로 진행한다.

[채용공고 원문]
{job_text}

[자기소개서 원문]
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
    t = (text or "").strip()

    # 공백/따옴표/기호 제거해서 비교 (예: "시작하기!" -> 시작하기)
    t2 = re.sub(r"[\s\"'“”‘’.,!?()<>[\]{}]", "", t)

    # 1) 정확 매칭
    if t2 in ("시작하기", "준비완료", "시작", "면접시작", "start", "Start", "START"):
        return True

    # 2) 포함 매칭(현장에서는 이게 제일 안전)
    # 예: "면접 시작하기", "시작할게요" 등
    if "시작" in t2:
        return True

    return False


class MessageReq(BaseModel):
    sessionId: str
    message: str


@router.post("/start")
async def start(
    url: str = Form(...),
    file: UploadFile = File(...),
    # session_id: str | None = Form(None),
):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")
    
    _validate_url(url)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    # session_id 서버에서 생성
    sid = str(uuid4())

    # 1) 파일 bytes 읽기
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF 파일이 비어 있습니다.")

    # 2) crawl
    job_text = await run_in_threadpool(crawl_url, url)
    # 3) extract
    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    # 4) summary
    resume_summary = await summarize_text(resume_text, language="ko", style="structured")
    # print(resume_summary)
    # 3) system prompt 생성 + 저장
    system_prompt = _build_system_prompt(job_text=job_text, resume_text=resume_summary)
    await redis_client.set(PROMPT_KEY.format(sid=sid), system_prompt, ex=TTL_SECONDS)

    # 4) 세션 상태 초기화 (Redis)
    await redis_client.set(STARTED_KEY.format(sid=sid), "False", ex=TTL_SECONDS)
    history = [{"role": "assistant", "content": READY_MESSAGE}]
    await redis_client.set(HISTORY_KEY.format(sid=sid), json.dumps(history), ex=TTL_SECONDS)

    # 5) 프론트로 payload 반환 (Chatbot이 readyMessage를 첫 메시지로 띄움)
    return {
        "sessionId": sid,
        "readyMessage": READY_MESSAGE,
        "payload": {
            "systemPrompt": system_prompt,
            "jobText": job_text,
            "resumeText": resume_summary,
        },
    }


@router.post("/message")
async def message(req: MessageReq):
    redis_client = await get_redis_client()
    if redis_client is None:
        raise HTTPException(status_code=500, detail="Redis 연결 실패")
    
    sid = (req.sessionId or "").strip()
    print("sid", sid)
    user_text = (req.message or "").strip()

    if not sid:
        raise HTTPException(status_code=400, detail="sessionId가 필요합니다.")

    # Redis에서 prompt 확인 (세션 존재 여부)
    system_prompt = await redis_client.get(PROMPT_KEY.format(sid=sid))
    if not system_prompt:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다. 먼저 /chat/start를 호출하세요.")

    if not user_text:
        raise HTTPException(status_code=400, detail="message가 비어 있습니다.")

    # 세션 히스토리 로드 (Redis)
    history_json = await redis_client.get(HISTORY_KEY.format(sid=sid))
    history = json.loads(history_json) if history_json else []
    history.append({"role": "user", "content": user_text})

    # 시작 상태 로드 (Redis)
    started_str = await redis_client.get(STARTED_KEY.format(sid=sid))
    started = started_str == "True"

    # 시작 트리거 처리
    if not started:
        if _is_start_trigger(user_text):
            await redis_client.set(STARTED_KEY.format(sid=sid), "True", ex=TTL_SECONDS)
            # 첫 질문 생성
            prompt = f"""
{system_prompt.encode()}

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
{system_prompt.decode()}

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


@router.post("/finish")
async def finish(req: MessageReq):
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