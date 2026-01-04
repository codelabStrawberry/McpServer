# mcp_stdio/client.py
import requests

BASE_URL = "http://localhost:3333"

def chat(prompt: str):
    r = requests.post(
        f"{BASE_URL}/mcp/tools/chat",
        json={"prompt": prompt},
        timeout=300
    )
    return r.json()

def rag_chat(question: str):
    r = requests.post(
        f"{BASE_URL}/mcp/tools/rag_chat",
        json={"question": question},
        timeout=300
    )
    return r.json()

def add_doc(doc_id: str, text: str):
    r = requests.post(
        f"{BASE_URL}/mcp/tools/add_doc",
        json={"id": doc_id, "text": text},
        timeout=60
    )
    return r.json()

def add_doc2(doc_id: str, text: str):
    r = requests.post(
        f"{BASE_URL}/mcp/tools/add_doc2",
        json={"id": doc_id, "text": text},
        timeout=60
    )
    return r.json()
