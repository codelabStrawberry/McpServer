import os
from chroma_db import add_document

DOCS_PATH = "/app/data/docs"

async def ingest_docs():
    # 1️⃣ 디렉터리 존재 확인
    if not os.path.exists(DOCS_PATH):
        print(f"⚠️ DOCS_PATH not found: {DOCS_PATH}")
        return

    if not os.path.isdir(DOCS_PATH):
        print(f"⚠️ DOCS_PATH is not a directory: {DOCS_PATH}")
        return

    files = os.listdir(DOCS_PATH)

    # 2️⃣ 파일 없음 체크
    if not files:
        print(f"ℹ️ No files in DOCS_PATH: {DOCS_PATH}")
        return

    txt_files = [f for f in files if f.endswith(".txt")]

    if not txt_files:
        print(f"ℹ️ No .txt files to ingest in: {DOCS_PATH}")
        return

    # 3️⃣ ingest 실행
    for filename in txt_files:
        path = os.path.join(DOCS_PATH, filename)

        if not os.path.isfile(path):
            print(f"⏭️ Skip non-file: {filename}")
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()

            doc_id = filename

            await add_document(doc_id, text)

        except Exception as e:
            print(f"❌ Failed to ingest {filename}: {e}")
