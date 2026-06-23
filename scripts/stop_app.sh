#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8502}"
LOG_DIR="$ROOT/logs"
PID_FILE="$LOG_DIR/streamlit.pid"

if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

port_pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$port_pid" ]]; then
    kill "$port_pid" >/dev/null 2>&1 || true
fi

echo "Retail dashboard stopped on port $PORT."
