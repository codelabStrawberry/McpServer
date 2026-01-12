FROM python:3.12-slim

WORKDIR /app

# curl, ca-certificates 설치
RUN apt-get update && \
    apt-get install -y curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Ollama 설치 (옵션: 호스트에서 미리 다운로드한 파일 복사 가능)
# COPY ollama /usr/bin/ollama
# RUN chmod +x /usr/bin/ollama

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# entrypoint 실행 권한
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
