#!/bin/sh

echo "▶ Waiting for Ollama..."
until curl -sf "$OLLAMA_BASE_URL/api/tags" > /dev/null; do
  sleep 2
done

echo "▶ Pull Ollama chat model: $OLLAMA_CHAT_MODEL"
curl -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_CHAT_MODEL\"}" || true

echo "▶ Pull Ollama embedding model: $OLLAMA_EMBED_MODEL"
curl -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_EMBED_MODEL\"}" || true

echo "▶ Pull Ollama crawl model: $OLLAMA_CRAWL_MODEL"
curl -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_CRAWL_MODEL\"}" || true

echo "▶ Start MCP Server"
exec uvicorn main:app --host 0.0.0.0 --port 3333