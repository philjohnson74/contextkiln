"""Deterministic git operations for ADWs, including the guard that keeps them off main.

GitHub doesn't protect main on this repo, so these checks are what enforce the rule.
An agent can switch branches during a build, so every commit and push checks that
the current branch is still the one the ADW created.
"""

import re
import subprocess
from typing import List, Optional

MAIN_BRANCH = "main"
REMOTE = "origin"
MAX_SLUG_LENGTH = 40


class GitError(Exception):
    """A git command failed, or a guard refused to run one."""


def _git(args: List[str], cwd: Optional[str], stdin: Optional[str] = None) -> str:
    """Run git and return its stripped stdout."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def current_branch(cwd: Optional[str] = None) -> str:
    """Return the current branch name.

    Raises:
        GitError: If HEAD is detached
    """
    try:
        return _git(["symbolic-ref", "--short", "HEAD"], cwd)
    except GitError as e:
        raise GitError(f"Not on a branch (detached HEAD?): {e}") from e


def ensure_on_work_branch(expected: str, cwd: Optional[str] = None) -> None:
    """Refuse to continue unless on the expected branch, which must not be main.

    Raises:
        GitError: If the expected branch is main, or the current branch differs
    """
    if expected == MAIN_BRANCH:
        raise GitError(f"Refusing to commit or push on {MAIN_BRANCH}")
    branch = current_branch(cwd)
    if branch == MAIN_BRANCH:
        raise GitError(f"Refusing to commit or push on {MAIN_BRANCH}")
    if branch != expected:
        raise GitError(f"Expected to be on {expected}, but on {branch}")


def is_clean(cwd: Optional[str] = None) -> bool:
    """Return whether the working tree has no changes. Ignored files don't count."""
    return _git(["status", "--porcelain"], cwd) == ""


def changed_files(cwd: Optional[str] = None) -> List[str]:
    """Return every file that differs from main, committed or not, including new ones."""
    tracked = _git(["diff", "--name-only", MAIN_BRANCH], cwd).splitlines()
    untracked = _git(["ls-files", "--others", "--exclude-standard"], cwd).splitlines()
    return sorted(set(tracked) | set(untracked))


def sync_main(cwd: Optional[str] = None) -> None:
    """Check out main and fast-forward it to the remote.

    Raises:
        GitError: If the working tree isn't clean, or main can't be fast-forwarded
    """
    if not is_clean(cwd):
        raise GitError("Working tree isn't clean. Commit or stash changes first")
    _git(["fetch", REMOTE], cwd)
    _git(["checkout", MAIN_BRANCH], cwd)
    _git(["pull", "--ff-only", REMOTE, MAIN_BRANCH], cwd)


def slugify(text: str) -> str:
    """Turn free text into a short branch-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH].rstrip("-") or "task"


def branch_name(adw_type: str, adw_id: str, description: str) -> str:
    """Build a branch name, e.g. adw/chore-a1b2c3d4-health-endpoint."""
    return f"adw/{adw_type}-{adw_id}-{slugify(description)}"


def create_branch(name: str, cwd: Optional[str] = None) -> None:
    """Create a work branch from the current commit and switch to it.

    Raises:
        GitError: If the name is main, or the branch already exists
    """
    if name == MAIN_BRANCH:
        raise GitError(f"Refusing to create a work branch named {MAIN_BRANCH}")
    _git(["checkout", "-b", name], cwd)


def commit_all(
    message: str, adw_id: str, expected_branch: str, cwd: Optional[str] = None
) -> str:
    """Stage everything git doesn't ignore, commit it and return the commit SHA.

    The adw_id trailer is added here, so it can't depend on an agent's message.

    Raises:
        GitError: If on the wrong branch, or there's nothing to commit
    """
    ensure_on_work_branch(expected_branch, cwd)
    if not message.strip():
        raise GitError("Refusing to commit with an empty message")
    _git(["add", "-A"], cwd)
    if _git(["diff", "--cached", "--name-only"], cwd) == "":
        raise GitError("Nothing to commit")
    _git(["commit", "-F", "-", "--trailer", f"ADW-Id: {adw_id}"], cwd, stdin=message)
    return _git(["rev-parse", "HEAD"], cwd)


def push_branch(expected_branch: str, cwd: Optional[str] = None) -> None:
    """Push the work branch to the same-named remote branch, and nowhere else.

    Raises:
        GitError: If on the wrong branch, or the push fails
    """
    ensure_on_work_branch(expected_branch, cwd)
    refspec = f"HEAD:refs/heads/{expected_branch}"
    _git(["push", "--set-upstream", REMOTE, refspec], cwd)


def return_to_main(cwd: Optional[str] = None) -> None:
    """Switch back to main so the next ADW starts clean."""
    _git(["checkout", MAIN_BRANCH], cwd)
