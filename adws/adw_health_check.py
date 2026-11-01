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
Check that the tools and model server an ADW depends on are ready.

Exits 0 if every check passes and 1 if any fails. With the local profile, this
loads the model if it isn't loaded already.

Usage:
    ./adws/adw_health_check.py

Examples:
    # Check a specific model profile
    ./adws/adw_health_check.py --profile local
"""

import os
import sys
import click
from rich.console import Console
from rich.table import Table

# Add the adw_modules directory to the path so we can import health
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "adw_modules"))

from health import run_health_checks
from models import DEFAULT_PROFILE, PROFILE_NAMES


@click.command()
@click.option(
    "--profile",
    type=click.Choice(PROFILE_NAMES),
    envvar="ADW_PROFILE",
    default=DEFAULT_PROFILE,
    show_default=True,
    help="Model profile to use (default can be set with ADW_PROFILE)",
)
def main(profile: str):
    """Check that the tools and model server an ADW depends on are ready."""
    console = Console()
    checks = run_health_checks(profile)

    table = Table(title=f"Health check: {profile}", box=None)
    table.add_column("Check", style="bold cyan")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    for check in checks:
        status = "[green]✅ OK[/green]" if check.ok else "[red]❌ Failed[/red]"
        table.add_row(check.name, status, check.detail)
    console.print(table)

    sys.exit(0 if all(check.ok for check in checks) else 1)


if __name__ == "__main__":
    main()
