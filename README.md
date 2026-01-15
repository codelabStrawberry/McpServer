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
docker compose build
docker compose up -d
docker compose up --build -d
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

# Docker / Ollama / MySQL 운영 및 정리 명령 모음

이 문서는 MySQL 컨테이너 실행, Ollama Host/Container 제어,
Chroma 강제 종료, Docker 전체 정리 및 테스트용 실행 명령을
하나의 Markdown 파일로 정리한 것입니다.

---

## 🧠 MySQL 설치 (Docker)

docker run -d \
  --name mysql8 \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=1234 \
  -e MYSQL_DATABASE=board_db \
  -e MYSQL_USER=user \
  -e MYSQL_PASSWORD=pass \
  -v mysql8-data:/var/lib/mysql \
  --restart unless-stopped \
  mysql:8.0

---

## 🧠 Ollama Host 서비스 중지 (중요)

Host에 설치된 Ollama 서비스는 Docker Ollama와 충돌하므로
반드시 중지 및 비활성화해야 합니다.

sudo systemctl stop ollama
sudo systemctl disable ollama

포트 확인 (출력 없어야 정상):

ss -lntp | grep 11434

---

## Docker Compose 재시작

docker compose down -v
docker compose up -d --build

---

## 🧠 Ollama / Chroma 강제 중지 (PID 기준)

컨테이너 PID 확인:

docker inspect ollama --format '{{.State.Pid}}'
docker inspect chroma --format '{{.State.Pid}}'

PID가 남아 있는 경우 강제 종료:

sudo kill -9 <PID>

컨테이너 강제 제거:

docker rm -f ollama chroma

---

## 컨테이너 상태 및 로그 확인

docker ps

docker logs ollama --tail 20
docker logs chroma --tail 20
docker logs mcp-server --tail 30

---

## Docker 전체 컨테이너 중지 / 제거

모든 컨테이너 중지:

docker stop $(docker ps -aq)

모든 컨테이너 제거:

docker rm $(docker ps -aq)

모든 이미지 제거:

docker rmi -f $(docker images -aq)

특정 컨테이너 중지:

sudo docker stop mcp-server ollama chroma

---

## Docker 패키지 완전 제거 (Ubuntu)

### 1️⃣ Docker 관련 패키지 제거

sudo apt-get remove --purge -y \
  docker-ce \
  docker-ce-cli \
  docker-buildx-plugin \
  docker-compose-plugin \
  docker-ce-rootless-extras

sudo apt-get remove --purge -y \
  python3-compose \
  python3-docker \
  python3-dockerpty

sudo apt autoremove -y

---

## Ollama 이미지 직접 실행 (디버깅용)

DNS 지정 + bash 진입:

docker run -it --rm \
  --dns=8.8.8.8 \
  --entrypoint /bin/bash \
  ollama/ollama:latest

볼륨 포함 실행:

docker run -it --rm \
  --dns=8.8.8.8 \
  -v ollama:/root/.ollama \
  --entrypoint /bin/bash \
  ollama/ollama:latest

---

## 참고

- Host Ollama + Docker Ollama 동시 실행 ❌
- 11434 포트 충돌 시 GPU/서버 모두 정상 동작 안 함
- 문제가 생기면 컨테이너 → 이미지 → Docker 순으로 정리하는 것이 가장 확실함


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

<윈도우>
MSYS_NO_PATHCONV=1 docker exec -it ollama /usr/bin/ollama list

```

## ❌ docker-compose-plugin 필요한 경우 (아직 초기 서버)

```bash
docker: command not found
docker: Cannot connect to the Docker daemon
docker compose: command not found

sudo apt update
sudo apt install docker docker-compose-plugin
```


# Ollama Docker GPU 설정 가이드 (Ubuntu + NVIDIA)

이 문서는 Docker 환경에서 Ollama 컨테이너가
NVIDIA GPU를 정상적으로 인식하도록 설정하는 전체 절차를
하나의 Markdown 파일로 정리한 것입니다.

---

## 사전 조건

- Ubuntu
- NVIDIA GPU
- NVIDIA Driver 설치 완료
- Docker / Docker Compose 설치 완료
- 호스트에서 nvidia-smi 정상 동작

nvidia-smi

---

## GPU가 컨테이너에 전달되었는지 확인

docker inspect ollama --format='{{.HostConfig.DeviceRequests}}'

정상 출력 예시:
[{gpu 0 [[gpu]] []}]

비어 있으면 GPU가 컨테이너에 전달되지 않은 상태입니다.

---

## 문제 원인

Docker는 기본적으로 GPU를 인식하지 못합니다.
따라서 NVIDIA Container Toolkit 설치가 필수입니다.

---

## NVIDIA Container Toolkit 설치 절차

아래 순서를 그대로 실행해야 합니다.

1. NVIDIA GPG 키 등록

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
| sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

2. NVIDIA 저장소 추가

curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
| sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
| sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

3. 패키지 목록 갱신

sudo apt-get update

4. NVIDIA Container Toolkit 설치

sudo apt-get install -y nvidia-container-toolkit

5. Docker 런타임 설정 (중요)

sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

※ Docker 재시작을 하지 않으면 100% 실패합니다.

---

## 설치 확인

docker info | grep -i nvidia

정상 출력:
Runtimes: nvidia runc

---

## GPU 테스트

docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi

---

## Ollama 컨테이너 재시작

docker compose down -v
docker compose up -d --build

---

## 최종 확인

docker inspect ollama --format='{{.HostConfig.DeviceRequests}}'

정상 출력이 나오면 GPU 설정 완료입니다.
