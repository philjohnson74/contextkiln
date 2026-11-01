#!/usr/bin/env bash
# Run all tests from the repo root: the ADWs, then the backend and frontend.
# Any arguments are passed to the ADW test run.
set -euo pipefail

cd "$(dirname "$0")/.."

uv run --with pytest --with pydantic --with python-dotenv --with click --with rich \
  pytest adws/tests "$@"

(cd apps/backend && uv run pytest)

[ -d apps/frontend/node_modules ] || (cd apps/frontend && npm ci)
(cd apps/frontend && npm test)
