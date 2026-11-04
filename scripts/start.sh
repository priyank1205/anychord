#!/usr/bin/env bash
# Starts the analyser and the website together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -x .venv/bin/python ] || { echo "First run: npm run setup"; exit 1; }
here=$(pwd -P)

# AnyChords left running from an earlier start (another Terminal tab, a window
# that was never closed, or one paused with Ctrl+Z) would keep serving old
# code. Stop our own: analyser and website processes running in this folder.
# Other programs are never touched.
folder_of() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true; }
if command -v lsof >/dev/null && command -v pgrep >/dev/null; then
  ours=""
  for pid in $(pgrep -f "uvicorn server.app:app" || true) $(pgrep -f "vite" || true); do
    if [ "$pid" != "$$" ] && [ "$(folder_of "$pid")" = "$here" ]; then
      kill -TERM "$pid" 2>/dev/null || true
      kill -CONT "$pid" 2>/dev/null || true # a paused one must wake up to exit
      ours="$ours $pid"
    fi
  done
  if [ -n "$ours" ]; then
    for _ in $(seq 1 15); do
      running=""
      for pid in $ours; do kill -0 "$pid" 2>/dev/null && running=1; done
      [ -z "$running" ] && break
      sleep 0.2
    done
    for pid in $ours; do
      if kill -0 "$pid" 2>/dev/null && [ "$(folder_of "$pid")" = "$here" ]; then kill -KILL "$pid" 2>/dev/null || true; fi
    done
    echo "Stopped AnyChords that was still running from before."
  fi
fi

# Ports: AnyChords' own (5288 for the website, 8288 for the analyser), or the
# next free ones if another program has them. Nothing else has to know: the
# page reaches the analyser through the website server (vite.config.js).
busy() {
  if command -v lsof >/dev/null; then
    lsof -ti "tcp:$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    ! .venv/bin/python -c 'import socket, sys; socket.socket().bind(("127.0.0.1", int(sys.argv[1])))' "$1" 2>/dev/null
  fi
}
free_port() {
  local port=$1
  while busy "$port"; do
    port=$((port + 1))
    if [ "$port" -ge $(($1 + 50)) ]; then
      echo "No free port between $1 and $port. Quit some other programs, then npm start again." >&2
      return 1
    fi
  done
  echo "$port"
}
api=$(free_port 8288)
web=$(free_port 5288)

# YouTube changes often, and yt-dlp (the downloader) keeps up with frequent
# releases. Once a day, install a newer one if there is one. If that fails
# (offline?), carry on with the installed copy.
stamp=server/vendor/.checked
if [ -z "$(find "$stamp" -mtime -1 2>/dev/null)" ]; then
  installed=$(sed -n "s/^__version__ = '\(.*\)'$/\1/p" server/vendor/yt_dlp/version.py 2>/dev/null || true)
  latest=$(.venv/bin/python -m pip index versions yt-dlp --disable-pip-version-check 2>/dev/null | sed -n 's/^yt-dlp (\(.*\))$/\1/p' || true)
  if [ -n "$latest" ] && { [ "$latest" != "$installed" ] || [ ! -d server/vendor/yt_dlp_ejs ]; }; then
    echo "Updating the YouTube downloader to yt-dlp $latest (about 15 seconds)..."
    if .venv/bin/python -m pip install --quiet --disable-pip-version-check --upgrade --timeout 20 \
        --target server/vendor "yt-dlp[default]==$latest" >/dev/null 2>&1; then
      touch "$stamp"
    else
      echo "Couldn't update it right now. Carrying on with yt-dlp ${installed:-as installed}."
    fi
  elif [ -n "$latest" ]; then
    touch "$stamp"
  fi
fi
.venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null ||
  echo "Note: YouTube downloads need Python 3.11+ for the latest fixes. Install it from python.org, then run: rm -rf .venv && npm run setup"

.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port "$api" &
analyser=$!
trap 'kill "$analyser" 2>/dev/null || true' EXIT INT TERM

# Open the page once the analyser answers, so it never says "not running"
# while the analyser is still warming up.
echo "Starting the analyser (a few seconds)..."
ready=""
for _ in $(seq 1 120); do
  if .venv/bin/python -c 'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=1)' \
      "http://127.0.0.1:$api/api/health" 2>/dev/null; then
    ready=1
    break
  fi
  kill -0 "$analyser" 2>/dev/null || { echo "The analyser stopped while starting; the messages above say why."; exit 1; }
  sleep 0.5
done
[ -n "$ready" ] || echo "The analyser is slow to start; opening the page anyway."

echo
echo "AnyChords: http://localhost:$web"
[ "$web" = 5288 ] || echo "(Port 5288 is used by another program, so AnyChords is on $web this time.)"
echo "Code version: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo
# --strictPort: the port was just checked; never let a second copy drift elsewhere.
ANYCHORDS_API_PORT=$api npx vite --port "$web" --strictPort --open
