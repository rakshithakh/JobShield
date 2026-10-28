#!/usr/bin/env bash
# Boots the backend with a fresh SQLite database and the built frontend,
# runs the browser tests, and tears everything down.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Prefer the repository venv (Windows Git Bash or POSIX); CI can use its PATH-installed tools.
if [[ -f "$ROOT/backend/.venv/Scripts/python.exe" ]]; then
  PYTHON="$ROOT/backend/.venv/Scripts/python.exe"
  ALEMBIC="$ROOT/backend/.venv/Scripts/alembic.exe"
elif [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PYTHON="$ROOT/backend/.venv/bin/python"
  ALEMBIC="$ROOT/backend/.venv/bin/alembic"
else
  PYTHON="$(command -v python3 || command -v python || true)"
  ALEMBIC="$(command -v alembic || true)"
fi

if [[ -z "$PYTHON" || ! -f "$PYTHON" ]]; then
  echo "Could not find Python. Expected backend/.venv or python3/python on PATH." >&2
  exit 1
fi

run_alembic() {
  if [[ -n "$ALEMBIC" && -f "$ALEMBIC" ]]; then
    "$ALEMBIC" "$@"
  else
    "$PYTHON" -m alembic "$@"
  fi
}

# Use the familiar ports when available; otherwise select free loopback ports so
# an existing development server cannot be mistaken for this E2E instance.
choose_port() {
  "$PYTHON" - "$1" "$2" <<'PY'
import socket
import sys

preferred = int(sys.argv[1])
excluded = {int(value) for value in sys.argv[2:] if value}

def available(port):
    if port in excluded:
        return False
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

if available(preferred):
    print(preferred)
else:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        while port in excluded:
            sock.close()
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        print(port)
PY
}

API_PORT="$(choose_port "${E2E_API_PORT:-8000}" "")"
WEB_PORT="$(choose_port "${E2E_WEB_PORT:-4173}" "$API_PORT")"
API_ORIGIN="http://127.0.0.1:$API_PORT"
WEB_ORIGIN="http://127.0.0.1:$WEB_PORT"

# mkstemp reserves a real, writable database file and emits a native path that
# SQLAlchemy accepts on Windows (sqlite:///C:/...) and POSIX (sqlite:////tmp/...).
DB="$($PYTHON -c 'import os, tempfile; fd, path = tempfile.mkstemp(prefix="jobsentinel_e2e_", suffix=".db"); os.close(fd); print(path.replace("\\", "/"))')"
TMP_DIR="${DB%/*}"
API_LOG="$TMP_DIR/jobsentinel_e2e_api.log"
WEB_LOG="$TMP_DIR/jobsentinel_e2e_web.log"

export DATABASE_URL="sqlite:///$DB" \
  ENVIRONMENT=development \
  CORS_ORIGINS="$WEB_ORIGIN" \
  RATE_LIMIT_PER_MINUTE=1000 \
  VITE_API_BASE_URL="$API_ORIGIN" \
  E2E_BASE_URL="$WEB_ORIGIN"

API=""
WEB=""
stop_server() {
  local pid="$1"
  [[ -z "$pid" ]] && return

  if [[ "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    # Git Bash PIDs differ from Windows PIDs. Terminate the Windows process tree
    # so npm/npx child processes do not survive the Bash wrapper.
    local windows_pid
    windows_pid="$(ps -W -p "$pid" | awk 'NR == 2 { print $4 }')"
    if [[ "$windows_pid" =~ ^[0-9]+$ ]] && command -v taskkill.exe >/dev/null 2>&1; then
      taskkill.exe //PID "$windows_pid" //T //F >/dev/null 2>&1 || true
    fi
  fi

  kill "$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
}

cleanup() {
  stop_server "$API"
  stop_server "$WEB"
  rm -f -- "$DB" "$DB-wal" "$DB-shm" "$API_LOG" "$WEB_LOG"
}
trap cleanup EXIT

if ! (cd "$ROOT/backend" && run_alembic upgrade head) >"$API_LOG" 2>&1; then
  echo "E2E database migration failed. Recent backend log:" >&2
  tail -n 80 "$API_LOG" >&2 || true
  exit 1
fi

echo "Starting E2E servers (API $API_ORIGIN, frontend $WEB_ORIGIN)."

(
  cd "$ROOT/backend"
  exec "$PYTHON" -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port "$API_PORT"
) >"$API_LOG" 2>&1 &
API=$!

(
  cd "$ROOT/frontend"
  npm run build
  exec node "$ROOT/frontend/node_modules/vite/bin/vite.js" preview \
    --host 127.0.0.1 --port "$WEB_PORT" --strictPort
) >"$WEB_LOG" 2>&1 &
WEB=$!

API_READY=0
WEB_READY=0
PREFLIGHT_HEADERS="$TMP_DIR/api-preflight.headers"
for ((i = 1; i <= 90; i++)); do
  if (( API_READY == 0 )) && curl -fsS "$API_ORIGIN/api/v1/health" >/dev/null 2>&1; then
    if curl -fsS -X OPTIONS "$API_ORIGIN/api/v1/dashboard/summary" \
      -H "Origin: $WEB_ORIGIN" \
      -H "Access-Control-Request-Method: GET" \
      -H "Access-Control-Request-Headers: x-session-token" \
      -D "$PREFLIGHT_HEADERS" -o /dev/null 2>/dev/null &&
      grep -qiF "access-control-allow-origin: $WEB_ORIGIN" "$PREFLIGHT_HEADERS"; then
      API_READY=1
    fi
  fi
  if (( WEB_READY == 0 )) && curl -fsS "$WEB_ORIGIN/" >/dev/null 2>&1; then
    WEB_READY=1
  fi
  if (( API_READY == 1 && WEB_READY == 1 )); then
    break
  fi
  sleep 1
done

if (( API_READY == 0 || WEB_READY == 0 )); then
  echo "E2E server startup timed out after 90 seconds (API and CORS ready: $API_READY, frontend ready: $WEB_READY)." >&2
  echo "Recent backend log ($API_LOG):" >&2
  tail -n 80 "$API_LOG" >&2 || true
  echo "Recent frontend log ($WEB_LOG):" >&2
  tail -n 80 "$WEB_LOG" >&2 || true
  exit 1
fi

cd "$ROOT"
"$PYTHON" -m pytest e2e -q "$@"
