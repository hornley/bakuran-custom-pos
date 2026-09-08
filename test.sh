#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
fi

printf '%s\n' 'Running backend tests with an isolated pytest database...'
(
  cd "$ROOT_DIR/backend"
  "$PYTHON_BIN" -m pytest -q
)

printf '%s\n' 'Building the frontend...'
(
  cd "$ROOT_DIR/frontend"
  npm test
  npm run build
)

printf '%s\n' 'All checks passed.'
