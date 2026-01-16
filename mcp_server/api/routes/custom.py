# backend/api/routes/custom.py
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

    host = _env_any("MYSQL_HOST", "DB_HOST", default="localhost")
    port = int(_env_any("MYSQL_PORT", "DB_PORT", default="3306"))
    user = _env_any("MYSQL_USER", "DB_USER", default="root")
    password = _env_any("MYSQL_PASSWORD", "DB_PASSWORD", default="", required=False)
    db = _env_any("MYSQL_DB", "DB_NAME", default="board_db")

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


def _split_csv(raw: str) -> List[str]:
    s = (raw or "").strip()
    if not s:
        return []
    s = re.sub(r"[\|\n\r\t/]+", ",", s)
    parts = [p.strip() for p in s.split(",")]
    out: List[str] = []
    seen = set()
    for p in parts:
        if not p:
            continue
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def _normalize_terms(terms: List[str]) -> List[str]:
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


def _pick_col(cols: set[str], candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in cols:
            return c
    return None


async def _table_exists(conn: aiomysql.Connection, table: str) -> bool:
    async with conn.cursor() as cur:
        await cur.execute("SHOW TABLES LIKE %s", (table,))
        return (await cur.fetchone()) is not None


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


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _try_extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)

    parsed = _safe_json_loads(t)
    if parsed is not None:
        return parsed

    i = t.find("{")
    j = t.rfind("}")
    if i != -1 and j != -1 and j > i:
        return _safe_json_loads(t[i : j + 1])

    return None


async def _fetch_candidates_from_db(
    *,
    job_cat: str,
    job_tech: List[str],
    job_keyword: List[str],
    limit: int = 200,
) -> List[Dict[str, Any]]:
    job_tech = _normalize_terms(job_tech)
    job_keyword = _normalize_terms(job_keyword)

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

        if not all([id_col, title_col, company_col, url_col]):
            raise RuntimeError(f"{table} 테이블 컬럼 매핑 실패. 현재 컬럼={cols_list}")

        blob_cols = []
        for c in [title_col, company_col, keyword_col, tech_col]:
            if c:
                blob_cols.append(f"COALESCE(`{c}`, '')")
        blob_expr = "LOWER(CONCAT_WS(' ', " + ", ".join(blob_cols) + "))" if blob_cols else "''"

        where = ["1=1"]
        where_params: List[Any] = []

        if cat_col and job_cat:
            where.append(f"`{cat_col}` = %s")
            where_params.append(job_cat)

        term_like: List[str] = []
        term_params: List[Any] = []
        for t in job_tech:
            term_like.append(f"{blob_expr} LIKE %s")
            term_params.append(f"%{t.lower()}%")
        for k in job_keyword:
            term_like.append(f"{blob_expr} LIKE %s")
            term_params.append(f"%{k.lower()}%")

        term_sql = f" AND ({' OR '.join(term_like)})" if term_like else ""

        score_terms: List[str] = []
        score_params: List[Any] = []
        for t in job_tech:
            score_terms.append(f"(CASE WHEN {blob_expr} LIKE %s THEN 2 ELSE 0 END)")
            score_params.append(f"%{t.lower()}%")
        for k in job_keyword:
            score_terms.append(f"(CASE WHEN {blob_expr} LIKE %s THEN 1 ELSE 0 END)")
            score_params.append(f"%{k.lower()}%")
        score_expr = " + ".join(score_terms) if score_terms else "0"

        select_sql = f"""
            SELECT
              `{id_col}` AS id,
              {f"`{cat_col}` AS job_cat" if cat_col else "'' AS job_cat"},
              `{title_col}` AS job_title,
              `{company_col}` AS job_company,
              `{url_col}` AS job_url,
              {f"`{keyword_col}` AS job_keyword" if keyword_col else "'' AS job_keyword"},
              {f"`{tech_col}` AS job_tech" if tech_col else "'' AS job_tech"},
              ({score_expr}) AS _score
            FROM `{table}`
            WHERE {" AND ".join(where)} {term_sql}
            ORDER BY _score DESC, `{id_col}` DESC
            LIMIT %s
        """.strip()

        params = score_params + where_params + term_params + [int(limit)]

        async with conn.cursor() as cur:
            await cur.execute(select_sql, tuple(params))
            rows = await cur.fetchall()

        if term_like and len(rows) < 30:
            select_sql2 = f"""
                SELECT
                  `{id_col}` AS id,
                  {f"`{cat_col}` AS job_cat" if cat_col else "'' AS job_cat"},
                  `{title_col}` AS job_title,
                  `{company_col}` AS job_company,
                  `{url_col}` AS job_url,
                  {f"`{keyword_col}` AS job_keyword" if keyword_col else "'' AS job_keyword"},
                  {f"`{tech_col}` AS job_tech" if tech_col else "'' AS job_tech"},
                  0 AS _score
                FROM `{table}`
                WHERE {" AND ".join(where)}
                ORDER BY `{id_col}` DESC
                LIMIT %s
            """.strip()
            params2 = where_params + [int(limit)]
            async with conn.cursor() as cur:
                await cur.execute(select_sql2, tuple(params2))
                rows = await cur.fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows or []:
            out.append(
                {
                    "id": r.get("id"),
                    "job_cat": r.get("job_cat") or "",
                    "job_title": r.get("job_title") or "",
                    "job_company": r.get("job_company") or "",
                    "job_url": r.get("job_url") or "",
                    "job_keyword": r.get("job_keyword") or "",
                    "job_tech": r.get("job_tech") or "",
                    "_score": int(r.get("_score") or 0),
                }
            )
        return out


def _fallback_rank(
    jobs: List[Dict[str, Any]],
    *,
    job_tech: List[str],
    job_keyword: List[str],
) -> List[Dict[str, Any]]:
    job_tech = _normalize_terms(job_tech)
    job_keyword = _normalize_terms(job_keyword)

    ranked: List[Dict[str, Any]] = []
    for j in jobs:
        blob = (
            f"{j.get('job_title','')} {j.get('job_company','')} "
            f"{j.get('job_keyword','')} {j.get('job_tech','')}"
        ).lower()

        tech_hits = [t for t in job_tech if t.lower() in blob]
        kw_hits = [k for k in job_keyword if k.lower() in blob]

        score = min(100, 8 * len(tech_hits) + 5 * len(kw_hits))

        ranked.append(
            {
                **j,
                "score": score,
                "matched_tech": tech_hits,
                "matched_keywords": kw_hits,
                "reasons": ["텍스트 포함 기반(룰) 점수"],
                "mode": "fallback_rule_based",
            }
        )

    ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
    return ranked


async def _llm_rerank(
    *,
    resume_summary: str,
    job_cat: str,
    job_tech: List[str],
    job_keyword: List[str],
    candidates: List[Dict[str, Any]],
    top_k: int,
) -> Optional[Dict[str, Any]]:
    short = candidates[:30]
    payload = [
        {
            "job_id": j.get("id"),
            "job_title": j.get("job_title", ""),
            "job_company": j.get("job_company", ""),
            "job_url": j.get("job_url", ""),
            "job_keyword": j.get("job_keyword", ""),
            "job_tech": j.get("job_tech", ""),
        }
        for j in short
    ]

    prompt = f"""
너는 채용공고 매칭 엔진이다. 아래 입력만 사용해서 '가장 적합한 공고 Top {top_k}'를 선정하라.

[입력]
- 사용자가 선택한 직무 카테고리(job_cat): {job_cat}
- 사용자가 입력/선택한 스킬(job_tech): {job_tech}
- 사용자가 입력/선택한 키워드(job_keyword): {job_keyword}
- 이력서 요약(resume_summary):
{resume_summary}

- 후보 채용공고 목록(candidates):
{json.dumps(payload, ensure_ascii=False)}

[출력 규칙]
- 반드시 JSON만 출력한다.
{{
  "top": [
    {{
      "job_id": "string|number|null",
      "score": 0-100,
      "matched_tech": ["..."],
      "matched_keywords": ["..."],
      "reasons": ["근거 2~4개"]
    }}
  ]
}}
- candidates에 없는 정보는 절대 만들지 마라.
""".strip()

    res = await ollama_chat(prompt)
    raw = (res.get("answer") or "").strip()
    parsed = _try_extract_json(raw)
    if not parsed or "top" not in parsed:
        return None
    return parsed


@router.post("/match-jobs")
async def match_jobs(
    file: UploadFile = File(...),
    job_cat: str = Form(...),
    job_tech: str = Form(""),
    job_keyword: str = Form(""),
    top_k: int = Form(8),
    use_llm: bool = Form(False),
    candidates_limit: int = Form(200),
    debug: bool = Form(False),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF만 업로드 가능합니다.")

    tech_list = _split_csv(job_tech)
    kw_list = _split_csv(job_keyword)
    k = max(1, min(int(top_k), 20))
    limit = max(50, min(int(candidates_limit), 1000))

    try:
        candidates = await _fetch_candidates_from_db(
            job_cat=job_cat,
            job_tech=tech_list,
            job_keyword=kw_list,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB에서 공고 후보 조회 실패: {e}")

    if not candidates:
        raise HTTPException(
            status_code=422,
            detail="DB에서 후보 공고를 찾지 못했습니다. (카테고리/데이터/컬럼 확인 필요)",
        )

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="업로드된 PDF가 비어 있습니다.")

    resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    if not resume_text or "추출하지 못했습니다" in str(resume_text) or str(resume_text).strip() == "Not text":
        raise HTTPException(status_code=422, detail="PDF에서 텍스트를 추출하지 못했습니다. (스캔 PDF면 OCR 필요)")

    resume_summary = await summarize_text(resume_text, language="korean", style="structured")

    ranked = _fallback_rank(candidates, job_tech=tech_list, job_keyword=kw_list)
    base_top = ranked[:k]

    if use_llm:
        llm_out = await _llm_rerank(
            resume_summary=resume_summary,
            job_cat=job_cat,
            job_tech=tech_list,
            job_keyword=kw_list,
            candidates=ranked,
            top_k=k,
        )

        if llm_out:
            id_map = {str(j.get("id")): j for j in ranked if j.get("id") is not None}
            enriched: List[Dict[str, Any]] = []
            for item in llm_out.get("top", []):
                jid = item.get("job_id")
                base = id_map.get(str(jid), {}) if jid is not None else {}
                enriched.append(
                    {
                        **base,
                        "score": item.get("score"),
                        "matched_tech": item.get("matched_tech", []),
                        "matched_keywords": item.get("matched_keywords", []),
                        "reasons": item.get("reasons", []),
                        "mode": "llm_rerank",
                    }
                )
            resp: Dict[str, Any] = {"matches": enriched[:k], "mode": "llm_rerank"}
        else:
            resp = {"matches": base_top, "mode": "fallback_rule_based (llm_parse_failed)"}
    else:
        resp = {"matches": base_top, "mode": "fallback_rule_based"}

    if debug:
        resp["debug"] = {
            "resume_summary": resume_summary,
            "candidates_count": len(candidates),
            "tech_list": tech_list,
            "keyword_list": kw_list,
        }

    return resp
