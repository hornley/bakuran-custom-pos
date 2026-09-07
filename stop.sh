#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"

stop_one() {
  local pid_file="$1" expected_cwd="$2" label="$3" pid actual_cwd
  if [ ! -f "$pid_file" ]; then
    echo "$label is not tracked by this project."; return 0
  fi
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  actual_cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    echo "$label is already stopped."; return 0
  fi
  if [ "$actual_cwd" != "$expected_cwd" ]; then
    echo "$label PID $pid is not running from this project; refusing to stop it." >&2
    return 1
  fi
  kill -TERM "$pid"
  for _ in $(seq 1 20); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "$label did not stop cleanly; refusing to force-kill it." >&2
    return 1
  fi
  rm -f "$pid_file"
  echo "$label stopped."
}

stop_one "$LOGS/frontend.pid" "$ROOT/frontend" "Frontend"
stop_one "$LOGS/backend.pid" "$ROOT/backend" "Backend"
