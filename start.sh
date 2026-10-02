#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
STREAMLIT_BIN="$VENV_DIR/bin/streamlit"
STATE_DIR="$PROJECT_ROOT/.streamlit"
STOP_FILE="$STATE_DIR/chatbot.stop"

cd "$PROJECT_ROOT"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
fi

mkdir -p "$STATE_DIR"
rm -f "$STOP_FILE"

"$PYTHON_BIN" -m pip install -r requirements.txt

exec "$STREAMLIT_BIN" run chatbot.py \
  --server.headless true \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --browser.gatherUsageStats false
