from fastapi import FastAPI
from contextlib import asynccontextmanager
from ollama_client import create_client, close_client
from api.routes import chat, rag, docs


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔥 FastAPI STARTUP: create_client()")
    await create_client()
    yield
    print("🔥 FastAPI SHUTDOWN: close_client()")
    await close_client()


app = FastAPI(
    title="MCP RAG Server",
    lifespan=lifespan
)

app.include_router(chat.router, prefix="/mcp/tools")
app.include_router(rag.router, prefix="/mcp/tools")
app.include_router(docs.router, prefix="/mcp/tools")
