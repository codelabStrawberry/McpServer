from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from api.services.crawl import crawl_url
from ollama import ollama_chat
from pydantic import BaseModel, HttpUrl

router = APIRouter()

class ResumeAnalyzeRequest(BaseModel):
    jc_code: str
    job_name: str | None = None
    url: HttpUrl
    resume_text: str
    
@router.post("/analyze")
async def analyze(req: ResumeAnalyzeRequest):
  if not req.jc_code:
    raise HTTPException(status_code=400, detail="jc_code가 필요합니다.")
  
  if not req.url:
      raise HTTPException(status_code=400, detail="채용공고 URL이 필요합니다.")
  
  text = (req.resume_text or "").strip()
  if len(text) < 200:
    raise HTTPException(status_code=400, detail="resume_text는 최소 200자 이상이어야 합니다.")
  if len(text) > 4000:
    raise HTTPException(status_code=400, detail="resume_text는 최대 4000자까지 허용합니다.")
  
  job_posting_text = ""
  try:
      job_posting_text = await run_in_threadpool(crawl_url, str(req.url))
  except Exception:
        job_posting_text = "채용공고 크롤링에 실패했습니다."
        
  job_label = req.job_name or req.jc_code
  
  
  prompt = f"""
너는 전문 자기소개서/면접 코치야.
아래 [직무], [채용공고], [자기소개서]를 바탕으로 '구체적이고 실행 가능한 피드백'을 제공해.

출력 형식(꼭 지켜):
1) 한줄 총평
2) 강점 3가지 (근거 문장 포함)
3) 개선점 3가지 (왜 문제인지 + 어떻게 고칠지)
4) 문장 개선 예시 3개 (원문 → 개선문)
5) 직무 적합도 점수(0~100) + 이유

[직무]
{job_label}

[채용공고]
{job_posting_text}

[자기소개서]
{text}
""".strip()

  result = await ollama_chat(prompt)
    
  return{
      "success": True,
      "feedback": result.get("answer", ""),
      "model": result.get("model", ""),
    }
  