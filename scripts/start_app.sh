#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8502}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
LOG_DIR="$ROOT/logs"
LOG_FILE="$LOG_DIR/streamlit.log"
PID_FILE="$LOG_DIR/streamlit.pid"
HEALTH_URL="http://$SERVER_HOST:$PORT/_stcore/health"

mkdir -p "$LOG_DIR" "$ROOT/.streamlit/uploaded_files"

if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Retail dashboard is already running: http://$SERVER_HOST:$PORT/"
    exit 0
fi

if [[ -f "$PID_FILE" ]]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
        kill "$old_pid" >/dev/null 2>&1 || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

port_pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$port_pid" ]]; then
    echo "Port $PORT is already occupied. Set another port, for example: PORT=8503 ./scripts/start_app.sh" >&2
    exit 1
fi

cd "$ROOT"
PORT="$PORT" SERVER_HOST="$SERVER_HOST" nohup "$ROOT/scripts/supervise_app.sh" </dev/null >> "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"

for _ in {1..30}; do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
        echo "Retail dashboard started: http://$SERVER_HOST:$PORT/"
        echo "Logs: $LOG_FILE"
        exit 0
    fi
    sleep 0.5
done

echo "Dashboard did not become healthy. Recent logs:" >&2
tail -80 "$LOG_FILE" >&2 || true
exit 1
