#!/bin/zsh

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="retail-channel-ai-assistant"
HEALTH_URL="http://127.0.0.1:8501/_stcore/health"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    container_status="$(docker ps -a --filter "name=^/${APP_NAME}$" --format "{{.Status}}" 2>/dev/null)"
    if [[ -n "$container_status" ]]; then
        echo "Docker container: $container_status"
    else
        echo "Docker container: not created"
    fi
else
    echo "Docker: unavailable"
fi

if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Health: ok"
    echo "URL: http://127.0.0.1:8501/"
    exit 0
fi

echo "Health: unavailable"
echo "Logs: docker logs $APP_NAME"
exit 1
