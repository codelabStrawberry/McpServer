# api/services/summarize.py
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Literal

from ollama import ollama_chat


def _chunk_text(text: str, max_chars: int = 6000) -> List[str]:
    """
    긴 텍스트를 문단 단위로 최대한 자연스럽게 분할
    """
    text = (text or "").strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    parts = re.split(r"\n{2,}", text)
    chunks: List[str] = []
    buf: List[str] = []
    cur = 0

    for p in parts:
        p = p.strip()
        if not p:
            continue

        add_len = len(p) + (2 if buf else 0)
        if cur + add_len > max_chars and buf:
            chunks.append("\n\n".join(buf))
            buf = [p]
            cur = len(p)
        else:
            buf.append(p)
            cur += add_len

    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


async def summarize_text(
    text: str,
    *,
    language: str = "korean",
    style: Literal["bullet", "structured"] = "structured",
    max_chunk_chars: int = 6000,
) -> str:
    """
    긴 텍스트도 안정적으로 요약:
    - chunk 요약 -> 최종 통합 요약
    """
    text = (text or "").strip()
    if not text:
        return ""

    chunks = _chunk_text(text, max_chars=max_chunk_chars)
    if not chunks:
        return ""

    chunk_summaries: List[str] = []
    for i, ch in enumerate(chunks, start=1):
        prompt = f"""
너는 유능한 어시스턴트이다.
다음 문서 텍스트를 {language}로 요약해 주세요.

규칙:
- 주요 사실만 유지하세요.
- 숫자, 날짜, 이름, 중요한 개체(entity)는 반드시 보존하세요.
- 텍스트에 없는 정보는 절대 추가하지 마세요.
- 출력 스타일: {"bullet points" if style=="bullet" else "structured sections"}.

Text (part {i}/{len(chunks)}):
{ch}
""".strip()
        chunk_summaries.append((await ollama_chat(prompt))["answer"])

    if len(chunk_summaries) == 1:
        return chunk_summaries[0].strip()

    combined = "\n\n".join(
        f"[Part {i} Summary]\n{s}" for i, s in enumerate(chunk_summaries, start=1)
    )

    final_prompt = f"""
너는 유능한 어시스턴트이다.
부분 요약들을 하나의 최종 요약으로 통합해 주세요. {language}로 작성해 주세요.

규칙:
- 중복된 내용은 제거하세요.
- 간결하면서도 완전하게 유지하세요.
- 중요한 구체적인 정보(숫자, 날짜, 이름, 개체 등)는 반드시 보존하세요.
- 출력 스타일: {"bullet points" if style=="bullet" else "structured sections"}.

Partial summaries:
{combined}
""".strip()

    final_response = await ollama_chat(final_prompt)
    return final_response["answer"].strip() if final_response else ""