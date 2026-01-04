# ollama-rag-mcp

Ollama + ChromaDB + FastAPI 기반 **MCP(Model Context Protocol) RAG 서버** 예제 프로젝트입니다.

로컬 LLM(Ollama)을 사용해 **Chat / RAG 검색 / 문서 추가**를 MCP Tool 형태의 API로 제공합니다.

이 프로젝트는 **FastAPI 서버 + MCP stdio 브리지 서버**를 분리하여  
Claude Desktop / Cursor / MCP Client에서 **직접 연결 가능한 “진짜 MCP 서버 구조”**를 제공합니다.

---

## 🧠 MCP 전체 아키텍처

┌──────────────────────────────┐
│ Claude Desktop / Cursor │
│ (MCP Client) │
└───────────────┬──────────────┘
│ stdio (JSON-RPC 2.0)
┌───────────────▼──────────────┐
│ MCP stdio Bridge Server │ ← mcp_stdio
│ - initialize │
│ - tools/list │
│ - tools/call │
└───────────────┬──────────────┘
│ HTTP (REST)
┌───────────────▼──────────────┐
│ FastAPI RAG Server │ ← mcp_server
│ /mcp/tools/chat │
│ /mcp/tools/rag_chat │
│ /mcp/tools/add_doc │
└───────────────┬──────────────┘
│
Ollama / ChromaDB

- **MCP stdio 서버**: MCP 표준(JSON-RPC 2.0)만 처리하는 얇은 브리지
- **FastAPI 서버**: 실제 Chat / RAG / 문서 저장 비즈니스 로직

---

## 📁 프로젝트 구조

```
ollama-rag-mcp/
├─ docker-compose.yml
├─ .env
├─ mcp_server/
│ ├─ Dockerfile
│ ├─ requirements.txt
│ ├─ main.py # FastAPI MCP 서버
│ ├─ rag.py # RAG 로직
│ ├─ chroma.py # ChromaDB client
│ ├─ ollama.py # Ollama 호출
│ ├─ entrypoint.sh # Ollama 모델 자동 pull
│ ├─ entrypoint.debug.sh # 디버그 전용 엔트리포인트
│ └─ ingest.py # 문서 일괄 인덱싱 스크립트
│
├─ mcp_stdio/ # ⭐ MCP stdio 브리지 서버 (신규)
│ ├─ server.py # JSON-RPC 2.0 stdio 서버
│ ├─ tools.py # MCP tool 정의
│ └─ client.py # FastAPI 호출 래퍼
│
└─ data/
└─ docs/ # RAG 문서 저장 디렉토리
```

---

---

## ⚙️ 환경 변수 (.env)

```env
# -----------------------
# Ollama
# -----------------------
OLLAMA_BASE_URL=http://ollama:11434

# Chat 모델
OLLAMA_CHAT_MODEL=gemma3:1b

# Embedding 모델 (⚠️ 반드시 embedding 전용 모델)
OLLAMA_EMBED_MODEL=nomic-embed-text

# -----------------------
# ChromaDB
# -----------------------
CHROMA_HOST=chroma
CHROMA_PORT=8000
CHROMA_COLLECTION=rag_docs

```

---

## 🚀 실행 순서

### 1️⃣ Docker 컨테이너 실행

```bash
docker-compose up --build -d
docker compose build --no-cache
docker-compose up -d
```

Docker 생성 후 `Dockerfile`에서 `entrypoint.sh`를 호출하여 아래 모델을 자동으로 pull 합니다.

- `gemma3:1b`
- `nomic-embed-text`

설치 여부는 다음 명령으로 확인합니다.

docker-compose stop
stop 했으면 : docker-compose up -d

docker-compose down

```bash
docker logs ollama
```

컨테이너 재실행 시:

```bash
docker compose up -d
```

---

### 2️⃣ Ollama 모델 수동 다운로드 (선택)

#### 기본 LLM 모델

```bash
docker exec -it ollama ollama pull gemma3:1b
```

#### Embedding 모델 (RAG 문서용)

```bash
docker exec -it ollama ollama pull nomic-embed-text
```

---

## 🐳 Docker 디버깅 명령어

```bash
docker-compose build
docker-compose up -d
docker-compose up --build -d
docker compose build --no-cache
```

---

## 🧪 API 테스트 (Windows CMD 기준)

> ⚠️ **Windows CMD에서는 반드시 한 줄 JSON + 이중 따옴표 escape 사용**

---

### 💬 Chat (LLM 단독)

```cmd
curl -X POST http://localhost:3333/mcp/tools/chat -H "Content-Type: application/json; charset=utf-8" -d "{\"prompt\":\"MCP 서버가 무엇인지 설명해줘\"}"
```

---

### 📥 문서 추가 (RAG 저장)

```cmd
curl -X POST http://localhost:3333/mcp/tools/add_doc -H "Content-Type: application/json; charset=utf-8" -d "{\"id\":\"doc-001\",\"text\":\"MCP 서버는 LLM과 외부 도구를 연결하는 중간 계층 서버이다.\"}"
```

```cmd
curl -X POST http://localhost:3333/mcp/tools/add_doc2 -H "Content-Type: application/json; charset=utf-8" -d "{\"id\":\"doc-002\",\"text\":\"RAG는 검색 기반으로 LLM의 환각을 줄이는 구조이다.\"}"
```

---

### 🔍 RAG 질의 (검색 + LLM)

```cmd
curl -X POST http://localhost:3333/mcp/tools/rag_chat -H "Content-Type: application/json; charset=utf-8" -d "{\"question\":\"MCP 서버 구조를 RAG 기준으로 설명해줘\"}"
```

---

## 🧠 내부 동작 흐름

```
Client (curl / MCP)
  └─ FastAPI (/mcp/tools/*)
       ├─ chat            → Ollama LLM 응답
       ├─ add_doc         → Embedding → ChromaDB 저장
       └─ rag_chat
            ├─ Embedding (nomic-embed-text)
            ├─ ChromaDB 검색
            └─ Ollama LLM 응답

Claude / Cursor
  └─ MCP stdio (JSON-RPC)
       └─ FastAPI (/mcp/tools/*)
            ├─ chat            → Ollama LLM
            ├─ add_doc         → Embedding → ChromaDB
            └─ rag_chat        → 검색 → Ollama LLM

```

---

✅ 특징
MCP 표준(JSON-RPC 2.0, stdio) 정식 구현
FastAPI ↔ MCP 서버 역할 완전 분리
Claude Desktop / Cursor 즉시 연결 가능
Docker 기반 로컬 LLM (Ollama)
ChromaDB 기반 RAG
Chat / Embedding 모델 분리 설계

---

## 📌 주의 사항

- Ollama embedding API는 **단일 텍스트 기준**으로 사용
- Embedding 모델은 반드시 embedding 전용 모델 사용
- 모든 async 함수는 반드시 `await` 필요
- Windows CMD는 JSON escape 필수

---

## 📜 License

MIT

## 📜 entrypoint 파일 수정됨

dos2unix entrypoint.debug.sh
dos2unix entrypoint.sh

1️⃣ Claude Desktop 설정

```json
{
  "mcpServers": {
    "ollama-rag": {
      "command": "D:\\path\\to\\ollama-rag-mcp\\.venv\\Scripts\\python.exe",
      "args": ["mcp_stdio/server.py"]
    }
  }
}
```

## 📜 Claude는 실제로 이렇게 실행함

D:\path\to\ollama-rag-mcp\.venv\Scripts\python.exe mcp_stdio/server.py

1️⃣ 실제 설치된 경로
D:\_StrawberryProject\McpServer

가상환경 생성 (다시 한 번 정확히)
1️⃣ 루트에서
cd D:\_StrawberryProject\McpServer
가상환경 만들기
python -m venv .venv

2️⃣ 활성화
cmd
.venv\Scripts\activate
git bash
source .venv/Scripts/activate

3️⃣ mcp_stdio 의존성만 설치
pip install requests pydantic
pip install --upgrade mcp
(또는 mcp_stdio/requirements.txt 사용)
python.exe -m pip install --upgrade pip

🧪 바로 테스트 (중요)
git bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./.venv/Scripts/python.exe mcp_stdio/server.py

cmd
'{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | .\.venv\Scripts\python.exe mcp_stdio\server.py
