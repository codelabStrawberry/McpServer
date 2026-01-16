import re
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool
from pydantic import HttpUrl

from api.services.extract import extract_pdf_text
from api.services.crawl import crawl_url
from ollama import ollama_chat
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

def _parse_questions(raw: str, limit: int = 5) -> list[str]:
  """
  LLM 출력이 번호/블릿/줄바꿈 형태여도 질문 리스트로 최대한 파싱
  """
  lines = [l.strip() for l in (raw or "").splitlines() if l.strip()]
  out: list[str] = []
  for l in lines:
        l = re.sub(r"^\s*[-•]\s*", "", l)          # bullet 제거
        l = re.sub(r"^\s*\d+\s*[.)]\s*", "", l)    # 1. / 1) 제거
        if len(l) >= 6:
            out.append(l)
        if len(out) >= limit:
            break
  return out

async def _call_ollama(prompt: str):
  """
  ollama_chat이 async일 수도, sync일 수도 있는 환경을 방어적으로 처리
  resume_analyze.py에서는 await ollama_chat(prompt) 형태라 async일 가능성이 큼.
  """
  import inspect
  
  if inspect.iscoroutinefunction(ollama_chat):
    return await ollama_chat(prompt)
  return await run_in_threadpool(ollama_chat, prompt)
  
@router.post("/questions")
async def make_questions(
  jc_code: str = Form(...),
  job_name: str | None = Form(None),
  url: HttpUrl = Form(...),
  file: UploadFile = File(...),
  n_questions: int = Form(4),
):
  # 1) 유효성 체크
  if not jc_code:
      raise HTTPException(status_code=400, detail="jc_code가 필요합니다.")
  if file.content_type != "application/pdf":
      raise HTTPException(status_code=400, detail="PDF만 업로드 가능합니다.")
  if n_questions < 4 or n_questions > 15:
      raise HTTPException(status_code=400, detail="n_questions는 4~15 사이여야 합니다.")
    
  # 1) PDF bytes 읽기
  pdf_bytes = await file.read()
  if not pdf_bytes:
      raise HTTPException(status_code=400, detail="업로드된 파일이 비어있습니다.") 
  
  # 2) extract.py 사용해서 텍스트 추출 (동기 함수 -> threadpool)
  resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes)
  resume_text = (resume_text or "").strip()
  
  if not resume_text or "추출하지 못했습니다" in resume_text or resume_text == "Not text":
      raise HTTPException(status_code=400, detail="PDF 텍스트 추출에 실패했습니다.")
  if len(resume_text) < 200:
      raise HTTPException(status_code=400, detail="추출된 텍스트가 너무 짧습니다(200자 미만).")
  if len(resume_text) > 8000:
      resume_text = resume_text[:8000]
  
  # 3) 채용공고 크롤링(타임아웃)
  try:
      jd_text = await asyncio.wait_for(
        run_in_threadpool(crawl_url, str(url)),
        timeout=120,
      )
  except Exception:
      jd_text = "채용공고 크롤링에 실패했습니다."
      
  job_label = job_name or jc_code
  
  # 3) 프롬포트
  prompt = f"""
너는 채용 면접관이다. 사용자의 입력(직무/채용공고/자기소개서)을 분석해 "면접 예상 질문"만 생성한다.
절대 요약하지 마라. 절대 해설/답변/머리말/부연설명/카테고리 제목을 쓰지 마라.
반드시 물음표 "?" 로 끝나는 문장만 출력하라.

출력 규칙(중요):
- 질문은 총 {n_questions}개
- 한 줄에 질문 1개
- 해설/머리말/추가 설명 금지
- 리스트 형태로 출력해줘.
- 반드시 물음표 "?" 로 끝나는 문장만 출력해줘

[직무]
{job_label}

[채용공고]
{jd_text}

[자기소개서]
{resume_text}
""".strip()

  # 4) Ollama 호출
  try:
    result = await asyncio.wait_for(_call_ollama(prompt), timeout=120)
  except Exception:
    raise HTTPException(status_code=504, detail="LLM 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.")
  
  raw = ""
  model = ""
  if isinstance(result, dict):
    model = result.get("model", "") or ""
    raw = (
      result.get("answer", "") 
      or result.get("content") 
      or (result.get("message", {}) or {}).get("content")
      or result.get("response")
      or ""
      )
  else:
      raw = str(result)
  raw = (raw or "").strip()

    
  questions = _parse_questions(raw, limit=n_questions)
  print("parsed questions:", questions)
  if not questions:
    questions = ["지원 동기와 해당 직무에서 본인의 강점을 설명해 주세요."]
    
  return {
      "success": True,
      "questions": questions,
      "resume_text": resume_text,
      "jd_text": jd_text,  # (선택) 프론트에서 저장 가능
      "model": model, # 디버깅용
      "raw": raw,
    }

class InterviewFeedbackRequest(BaseModel):
  jc_code: str
  job_name: Optional[str] = None
  url: HttpUrl
  resume_text: str
  jd_text: Optional[str] = None
  question: str
  user_answer: str
  
@router.post("/feedback")
async def make_feedback(req: InterviewFeedbackRequest):
  # 1) validate
  if not req.jc_code:
    raise HTTPException(status_code=400, detail="jc_code가 필요합니다.")
  
  resume_text = (req.resume_text or "").strip()
  if len(resume_text) < 200:
    raise HTTPException(status_code=400, detail="resume_text는 최소 200자 이상이어야 합니다.")
  if len(resume_text) > 8000:
    resume_text = resume_text[:8000]
    
  q = (req.question or "").strip()
  if not q:
    raise HTTPException(status_code=400, detail="question이 필요합니다.")
  
  user_answer = (req.user_answer or "").strip()
  if len(user_answer) < 20:
    raise HTTPException(status_code=400, detail="user_answer는 최소 20자 이상이어야 합니다.")
  if len(user_answer) > 2000:
    user_answer = user_answer[:2000]
    
  # 2) jd text 확보 (프론트가 보내면 우선 사용)
  jd_text = (req.jd_text or "").strip()
  if not jd_text:
    try:
      jd_text = await asyncio.wait_for(
        run_in_threadpool(crawl_url, str(req.url)),
        timeout=120,
      )
    except Exception:
      jd_text = ""
      
  job_label = req.job_name or req.jc_code
      
# 3) prompt (피드백만, 구조화)
  prompt = f"""
너는 면접 코치다. 아래 입력을 바탕으로 "지원자의 답변 피드백"을 한국어로 작성해라.
절대 면접관 역할극을 하지 말고, 평가/개선 중심으로 코칭하라.

출력 형식(중요): 아래 섹션 제목을 그대로 사용해서 작성
1) 한줄총평: (1문장)
2) 잘한점: (불릿 3개)
3) 아쉬운점: (불릿 3개)
4) JD매칭: (채용공고 키워드/역량 관점에서 빠진 요소 2~3개)
5) STAR보완: (S/T/A/R 각각 1~2문장으로 보완 제안)
6) 개선된 답변 예시: (사용자 답변을 기반으로 60~90초 분량, 8~12문장, 사실을 지어내지 말 것)

규칙:
- 자기소개서/채용공고에 없는 사실은 만들어내지 말 것 (없으면 일반화해서 표현)
- 군더더기 인사말/머리말/면접질문 재진술 금지
- 위 섹션 외의 내용 추가 금지

[직무]
{job_label}

[채용공고]
{jd_text}

[자기소개서]
{resume_text}

[면접 질문]
{q}

[사용자 답변]
{user_answer}
""".strip()

  try:
    result = await asyncio.wait_for(_call_ollama(prompt), timeout=120)
  except Exception:
      raise HTTPException(status_code=504, detail="LLM 응답이 지연되고 있습니다. 잠시 후 다시 시도해주세요.")
    
  model = ""
  if isinstance(result, dict):
      feedback = result.get("answer", "") or result.get("content", "") or ""
      model = result.get("model") or ""
  else:
      feedback = str(result)
      
  feedback = (feedback or "").strip()
  if not feedback:
      raise HTTPException(status_code=500, detail="빈 피드백이 반환되었습니다.")
    
  return {
      "success": True,
      "feedback": feedback,
      "model": model,
      "question": q,
    }
      
    
    