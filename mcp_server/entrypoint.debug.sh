#!/bin/sh
set -e

echo "▶ Waiting for Ollama..."
until curl -s "$OLLAMA_BASE_URL/api/tags" > /dev/null; do
  sleep 2
done

echo "▶ Pull Ollama chat model: $OLLAMA_CHAT_MODEL"
curl -s -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_CHAT_MODEL\"}"

echo "▶ Pull Ollama embedding model: $OLLAMA_EMBED_MODEL"
curl -s -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_EMBED_MODEL\"}"

echo "▶ Start MCP Server (debug mode)"
exec python -m debugpy \
  --listen 0.0.0.0:5678 \
  --wait-for-client \
  -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 3333
