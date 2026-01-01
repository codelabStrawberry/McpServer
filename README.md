📁 프로젝트 구조
ollama-rag-mcp/
├─ docker-compose.yml
├─ .env
├─ mcp_server/
│ ├─ Dockerfile
│ ├─ requirements.txt
│ ├─ main.py # FastAPI MCP 서버
│ ├─ rag.py # RAG 로직
│ ├─ chroma.py # Chroma client
│ └─ ollama.py # Ollama 호출
└─ data/
└─ docs/ # RAG 문서

📁 실행 순서
docker compose up -d
docker exec -it ollama ollama pull 모델
DEFAULT_MODEL = "gemma3:1b"
docker exec -it ollama ollama pull gemma3:1b
📁 ollama embed 모델
docker exec -it ollama ollama pull nomic-embed-text

🔎 docker debuge
docker-compose build
docker-compose up -d
docker-compose up --build -d
docker compose build --no-cache

📁 테스트 curl : cmd 에서
curl -X POST http://localhost:3333/mcp/tools/chat -H "Content-Type: application/json; charset=utf-8" -d "{\"prompt\":\"MCP 서버가 무엇인지 설명해줘\"}"

curl -X POST http://localhost:3333/mcp/tools/add_doc -H "Content-Type: application/json" -d "{\"id\":\"doc-001\",\"text\":\"MCP 서버는 LLM과 외부 도구를 연결하는 중간 계층 서버이다.\"}"

curl -X POST http://localhost:3333/mcp/tools/chat -H "Content-Type: application/json; charset=utf-8" -d "{\"prompt\":\"MCP 서버가 무엇인지 설명해줘\"}"

curl -X POST http://localhost:3333/mcp/tools/rag_chat -H "Content-Type: application/json; charset=utf-8" -d "{\"question\":\"MCP 서버 구조를 RAG 기준으로 설명해줘\"}"

curl -X POST http://localhost:3333/mcp/tools/add_doc -H "Content-Type: application/json; charset=utf-8" -d "{\"id\":\"doc-001\",\"text\":\"MCP 서버는 LLM과 외부 도구를 연결하는 중간 계층 서버이다.\"}"

curl -X POST http://localhost:3333/mcp/tools/add_doc2 -H "Content-Type: application/json; charset=utf-8" -d "{\"id\":\"doc-002\",\"text\":\"RAG는 검색 기반으로 LLM의 환각을 줄이는 구조이다.\"}"
