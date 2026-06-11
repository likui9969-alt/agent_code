#!/bin/bash
# ============================================================================
# Docker entrypoint — AI Code Assistant
#
# Responsibilities:
#   1. Wait for Redis to be reachable (with timeout).
#   2. Print a startup banner.
#   3. exec uvicorn so signals (SIGTERM / SIGINT) reach the server.
# ============================================================================

set -euo pipefail

REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-info}"
WORKERS="${WORKERS:-1}"

# ── Wait for Redis ──────────────────────────────────────────────────────────
wait_for_redis() {
    local host port
    # Parse host:port from REDIS_URL
    # Supports: redis://host:port/db, redis://:pass@host:port/db
    host=$(echo "$REDIS_URL" | sed -n 's|.*redis://.*@\?\([^:/]*\).*|\1|p')
    port=$(echo "$REDIS_URL" | sed -n 's|.*:\([0-9]\+\)/.*|\1|p' | head -1)
    host="${host:-redis}"
    port="${port:-6379}"

    echo "Waiting for Redis at ${host}:${port} ..."
    local waited=0
    while [ $waited -lt 30 ]; do
        if python -c "
import socket, sys
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${host}', ${port}))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
            echo "Redis is ready."
            return 0
        fi
        sleep 2
        waited=$((waited + 2))
    done
    echo "WARNING: Redis not reachable after ${waited}s — starting anyway (graceful fallback)."
}

# ── Main ────────────────────────────────────────────────────────────────────
echo "============================================"
echo "  AI Code Assistant  v1.0.0"
echo "  Host:   ${APP_HOST}:${APP_PORT}"
echo "  Redis:  ${REDIS_URL}"
echo "  Workers: ${WORKERS}"
echo "============================================"

if [ "${REDIS_ENABLED:-true}" = "true" ]; then
    wait_for_redis
fi

exec python -m uvicorn app.main:app \
    --host "${APP_HOST}" \
    --port "${APP_PORT}" \
    --workers "${WORKERS}" \
    --log-level "${LOG_LEVEL}" \
    --no-access-log
