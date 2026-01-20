import json
import re

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from api.db.mysql import get_mysql_pool

from api.services.extract import extract_pdf_text
from api.services.summarize import summarize_text
from starlette.concurrency import run_in_threadpool

from ollama import ollama_chat

router = APIRouter()


@router.post("/match")
async def match(
    file: UploadFile = File(...),
    job_cat: str = Form(...),
    tech_text: str = Form(""),
    role_text: str = Form("")):
    print("file", file)
    print("job_cat", job_cat)
    print("tech_text", tech_text)
    print("role_text", role_text)
    
    pool = await get_mysql_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            sql = """
                SELECT job_title, job_company, job_url, job_tech, job_keyword FROM job_trend
                WHERE job_cat = %s
                    AND job_tech LIKE %s
                    AND job_keyword LIKE %s;
            """
            
            await cursor.execute(sql, (job_cat, f"%{tech_text}%", f"%{role_text}%",))
            match_list = await cursor.fetchall()
            print("match_list:", match_list)
            result = {"jobs": []}
            for match in match_list:
                title, company, url, job_tech, job_keyword = match
                item = {"title": title, "company": company, "url": url, "job_tech": json.loads(job_tech), "keyword": job_keyword}
                result["jobs"].append(item)
                
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")
    
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="업로드된 PDF가 비어 있습니다.")
    
    # resume_text = await run_in_threadpool(extract_pdf_text, pdf_bytes, summarize=False)
    # resume_summary = await summarize_text(resume_text, language="ko", style="structured")
    
    # print(resume_summary)
    
    resume_summary = """
    ## 유능한 어시스턴트의 요약: 엔테크서비스 풀스택 웹개발자

      **1. 자기소개**

      저는 엔테크서비스의 풀스택 웹개발자, 2025 상반기 인턴입니다. 높은 책임감을 가지고 최적의 코드를 생산하는 백엔드 개발자로서, 복잡한 요구 사항을 적절하게 분리하고 추상화하여 간결한 로직으로 구현하는 데 중점을 둡니다. 객체지향 
      적인 코드 설계와 가독성 높은 코드를 선호하며, 다양한 프로젝트와 대외 활동을 통해 효과적인 협업 능력을 갖추었습니다.

      **2. 성격의 장단점**

      *   **강점:** 성과 중심적인 사고로 프로젝트의 완성도를 높이고, 팀의 시너지를 극대화합니다. 졸업 프로젝트에서 APNs, JWT 동작 방식을 팀원들에게 공유하며 시스템 이해도를 높였고, 연합 동아리 프로젝트에서 통계 자료를 수집하여 기 
      획 정교화에 기여했습니다.
      *   **단점:** 성과에 집중한 나머지 팀원의 상황을 살피지 못하는 경험이 있습니다. 공학경진대회 준비 중 프론트엔드 작업 지연을 미리 인지하지 못해, 계획했던 완성도와 일정에 차질이 생겼습니다. 이후에는 주기적으로 작업 상황을 공유
      하고, 사소한 어려움도 함께 점검하는 소통 습관을 들이며 부족함을 보완해 나가고 있습니다.

      **3. 취미 활동**

      *   헬스 활동을 통해 꾸준함과 체력을 기르고 있습니다. 개발자에게 중요한 집중력을 유지하는 데 도움이 됩니다.
      *   IT 트렌드, 조직 문화, 심리학 등 다양한 주제의 독서를 통해 사고의 폭을 넓히고, 개발 외적인 분석도 함께 키워가고 있습니다.

      **4. 프로젝트 경험**

      *   **'Tokpik' 프로젝트:** 백엔드 개발을 맡아, ChatGPT를 활용한 사용자 맞춤형 대화 주제 제공을 위한 API 연동 방식을 고민했습니다. 초기에는 구현 유도를 높였지만, 러닝 커브가 가속화되고 코드 유지보수가 복잡해질 우려가 있었습니
      다. 이후, Spring AI를 도입하여 확장성과 생산성을 모두 확보할 수 있었습니다.
      *   **'인텔리젼스 CEC팀 인턴' 프로젝트:** CJ제일제당 고객사 자산 관리 시스템(APM) 변경 과정 데이터 마이그레이션 참여 및 기존 마이그레이션 시스템 로직 분석 및 개선, SRP 기반 리팩토링 수행
      *   **GitHub:** [https://github.com/Minjae-An](https://github.com/Minjae-An)
      *   **Blog:** [https://velog.io/@mj3242/posts](https://velog.io/@mj3242/posts)
      *   **LinkedIn:** [https://www.linkedin.com/in/minjae-an-1866b4287/](https://www.linkedin.com/in/minjae-an-1866b4287/)

      **5. 추가 정보**

      *   **기술 스택:** Java, Spring, Redis, AWS, Git, Docker 등
      *   **학력:** [학교 정규 과정 이외에 개발 참여경험이 있다면 소개해주세요.]

      ---

      **참고:** 위 요약은 텍스트의 일부를 바탕으로 작성되었으며, 보다 자세한 내용은 각 항목에 대한 추가 설명을 포함할 수 있습니다.
    """
    prompt = f"""
너는 맞춤형 채용 공고 매칭 전문가야. 
제공된 [채용 공고 목록]에서 사용자의 [자기소개서 요약] 및 요청 사항과 가장 잘 어울리는 공고를 **딱 2개만** 선정해서 JSON 형식으로 출력해줘.

### 지시 사항
1. 반드시 아래의 [응답 JSON 형식]을 엄격히 지켜서 응답할 것.
2. 텍스트 설명 없이 오직 JSON 데이터만 반환할 것.
3. [채용 공고 목록]에 데이터가 2개보다 적다면 있는 만큼만 출력할 것.
4. '필수_기술_스택'과 '핵심_직무_역량'은 [채용 공고 목록]의 데이터를 기반으로 작성하되, '자격_요건_및_우대사항'은 [자기소개서 요약]과 대조하여 요약해서 작성할 것.

### 응답 JSON 형식
{{
  "matched_jobs": [
    {{
      "company_name": "회사명",
      "url": "공고 URL",
      "required_tech_stack": "기술 스택 목록",
      "core_competencies": "핵심 직무 역량",
      "requirements_and_preferences": "자격 요건 및 우대사항 요약"
    }},
    {{
      "company_name": "회사명",
      "url": "공고 URL",
      "required_tech_stack": "기술 스택 목록",
      "core_competencies": "핵심 직무 역량",
      "requirements_and_preferences": "자격 요건 및 우대사항 요약"
    }}
  ]
}}

[채용 공고 목록]
{match_list}

[자기소개서 요약]
{resume_summary}

[직무 카테고리]: {job_cat}
[기술 스택]: {tech_text}
[매칭 키워드]: {role_text}
"""
    # res = await ollama_chat(prompt)
    
    # print("=====================")
    # print(res)
    # print("=====================")
    
    
    # answer_raw = res.get("answer", "")
    # print(answer_raw)
    
    answer_raw = {"matched_jobs": [
        {
          "company_name": "코닉글로리",
          "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx=52800514",
          "required_tech_stack": ["Java", "JSP", "JavaScript", "Spring Framework", "SQL"],
          "core_competencies": "JSP 기반 웹 개발",
          "requirements_and_preferences": "자격요건: 경력 3년 이상, 대학졸업(2,3년) 이상, JSP 및 Java 개발 경험 보유, 웹 개발 관련 프레임워크 경험"
        },
        {
          "company_name": "맑은소프트",
          "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx=52743613",
          "required_tech_stack": ["Java", "JSP", "MySQL", "Linux", "WAS"],
          "core_competencies": "온라인 교육 솔루션 웹 개발",
          "requirements_and_preferences": "자격요건: 경력 3년 이상, 대학졸업(2,3년) 이상, LMS (원격) 동종업계 경력"
        },
        {
          "company_name": "제이더플로어",
          "url": "https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx=52784169",
          "required_tech_stack": ["TypeScript", "Next.js", "React", "Node.js", "HTML/CSS", "JavaScript", "RESTful API", "GraphQL"],
          "core_competencies": "웹 서비스 개발 및 유지보수, SSR/SSR 기반 프로젝트 경험, API 연동 및 데이터 처리",
          "requirements_and_preferences": "Next.js, React, Node.js 기반 프로젝트 경력, 프론트엔드 엔지니어링 경험, Docker, CI/CD 사용 경험"
        }]
    }
    

    
    return answer_raw                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          