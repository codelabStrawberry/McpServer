# api/routes/custom.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import aiomysql
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool

from api.services.extract import extract_pdf_text
from api.services.summarize import summarize_text
from ollama import ollama_chat

router = APIRouter(prefix="/ai/custom", tags=["custom"])

_pool: Optional[aiomysql.Pool] = None


def _env_any(*names: str, default: Optional[str] = None, required: bool = True) -> str:
    """
    여러 환경변수 후보 중 먼저 설정된 값을 반환한다.
    예) _env_any("MYSQL_HOST", "DB_HOST")
    """
    for name in names:
        v = os.getenv(name)
        if v is not None and str(v).strip() != "":
            return v

    if default is not None:
        return default

    if required:
        raise RuntimeError(f"환경변수 {', '.join(names)} 중 하나가 설정되어 있지 않습니다.")

    return ""


async def _get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is not None:
        return _pool


    host = _env_any("MYSQL_HOST", "DB_HOST")
    port = int(_env_any("MYSQL_PORT", "DB_PORT", default="3307"))
    user = _env_any("MYSQL_USER", "DB_USER")
    password = _env_any("MYSQL_PASSWORD", "DB_PASSWORD", default="", required=False)
    db = _env_any("MYSQL_DB", "DB_NAME")

    _pool = await aiomysql.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        charset="utf8mb4",
        autocommit=True,
        minsize=1,
        maxsize=int(os.getenv("DB_POOL_MAX", "10")),
        cursorclass=aiomysql.DictCursor,
    )
    return _pool


@router.on_event("shutdown")
async def _shutdown_pool():
    global _pool
    if _pool is None:
        return
    _pool.close()
    await _pool.wait_closed()
    _pool = None


async def _table_exists(conn: aiomysql.Connection, table: str) -> bool:
    async with conn.cursor() as cur:
        await cur.execute("SHOW TABLES LIKE %s", (table,))
        row = await cur.fetchone()
        return row is not None


async def _resolve_recruit_table(conn: aiomysql.Connection) -> str:
    if await _table_exists(conn, "job_trend"):
        return "job_trend"
    if await _table_exists(conn, "job_recruit"):
        return "job_recruit"
    raise RuntimeError("공고 테이블(job_trend 또는 job_recruit)을 찾을 수 없습니다.")


async def _get_columns(conn: aiomysql.Connection, table: str) -> List[str]:
    async with conn.cursor() as cur:
        await cur.execute(f"SHOW COLUMNS FROM `{table}`")
        rows = await cur.fetchall()
    return [r["Field"] for r in rows]


def _pick_col(cols: set[str], candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return c
    return None


def _normalize_term_list(terms: List[str]) -> List[str]:
    out: List[str] = []
    for t in terms:
        t = (t or "").strip()
        if not t:
            continue
        t = re.sub(r"\s+", " ", t)
        out.append(t)

    uniq: List[str] = []
    seen = set()
    for t in out:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    return uniq


async def _fetch_candidates_from_db(
    *,
    job_cat: str,
    job_tech: List[str],
    job_keyword: List[str],
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    job_trend/job_recruit에서 후보 공고 조회.
    반환 dict는 통일 키를 최대한 제공:
      id, recruit_id, job_cat, job_title, job_company, jobiwg_url, job_keyword, job_tech
    """
    job_tech = _normalize_term_list(job_tech)
    job_keyword = _normalize_term_list(job_keyword)

    pool = await _get_pool()
    async with pool.acquire() as conn:
        table = await _resolve_recruit_table(conn)
        cols_list = await _get_columns(conn, table)
        cols = set(cols_list)

        id_col = _pick_col(cols, ["id", "recruit_id", "job_id"])
        cat_col = _pick_col(cols, ["job_big", "job_cat", "job_category", "jc_name", "name"])
        title_col = _pick_col(cols, ["job_title", "title"])
        company_col = _pick_col(cols, ["job_company", "company"])
        url_col = _pick_col(cols, ["job_url", "url", "link"])
        keyword_col = _pick_col(cols, ["job_keyword", "keyword"])
        tech_col = _pick_col(cols, ["job_tech", "tech", "skills", "stack"])

        if not any([title_col, company_col, url_col]):
            raise RuntimeError(
                f"{table} 테이블에서 공고 기본 컬럼(title/company/url)을 찾지 못했습니다. 현재 컬럼={cols_list}"
            )

 
        select_parts = []
        if id_col:
            select_parts.append(f"`{id_col}` AS `id`")
            select_parts.append(f"`{id_col}` AS `recruit_id`")
        else:
            select_parts.append("NULL AS `id`")
            select_parts.append("NULL AS `recruit_id`")

        select_parts.append(f"`{cat_col}` AS `job_cat`" if cat_col else "NULL AS `job_cat`")
        select_parts.append(f"`{title_col}` AS `job_title`" if title_col else "'' AS `job_title`")
        select_parts.append(f"`{company_col}` AS `job_company`" if company_col else "'' AS `job_company`")
        select_parts.append(f"`{url_col}` AS `job_url`" if url_col else "'' AS `job_url`")
        select_parts.append(f"`{keyword_col}` AS `job_keyword`" if keyword_col else "'' AS `job_keyword`")
        select_parts.append(f"`{tech_col}` AS `job_tech`" if tech_col else "'' AS `job_tech`")

        select_sql = ", ".join(select_parts)

        # 검색
        blob_cols = []
        for c in [title_col, company_col, keyword_col, tech_col]:
            if c:
                blob_cols.append(f"COALESCE(`{c}`, '')")
        blob_expr = "LOWER(CONCAT_WS(' ', " + ", ".join(blob_cols) + "))" if blob_cols else "''"

        where = ["1=1"]
        params: List[Any] = []

        # 카테고리
        if cat_col and job_cat:
            where.append(f"`{cat_col}` = %s")
            params.append(job_cat)


        term_like = []
        term_params: List[Any] = []
        for t in job_tech:
            term_like.append(f"{blob_expr} LIKE %s")
            term_params.append(f"%{t.lower()}%")
        for k in job_keyword:
            term_like.append(f"{blob_expr} LIKE %s")
            term_params.append(f"%{k.lower()}%")

        use_term_filter = len(term_like) > 0

        # tech 2점, keyword 1점
        score_terms = []
        score_params: List[Any] = []
        for t in job_tech:
            score_terms.append(f"(CASE WHEN {blob_expr} LIKE %s THEN 2 ELSE 0 END)")
            score_params.append(f"%{t.lower()}%")
        for k in job_keyword:
            score_terms.append(f"(CASE WHEN {blob_expr} LIKE %s THEN 1 ELSE 0 END)")
            score_params.append(f"%{k.lower()}%")
        score_expr = " + ".join(score_terms) if score_terms else "0"

        order_by = f"ORDER BY ({score_expr}) DESC"
        if id_col:
            order_by += f", `{id_col}` DESC"

        base_sql = f"SELECT {select_sql} FROM `{table}` WHERE " + " AND ".join(where)

        async def _run(sql: str, p: List[Any]) -> List[Dict[str, Any]]:
            async with conn.cursor() as cur:
                await cur.execute(sql + f" {order_by} LIMIT %s", tuple(p + score_params + [int(limit)]))
                return await cur.fetchall()

        if use_term_filter:
            sql = base_sql + " AND (" + " OR ".join(term_like) + ")"
            rows = await _run(sql, params + term_params)
            if len(rows) < min(50, limit // 2):
                rows = await _run(base_sql, params)
        else:
            rows = await _run(base_sql, params)

        out = []
        for r in rows:
            out.append(
                {
                    **r,
                    "job_title": r.get("job_title") or "",
                    "job_company": r.get("job_company") or "",
                    "job_url": r.get("job_url") or "",
                    "job_keyword": r.get("job_keyword") or "",
                    "job_tech": r.get("job_tech") or "",
                }
            )
        return out


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
    MAX_CANDIDATES_FOR_LLM = 30
    short_candidates = candidates[:MAX_CANDIDATES_FOR_LLM]

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
    top_k: int = Form(8),
    debug: bool = Form(False),
    candidates_limit: int = Form(200),
):
    """
    PDF(이력서) + 사용자 선택값(job_cat/job_tech/job_keyword)을 받아,
    DB(job_trend/job_recruit)에서 후보 공고를 조회하고 Top-K 공고 매칭 결과를 반환한다.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF만 업로드 가능합니다.")

    # 1) 사용자 입력 파싱
    job_tech_list = _split_csv(job_tech)
    job_keyword_list = _split_csv(job_keyword)

    # 2) 공고 조회
    try:
        candidates = await _fetch_candidates_from_db(
            job_cat=job_cat,
            job_tech=job_tech_list,
            job_keyword=job_keyword_list,
            limit=max(50, min(int(candidates_limit), 1000)),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB에서 공고 후보 조회 실패: {e}")

    if not candidates:
        raise HTTPException(
            status_code=422,
            detail="DB에서 후보 공고를 찾지 못했습니다. (카테고리/키워드 조건 또는 job_trend 데이터/컬럼 확인 필요)",
        )

    # 3) PDF bytes 읽기
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="업로드된 PDF가 비어 있습니다.")

    # 4) extract -> summarize
    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    if not resume_text or "추출하지 못했습니다" in resume_text:
        raise HTTPException(status_code=422, detail="PDF에서 텍스트를 추출하지 못했습니다.")

    resume_summary = await summarize_text(resume_text, language="ko", style="structured")

    # 5) LLM 매칭
    k = max(1, min(int(top_k), 20))
    llm_out = await _llm_match_jobs(
        resume_summary=resume_summary,
        job_cat=job_cat,
        job_tech=job_tech_list,
        job_keyword=job_keyword_list,
        candidates=candidates,
        top_k=k,
    )

    # 6) LLM 파싱 실패 >> fallback
    if llm_out.get("_parse_failed"):
        ranked = _fallback_rank(candidates, job_tech=job_tech_list, job_keyword=job_keyword_list)
        resp = {"matches": ranked[:k], "mode": "fallback_rule_based"}
        if debug:
            resp["debug"] = {
                "raw_llm": llm_out.get("raw"),
                "resume_summary": resume_summary,
                "candidates_count": len(candidates),
            }
        return resp

    id_to_job: Dict[str, Dict[str, Any]] = {}
    for j in candidates:
        jid = j.get("id") or j.get("job_id") or j.get("recruit_id")
        if jid is None:
            continue
        id_to_job[str(jid)] = j

    enriched = []
    for item in llm_out.get("top", []):
        jid = item.get("job_id")
        base = id_to_job.get(str(jid), {}) if jid is not None else {}
        enriched.append(
            {
                **base,
                "score": item.get("score"),
                "matched_tech": item.get("matched_tech", []),
                "matched_keywords": item.get("matched_keywords", []),
                "reasons": item.get("reasons", []),
            }
        )

    resp = {"matches": enriched[:k], "mode": "llm_rerank"}
    if debug:
        resp["debug"] = {"resume_summary": resume_summary, "candidates_count": len(candidates)}
    return resp
