from chroma_db import search
from ollama import ollama_chat


async def rag_chat(question: str):
    docs = await search(question)

    # 기본 프롬프트 (문맥 없어도 동작)
    prompt = f"""
너는 유능한 AI 어시스턴트야.
질문에 대해 정확하고 간결하게 답해줘.

[질문]
{question}
"""

    # 문맥이 있을 경우만 RAG 프롬프트로 확장
    if docs:
        context = "\n".join(docs)
        prompt = f"""
너는 문서 기반 RAG 어시스턴트야.
아래 문맥을 참고해서 질문에 답해줘.
문맥에 없는 내용은 추측하지 말고, 모르면 모른다고 말해.

[문맥]
{context}

[질문]
{question}
"""

    return await ollama_chat(prompt)
