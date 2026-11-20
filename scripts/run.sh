#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
if [[ ! -x .venv/bin/python ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv
  else
    python3 -m venv .venv
  fi
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pytest, faster_whisper, multipart' >/dev/null 2>&1; then
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    .venv/bin/python -m pip install -r requirements.txt
  fi
fi
exec .venv/bin/python -m uvicorn server:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --workers 1 "$@"
