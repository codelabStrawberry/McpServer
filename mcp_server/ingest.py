import os
from chroma_db import add_doc

DOCS_PATH = "/app/data/docs"

def ingest_docs():
    for filename in os.listdir(DOCS_PATH):
        if not filename.endswith(".txt"):
            continue

        path = os.path.join(DOCS_PATH, filename)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        doc_id = filename
        add_doc(doc_id, text)
