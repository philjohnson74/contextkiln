#!/usr/bin/env bash
# Start the backend and frontend in the background. Stop them with scripts/stop.sh.
set -euo pipefail

cd "$(dirname "$0")/.."

BACKEND_PORT=8000
FRONTEND_PORT=5173
RUN_DIR=.run

mkdir -p "$RUN_DIR"

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $port is already in use. Run scripts/stop.sh, or stop whatever is using it." >&2
    exit 1
  fi
done

(cd apps/backend && uv sync --quiet)
[ -d apps/frontend/node_modules ] || (cd apps/frontend && npm ci --silent)

# Run the binaries directly, so the saved PIDs belong to the servers themselves.
(
  cd apps/backend
  exec nohup .venv/bin/uvicorn --factory app.main:create_app \
    --host 127.0.0.1 --port "$BACKEND_PORT" >"../../$RUN_DIR/backend.log" 2>&1
) &
echo $! >"$RUN_DIR/backend.pid"

(
  cd apps/frontend
  exec nohup node_modules/.bin/vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort \
    >"../../$RUN_DIR/frontend.log" 2>&1
) &
echo $! >"$RUN_DIR/frontend.pid"

wait_for() {
  local name=$1 url=$2 log=$3
  for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then
      return 0
    fi
    sleep 0.5
  done
  echo "The $name didn't start. Last lines of $log:" >&2
  tail -n 20 "$log" >&2
  scripts/stop.sh >/dev/null
  exit 1
}

wait_for backend "http://127.0.0.1:$BACKEND_PORT/health" "$RUN_DIR/backend.log"
wait_for frontend "http://127.0.0.1:$FRONTEND_PORT/" "$RUN_DIR/frontend.log"

echo "Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "Logs:     $RUN_DIR/"
