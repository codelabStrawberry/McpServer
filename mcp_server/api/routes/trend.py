import json
from multiprocessing import pool
import re

from fastapi import APIRouter
from pydantic import BaseModel

from api.db.mysql import get_mysql_pool

from ollama import ollama_chat

router = APIRouter()

class TrendRequest(BaseModel):
    job_cat: str

async def fetch_job_trend_data(job_cat: str) -> str:
    pool = await get_mysql_pool()
    if pool is None:
        return {"error": "MySQL 연결 실패"}
    
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            if job_cat == "IT개발·데이터":
                sql = "SELECT job_tech, job_core FROM job_trend WHERE job_cat = %s"
                
                await cursor.execute(sql, (job_cat,))
                trends = await cursor.fetchall()
                
                tech_list = []
                core_list = []
                
                for row in trends:
                    job_tech = row[0]
                    job_core = row[1]
                    tech_list.append(job_tech)
                    core_list.append(job_core)
                job_analysis = f'"기술 트렌드": [{', '.join(tech_list)}], "핵심 역량": [{', '.join(core_list)}]'
            
            else:
                sql = "SELECT job_keyword FROM job_trend WHERE job_cat = %s"
                
                await cursor.execute(sql, (job_cat,))
                keywords = await cursor.fetchall()
                
                keyword_list = []
                for row in keywords:
                    keyword = row[0]
                    keyword_list.append(keyword)
                job_analysis = ", ".join(keyword_list)
                
    return job_analysis

@router.post("/jobfit")
async def jobfit(request: TrendRequest):
    job_analysis = await fetch_job_trend_data(request.job_cat)
    
    prompt = f"""
        아래는 {request.job_cat} 분야의 최근 채용 트렌드를 요약한 JSON 형식의 데이터입니다.
        이를 참고하여 해당 직무에 적합한 추가적인 핵심 키워드를 선정해 주세요.
        선택된 키워드에 많이 언급되거나 중요한 정도에 따라 0부터 10 사이의 점수를 부여하고 각 키워드와 점수를 함께 JSON 배열로 응답해주세요.
        예시 응답 형식: {{"keywords": [{{"keyword": "키워드1", "score": 10}}, ... ]}}
        반드시 주어진 예시 응답 형식의 JSON 형식으로만 응답해야 하며, 다른 설명이나 부가적인 내용은 포함하지 마세요.
        
        채용 트렌드 JSON 데이터:
        {job_analysis}
        
        응답할 JSON의 키워드 개수는 반드시 5개 이상, 10개 이하여야합니다.
    """
        
    res = await ollama_chat(prompt)
    answer_raw = res.get("answer", "")

    print("Jobfit 분석 응답:", answer_raw)
    try:
        sanitized_answer_str = re.sub(r"```json|```", "", answer_raw).strip()
        
        jobfits = json.loads(sanitized_answer_str)
        if not jobfits.get("keywords"):
            print(jobfits)
            return {"error": "키워드 분석 실패"}
    
        result = []
        
        for item in jobfits["keywords"]:
            keyword = item.get("keyword")
            if keyword == request.job_cat:
                continue  # 직무명과 동일한 키워드는 제외
            result.append(item)
            if len(result) >= 5:
                break
            
        if result[0]["score"] <= 1:
            map(lambda x: x.update({"score": x["score"] * 10}), result)
            
        print(result)
        return {"jobfit": result}
        
    except (json.JSONDecodeError, TypeError) as e:
        return {"error": f"JSON 파싱 실패: {e}", "raw_answer": answer_raw}
            
@router.post("/career_advice")
async def career_advice(request: TrendRequest):
    job_analysis = await fetch_job_trend_data(request.job_cat)
    
    prompt = f"""
        당신은 직업 커리어 상담 전문가입니다.
        저는 당신에게 {request.job_cat} 분야의 최근 트렌드를 바탕으로 커리어를 발전시키기 위한 전략을 제안받고 싶습니다.
        주어진 JSON 데이터는 {request.job_cat} 분야의 최근 채용 트렌드를 요약한 것입니다.
        이를 참고하여 이 분야에서 성공적인 커리어를 쌓기 위해 어떤 기술과 역량을 키워야 할지 조언해 주세요.
        
        채용 트렌드 JSON 데이터:
        {job_analysis}
        
        당신의 조언은 구체적이고 실용적이어야 하며, 최대한 요약해서 300자 이내로 대답해주세요.
        반드시 한국어로 답변해주세요.
    """

    res = await ollama_chat(prompt)
    answer_raw = res.get("answer", "")
    
    return {"career": answer_raw}