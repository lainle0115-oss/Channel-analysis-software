#!/bin/zsh

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8502}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/streamlit.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

trap 'exit 0' INT TERM

while true; do
    printf '\n[%s] Starting Streamlit\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
    "$ROOT/.venv/bin/streamlit" run "$ROOT/app.py" \
        --server.address "$SERVER_HOST" \
        --server.port "$PORT" \
        --server.headless true >> "$LOG_FILE" 2>&1
    exit_code=$?
    printf '[%s] Streamlit exited with code %s; restarting in 2 seconds\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$exit_code" >> "$LOG_FILE"
    sleep 2
done
