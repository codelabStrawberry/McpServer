# rag.py
from chroma_db import search
from ollama import ollama_chat

async def rag_chat(question: str):
    docs = await search(question)

    context = "\n".join(docs) if docs else ""

    prompt = f"""
다음 문맥을 참고해서 질문에 답해줘.

[문맥]
{context}

[질문]
{question}
"""

    return await ollama_chat(prompt)