#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="retail-channel-ai-assistant"
IMAGE_NAME="${APP_NAME}:local"
UPLOAD_DIR="$ROOT/.streamlit/uploaded_files"
HEALTH_URL="http://127.0.0.1:8501/_stcore/health"

ensure_docker() {
    if docker info >/dev/null 2>&1; then
        return 0
    fi

    if command -v orbctl >/dev/null 2>&1; then
        orbctl start >/dev/null 2>&1 || true
    fi

    if ! docker info >/dev/null 2>&1; then
        echo "Docker is not running. Start OrbStack, then run scripts/start_app.sh again." >&2
        exit 1
    fi
}

ensure_docker
mkdir -p "$UPLOAD_DIR"

running_container="$(docker ps --filter "name=^/${APP_NAME}$" --format "{{.Names}}" 2>/dev/null || true)"
if [[ "$running_container" == "$APP_NAME" ]] && curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Retail dashboard is already healthy in Docker: http://127.0.0.1:8501/"
    exit 0
fi

pkill -f "$ROOT/scripts/supervise_app.sh" >/dev/null 2>&1 || true
screen -S "$APP_NAME" -X quit >/dev/null 2>&1 || true
docker rm -f "$APP_NAME" >/dev/null 2>&1 || true

port_pid="$(lsof -tiTCP:8501 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$port_pid" ]]; then
    kill "$port_pid" >/dev/null 2>&1 || true
    sleep 1
fi

docker build -t "$IMAGE_NAME" "$ROOT"
docker run -d \
    --name "$APP_NAME" \
    -p 8501:8501 \
    -v "$UPLOAD_DIR:/app/.streamlit/uploaded_files" \
    "$IMAGE_NAME" >/dev/null

for _ in {1..20}; do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
        echo "Retail dashboard started in Docker: http://127.0.0.1:8501/"
        exit 0
    fi
    sleep 0.5
done

echo "Dashboard did not become healthy. Recent Docker logs:" >&2
docker logs --tail 80 "$APP_NAME" >&2 || true
exit 1
