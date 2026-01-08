from fastapi import FastAPI
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from ollama_client import create_client, close_client
from api.routes import chat, rag, docs, chatRuntime


# .env 파일 로드
load_dotenv()

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

# -----------------------
# CORS 설정
# -----------------------
# .env에서 읽어서 리스트 형태로 변환
origins = os.getenv("CORS_ORIGINS", "").split(",")
print("CORS_ORIGIN =", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat.router, prefix="/chat")
app.include_router(chatRuntime.router, prefix="")
app.include_router(rag.router, prefix="/mcp/tools")
app.include_router(docs.router, prefix="/mcp/tools")
