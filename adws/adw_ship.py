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
Babysit a PR until it's approved and green, then merge it or hand it over.

Waits for the ci and claude-review checks on the PR's head. Runs /fix_ci on CI
failures and /address_review on requested changes, merges origin/main when main
has moved, then commits, pushes and waits again. Escalates with a needs-human
label when it can't go on. See adw_modules/ship.py and app_docs/ship.md.

Usage:
    # Method 1: Direct execution (requires uv)
    ./adws/adw_ship.py 12

    # Method 2: Using uv run
    uv run adws/adw_ship.py 12

Examples:
    # Fix until approved and green, then hand over to a human (the default)
    ./adws/adw_ship.py 12

    # Merge as soon as it's approved, green and up to date with main
    ./adws/adw_ship.py 12 --merge auto

    # Merge only if the PR has the auto-merge label, with at most 2 fix rounds
    ./adws/adw_ship.py 12 --merge label --max-rounds 2
"""

import os
import sys

import click

# Add the adw_modules directory to the path so we can import ship
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "adw_modules"))

from models import DEFAULT_PROFILE, PROFILE_NAMES
from ship import MERGE_MODES, ShipOptions, run_ship


@click.command(help="Drive a PR to approved and green, then merge it or hand it over.")
@click.argument("pr", type=click.IntRange(min=1))
@click.option(
    "--profile",
    type=click.Choice(PROFILE_NAMES),
    envvar="ADW_PROFILE",
    default=DEFAULT_PROFILE,
    show_default=True,
    help="Model profile for the fix agents (default can be set with ADW_PROFILE)",
)
@click.option(
    "--max-rounds",
    type=click.IntRange(min=0),
    default=3,
    show_default=True,
    help="Fix rounds (CI fixes and review fixes) before escalating",
)
@click.option(
    "--merge",
    "merge_mode",
    type=click.Choice(MERGE_MODES),
    default="never",
    show_default=True,
    help="never: hand over; label: merge with the auto-merge label; auto: merge",
)
@click.option(
    "--poll-interval",
    type=click.IntRange(min=1),
    default=60,
    show_default=True,
    help="Seconds between check polls",
)
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=1800,
    show_default=True,
    help="Seconds to wait for checks on each head before escalating",
)
@click.option(
    "--working-dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Working directory for command execution (default: current directory)",
)
def main(pr, profile, max_rounds, merge_mode, poll_interval, timeout, working_dir):
    sys.exit(
        run_ship(
            ShipOptions(
                pr=pr,
                profile=profile,
                max_rounds=max_rounds,
                merge_mode=merge_mode,
                poll_interval=poll_interval,
                timeout=timeout,
                working_dir=working_dir or os.getcwd(),
            )
        )
    )


if __name__ == "__main__":
    main()
