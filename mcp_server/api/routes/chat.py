from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool
from urllib.parse import urlparse
from uuid import uuid4

from api.services.crawl import crawl_url
from api.services.extract import extract_pdf_text


router = APIRouter()

SESSION_PROMPTS: dict[str, str] = {}

def _validate_url(url: str) -> None:
  try:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
      raise ValueError("Invalid URL")
  except Exception:
    raise HTTPException(status_code=400, detail="URL 형식이 올바르지 않습니다.")

@router.post("/start")
async def start(
    url: str = Form(...),
    file: UploadFile = File(...),
    session_id: str | None = Form(None),

):
    
    sid = session_id or str(uuid4())

    _validate_url(url)

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    # 1) 파일 bytes 먼저 읽기 (UploadFile은 async read)
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        # 2) 크롤링/추출 병렬 느낌으로 threadpool로 분리 실행
        job_text = await run_in_threadpool(crawl_url, url)
        resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes)
        
        # 3) 시스템 프롬프트(예시) 구성
        system_prompt = f"""
You are an interview coach. Review the job posting (job_text) and the resume (resume_text), then ask customized interview questions.
- Use English for all responses.
- Ask one question at a time.
- After each answer, give feedback and provide an improved sample answer.
- Then move on to the next question.
- Continue this process until the user asks to stop.
- Keep the conversation concise and focused on real-world practice.

[JOB POSTING]
{job_text}

[RESUME]
{resume_text}
""".strip()

        SESSION_PROMPTS[sid] = system_prompt

        return {
            "sessionId": sid,
            # "jobText": job_text,
            # "resumeText": resume_text,    
            # "systemPrompt": system_prompt,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {str(e)}")
