from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from ollama import ollama_chat
from pathlib import Path
import uuid
from api.services.extract import extract_pdf_text  # 앞서 작성한 PDF 추출 함수
from api.services.crawl import crawl_url
from starlette.concurrency import run_in_threadpool
from api.services.get_single_recruit import get_single_recruit

import re
from collections import defaultdict

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

async def read_pdf_text(file: UploadFile) -> str:
    """
    UploadFile 형태의 PDF 파일을 읽어서 텍스트로 반환합니다.
    """
    # PDF인지 체크 (간단히 MIME 타입으로)
    if file.content_type != "application/pdf":
        return "업로드한 파일이 PDF가 아닙니다."

    # 비동기로 파일 내용 읽기
    file.file.seek(0)  # 파일 포인터 처음으로 되돌리기
    pdf_bytes = await file.read()
    
    print("pdd read len:", len(pdf_bytes))

    # extract_pdf_text 함수로 텍스트 추출
    text = extract_pdf_text(pdf_bytes)

    return text

def find_sentences_with_keywords(text, keywords):
    """
    text: 긴 문자열 (한글도 가능)
    keywords: 찾고 싶은 키워드 리스트 (한글 포함 가능)
    return: {키워드: [문장1, 문장2, ...], ...} 형태의 딕셔너리
    """
    # 한글에서는 줄바꿈도 문장 구분으로 포함
    sentences = re.split(r'(?<=[.!?])\s*', text)
    
    result = defaultdict(list)
    
    for sentence in sentences:
        lower_sentence = sentence.lower()
        for kw in keywords:
            if kw.lower() in lower_sentence:
                result[kw].append(sentence.strip())
    
    return dict(result)


keywords = ["모집", "자격", "우대"]

def extract_language_text(text: str) -> str:
    """
    크롤링된 텍스트에서
    - 한글, 영어만 유지
    - 특수문자 제거
    - 공백 정리
    """
    # 1. 한글, 영어, 공백만 남기기
    cleaned = re.sub(r"[^가-힣a-zA-Z\s]", " ", text)

    # 2. 연속 공백 제거
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()

def extract_job_text(job: dict) -> str:
    fields = [
        job.get("title", ""),
        job.get("company", ""),
        " ".join(job.get("job_category", [])),
        job.get("content", "")
    ]

    text = " ".join(fields)

    cleaned = re.sub(r"[^가-힣a-zA-Z\s]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()



@router.post("/jobfit")
async def jobfit(
    job: str = Form(...),
    url: str = Form(None),
    coverLetter: UploadFile = File(...)
):
    # 1️⃣ 파일 저장
    file_ext = Path(coverLetter.filename).suffix
    save_name = f"{uuid.uuid4()}{file_ext}"
    save_path = UPLOAD_DIR / save_name

    with open(save_path, "wb") as f:
        f.write(await coverLetter.read())

    
    print("job:", job)
    print("url:", url)
    print("filename:", coverLetter.filename)
    print("saved:", save_path)
    
    pdftext = await read_pdf_text(coverLetter)
    print("pdftext:", pdftext[:100])
    
     # crawl
    job_text = await get_single_recruit(url)
    if not job_text:
        print("crawl: EMPTY or None")
    else:
        print(f"crawl: {job_text}")
        job_text = extract_job_text(job_text)
        print(f"crawl2: {job_text}")   
    

    # 2️⃣ AI 프롬프트 생성
    final_prompt = f"""
너는 유능한 AI 어시스턴트야.
질문에 대해 정확하고 간결하게 답해줘.

[직무]
{job}

[취업공고]
{job_text}
여기에 지원할꺼야!!

[자기소개서]
{pdftext}

[질문]
취업 전략에 대한 종합적인 피드백을 요약해줘
""".strip()

    result = await ollama_chat(final_prompt)

    return {
        "job": job,
        "filename": coverLetter.filename,
        "saved_path": str(save_path),
        "response": result,
    }