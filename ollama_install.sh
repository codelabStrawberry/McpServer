cat <<'EOF' > ollama_install.sh
#!/bin/bash
set -e

echo "▶ Installing Ollama CLI wrapper (Docker-only)"

# --------------------------------------------------
# 1. Docker 필수 체크
# --------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker is not installed"
  exit 1
fi

# --------------------------------------------------
# 2. Host Ollama 완전 제거 (있을 경우)
# --------------------------------------------------
echo "▶ Removing host Ollama (if exists)..."

sudo systemctl stop ollama 2>/dev/null || true
sudo systemctl disable ollama 2>/dev/null || true
sudo rm -f /etc/systemd/system/ollama.service
sudo rm -rf /usr/local/lib/ollama
sudo rm -f /usr/local/bin/ollama
sudo systemctl daemon-reload || true

# --------------------------------------------------
# 3. Docker exec 기반 Ollama CLI wrapper 생성
# --------------------------------------------------
echo "▶ Installing Docker-based Ollama CLI wrapper..."

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

# --------------------------------------------------
# 4. 설치 결과 안내
# --------------------------------------------------
echo
echo "✅ Host Ollama server NOT installed"
echo "✅ systemd ollama REMOVED"
echo "✅ Docker-only Ollama architecture enforced"
echo "✅ CLI wrapper installed at /usr/local/bin/ollama"
echo
echo "Usage (host):"
echo "  ollama list"
echo "  ollama pull gemma3:4b"
echo
echo "Note:"
echo "  - Models are stored in the Ollama container volume"
echo "  - MCP Server should use Ollama REST API (not CLI)"
EOF
