#!/bin/zsh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT/scripts/stop_app.sh"
sleep 1
"$ROOT/scripts/start_app.sh"
