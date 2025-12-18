#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Initialize database
python -m elephant.database

# Start cron service in background
python -m elephant.cron --service &
CRON_PID=$!

# Start API server
python -m elephant --host "${HOST}" --port "${PORT}" &
APP_PID=$!

cleanup() {
  kill "${CRON_PID}" "${APP_PID}" 2>/dev/null || true
  wait "${CRON_PID}" "${APP_PID}" 2>/dev/null || true
}

trap cleanup SIGINT SIGTERM

# Wait for either process to exit
wait -n "${CRON_PID}" "${APP_PID}"
EXIT_CODE=$?
cleanup
exit "${EXIT_CODE}"
