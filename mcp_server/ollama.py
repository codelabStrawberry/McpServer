# ollama.py
import os
import httpx
from fastapi import HTTPException
import asyncio

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:1b")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

async def ollama_embed(text: str) -> list[float]:
    """
    단일 텍스트 → embedding vector
    """
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="embedding text가 비어있음")

    payload = {
        "model": EMBED_MODEL,
        "prompt": text.strip()
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        res = await client.post(f"{OLLAMA_URL}/api/embeddings", json=payload)

    if res.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama embedding error: {res.text}"
        )

    return res.json()["embedding"]


async def ollama_embed_batch(texts: list[str]) -> list[list[float]]:
    """
    여러 텍스트 → embedding vectors
    (Ollama는 batch 미지원 → client에서 gather)
    """
    if not texts:
        return []

    return await asyncio.gather(
        *(ollama_embed(text) for text in texts)
    )

    
async def ollama_chat(prompt: str):
    if not prompt or prompt.strip() == "":
        raise HTTPException(status_code=400, detail="prompt 값이 없다")

    payload = {
        "model": CHAT_MODEL,
        "prompt": prompt.strip(),
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 1000
        }
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload
            )

        if res.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"Ollama error: {res.text}"
            )

        data = res.json()

        return {
            "success": True,
            "question": prompt,
            "answer": data.get("response", ""),
            "model": data.get("model", CHAT_MODEL),
            "metadata": {
                "total_duration": data.get("total_duration"),
                "load_duration": data.get("load_duration"),
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
                "eval_duration": data.get("eval_duration")
            }
        }

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama 서버 연결 실패")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama 서버 타임아웃")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama 통신 에러: {str(e)}")
