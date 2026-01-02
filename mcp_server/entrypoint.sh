#!/bin/sh
set -e

echo "▶ Pull Ollama chat model: $OLLAMA_CHAT_MODEL"
curl -s -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_CHAT_MODEL\"}"

echo "▶ Pull Ollama embedding model: $OLLAMA_EMBED_MODEL"
curl -s -X POST "$OLLAMA_BASE_URL/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"$OLLAMA_EMBED_MODEL\"}"

echo "▶ Start MCP Server"
exec uvicorn main:app --host 0.0.0.0 --port 3333