cat <<'EOF' > ollama_install.sh
#!/bin/bash
set -e

echo "▶ Installing Ollama CLI wrapper (Docker-only)"

# docker 필수
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker is not installed"
  exit 1
fi

# host ollama 흔적 제거
sudo systemctl stop ollama 2>/dev/null || true
sudo systemctl disable ollama 2>/dev/null || true
sudo rm -f /etc/systemd/system/ollama.service
sudo rm -rf /usr/local/lib/ollama
sudo rm -f /usr/local/bin/ollama
sudo systemctl daemon-reload

# docker exec wrapper 생성
sudo tee /usr/local/bin/ollama >/dev/null <<'WRAP'
#!/bin/bash
set -e

CONTAINER_NAME=ollama

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "❌ Ollama container is not running"
  echo "   → docker compose up -d ollama"
  exit 1
fi

exec docker exec -it "$CONTAINER_NAME" ollama "$@"
WRAP

sudo chmod +x /usr/local/bin/ollama

echo
echo "✅ Host Ollama server NOT installed"
echo "✅ systemd ollama REMOVED"
echo "✅ CLI wrapper installed at /usr/local/bin/ollama"
echo
echo "Usage:"
echo "  ollama list"
echo "  ollama pull gemma3:1b"
EOF
