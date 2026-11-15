#!/usr/bin/env bash
# One-command local start: builds the UI once, installs the backend, opens the browser.
set -e
cd "$(dirname "$0")"
if [ ! -d frontend/dist ]; then (cd frontend && npm install && npm run build); fi
python3 -m pip install -q -e ./backend
DCF_STATIC_DIR="$(pwd)/frontend/dist" python3 -m dcfmc serve --open "$@"
