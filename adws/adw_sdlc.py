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
Run the whole lifecycle for one piece of work: plan, build, test, open a PR, ship.

Takes a prompt, a GitHub issue, or nothing (the oldest open adw-ready issue opened
by the repo owner). Runs the lifecycle to open a ready PR, then adw_ship to fix it
until it's approved and green, and merges or hands it over. Closes the issue once
merged, or comments on it. See adw_modules/sdlc.py and app_docs/sdlc.md.

Usage:
    # Method 1: Direct execution (requires uv)
    ./adws/adw_sdlc.py "Add a health endpoint"

    # Method 2: Using uv run
    uv run adws/adw_sdlc.py --issue 12

Examples:
    # From a prompt, handing the approved PR over to a human (the default)
    ./adws/adw_sdlc.py "Add a health endpoint"

    # From an issue
    ./adws/adw_sdlc.py --issue 12

    # The oldest ready backlog issue
    ./adws/adw_sdlc.py

    # Build on the local model, merge only PRs with the auto-merge label
    ./adws/adw_sdlc.py --issue 12 --build-profile local --merge label
"""

import os
import sys

import click

# Add the adw_modules directory to the path so we can import sdlc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "adw_modules"))

from models import DEFAULT_PROFILE, PROFILE_NAMES
from sdlc import ADW_TYPES, SdlcOptions, run_sdlc
from ship import MERGE_MODES


@click.command(help="Plan, build, test, open and ship a PR for a prompt or an issue.")
@click.argument("prompt", required=False)
@click.option("--issue", type=click.IntRange(min=1), help="Work on this GitHub issue")
@click.option(
    "--type",
    "adw_type",
    type=click.Choice(ADW_TYPES),
    help="Workflow type (default: from the issue's bug/chore label, else feature)",
)
@click.option(
    "--profile",
    type=click.Choice(PROFILE_NAMES),
    envvar="ADW_PROFILE",
    default=DEFAULT_PROFILE,
    show_default=True,
    help="Model profile to use (default can be set with ADW_PROFILE)",
)
@click.option(
    "--plan-profile",
    type=click.Choice(PROFILE_NAMES),
    help="Model profile for planning (default: --profile)",
)
@click.option(
    "--build-profile",
    type=click.Choice(PROFILE_NAMES),
    help="Model profile for building (default: --profile)",
)
@click.option(
    "--ship-profile",
    type=click.Choice(PROFILE_NAMES),
    help="Model profile for the ship fix agents (default: --profile)",
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
    "--max-rounds",
    type=click.IntRange(min=0),
    default=3,
    show_default=True,
    help="Fix rounds (CI fixes and review fixes) before escalating",
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
def main(
    prompt,
    issue,
    adw_type,
    profile,
    plan_profile,
    build_profile,
    ship_profile,
    merge_mode,
    max_rounds,
    poll_interval,
    timeout,
    working_dir,
):
    if prompt and issue:
        raise click.UsageError("Give a PROMPT or --issue, not both")
    sys.exit(
        run_sdlc(
            SdlcOptions(
                prompt=prompt,
                issue=issue,
                adw_type=adw_type,
                plan_profile=plan_profile or profile,
                build_profile=build_profile or profile,
                ship_profile=ship_profile or profile,
                merge_mode=merge_mode,
                max_rounds=max_rounds,
                poll_interval=poll_interval,
                timeout=timeout,
                working_dir=working_dir or os.getcwd(),
            )
        )
    )


if __name__ == "__main__":
    main()
