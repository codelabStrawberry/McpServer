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
당신은 면접 코치입니다. 채용 공고(JOB POSTING)와 이력서(RESUME)를 바탕으로 맞춤형 면접 질문을 해주세요.
- 질문은 한 번에 하나씩 해주세요.
- 사용자가 답변하면 피드백과 더 나은 답변 예시를 함께 제공해주세요.
- 간결하고 실무 중심으로 진행해주세요.

[JOB POSTING]
{job_text}

[RESUME]
{resume_text}
""".strip()

        SESSION_PROMPTS[sid] = system_prompt

        return {
            "sessionId": sid,
            "jobText": job_text,
            "resumeText": resume_text,    
            "systemPrompt": system_prompt,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"처리 중 오류: {str(e)}")
