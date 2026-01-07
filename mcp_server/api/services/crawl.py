# services/crawl.py
import re
import httpx
from bs4 import BeautifulSoup

def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text

def crawl_url(url: str, timeout: float = 15.0) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; InterviewBot/1.0; +https://example.com)"
    }

    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # 불필요 태그 제거
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    # 1차: main/article 우선
    main = soup.find("main") or soup.find("article")
    if main:
        text = main.get_text(" ", strip=True)
    else:
        text = soup.get_text(" ", strip=True)

    text = _clean_text(text)

    # 너무 길면 잘라서 내려주기 (프롬프트 폭주 방지)
    MAX_CHARS = 20000
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " ...[truncated]"

    if not text:
        return "크롤링 결과가 비어 있습니다. (JS 렌더링이 필요한 페이지일 수 있어요.)"

    return text
