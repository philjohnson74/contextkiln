#!/usr/bin/env bash
# Stop the servers started by scripts/start.sh.
set -euo pipefail

cd "$(dirname "$0")/.."

RUN_DIR=.run

for name in backend frontend; do
  pid_file="$RUN_DIR/$name.pid"
  if [ ! -f "$pid_file" ]; then
    echo "$name: not running"
    continue
  fi

  pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid"
    fi
    echo "$name: stopped"
  else
    echo "$name: not running"
  fi
  rm -f "$pid_file"
done
