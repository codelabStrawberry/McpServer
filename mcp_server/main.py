from fastapi import FastAPI
from pydantic import BaseModel

from chroma_db import add_doc
from chroma_db import add_document
from rag import rag_chat
from ollama import ollama_chat

app = FastAPI(title="MCP RAG Server")

class ChatPayload(BaseModel):
    prompt: str

class RagPayload(BaseModel):
    question: str

class DocPayload(BaseModel):
    id: str
    text: str

@app.post("/mcp/tools/chat")
async def mcp_chat(payload: ChatPayload):
    return {"result": await ollama_chat(payload.prompt)}

@app.post("/mcp/tools/rag_chat")
async def mcp_rag(payload: RagPayload):
    return {"result": await rag_chat(payload.question)}

@app.post("/mcp/tools/add_doc")
async def mcp_add_doc(payload: DocPayload):
    await add_doc(payload.id, payload.text)   # ✅ 반드시 await
    return {"status": "ok"}

@app.post("/mcp/tools/add_doc2")
async def mcp_add_doc2(payload: DocPayload):
    await add_document(payload.id, payload.text)
    return {"status": "ok"}