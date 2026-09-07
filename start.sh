#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"
BACKEND_PORT=5300
FRONTEND_PORT=5200
BACKEND_PID_FILE="$LOGS/backend.pid"
FRONTEND_PID_FILE="$LOGS/frontend.pid"

mkdir -p "$LOGS"

pid_is_alive() {
  [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null
}

process_command() {
  tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null || true
}

port_is_busy() {
  local port="$1"
  ss -ltnH 2>/dev/null | awk -v port=":$port" '$4 ~ port "$" { found=1 } END { exit(found ? 0 : 1) }'
}

pid_file_is_project_process() {
  local pid_file="$1" expected_cwd="$2" expected_marker="$3" pid actual_cwd actual_cmd
  [ -f "$pid_file" ] || return 1
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  pid_is_alive "$pid" || return 1
  actual_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  actual_cmd="$(process_command "$pid")"
  [ "$actual_cwd" = "$expected_cwd" ] && [[ "$actual_cmd" == *"$expected_marker"* ]]
}

stop_stale_project_process() {
  local pid_file="$1" expected_cwd="$2" expected_marker="$3" label="$4" pid actual_cwd actual_cmd
  [ -f "$pid_file" ] || return 0
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  pid_is_alive "$pid" || { rm -f "$pid_file"; return 0; }
  actual_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  actual_cmd="$(process_command "$pid")"
  if [ "$actual_cwd" = "$expected_cwd" ] && [[ "$actual_cmd" != *"$expected_marker"* ]]; then
    echo "Stopping stale $label process $pid from this project." >&2
    kill -TERM "$pid"
    for _ in $(seq 1 20); do
      pid_is_alive "$pid" || break
      sleep 0.25
    done
    if pid_is_alive "$pid"; then
      echo "$label stale process did not stop cleanly." >&2
      exit 1
    fi
    rm -f "$pid_file"
  fi
}

ensure_backend_dependencies() {
  if [ ! -x "$BACKEND/.venv/bin/python" ] || ! "$BACKEND/.venv/bin/python" -c 'import fastapi, pydantic, uvicorn' >/dev/null 2>&1; then
    command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
    python3 -m venv --clear "$BACKEND/.venv"
    "$BACKEND/.venv/bin/python" -m pip install -r "$BACKEND/requirements.txt"
  fi
}

ensure_frontend_dependencies() {
  if [ ! -x "$FRONTEND/node_modules/.bin/vite" ]; then
    command -v npm >/dev/null || { echo "npm is required" >&2; exit 1; }
    (cd "$FRONTEND" && npm install)
  fi
}

stop_stale_project_process "$BACKEND_PID_FILE" "$BACKEND" "$BACKEND/.venv/bin/python" "backend"
stop_stale_project_process "$FRONTEND_PID_FILE" "$FRONTEND" "$FRONTEND/node_modules/.bin/vite" "frontend"

if ! pid_file_is_project_process "$BACKEND_PID_FILE" "$BACKEND" "$BACKEND/.venv/bin/python"; then
  rm -f "$BACKEND_PID_FILE"
  if port_is_busy "$BACKEND_PORT"; then
    echo "Backend port $BACKEND_PORT is already in use by another process." >&2
    exit 1
  fi
  ensure_backend_dependencies
  (
    cd "$BACKEND"
    nohup "$BACKEND/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" >> "$LOGS/backend.log" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"
  )
fi

if ! pid_file_is_project_process "$FRONTEND_PID_FILE" "$FRONTEND" "$FRONTEND/node_modules/.bin/vite"; then
  rm -f "$FRONTEND_PID_FILE"
  if port_is_busy "$FRONTEND_PORT"; then
    echo "Frontend port $FRONTEND_PORT is already in use by another process." >&2
    exit 1
  fi
  ensure_frontend_dependencies
  (
    cd "$FRONTEND"
    nohup "$FRONTEND/node_modules/.bin/vite" --host 0.0.0.0 --port "$FRONTEND_PORT" >> "$LOGS/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"
  )
fi

for _ in $(seq 1 40); do
  backend_ready=0
  frontend_ready=0
  curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/dashboard" >/dev/null 2>&1 && backend_ready=1 || true
  curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1 && frontend_ready=1 || true
  if [ "$backend_ready" -eq 1 ] && [ "$frontend_ready" -eq 1 ]; then
    echo "Bakuran POS is running."
    echo "Frontend: http://100.108.61.26:$FRONTEND_PORT"
    echo "Backend:  http://100.108.61.26:$BACKEND_PORT"
    exit 0
  fi
  sleep 0.25
done

echo "Bakuran POS did not become ready. Check $LOGS/backend.log and $LOGS/frontend.log." >&2
exit 1
