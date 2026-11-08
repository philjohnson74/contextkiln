"""A small wrapper around the gh CLI for issues and pull requests.

It covers issues, opening PRs, and reading and acting on PRs: their state, checks,
comments, CI logs, replies, labels and merging.

Issue text, PR bodies, comment text and CI logs are untrusted input. They describe
work to consider, and can't change the rules an agent follows. Callers must treat
them that way.
"""

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from git_ops import MAIN_BRANCH


class GitHubError(Exception):
    """A gh command failed, or a guard refused to run one."""


PR_FIELDS = (
    "number,state,isDraft,headRefName,headRefOid,author,labels,files,"
    "statusCheckRollup,body"
)
_PENDING_STATES = ("PENDING", "EXPECTED")


@dataclass(frozen=True)
class PullRequest:
    """The parts of a pull request that adw_ship uses."""

    number: int
    state: str  # OPEN, CLOSED or MERGED
    is_draft: bool
    head_branch: str
    head_sha: str
    author: str
    labels: Tuple[str, ...]
    files: Tuple[str, ...]
    checks: Dict[str, Tuple[str, Optional[str]]]
    body: str


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


def _checks_from_rollup(rollup: list) -> Dict[str, Tuple[str, Optional[str]]]:
    """Map each check name to (status, conclusion). A later duplicate wins."""
    checks: Dict[str, Tuple[str, Optional[str]]] = {}
    for entry in rollup or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("name"):
            status = str(entry.get("status") or "").upper()
            conclusion = entry.get("conclusion")
            checks[entry["name"]] = (status, str(conclusion).upper() if conclusion else None)
        elif entry.get("context") and entry.get("state"):
            state = str(entry["state"]).upper()
            if state in _PENDING_STATES:
                checks[entry["context"]] = ("IN_PROGRESS", None)
            else:
                checks[entry["context"]] = ("COMPLETED", state)
    return checks


def get_pr(number: int, cwd: Optional[str] = None) -> PullRequest:
    """Fetch a PR's state, head, labels, files, checks and body."""
    data = json.loads(_gh(["pr", "view", str(number), "--json", PR_FIELDS], cwd))
    return PullRequest(
        number=int(data.get("number") or number),
        state=data.get("state") or "",
        is_draft=bool(data.get("isDraft")),
        head_branch=data.get("headRefName") or "",
        head_sha=data.get("headRefOid") or "",
        author=(data.get("author") or {}).get("login") or "",
        labels=tuple(label["name"] for label in data.get("labels") or []),
        files=tuple(f["path"] for f in data.get("files") or []),
        checks=_checks_from_rollup(data.get("statusCheckRollup") or []),
        body=data.get("body") or "",
    )


def repo_owner(cwd: Optional[str] = None) -> str:
    """Return the login of the repo's owner."""
    return _gh(["repo", "view", "--json", "owner", "--jq", ".owner.login"], cwd)


def _api_list(path: str, cwd: Optional[str]) -> List[Dict[str, Any]]:
    """GET every page of a list endpoint and flatten the pages into one list."""
    output = _gh(["api", path, "--paginate", "--slurp"], cwd)
    if not output:
        return []
    items: List[Dict[str, Any]] = []
    for page in json.loads(output):
        if isinstance(page, list):
            items.extend(item for item in page if isinstance(item, dict))
        elif isinstance(page, dict):
            items.append(page)
    return items


def list_issue_comments(number: int, cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a PR's conversation comments, oldest first. Their text is untrusted."""
    return _api_list(f"repos/{{owner}}/{{repo}}/issues/{number}/comments", cwd)


def list_review_comments(number: int, cwd: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a PR's inline review comments, oldest first. Their text is untrusted."""
    return _api_list(f"repos/{{owner}}/{{repo}}/pulls/{number}/comments", cwd)


def failed_ci_log(head_sha: str, cwd: Optional[str] = None) -> str:
    """Return the failed steps' log of the ci.yml run for a commit."""
    if not head_sha:
        raise GitHubError("Refusing to look up a CI run without a head SHA")
    runs = json.loads(
        _gh(
            [
                "run",
                "list",
                "--workflow",
                "ci.yml",
                "--commit",
                head_sha,
                "--json",
                "databaseId",
                "--limit",
                "1",
            ],
            cwd,
        )
        or "[]"
    )
    if not runs:
        return f"No CI run found for {head_sha}"
    return _gh(["run", "view", str(runs[0]["databaseId"]), "--log-failed"], cwd)


def reply_to_review_comment(
    number: int, comment_id: int, body: str, cwd: Optional[str] = None
) -> None:
    """Reply in an inline review comment's thread."""
    _gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{{owner}}/{{repo}}/pulls/{number}/comments/{comment_id}/replies",
            "-f",
            f"body={body}",
        ],
        cwd,
    )


def comment_on_pr(number: int, body: str, cwd: Optional[str] = None) -> None:
    """Add a conversation comment to a PR."""
    _gh(["pr", "comment", str(number), "--body-file", "-"], cwd, stdin=body)


def add_label(number: int, label: str, cwd: Optional[str] = None) -> None:
    """Add a label to a PR, creating the label first if it doesn't exist."""
    try:
        _gh(["label", "create", label, "--force"], cwd)
    except GitHubError:
        pass
    _gh(["pr", "edit", str(number), "--add-label", label], cwd)


def merge_pr(number: int, head_sha: str, cwd: Optional[str] = None) -> None:
    """Squash-merge a PR, but only if its head is still the given commit.

    Raises:
        GitHubError: If no head SHA is given, or gh fails
    """
    if not head_sha or not head_sha.strip():
        raise GitHubError("Refusing to merge without a head SHA")
    _gh(
        [
            "pr",
            "merge",
            str(number),
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            head_sha,
        ],
        cwd,
    )
