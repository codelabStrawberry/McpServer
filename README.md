# ollama-rag-mcp

Ollama + ChromaDB + FastAPI 기반 **MCP(Model Context Protocol) RAG 서버** 예제 프로젝트입니다.

로컬 LLM(Ollama)을 사용해 **Chat / RAG 검색 / 문서 추가**를 MCP Tool 형태의 API로 제공합니다.

---

## 📁 프로젝트 구조

```
ollama-rag-mcp/
├─ docker-compose.yml
├─ .env
├─ mcp_server/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  ├─ main.py        # FastAPI MCP 서버
│  ├─ rag.py         # RAG 로직
│  ├─ chroma.py      # ChromaDB client
│  └─ ollama.py      # Ollama 호출
└─ data/
   └─ docs/          # RAG 문서 저장 디렉토리
```

---

## ⚙️ 환경 변수 (.env)

```env
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:1b

CHROMA_HOST=chroma
CHROMA_PORT=8000
CHROMA_COLLECTION=rag_docs
```

---

## 🚀 실행 순서

### 1️⃣ Docker 컨테이너 실행

```bash
docker compose up -d
```

---

### 2️⃣ Ollama 모델 다운로드

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
       ├─ ollama_chat      → Ollama LLM 응답
       ├─ add_doc          → Embedding → ChromaDB 저장
       └─ rag_chat
            ├─ Embedding (nomic-embed-text)
            ├─ ChromaDB 검색
            └─ Ollama LLM 응답
```

---

## ✅ 특징

- Docker 기반 로컬 LLM (Ollama)
- ChromaDB 벡터 검색
- FastAPI MCP Tool 구조
- Async 기반 RAG 파이프라인
- Windows / Linux 모두 사용 가능

---

## 📌 주의 사항

- Ollama embedding API는 **단일 텍스트 기준**으로 사용
- 모든 async 함수는 반드시 `await` 필요
- Windows CMD는 JSON escape 필수

---

## 📜 License

MIT
