import os
import chromadb
from ollama import ollama_embed  # async embedding 함수
from ollama import ollama_embed_batch

# -----------------------
# ChromaDB client
# -----------------------
client = chromadb.HttpClient(
    host=os.getenv("CHROMA_HOST", "chroma"),
    port=int(os.getenv("CHROMA_PORT", 8000))
)

collection = client.get_or_create_collection(
    name=os.getenv("CHROMA_COLLECTION", "rag_docs")
)

# -----------------------
# Add document with embedding (ASYNC)
# -----------------------
async def add_doc(doc_id: str, text: str):
    vector = await ollama_embed(text)

    collection.add(
        ids=[doc_id],
        documents=[text],
        embeddings=[vector]   # Chroma는 list[list[float]] 필요
    )


# -----------------------
# Search with embedding (ASYNC)
# -----------------------
async def search(query: str, k: int = 3) -> list[str]:
    vector = await ollama_embed(query)

    result = collection.query(
        query_embeddings=[vector],
        n_results=k
    )

    docs = result.get("documents")
    if not docs or not docs[0]:
        return []

    return docs[0]



def split_text(text: str, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


async def add_document(doc_id: str, full_text: str):
    chunks = split_text(full_text)
    if not chunks:
        return

    vectors = await ollama_embed_batch(chunks)

    if len(chunks) != len(vectors):
        raise RuntimeError("chunk/vector 개수 불일치")

    collection.add(
        ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=vectors
    )
    print(f"✅ added to chroma: {doc_id}", flush=True)



