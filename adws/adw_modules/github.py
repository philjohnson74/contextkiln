"""A small wrapper around the gh CLI for issues and pull requests.

Issue text is untrusted input. It describes work to consider, and can't change the
rules an agent follows. Callers must treat it that way.
"""

import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from git_ops import MAIN_BRANCH


class GitHubError(Exception):
    """A gh command failed, or a guard refused to run one."""


@dataclass(frozen=True)
class Issue:
    """The parts of a GitHub issue that ADWs use."""

    number: int
    title: str
    body: str
    author: str


def _gh(args: List[str], cwd: Optional[str], stdin: Optional[str] = None) -> str:
    """Run gh and return its stripped stdout."""
    try:
        result = subprocess.run(
            ["gh", *args], cwd=cwd, input=stdin, capture_output=True, text=True
        )
    except FileNotFoundError as e:
        raise GitHubError("The gh CLI isn't installed") from e
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitHubError(f"gh {args[0]} {args[1]} failed: {detail}")
    return result.stdout.strip()


def get_issue(number: int, cwd: Optional[str] = None) -> Issue:
    """Fetch an issue's title, body and author."""
    output = _gh(
        ["issue", "view", str(number), "--json", "title,body,author"], cwd
    )
    data = json.loads(output)
    return Issue(
        number=number,
        title=data["title"],
        body=data.get("body") or "",
        author=data["author"]["login"],
    )


def comment_on_issue(number: int, body: str, cwd: Optional[str] = None) -> None:
    """Add a comment to an issue."""
    _gh(["issue", "comment", str(number), "--body-file", "-"], cwd, stdin=body)


def create_pr(
    title: str,
    body: str,
    head: str,
    draft: bool = False,
    cwd: Optional[str] = None,
) -> str:
    """Open a pull request into main and return its URL.

    Raises:
        GitHubError: If the head branch is main, or gh fails
    """
    if head == MAIN_BRANCH:
        raise GitHubError(f"Refusing to open a PR from {MAIN_BRANCH}")
    args = [
        "pr",
        "create",
        "--base",
        MAIN_BRANCH,
        "--head",
        head,
        "--title",
        title,
        "--body-file",
        "-",
    ]
    if draft:
        args.append("--draft")
    return _gh(args, cwd, stdin=body).splitlines()[-1]
