import asyncio
import os
import httpx
from bs4 import BeautifulSoup

import ollama

import base64
from PIL import Image
from io import BytesIO
import html2text
import re
import json
from ollama_client import get_client

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
CRAWL_MODEL = os.getenv("OLLAMA_CRAWL_MODEL", "qwen3-vl:2b")

SARAMIN_CATEGORIES = {
    "16": "기획·전략", "14": "마케팅·홍보·조사", "3": "회계·세무·재무",
    "5": "인사·노무·HRD", "4": "총무·법무·사무", "2": "IT개발·데이터",
    "15": "디자인", "8": "영업·판매·무역", "21": "고객상담·TM",
    "18": "구매·자재·물류", "12": "상품기획·MD", "7": "운전·운송·배송",
    "10": "서비스", "11": "생산", "22": "건설·건축", "6": "의료",
    "9": "연구·R&D", "19": "교육", "13": "미디어·문화·스포츠",
    "17": "금융·보험", "20": "공공·복지"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}

OCR_SEMAPHORE = asyncio.Semaphore(8)


# async def perform_qwen3vl_ocr(img_url, client):
#     async with OCR_SEMAPHORE:
#         try:
#             # 이미지 비동기 다운로드
#             img_res = await client.get(img_url, timeout=5)
#             img_res.raise_for_status()

#             # 이미지 처리(gif, 투명 등 처리)
#             def process_img(content):
#                 img = Image.open(BytesIO(content))
#                 if img.mode != 'RGB':
#                     img = img.convert('RGB')
#                 buffer = BytesIO()
#                 img.save(buffer, format='PNG')
#                 return base64.b64encode(buffer.getvalue()).decode('utf-8')

#             img_base64 = await asyncio.to_thread(process_img, img_res.content)

#             prompt = """
#             이 이미지는 어느 특정 회사의 채용 공고의 일부입니다.
#             이미지 내의 작성된 모든 내용을 마크다운 형식으로 추출해주세요.
#             만약 표가 있다면 반드시 마크다운 표 형식을 유지해주세요.
#             만약 이미지 내에 텍스트나 표 등이 없다면 '내용이 없습니다.'로 응답해주세요.
#             """
            
#             payload = {
#                 "model": CRAWL_MODEL,
#                 "messages": [
#                     {
#                         "role": "user",
#                         "content": prompt,
#                         "images": [img_base64]  # base64 string (data: 제거된 상태)
#                     }
#                 ]
#             }
#             ollam_client = get_client()
#             ollama_res = await ollam_client.post(f"{OLLAMA_URL}/api/chat", json=payload)

#             extracted_text = ollama_res['message']['content']
#             print(f"extracted_text :  {extracted_text}")
#             return f"\n\n> **[VLM 추출 시작]**\n{extracted_text}\n> **[VLM 추출 종료]**\n\n"

#         except Exception as e:
#             print(f"OCR failed ({img_url}): {e}")
#             return ""


def get_info_from_metadata(html_content):
    try:
        title_match = re.search(r'\]\s+(.*?)(?=\([^)]*?\)\s*-\s*사람인)', html_content)
        company_match = re.search(r"companyNm\s*=\s*'([^']+)'", html_content)

        title =  json.loads(f'"{title_match.group(1)}"') if title_match else "N/A"
        company = json.loads(f'"{company_match.group(1)}"') if company_match else "N/A"

        return title, company

    except Exception as e:
        return "N/A", "N/A"


# def format_url(src):
#     if src.startswith('//'):
#         full_img_url = "https:" + src
#     elif src.startswith('/'):
#         full_img_url = "https://www.saramin.co.kr" + src
#     else:
#         full_img_url = src
#     return full_img_url


async def fetch_recruit(code, cat_nm, title, company, semaphore, client):
    find_url = f"https://www.saramin.co.kr/zf_user/jobs/list/job-category?cat_mcls={code}&searchword={title}"

    async with semaphore:
        try:
            res = await client.get(find_url, timeout=5)
            res.raise_for_status()

            soup = BeautifulSoup(res.content, 'html.parser')

            recruit_list = soup.select_one('div.common_recruilt_list')
            if not recruit_list:
                return None

            recruits = recruit_list.select('div.list_item')
            for recruit in recruits:
                fetch_title = recruit.select_one('div.job_tit a.str_tit span')
                fetch_company = recruit.select_one('div.company_nm a')

                if fetch_title and fetch_company:
                    fetch_title_nm = fetch_title.text.strip()
                    fetch_company_nm = fetch_company.text.strip()

                    if title == fetch_title_nm and company == fetch_company_nm:
                        return cat_nm

        except Exception as e:
            print(f"Failed to fetch {cat_nm} job recruit list: {e}")

    return None


async def get_cat_mcls_by_search(title, company, client):
    # 동시 접속 제한(사람인 보안 정책 고려)
    semaphore = asyncio.Semaphore(5)

    # 모든 카테고리에 대한 작업 리스트 생성
    task = [
        fetch_recruit(code, cat_nm, title, company, semaphore, client)
        for code,cat_nm in SARAMIN_CATEGORIES.items()
    ]

    # 작업 병렬처리 후 결과 대기
    result = await asyncio.gather(*task)

    return [res for res in result if res is not None]

async def extract_jd_markdown(jd_url, client):
    try:
        # 메인 페이지 요청
        res = await client.get(jd_url)
        res.raise_for_status()
        res_text = res.content.decode('utf-8')

        # 메타데이터 추출
        title, company = get_info_from_metadata(res_text)

        # 직종 검색과 상세 페이지 URL 준비
        cat_task = asyncio.create_task(get_cat_mcls_by_search(title, company, client))

        match = re.search(r'rec_idx=(\d+)', jd_url)
        if not match:
            return ""

        inner_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={match.group(1)}"

        # 상세 페이지 요청
        detail_res = await client.get(inner_url)
        detail_res.raise_for_status()

        # 직종 검색 결과 대기
        cat_mcls = await cat_task

        soup = BeautifulSoup(detail_res.text, 'html.parser')
        body = soup.find('body')
        if not body:
            return ""

        # img_tags = body.find_all('img')

        # ocr 작업 병렬 실행
        # ocr_tasks = []
        # valid_imgs = []

        # for img in img_tags:
        #     src = img.get('src')
        #     if src and not any(k in src.lower() for k in ['icon', 'logo', 'blank', 'pixel', 'watermark']):
        #         full_img_url = format_url(src)
        #         valid_imgs.append(img)
        #         ocr_tasks.append(perform_qwen3vl_ocr(full_img_url, client))
        #     else:
        #         img.decompose()

        # # ocr 작업 실행 후 결과 대기
        # print(f"총 {len(ocr_tasks)}개의 이미지 병렬 처리 시작...")
        # ocr_results = await asyncio.gather(*ocr_tasks)

        # # 이미지 태그를 추출된 텍스트로 교체
        # for img, ocr_text in zip(valid_imgs, ocr_results):
        #     if ocr_text:
        #         img.replace_with(soup.new_string(ocr_text))
        #     else:
        #         img.decompose()

        # 마크다운 형태로 변환
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.bypass_tables = False
        h.body_width = 0

        markdown_content = h.handle(str(body))
        markdown_result = re.sub(r'\n{3,}', '\n\n', markdown_content)

        return {
            "title": title,
            "company": company,
            "job_category": cat_mcls,
            "content": markdown_result
        }
    except Exception as e:
        print(f"Error in extract_jd_markdown: {e}")
        return ""



# if __name__ == "__main__":
#     url = "https://www.saramin.co.kr/zf_user/jobs/relay/view?isMypage=no&rec_idx=52601079&recommend_ids=eJxdz8ERQyEIBNBqcmcRFjinEPvvIn7Hr068PcEFXczAFj2BT3xdw9SJXqJ%2F7DYvjBKUtx2wZHsYs6omUrVJakoegibYjJGMPKM21yiajnNeb656mBTzihu7xBX3crWrq7drtyqXdtgQ10eYpTX5A8xcPzg%3D&view_type=list&gz=1&relayNonce=d88c820c8b5b28eaafce&immediately_apply_layer_open=n#seq=0"
#     result = asyncio.run(extract_jd_markdown(url, client))
#
#     if result:
#         print("\n [Test Result]")
#         print(f"공고 제목: {result['title']}")
#         print(f"기업 이름: {result['company']}")
#         print(f"직업 분류: {result['job_category']}")
#         print("-" * 30)
#         print(result['content'])