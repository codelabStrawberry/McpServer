# services/extract.py
import io
import re
import pdfplumber
from api.services.summarize import summarize_text

def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    summarize: bool = False,
    summary_style: str = "structured",   # "bullet" | "structured"
    return_mode: str = "text",           # "text" | "summary" | "both"
) -> str:
    if not pdf_bytes:
        return "Not text"

    out = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            t = t.strip()
            if t:
                out.append(t)

    text = "\n\n".join(out)
    text = _clean_text(text)

    MAX_CHARS = 20000
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + " ...[truncated]"

    if not text:
        return "PDF에서 텍스트를 추출하지 못했습니다."

    if not summarize:
        return text

#     summary = summarize_text(text, language="ko", style=summary_style)

#     if return_mode == "summary":
#         return summary
#     if return_mode == "both":
#         return f"""[SUMMARY]
# {summary}

# [EXTRACTED_TEXT]
# {text}
# """   

    return text
