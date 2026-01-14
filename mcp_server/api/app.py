from fastapi import FastAPI
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from ollama_client import create_client, close_client
from ingest import ingest_docs
from api.routes import chat, rag, docs, jobfit_route, resume_analyze, interview
from api.db.redis import get_redis_client  # 새 모듈 임포트

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")
INGEST_ON_STARTUP = os.getenv("INGEST_ON_STARTUP", "false").lower()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔥 FastAPI STARTUP: create_client()", flush=True)
    await create_client()

    print("🔥 FastAPI STARTUP: ingest_docs()", flush=True)
    if(INGEST_ON_STARTUP == "true"):
        await ingest_docs()

    # Redis 연결 초기화
    print("🔥 FastAPI STARTUP: Redis 연결", flush=True)
    await get_redis_client()  # 연결 테스트 포함

    yield

    print("🔥 FastAPI SHUTDOWN: close_client()", flush=True)
    await close_client()
    
    redis_client = await get_redis_client()
    if redis_client:
        await redis_client.aclose()



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
app.include_router(jobfit_route.router, prefix="")
app.include_router(rag.router, prefix="/mcp/tools")
app.include_router(docs.router, prefix="/mcp/tools")
app.include_router(resume_analyze.router, prefix="/resume")
app.include_router(interview.router, prefix="/interview")
