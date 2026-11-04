#!/usr/bin/env bash
# Starts the analyser and the website together. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -x .venv/bin/python ] || { echo "First run: npm run setup"; exit 1; }

# AnyChords left running from an earlier start (another Terminal tab, a window
# that was never closed, or one paused with Ctrl+Z) holds the ports and would
# keep serving old code. Stop our own leftovers; leave other programs alone.
if pkill -f "uvicorn server.app:app" 2>/dev/null; then
  echo "Stopped an AnyChords analyser that was still running from before."
  sleep 1
fi
here=$(pwd -P)
holders() { lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null || true; }
folder_of() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1 || true; }
if command -v lsof >/dev/null; then
  for port in 8000 5173; do
    ours=""
    for pid in $(holders "$port"); do
      if [ "$(folder_of "$pid")" = "$here" ]; then
        kill -TERM "$pid" 2>/dev/null || true
        kill -CONT "$pid" 2>/dev/null || true # a paused one must wake up to exit
        ours="$ours $pid "
      fi
    done
    if [ -n "$ours" ]; then
      for _ in $(seq 1 15); do
        [ -z "$(holders "$port")" ] && break
        sleep 0.2
      done
      for pid in $(holders "$port"); do
        case "$ours" in *" $pid "*) kill -KILL "$pid" 2>/dev/null || true ;; esac
      done
      sleep 0.2
      echo "Stopped AnyChords that was still running from before (port $port)."
    fi
    pid=$(holders "$port" | head -n 1)
    if [ -n "$pid" ]; then
      name=$(ps -o comm= -p "$pid" 2>/dev/null || true)
      name=${name##*/}
      where=$(folder_of "$pid")
      echo "Port $port is in use by another program: ${name:-unknown} (pid $pid, in ${where:-an unknown folder})."
      echo "AnyChords needs this port. Quit that program, then run npm start again."
      exit 1
    fi
  done
fi

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

.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8000 &
analyser=$!
trap 'kill "$analyser" 2>/dev/null || true' EXIT INT TERM

echo "AnyChords is starting: http://localhost:5173 (the analyser warms up for a few seconds)"
echo "Code version: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
# --strictPort: never quietly start a second page server on another port.
npx vite --port 5173 --strictPort --open
