#!/bin/zsh

set -euo pipefail

ROOT="/Users/cocachloe/Documents/职业/retail-channel-ai-assistant"
export HOME="/Users/cocachloe"
export PYTHONUNBUFFERED=1
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

cd "$ROOT"
exec "$ROOT/.venv/bin/python" -m streamlit run "$ROOT/app.py" \
    --server.address 127.0.0.1 \
    --server.port 8502 \
    --server.headless true \
    --browser.gatherUsageStats false
