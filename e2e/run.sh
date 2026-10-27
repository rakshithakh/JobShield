
#!/usr/bin/env bash

# Boots the backend with a fresh SQLite database and the built frontend,
# runs the browser tests, and tears everything down.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB="$(mktemp -u /tmp/jobsentinel_e2e_XXXX.db)"

export DATABASE_URL="sqlite:///$DB" \
  ENVIRONMENT=development \
  CORS_ORIGINS=http://localhost:4173 \
  RATE_LIMIT_PER_MINUTE=1000 \
  VITE_API_BASE_URL=http://localhost:8000

(
  cd "$ROOT/backend"
  alembic upgrade head >/dev/null
  exec uvicorn app.main:create_app --factory --port 8000 \
    >/tmp/e2e_api.log 2>&1
) &
API=$!

(
  cd "$ROOT/frontend"
  npm run build >/dev/null
  exec npx vite preview --port 4173 --strictPort \
    >/tmp/e2e_web.log 2>&1
) &
WEB=$!

trap 'kill "$API" "$WEB" 2>/dev/null || true; rm -f "$DB"' EXIT

for i in $(seq 1 60); do
  if curl -sf localhost:8000/api/v1/health >/dev/null &&
     curl -sf localhost:4173 >/dev/null; then
    break
  fi
  sleep 1
done

cd "$ROOT"
python3 -m pytest e2e -q "$@"
