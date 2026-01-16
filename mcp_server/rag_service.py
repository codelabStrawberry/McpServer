import os
import chromadb
from chromadb.utils import embedding_functions

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import uuid

# -----------------------
# ChromaDB HTTP Client
# -----------------------
client = chromadb.HttpClient(
    host=os.getenv("CHROMA_HOST", "chroma"),
    port=int(os.getenv("CHROMA_PORT", 8000))
)

# -----------------------
# Embedding Function (고정)
# -----------------------
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

# -----------------------
# Collection (고정 이름)
# -----------------------
collection = client.get_or_create_collection(
    name="samsung_docs",
    embedding_function=embedding_function
)

TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=250,
    chunk_overlap=100
)

def ingest_document(file_path: str, original_filename: str):
    ext = os.path.splitext(original_filename)[1].lower()
    text = ""

    if ext == ".pdf":
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += page.extract_text() or ""

    elif ext == ".txt":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="cp949") as f:
                text = f.read()
    else:
        return 0

    if not text.strip():
        return 0

    chunks = TEXT_SPLITTER.split_text(text)
    if not chunks:
        return 0

    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [{"source": original_filename} for _ in chunks]

    collection.add(
        documents=chunks,
        ids=ids,
        metadatas=metadatas
    )

    return len(chunks)

def search_documents(query_text: str, k: int = 3, source_filter: str = None):
    where_clause = None
    if source_filter and source_filter != "All Documents":
        where_clause = {"source": source_filter}

    results = collection.query(
        query_texts=[query_text],
        n_results=k,
        where=where_clause
    )

    docs = results.get("documents")
    if not docs or not docs[0]:
        return []

    return docs[0]

def get_document_count():
    return collection.count()


def get_unique_sources():
    data = collection.get(include=["metadatas"])
    return list({m["source"] for m in data["metadatas"] if "source" in m})


def reset_database():
    client.delete_collection("samsung_docs")
