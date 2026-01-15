# api/routes/custom.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool

from api.services.extract import extract_pdf_text
from api.services.summarize import summarize_text
from ollama import ollama_chat

router = APIRouter(prefix="/ai/custom", tags=["custom"])


def _split_csv(raw: str) -> List[str]:
    """
    "React, Node.js  MySQL" / "React|Node.js|MySQL" 등 입력을 최대한 유연하게 list로 변환
    """
    s = (raw or "").strip()
    if not s:
        return []
    s = re.sub(r"[\|\n\r\t/]+", ",", s)
    parts = [p.strip() for p in s.split(",")]
    return [p for p in parts if p]


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _fallback_rank(
    jobs: List[Dict[str, Any]],
    *,
    job_tech: List[str],
    job_keyword: List[str],
) -> List[Dict[str, Any]]:
    """
    LLM 결과가 JSON 파싱 실패할 때를 대비한 룰 기반 fallback.
    - 공고의 title/company/keyword/tech 텍스트에 사용자 tech/keyword가 포함되는지로 점수 부여
    """
    tech_l = [t.lower() for t in job_tech]
    kw_l = [k.lower() for k in job_keyword]

    ranked = []
    for j in jobs:
        title = str(j.get("job_title") or j.get("title") or "")
        company = str(j.get("job_company") or j.get("company") or "")
        kw = str(j.get("job_keyword") or j.get("keyword") or "")
        tech = str(j.get("job_tech") or j.get("tech") or "")

        blob = f"{title} {company} {kw} {tech}".lower()

        tech_hits = [t for t in job_tech if t.lower() in blob]
        kw_hits = [k for k in job_keyword if k.lower() in blob]

        score = 0
        score += 8 * len(tech_hits)
        score += 5 * len(kw_hits)

        ranked.append(
            {
                **j,
                "score": min(100, score),
                "matched_tech": tech_hits,
                "matched_keywords": kw_hits,
                "reason": "fallback_rule_based",
            }
        )

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    return ranked


async def _llm_match_jobs(
    *,
    resume_summary: str,
    job_cat: str,
    job_tech: List[str],
    job_keyword: List[str],
    candidates: List[Dict[str, Any]],
    top_k: int,
) -> Dict[str, Any]:
    """
    후보 공고(candidates)를 LLM이 top_k로 재정렬 + 근거 반환
    """
    # LLM에 넘길 후보는 너무 크면 느려지므로 상한을 둡니다.
    MAX_CANDIDATES_FOR_LLM = 30
    short_candidates = candidates[:MAX_CANDIDATES_FOR_LLM]

    # 후보 공고를 최소 필드만 남겨 LLM 입력을 절약
    llm_jobs = []
    for j in short_candidates:
        llm_jobs.append(
            {
                "job_id": j.get("id") or j.get("job_id") or j.get("recruit_id"),
                "job_title": j.get("job_title") or j.get("title"),
                "job_company": j.get("job_company") or j.get("company"),
                "job_url": j.get("job_url") or j.get("url"),
                "job_keyword": j.get("job_keyword") or j.get("keyword"),
                "job_tech": j.get("job_tech") or j.get("tech"),
            }
        )

    prompt = f"""
너는 채용공고 매칭 엔진이다. 아래 입력만 사용해서 '가장 적합한 공고 Top {top_k}'를 선정하라.

[입력]
- 사용자가 선택한 직무 카테고리(job_cat): {job_cat}
- 사용자가 입력/선택한 스킬(job_tech): {job_tech}
- 사용자가 입력/선택한 키워드(job_keyword): {job_keyword}
- 이력서 요약(resume_summary):
{resume_summary}

- 후보 채용공고 목록(candidates, 최대 {len(llm_jobs)}개):
{json.dumps(llm_jobs, ensure_ascii=False)}

[출력 규칙]
- 반드시 JSON만 출력한다. (설명 문장 금지)
- 아래 스키마를 정확히 지켜라.
{{
  "top": [
    {{
      "job_id": "string|number|null",
      "score": 0-100,
      "matched_tech": ["..."],
      "matched_keywords": ["..."],
      "reasons": ["근거를 짧게 2~4개"]
    }}
  ],
  "notes": "짧은 한 줄(선택)"
}}
- score는 상대평가로 0~100.
- candidates에 없는 정보는 절대 만들지 마라.
""".strip()

    res = await ollama_chat(prompt)
    answer = (res.get("answer") or "").strip()

    parsed = _safe_json_loads(answer)
    if parsed is None or "top" not in parsed:
        return {"_parse_failed": True, "raw": answer}

    return parsed


@router.post("/match-jobs")
async def match_jobs(
    file: UploadFile = File(...),
    job_cat: str = Form(...),
    job_tech: str = Form(""),
    job_keyword: str = Form(""),
    # 프론트(또는 Node)가 미리 뽑아준 후보 공고 리스트(JSON 문자열)
    candidates_json: str = Form("[]"),
    top_k: int = Form(8),
    debug: bool = Form(False),
):
    """
    PDF(이력서) + 사용자 선택값(job_cat/job_tech/job_keyword) + 후보 공고 리스트를 받아
    Top-K 공고 매칭 결과를 반환한다.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF만 업로드 가능합니다.")

    # 1) 후보 공고 파싱
    try:
        candidates = json.loads(candidates_json or "[]")
        if not isinstance(candidates, list):
            raise ValueError("candidates_json must be a list")
    except Exception:
        raise HTTPException(status_code=400, detail="candidates_json이 올바른 JSON 배열이 아닙니다.")

    if not candidates:
        raise HTTPException(status_code=422, detail="후보 공고(candidates)가 비어 있습니다. 먼저 공고를 조회해서 넘겨주세요.")

    # 2) 사용자 입력 파싱
    job_tech_list = _split_csv(job_tech)
    job_keyword_list = _split_csv(job_keyword)

    # 3) PDF bytes 읽기
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="업로드된 PDF가 비어 있습니다.")

    # 4) extract -> summarize (chat.py 패턴 참고: run_in_threadpool + summarize_text) :contentReference[oaicite:5]{index=5}
    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    if not resume_text or "추출하지 못했습니다" in resume_text:
        raise HTTPException(status_code=422, detail="PDF에서 텍스트를 추출하지 못했습니다.")

    resume_summary = await summarize_text(resume_text, language="ko", style="structured")

    # 5) LLM 매칭(Top-K)
    llm_out = await _llm_match_jobs(
        resume_summary=resume_summary,
        job_cat=job_cat,
        job_tech=job_tech_list,
        job_keyword=job_keyword_list,
        candidates=candidates,
        top_k=max(1, min(int(top_k), 20)),
    )

    # 6) LLM 파싱 실패 시 fallback 랭킹 제공
    if llm_out.get("_parse_failed"):
        ranked = _fallback_rank(
            candidates,
            job_tech=job_tech_list,
            job_keyword=job_keyword_list,
        )
        top = ranked[: max(1, min(int(top_k), 20))]
        resp = {"matches": top, "mode": "fallback_rule_based"}
        if debug:
            resp["debug"] = {
                "raw_llm": llm_out.get("raw"),
                "resume_summary": resume_summary,
            }
        return resp

    # LLM이 준 top을 원본 candidates와 조인해서 필요한 메타데이터 보강
    id_to_job = {}
    for j in candidates:
        jid = j.get("id") or j.get("job_id") or j.get("recruit_id")
        id_to_job[str(jid)] = j

    enriched = []
    for item in llm_out.get("top", []):
        jid = item.get("job_id")
        base = id_to_job.get(str(jid), {})
        enriched.append(
            {
                **base,
                "score": item.get("score"),
                "matched_tech": item.get("matched_tech", []),
                "matched_keywords": item.get("matched_keywords", []),
                "reasons": item.get("reasons", []),
            }
        )

    resp = {"matches": enriched[: max(1, min(int(top_k), 20))], "mode": "llm_rerank"}
    if debug:
        resp["debug"] = {"resume_summary": resume_summary}
    return resp
