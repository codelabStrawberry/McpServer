# api/rag/rag.py

from __future__ import annotations

from typing import List
import chromadb
import os
import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from ollama import ollama_chat, ollama_embed, ollama_embed_batch  # async 버전만 사용
from ollama_client import get_client


OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b")

# ChromaDB 클라이언트 (동기)
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")

client = chromadb.PersistentClient(path="./chroma_db")

def _get_client():
    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=500,
            detail="Ollama HTTP client not initialized (startup not executed)"
        )
    return client

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> List[str]:
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    text = text.strip()
    text_len = len(text)

    step = max(1, chunk_size - overlap)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        start += step

    return chunks


def _save_to_chroma_sync(chunks: List[str], embeddings: List[List[float]], collection_name: str) -> None:
    """Chroma 저장은 동기 함수(=threadpool에서 호출)"""
    if not chunks:
        return
    if len(chunks) != len(embeddings):
        raise ValueError("chunks/embeddings 길이가 다릅니다.")

    collection = client.get_or_create_collection(name=collection_name)

    ids = [f"chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"source": "resume", "chunk_index": i} for i in range(len(chunks))]

    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=ids,
        metadatas=metadatas,
    )

    print(f"ChromaDB 저장 완료: {collection_name} (총 {len(chunks)} chunks)")


async def save_to_chroma(text: str, collection_name: str) -> None:
    """
    ✅ /start에서 호출할 함수 (async)
    - 임베딩 생성은 async(메인 루프)
    - Chroma add는 threadpool
    """
    if not text or not text.strip():
        print("저장할 텍스트가 비어있음 → 저장 스킵")
        return

    chunks = chunk_text(text, chunk_size=500, overlap=80)
    if not chunks:
        print("청크가 생성되지 않음 → 저장 스킵")
        return

    # 임베딩은 async로 한 번에 생성
    embeddings = await ollama_embed_batch(chunks)

    # Chroma 저장만 threadpool
    await run_in_threadpool(_save_to_chroma_sync, chunks, embeddings, collection_name)


def _query_chroma_sync(query_embedding: List[float], collection_name: str, top_k: int) -> List[str]:
    """Chroma query는 동기 함수(=threadpool에서 호출)"""
    collection = client.get_collection(name=collection_name)
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    if results and results.get("documents"):
        return results["documents"][0] or []
    return []


async def retrieve_from_chroma(query: str, collection_name: str, top_k: int = 3) -> List[str]:
    """
    ✅ 검색은 async 함수로 제공
    - query 임베딩: async
    - chroma query: threadpool
    """
    try:
        q = (query or "").strip()
        if not q:
            return []

        query_embedding = await ollama_embed(q)
        return await run_in_threadpool(_query_chroma_sync, query_embedding, collection_name, top_k)

    except Exception:
        import traceback
        print(f"ChromaDB 검색 실패 ({collection_name}): {traceback.format_exc()}")
        return []


def delete_chroma_collection(collection_name: str):
    try:
        client.delete_collection(name=collection_name)
        print(f"ChromaDB 컬렉션 삭제 완료: {collection_name}")
    except Exception as e:
        print(f"컬렉션 삭제 실패 ({collection_name}): {e}")


async def rag_ollama_chat(
    base_prompt: str,
    collection_name: str,
    temperature: float = 0.3,
    top_p: float = 0.75,
    repeat_penalty: float = 1.15,
    num_predict: int = 300,          # 너무 긴 답변 방지용으로 기본값 낮춤
    **extra_options
):
    retrieved = await retrieve_from_chroma(base_prompt, collection_name, top_k=3)

    if retrieved:
        rag_context = "\n\n[참고할 자기소개서 관련 내용]\n" + "\n".join(
            f"- {chunk[:300]}..." for chunk in retrieved
        )
        full_prompt = base_prompt + rag_context
    else:
        full_prompt = base_prompt
        print("RAG 검색 결과 없음 → 일반 ollama_chat으로 fallback")

    # 직접 payload 구성
    payload = {
        "model": CHAT_MODEL,
        "prompt": full_prompt.strip(),
        "stream": False,
        "keep_alive": -1,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "repeat_penalty": repeat_penalty,
            "num_predict": 150,
            **extra_options
        }
    }

    # ollama_chat 내부에서 쓰던 동일한 client 재사용
    client = _get_client()  # ollama_chat에서 정의된 함수라고 가정
    # 만약 _get_client()가 접근 불가라면 아래처럼 직접 생성해도 됨
    # client = httpx.AsyncClient()

    res = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)

    if res.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Ollama error: {res.text}"
        )

    data = res.json()

    return {
        "success": True,
        "answer": data.get("response", ""),
        "model": data.get("model", CHAT_MODEL),
        "metadata": {
            "total_duration": data.get("total_duration"),
            "load_duration": data.get("load_duration"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "eval_duration": data.get("eval_duration"),
        },
    }