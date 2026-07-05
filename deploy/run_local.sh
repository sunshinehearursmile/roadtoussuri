#!/usr/bin/env bash
# Run Road to Ussuri locally (browser UI on :8080, MCP server on :8000).
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -e . 2>/dev/null || pip install -q \
  fastapi "uvicorn[standard]" pyyaml groq click rich httpx python-dotenv jinja2

echo "▶ MCP server → http://localhost:8000"
python -m uvicorn mcp_server.server:app --host 0.0.0.0 --port 8000 &
MCP_PID=$!

echo "▶ Web UI    → http://localhost:8080"
python -m web.serve &
WEB_PID=$!

trap 'kill $MCP_PID $WEB_PID 2>/dev/null' INT TERM
wait
