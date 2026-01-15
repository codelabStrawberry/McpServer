import aiomysql as mysql
import asyncio

import os
from dotenv import load_dotenv

load_dotenv()  # .env 로드 (필요 시)

MYSQL_HOST = os.getenv("MYSQL_HOST", "host.docker.internal")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3307))
MYSQL_USER = os.getenv("MYSQL_USER")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
MYSQL_DB = os.getenv("MYSQL_DB")

async def get_mysql_pool():
    try:
        pool = await mysql.create_pool(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            autocommit=True,
            charset="utf8mb4",
        )
        print("✅ MySQL 연결 성공!")
        return pool
    except Exception as e:
        print(f"❌ MySQL 연결 실패: {e}")
        return None