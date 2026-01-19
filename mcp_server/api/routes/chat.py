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

# from api.services.crawl import crawl_url
from api.services.get_single_recruit import get_single_recruit
from api.services.extract import extract_pdf_text
from api.services.summarize import summarize_text
from ollama import ollama_chat, ollama_embed_batch  # 기존 ollama_chat 유지 (fallback용)
from api.rag.rag import rag_ollama_chat, save_to_chroma, delete_chroma_collection, chunk_text

router = APIRouter()

TTL_SECONDS = 60 * 60  # 1 hour

PROMPT_KEY = "session:prompt:{sid}"
HISTORY_KEY = "session:history:{sid}"
STARTED_KEY = "session:started:{sid}"
TOPIC_TURN_KEY = "session:topic_turn:{sid}"  # 꼬리질문 카운트용
MAX_FOLLOWUPS = 2  # 꼬리질문 2번 하고 나면 새 질문으로 전환

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
너는 특정 회사의 채용 면접을 진행하는 **실무 면접관**이다.

[역할]
- 너는 항상 지원자를 평가하는 면접관 역할만 한다.
- 절대 지원자 대신 답변을 말하지 않는다.
- ‘면접 연습용 챗봇’이라는 사실은 언급하지 않는다.
- 항상 자연스러운 한국어로만 짧게 말한다.

[대화 원칙]
- 한 번에 한 개의 질문만 한다.
- 불필요한 인사말, 잡담, 장황한 설명을 붙이지 않는다.
- 지원자의 이전 답변을 그대로 복붙하거나 길게 요약하지 않는다.
- 채용공고와 이력서 내용을 그대로 읽어주거나 나열하지 않는다.
- 과한 칭찬(“완벽합니다”, “정말 좋네요”)은 피하고, **간단한 피드백 + 다음 질문** 구조를 유지한다.

[참고 자료]
- 아래 채용공고와 이력서 요약을 바탕으로, 실제 면접처럼 질문을 설계한다.
- 다만, 원문 문장을 그대로 읽거나 나열하지 말고, 질문에만 참고자료로 활용한다.

[채용공고 요약]
{job_text}

[이력서 요약]
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
    job_crawl = await get_single_recruit(url)
    job_text = job_crawl["content"]
    print(job_text)
    # print("타입은?", type(job_text))

    # 3) extract
    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    # print("이력서 타입은?", type(resume_text))

    # 4) summary (기존 요약 유지)
    resume_summary = await summarize_text(resume_text, language="ko", style="structured")

    # 5) system prompt 생성 + 저장
    system_prompt = _build_system_prompt(job_text=job_text, resume_text=resume_summary)
    await redis_client.set(PROMPT_KEY.format(sid=sid), system_prompt, ex=TTL_SECONDS)

    # 6) 세션 상태 초기화 (Redis)
    await redis_client.set(STARTED_KEY.format(sid=sid), "False", ex=TTL_SECONDS)
    await redis_client.set(TOPIC_TURN_KEY.format(sid=sid), "0", ex=TTL_SECONDS)
    history = [{"role": "assistant", "content": READY_MESSAGE}]
    await redis_client.set(
        HISTORY_KEY.format(sid=sid),
        json.dumps(history, ensure_ascii=False),
        ex=TTL_SECONDS,
    )

    # 추가: ChromaDB에 resume_text 저장 (RAG용)
    collection_name = f"resume_{sid}"
    try:
        await save_to_chroma(resume_text, collection_name)
    except Exception as e:
        # ChromaDB 실패 시 로그만 남기고 진행 (종속되지 않음)
        print(f"ChromaDB 저장 실패: {e}")

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
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    if isinstance(history_json, (bytes, bytearray)):
        history_json = history_json.decode("utf-8")

    started_b = await redis_client.get(STARTED_KEY.format(sid=sid))
    started_s = "False" if started_b is None else (
        started_b.decode("utf-8") if isinstance(started_b, (bytes, bytearray)) else str(started_b)
    )

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

    if not user_text:
        raise HTTPException(status_code=400, detail="message가 비어 있습니다.")

    # Redis에서 prompt 확인 (세션 존재 여부)
    system_prompt_b = await redis_client.get(PROMPT_KEY.format(sid=sid))
    if not system_prompt_b:
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다. 먼저 /chat/start를 호출하세요.",
        )

    if isinstance(system_prompt_b, (bytes, bytearray)):
        system_prompt = system_prompt_b.decode("utf-8")
    else:
        system_prompt = str(system_prompt_b)

    # history 로드
    history_json = await redis_client.get(HISTORY_KEY.format(sid=sid))
    if history_json and isinstance(history_json, (bytes, bytearray)):
        history_json = history_json.decode("utf-8")
    history = json.loads(history_json) if history_json else []

    # 사용자 메시지 추가
    history.append({"role": "user", "content": user_text})

    # started 로드
    started_b = await redis_client.get(STARTED_KEY.format(sid=sid))
    started_s = "False" if started_b is None else (
        started_b.decode("utf-8") if isinstance(started_b, (bytes, bytearray)) else str(started_b)
    )
    started = started_s == "True"

    # 시작 트리거 처리 (아직 started=False 인 상태)
    if not started:
        if _is_start_trigger(user_text):
            await redis_client.set(STARTED_KEY.format(sid=sid), "True", ex=TTL_SECONDS)
            await redis_client.set(TOPIC_TURN_KEY.format(sid=sid), "0", ex=TTL_SECONDS)

            prompt = f"""
{system_prompt}

[이번 턴의 목표]
- 지금부터 **첫 번째 면접 질문**을 만든다.
- 지원자의 이력서와 채용공고를 참고하여, 가장 기본이 되는 질문 1개만 작성한다.

[출력 형식]
- 오직 질문 1문장만 출력한다.
- 설명, 인사말, 앞뒤 문장은 절대 쓰지 않는다.
- 30자를 넘지 않는 자연스러운 한국어 문장으로 작성한다.
- 반드시 물음표(?)로 끝나야 한다.
- 두 개 이상의 질문을 한 문장에 넣지 않는다.

위 조건을 만족하는 첫 질문 1개만 출력해라.
""".strip()

            collection_name = f"resume_{sid}"
            res = await rag_ollama_chat(
                base_prompt=prompt,
                collection_name=collection_name,
                temperature=0.0,           # 0.0으로 고정 (창의성 완전 차단)
                top_p=0.1,
                repeat_penalty=1.5,        # 반복/장황함 강하게 억제
                num_predict=120
                )
            answer = (res.get("answer") or "").strip() or "좋습니다. 먼저 자기소개를 1분 정도로 해주세요."

            history.append({"role": "assistant", "content": answer})
            await redis_client.set(
                HISTORY_KEY.format(sid=sid),
                json.dumps(history, ensure_ascii=False),
                ex=TTL_SECONDS,
            )

            return {"sessionId": sid, "answer": answer}

        # 아직 시작 전이면 READY_MESSAGE 반복
        answer = READY_MESSAGE
        history.append({"role": "assistant", "content": answer})
        await redis_client.set(
            HISTORY_KEY.format(sid=sid),
            json.dumps(history, ensure_ascii=False),
            ex=TTL_SECONDS,
        )
        return {"sessionId": sid, "answer": answer}

    # === 여기부터는 started == True, 면접 진행 중 ===

    # 꼬리질문 카운트 로드
    topic_turn_b = await redis_client.get(TOPIC_TURN_KEY.format(sid=sid))
    topic_turn_s = "0" if topic_turn_b is None else (
        topic_turn_b.decode("utf-8") if isinstance(topic_turn_b, (bytes, bytearray)) else str(topic_turn_b)
    )
    topic_turn = int(topic_turn_s) if topic_turn_s.isdigit() else 0

    collection_name = f"resume_{sid}"

    # 1) 아직 꼬리질문 횟수가 MAX_FOLLOWUPS 미만이면 → 같은 주제에 대한 follow-up
    if topic_turn < MAX_FOLLOWUPS:
        prompt = f"""
{system_prompt}

너는 이제 방금 직전에 지원자가 한 답변에 대해
1) 아주 짧은 피드백
2) 같은 주제에 대한 꼬리질문 1개
를 생성해야 한다.

[중요 제약]
- 지원자의 답변을 대신 말하거나 재구성하지 않는다.
- “좋은 답변이네요”, “아주 훌륭합니다” 같은 과한 칭찬은 피한다.
- “자, 그럼”, “네, 좋습니다” 같은 군더더기 연결어를 쓰지 않는다.
- RAG로 참고한 이력서 내용을 그대로 읽어주지 않는다.
- 오직 **현재 주제**에 대한 꼬리질문만 한다. 새 주제로 바꾸지 않는다.
- 전체 출력은 반드시 2줄이어야 한다.

[참고용 최근 대화 일부]
{_format_history(history)}

위 형식을 절대 어기지 말고,
정확히 2줄만 출력해라.
""".strip()


        res = await rag_ollama_chat(
            base_prompt=prompt,
            collection_name=collection_name,
            temperature=0.0,           # 0.0으로 고정 (창의성 완전 차단)
            top_p=0.1,
            repeat_penalty=1.5,        # 반복/장황함 강하게 억제
            num_predict=120
            )
        answer = res.get("answer", "").strip()
        if not answer:
            answer = "좋은 답변이에요. 조금 더 구체적으로 상황(S), 과제(T), 행동(A), 결과(R)를 나눠서 설명해줄 수 있을까요?"

        topic_turn += 1
        await redis_client.set(
            TOPIC_TURN_KEY.format(sid=sid),
            str(topic_turn),
            ex=TTL_SECONDS,
        )

    # 2) 꼬리질문을 충분히 한 경우 → 새로운 주제의 질문으로 전환
    else:
        prompt = f"""
{system_prompt}

이제 방금까지 이야기하던 주제와는 **다른 새로운 주제**로 질문을 바꿔야 한다.
지원자의 이력서와 채용공고를 참고하여,
다른 역량이나 다른 경험을 묻는 새로운 질문을 만들어라.

[중요 제약]
- 직전 답변에 대한 긴 평가나 요약, 감상문을 쓰지 않는다.
- “이제 다른 질문을 드리겠습니다” 같은 메타 멘트를 쓰지 않는다.
- 지원자의 답변을 다시 정리하거나 대신 말하지 않는다.
- 이전과 **완전히 다른 주제**가 되도록 한다. (예: 협업 → 갈등 해결, 실패 경험 → 성과 경험 등)
- 전체 출력은 반드시 2줄이어야 한다.

[출력 형식 – 반드시 이 형식 그대로]
1줄째: 아주 짧은 연결 코멘트 또는 비워둔 한 줄 (최대 10자)
       예) “좋습니다”, “다른 경험도 듣고 싶어요” 등
2줄째: 새로운 주제의 면접 질문 1개 (최대 35자, 반드시 물음표로 끝남)

[참고용 최근 대화 일부]
{_format_history(history)}

위 형식에서 벗어나지 말고,
정확히 2줄만 출력해라.
""".strip()

        res = await rag_ollama_chat(
            base_prompt=prompt,
            collection_name=collection_name,
            temperature=0.0,           # 0.0으로 고정 (창의성 완전 차단)
            top_p=0.1,
            repeat_penalty=1.5,        # 반복/장황함 강하게 억제
            num_predict=120
            )
        answer = res.get("answer", "").strip()
        if not answer:
            answer = "좋습니다. 다른 경험 하나를 골라서, 본인이 가장 성장했다고 느낀 순간을 이야기해 주실 수 있을까요?"

        # 새 주제로 넘어갔으니 꼬리질문 카운트 리셋
        topic_turn = 0
        await redis_client.set(
            TOPIC_TURN_KEY.format(sid=sid),
            str(topic_turn),
            ex=TTL_SECONDS,
        )

    # 공통: history 저장
    history.append({"role": "assistant", "content": answer})
    try:
        await redis_client.set(
            HISTORY_KEY.format(sid=sid),
            json.dumps(history, ensure_ascii=False),
            ex=TTL_SECONDS,
        )
        # 디버깅용 로그
        saved = await redis_client.get(HISTORY_KEY.format(sid=sid))
        if saved:
            saved_decoded = saved.decode("utf-8") if isinstance(saved, bytes) else saved
            print(f"Redis 저장 확인: {len(json.loads(saved_decoded))} 메시지")
    except Exception as redis_err:
        print(f"Redis 저장 실패: {redis_err}")

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
    await redis_client.delete(TOPIC_TURN_KEY.format(sid=sid))

    # 추가: ChromaDB 컬렉션 삭제
    collection_name = f"resume_{sid}"
    try:
        await run_in_threadpool(delete_chroma_collection, collection_name)
    except Exception as e:
        print(f"ChromaDB 삭제 실패: {e}")

    return {"sessionId": sid, "status": "terminated"}
