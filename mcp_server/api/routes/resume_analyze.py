from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
# from api.services.crawl import crawl_url
from ollama import ollama_chat
from pydantic import BaseModel, HttpUrl
from api.services.get_single_recruit import get_single_recruit
import asyncio
from urllib.parse import urlparse

router = APIRouter()

@router.post("/analyze")
async def make_analyze(
  jc_code: str = Form(...),
  job_name: str | None = Form(None),
  url: str = Form(...),
  resume_text: str = Form(...),
):
  
  # 0) URL 검증/정리
  url = (url or "").strip()
  if not (url.startswith("http://") or url.startswith("https://")):
    raise HTTPException(status_code=400, detail="url은 http:// 또는 https://로 시작해야합니다.")
  
 # 1) 유효성 체크
  if not jc_code:
    raise HTTPException(status_code=400, detail="jc_code가 필요합니다.")
  
  if not url:
      raise HTTPException(status_code=400, detail="채용공고 URL이 필요합니다.")
  
  text = (resume_text or "").strip()
  
  if len(text) < 200:
    raise HTTPException(status_code=400, detail="resume_text는 최소 200자 이상이어야 합니다.")
  if len(text) > 4000:
    raise HTTPException(status_code=400, detail="resume_text는 최대 4000자까지 허용합니다.")
  
 # 3) 채용공고 크롤링(타임아웃)
  jd_text = ""

  try:
    job_crawl = await asyncio.wait_for(get_single_recruit(str(url)), timeout=120)
    
    if not job_crawl or not job_crawl.get("content"):
      jd_text = "채용공고 크롤링 실패했습니다"
    else:
      jd_text = (job_crawl.get("content") or "").strip()
      print("크롤링된 채용공고 텍스트 길이:", len(jd_text))
      print("크롤링된 채용공고 텍스트:", jd_text)
      
  except Exception:
        jd_text = "채용공고 크롤링에 실패했습니다."
        
  job_label = job_name or jc_code
  
  
  prompt = f"""
너는 전문 자기소개서/면접 코치야.
아래 [직무], [채용공고], [자기소개서]를 바탕으로 '구체적이고 실행 가능한 피드백'을 제공해.

[직무]
{job_label}

[채용공고]
{jd_text}

[자기소개서]
{text}

출력 규칙(중요):
- 강점 3가지 (근거 문장 포함)
- 개선점 3가지 (왜 문제인지 + 어떻게 고칠지)
- 추가 조언 1가지만 간략하게 알려주기
- 해설/머리말/추가 설명 금지
- 1500자 이내로 알려주기
""".strip()

  result = await ollama_chat(prompt)
  
  if isinstance(result, dict):
      feedback = result.get("answer", "")
      model = result.get("model", "")
  else:
      feedback = str(result)
      model = ""
    
  return{
      "success": True,
      "feedback": feedback,
      "model": model,
    }
  