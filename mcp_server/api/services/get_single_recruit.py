import asyncio
import httpx
from bs4 import BeautifulSoup
import os
import re
from tqdm.asyncio import tqdm
from api.services.get_recruit_util_py import extract_jd_markdown, SARAMIN_CATEGORIES, HEADERS

BASE_DIR = "jd_crawled"

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)


async def get_single_recruit(url):
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=5) as client:
        result = await extract_jd_markdown(url, client)
        if not result or not result.get('content'):
            print(f"분석 실패, 혹은 내용이 없습니다.: {url}")
            return
        return result
        # save_title = sanitize_filename(result['title'])
        # save_company = sanitize_filename(result['company'])
        # content = result['content']
        # cat_list = result.get("job_category", [])

        # def save_file(category):
        #     cat_dir = os.path.join(BASE_DIR, sanitize_filename(category))
        #     os.makedirs(cat_dir, exist_ok=True)

        #     file_path = os.path.join(cat_dir, f"{save_title}_{save_company}.md")

        #     with open(file_path, "w", encoding="utf-8") as f:
        #         f.write(f"URL: {url}\n")
        #         f.write("_" * 50 + "\n\n")
        #         f.write(f"Title: {result['title']}\n")
        #         f.write(f"Company: {result['company']}\n\n")
        #         f.write("_" * 50 + "\n\n")
        #         f.write(content)
        #     return file_path

        # tasks = [asyncio.to_thread(save_file, cat) for cat in cat_list]

        # if tasks:
        #     saved_path = await asyncio.gather(*tasks)
        #     print(f"저장 완료 ({len(saved_path)}개 직종: {save_title}_{save_company})")
        # else:
        #     print(f"분류된 직종이 없습니다.: {save_title}_{save_company}")