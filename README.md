# ollama-rag-mcp

Ollama + ChromaDB + FastAPI 기반 **MCP(Model Context Protocol) RAG 서버** 예제 프로젝트입니다.

로컬 LLM(Ollama)을 사용해 **Chat / RAG 검색 / 문서 추가**를 MCP Tool 형태의 API로 제공합니다.

---

---

## 📁 프로젝트 구조

```
MCPSERVER/
├─ data/
│ └─ docs/
│ └─ chroma_data1.txt # 예제 RAG 문서
│
├─ mcp_server/
│ ├─ api/
│ │ ├─ routes/
│ │ │ ├─ chat.py # /mcp/tools/chat
│ │ │ ├─ rag.py # /mcp/tools/rag_chat
│ │ │ └─ docs.py # /mcp/tools/add_doc, add_doc2
│ │ ├─ init.py
│ │ ├─ app.py # FastAPI app + lifespan
│ │ └─ schemas.py # Pydantic request models
│ │
│ ├─ chroma_db.py # ChromaDB client + 검색/저장 로직
│ ├─ ollama.py # Ollama API wrapper (chat / embedding)
│ ├─ ollama_client.py # AsyncClient 전역 관리
│ ├─ rag.py # RAG prompt 구성 로직
│ ├─ ingest.py # 문서 ingest 유틸 (선택)
│ ├─ main.py # uvicorn entrypoint
│ │
│ ├─ Dockerfile
│ ├─ Dockerfile_Debug
│ ├─ entrypoint.sh # 모델 pull + 서버 실행
│ ├─ entrypoint_debug.sh
│ └─ requirements.txt
│
├─ .env
├─ .env_sample
├─ docker-compose.yml
├─ docker-compose_Debug.yml
└─ README.md
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


```

## 🧠  redis 설치

docker run -d --name redis7 -p 6379:6379 redis:7

## 🧠  ollama host 중지
sudo systemctl stop ollama
sudo systemctl disable ollama
ss -lntp | grep 11434   # 출력 없어야 함

docker compose down -v
docker compose up -d --build

## 🧠  ollama chroma 강제 중지
docker inspect ollama --format '{{.State.Pid}}'
docker inspect chroma --format '{{.State.Pid}}'

sudo kill -9 12345(PID)

docker rm -f ollama chroma


docker ps
docker logs ollama --tail 20
docker logs chroma --tail 20
docker logs mcp-server --tail 30


docker stop $(docker ps -aq)
docker rm $(docker ps -aq)

docker rmi -f $(docker images -aq)

sudo docker stop mcp-server ollama chroma

1️⃣ Docker 패키지 제거
sudo apt-get remove --purge -y docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras
sudo apt-get remove --purge -y python3-compose python3-docker python3-dockerpty
sudo apt autoremove -y


docker run -it --rm --dns=8.8.8.8 --entrypoint /bin/bash ollama/ollama:latest

docker run -it --rm \
  --dns=8.8.8.8 \
  -v ollama:/root/.ollama \
  --entrypoint /bin/bash \
  ollama/ollama:latest

# 컨테이너 안에서
/usr/bin/ollama serve &
/usr/bin/ollama pull gemma3:1b
/usr/bin/ollama pull nomic-embed-text
/usr/bin/ollama list


# 1️⃣ Ollama 서버 백그라운드 실행
/usr/bin/ollama serve &

# 2️⃣ gemma3:1b 모델 설치
/usr/bin/ollama pull gemma3:1b

# 3️⃣ nomic-embed-text 모델 설치
/usr/bin/ollama pull nomic-embed-text

# 4️⃣ 설치된 모델 확인
/usr/bin/ollama list

---

---

## 🐳 Docker 디버깅 명령어

---

chmod +x ollama_install.sh

./ollama_install.sh

sudo ./ollama_install.sh
---

---

## 🐳 컨테이너 안 or 외부에서 모델 pull

```bash
<생성>
docker exec -it ollama /usr/bin/ollama pull gemma3:1b
docker exec -it ollama /usr/bin/ollama pull nomic-embed-text

<제거>
docker exec -it ollama /usr/bin/ollama rm gemma3:1b
docker exec -it ollama /usr/bin/ollama rm nomic-embed-text

docker exec -it ollama /usr/bin/ollama list

```