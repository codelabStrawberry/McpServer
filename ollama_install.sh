#!/bin/bash
set -e

echo "▶ Installing Ollama CLI on Ubuntu..."

# 필수 패키지
apt-get update && apt-get install -y curl unzip ca-certificates

# Ollama CLI 설치
curl -sSL https://ollama.com/install.sh | sh

# PATH 설정
export PATH="$HOME/.ollama/bin:$PATH"

# 설치 확인
ollama version

echo "▶ Ollama CLI installed! You can now run:"
echo "   ollama pull <model_name>"
echo "   ollama list"
