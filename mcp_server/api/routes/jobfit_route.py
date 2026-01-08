from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from ollama import ollama_chat
from pathlib import Path
import uuid

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/")
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

    # 2️⃣ AI 프롬프트 생성
    final_prompt = f"""
너는 유능한 AI 어시스턴트야.
질문에 대해 정확하고 간결하게 답해줘.

[직무]
{job}

[질문]
취업전략에 대해서 설명해줘
""".strip()

    result = await ollama_chat(final_prompt)

    return {
        "job": job,
        "filename": coverLetter.filename,
        "saved_path": str(save_path),
        "response": result,
    }