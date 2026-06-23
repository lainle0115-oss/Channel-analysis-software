#!/bin/zsh

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8502}"
SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
LOG_FILE="$ROOT/logs/streamlit.log"
PID_FILE="$ROOT/logs/streamlit.pid"
HEALTH_URL="http://$SERVER_HOST:$PORT/_stcore/health"

if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        echo "Process: running (pid $pid)"
    else
        echo "Process: stale pid file"
    fi
else
    echo "Process: not started by script"
fi

if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
    echo "Health: ok"
    echo "URL: http://$SERVER_HOST:$PORT/"
    echo "Logs: $LOG_FILE"
    exit 0
fi

echo "Health: unavailable"
echo "URL: http://$SERVER_HOST:$PORT/"
echo "Logs: $LOG_FILE"
exit 1
