import json
import re

from fastapi import APIRouter
from pydantic import BaseModel

from api.db.mysql import get_mysql_pool

from ollama import ollama_chat

router = APIRouter()

class TrendRequest(BaseModel):
    job_cat: str

@router.post("/jobfit")
async def jobfit(request: TrendRequest):
    pool = await get_mysql_pool()
    if pool is None:
        return {"error": "MySQL 연결 실패"}
    
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT job_keyword FROM job_trend WHERE job_cat = %s"
            
            await cursor.execute(sql, (request.job_cat,))
            keywords = await cursor.fetchall()
            
            keyword_list = []
            for row in keywords:
                keyword = row[0]
                keyword_list.append(keyword)
            job_analysis = ", ".join(keyword_list)
            
            prompt = f"""
                아래는 {request.job_cat} 분야의 최근 채용 트렌드를 요약한 JSON 형식의 데이터입니다.
                이 중 해당 직무에 관련된 키워드 중 주어진 데이터에서 많이 언급 된 상위 5개의 키워드를 선정해주세요.
                선정된 키워드를 중요도에 따라 0부터 10 사이의 점수를 부여해서 각 키워드와 함께 JSON 배열로 응답해주세요.
                예시 응답 형식: {{"keywords": [{{"keyword": "키워드1", "score": 10}}, ... ]}}
                반드시 주어진 예시 응답 형식의 JSON 형식으로만 응답해야 하며, 다른 설명이나 부가적인 내용은 포함하지 마세요.
                
                채용 트렌드 JSON 데이터:
                {job_analysis}
            """
            
            res = await ollama_chat(prompt)
            answer_raw = res.get("answer", "")
            
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
                print(result)
                return {"jobfit": result}
            
            except (json.JSONDecodeError, TypeError) as e:
                return {"error": f"JSON 파싱 실패: {e}", "raw_answer": answer_raw}
            
@router.post("/career_advice")
async def career_advice(request: TrendRequest):
    pool = await get_mysql_pool()
    if pool is None:
        return {"error": "MySQL 연결 실패"}
    
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = "SELECT job_keyword FROM job_trend WHERE job_cat = %s"
            
            await cursor.execute(sql, (request.job_cat,))
            keywords = await cursor.fetchall()
            
            keyword_list = []
            for row in keywords:
                keyword = row[0]
                keyword_list.append(keyword)
            job_analysis = ", ".join(keyword_list)

            prompt = f"""
                {request.job_cat} 분야의 최근 트렌드를 바탕으로 커리어를 발전시키기 위한 전략을 제안받고 싶습니다.
                주어진 JSON 데이터는 {request.job_cat} 분야의 최근 채용 트렌드를 요약한 것입니다.
                이를 참고하여 이 분야에서 성공적인 커리어를 쌓기 위해 어떤 기술과 역량을 키워야 할지 조언해 주세요.
                응답은 간결한 문장 5개 정도로 작성해주세요.
                
                채용 트렌드 JSON 데이터:
                {job_analysis}
            """

            res = await ollama_chat(prompt)
            answer_raw = res.get("answer", "")
            print("커리어 전략 추천:", answer_raw)
            
            return {"career": answer_raw}