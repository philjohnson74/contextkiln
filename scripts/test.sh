#!/usr/bin/env bash
# Run all tests from the repo root. Phase 4 adds the backend and frontend suites.
set -euo pipefail

cd "$(dirname "$0")/.."

uv run --with pytest --with pydantic --with python-dotenv --with click --with rich \
  pytest adws/tests "$@"
