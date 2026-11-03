#!/usr/bin/env bash
# Starts the analyser and the website together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -x .venv/bin/python ] || { echo "First run: npm run setup"; exit 1; }

.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 &
analyser=$!
trap 'kill "$analyser" 2>/dev/null || true' EXIT INT TERM

echo "AnyChords is starting: http://localhost:5173 (the analyser warms up for a few seconds)"
npx vite --port 5173 --open
