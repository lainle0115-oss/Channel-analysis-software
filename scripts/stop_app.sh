#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="retail-channel-ai-assistant"

docker rm -f "$APP_NAME" >/dev/null 2>&1 || true
screen -S "$APP_NAME" -X quit >/dev/null 2>&1 || true
pkill -f "$ROOT/scripts/supervise_app.sh" >/dev/null 2>&1 || true

port_pid="$(lsof -tiTCP:8501 -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$port_pid" ]]; then
    kill "$port_pid" >/dev/null 2>&1 || true
fi

echo "Retail dashboard stopped."
