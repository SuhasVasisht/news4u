#!/bin/sh
set -eu

: "${RUN_DB_MIGRATIONS_ON_STARTUP:=true}"
: "${STARTUP_CATCHUP_ENABLED:=true}"
: "${WEB_STARTUP_HEALTH_RETRIES:=60}"

if [ "$RUN_DB_MIGRATIONS_ON_STARTUP" = "true" ]; then
  npm run db:migrate
fi

npm run start &
app_pid=$!

cleanup() {
  kill "$app_pid" 2>/dev/null || true
}

trap cleanup INT TERM

attempt=0
until curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$WEB_STARTUP_HEALTH_RETRIES" ]; then
    echo "web failed to become healthy during startup" >&2
    exit 1
  fi
  sleep 1
done

if [ "$STARTUP_CATCHUP_ENABLED" = "true" ]; then
  if ! npm run startup:catchup; then
    echo "startup catch-up failed; leaving web online for later retry" >&2
  fi
fi

wait "$app_pid"
