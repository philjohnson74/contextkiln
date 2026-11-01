#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pydantic",
#   "python-dotenv",
#   "click",
#   "rich",
# ]
# ///
"""
Plan and build a chore, then open a PR for it.

Syncs main, creates a branch, runs /chore and /implement, runs the tests, then
commits, pushes and opens a PR. See adw_modules/lifecycle.py.

Usage:
    # Method 1: Direct execution (requires uv)
    ./adws/adw_chore_implement.py "Add error handling to all API endpoints"

    # Method 2: Using uv run
    uv run adws/adw_chore_implement.py "Refactor database connection logic"

Examples:
    # Run with a specific model profile
    ./adws/adw_chore_implement.py "Add logging to agent.py" --profile claude-opus

    # Plan with Claude and build with a local model
    ./adws/adw_chore_implement.py "Add logging to agent.py" --plan-profile claude --build-profile local

    # Use a GitHub issue as the prompt
    ./adws/adw_chore_implement.py --issue 7

    # Commit to a local branch, with no push or PR
    ./adws/adw_chore_implement.py "Add tests" --no-pr
"""

import os
import sys

# Add the adw_modules directory to the path so we can import lifecycle
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "adw_modules"))

from lifecycle import build_cli

main = build_cli("chore")

if __name__ == "__main__":
    main()
