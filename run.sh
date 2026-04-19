#!/usr/bin/env bash
# NTC score API — create/activate venv, install deps, start uvicorn.
# Usage: ./run.sh [--port 8000] [--no-install]

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PORT=8000
DO_INSTALL=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="${2:?}"; shift 2 ;;
    --no-install) DO_INSTALL=0; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Creating virtual environment in .venv ..."
  python3 -m venv .venv
fi

if [[ "$DO_INSTALL" -eq 1 ]]; then
  echo "Installing dependencies ..."
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
fi

echo "Starting API on http://127.0.0.1:${PORT} (docs: http://127.0.0.1:${PORT}/docs)"
exec "$ROOT/.venv/bin/python" -m uvicorn ntc_score_api:app --host 0.0.0.0 --port "$PORT"
