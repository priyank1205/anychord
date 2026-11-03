#!/usr/bin/env bash
# One-time setup for AnyChords on macOS or Linux:
# website packages, a Python environment for the analyser, yt-dlp, ffmpeg.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

command -v node >/dev/null || fail "Node.js is missing. Install the LTS version from https://nodejs.org, then run 'npm run setup' again."
command -v python3 >/dev/null || fail "Python 3 is missing. Install it from https://www.python.org/downloads/, then run 'npm run setup' again."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "Python 3.10 or newer is needed (you have $(python3 --version)). Install a newer one from https://www.python.org/downloads/."

if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then
    step "Installing ffmpeg with Homebrew"
    brew install ffmpeg
  else
    fail "ffmpeg is missing. Mac: install Homebrew from https://brew.sh, then run 'brew install ffmpeg'. Linux: 'sudo apt install ffmpeg'. Then run 'npm run setup' again."
  fi
fi

step "Installing website packages"
npm install --no-audit --no-fund

step "Creating the analyser's Python environment (.venv)"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r server/requirements.txt

step "Installing yt-dlp (YouTube audio downloader)"
.venv/bin/python -m pip install --quiet --upgrade --target server/vendor yt-dlp

printf '\n\033[32mAll set.\033[0m Start AnyChords with:  npm start\n'
