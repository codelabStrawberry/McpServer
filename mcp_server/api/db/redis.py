# api/core/redis.py
import os
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()  # .env 로드 (필요 시)

REDIS_URL = os.getenv("REDIS_URL", "redis://host.docker.internal:6379/0")
_redis_client = None  # lazy initialization

async def get_redis_client():
    global _redis_client
    if _redis_client:
        return _redis_client

    try:
        client = redis.from_url(REDIS_URL, decode_responses=True)
        await client.ping()
        print("✅ Redis 연결 성공")
        _redis_client = client
    except Exception as e:
        print(f"⚠️ Redis 비활성화: {e}")
        _redis_client = None

    return _redis_client