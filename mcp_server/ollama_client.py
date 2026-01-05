# mcp_server/ollama_client.py
import httpx

ollama_http_client: httpx.AsyncClient | None = None


async def create_client():
    global ollama_http_client
    ollama_http_client = httpx.AsyncClient(timeout=60.0)


async def close_client():
    global ollama_http_client
    if ollama_http_client:
        await ollama_http_client.aclose()
        ollama_http_client = None
