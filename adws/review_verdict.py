#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "click",
# ]
# ///
"""
Post the Claude review verdict to a PR and set the `claude-review` check.

Used by `.github/workflows/claude-review.yml` after the reviewer has written
`.review/review.md`.

Usage:
    uv run adws/review_verdict.py post \\
        --review-file .review/review.md \\
        --pr 12 \\
        --repo owner/name \\
        --comments-file .review/comments.json \\
        --diff-lines 1043

Exit codes:
    0  The verdict is APPROVE and the summary comment was posted.
    1  The verdict is REQUEST_CHANGES, there is no valid verdict, the
       comments file is invalid, or posting the comment failed. An APPROVE
       without full diff coverage (`Diff read: N of M lines`) is downgraded
       to REQUEST_CHANGES and exits 1.
"""

import json
import os
import subprocess
import sys

import click

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "adw_modules"))

import review  # noqa: E402

BOT_LOGIN = "github-actions[bot]"


def post_comment(pr: int, repo: str, body: str) -> None:
    """Post `body` as a PR comment. The only place this script calls gh."""
    result = subprocess.run(
        ["gh", "pr", "comment", str(pr), "--repo", repo, "--body-file", "-"],
        input=body,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh pr comment failed: {result.stderr.strip()}")


def bot_comment_bodies(comments: list) -> list[str]:
    """Return the bodies of comments posted by `github-actions[bot]`."""
    return [
        c.get("body") or ""
        for c in comments
        if isinstance(c, dict) and (c.get("user") or {}).get("login") == BOT_LOGIN
    ]


@click.group()
def cli():
    """Claude PR review helpers."""


@cli.command()
@click.option("--review-file", type=click.Path(dir_okay=False), required=True,
              help="The reviewer's verdict file, e.g. .review/review.md.")
@click.option("--pr", type=int, required=True, help="Pull request number.")
@click.option("--repo", type=str, required=True, help="Repository as owner/name.")
@click.option("--comments-file", type=click.Path(exists=True, dir_okay=False),
              required=True, help="JSON list of the PR's issue comments.")
@click.option("--diff-lines", type=click.IntRange(min=0), required=True,
              help="Line count of .review/diff.patch; 0 means nothing to read.")
def post(review_file, pr, repo, comments_file, diff_lines):
    """Post the summary comment with its marker; exit 0 only on APPROVE."""
    try:
        with open(comments_file, encoding="utf-8") as f:
            comments = json.load(f)
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"cannot read comments file: {exc}")
    if not isinstance(comments, list):
        raise click.ClickException("comments file must contain a JSON list")

    round_number = review.next_round(bot_comment_bodies(comments))

    valid = True
    reason = ""
    try:
        with open(review_file, encoding="utf-8") as f:
            text = f.read()
        verdict, summary = review.parse_review_file(text)
    except FileNotFoundError:
        valid, reason = False, "review file not found"
    except OSError as exc:
        valid, reason = False, f"cannot read review file: {exc}"
    except ValueError as exc:
        valid, reason = False, str(exc)

    if valid:
        verdict, summary = review.enforce_coverage(verdict, summary, diff_lines)
    else:
        verdict = "REQUEST_CHANGES"
        summary = review.no_verdict_summary(reason)

    body = review.format_summary_comment(verdict, summary, round_number)
    try:
        post_comment(pr, repo, body)
    except Exception as exc:  # noqa: BLE001 - any failure must turn the check red
        click.echo(f"error: {exc}", err=True)
        sys.exit(1)

    if valid:
        click.echo(verdict)
    else:
        click.echo(f"REQUEST_CHANGES (no valid verdict: {reason})")
    sys.exit(0 if verdict == "APPROVE" else 1)


if __name__ == "__main__":
    cli()
