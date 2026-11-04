#!/usr/bin/env bash
# Starts the analyser and the website together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -x .venv/bin/python ] || { echo "First run: npm run setup"; exit 1; }

# An analyser left running from an earlier session (another terminal, or the
# old `npm run dev:analyzer`) would keep answering with old code. Stop it.
if pkill -f "uvicorn server.app:app" 2>/dev/null; then
  echo "Stopped an AnyChords analyser that was still running from before."
  sleep 1
fi
for port in 8000 5173; do
  if command -v lsof >/dev/null && lsof -ti "tcp:$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is still in use (an old AnyChords window or terminal?)."
    echo "Close it, or run:  lsof -ti tcp:$port | xargs kill   then npm start again."
    exit 1
  fi
done

.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 &
analyser=$!
trap 'kill "$analyser" 2>/dev/null || true' EXIT INT TERM

echo "AnyChords is starting: http://localhost:5173 (the analyser warms up for a few seconds)"
echo "Code version: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
# --strictPort: never quietly start a second page server on another port.
npx vite --port 5173 --strictPort --open
