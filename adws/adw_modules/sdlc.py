"""adw_sdlc: plan, build, test, open a PR, then ship it, for one prompt or issue.

This composes the lifecycle (`lifecycle.run_lifecycle`) and the babysitter
(`ship.run_ship_with_summary`) under one `adw_id`. Control flow is deterministic
Python. Agents only edit code and write text, inside those two workflows.

Issue text is untrusted input. Only issues opened by the repo owner are worked on,
and that's checked before any GitHub write. The lifecycle hands the issue text to
agents marked as untrusted.
"""

import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

import agent
import git_ops
import github
from git_ops import GitError
from github import GitHubError, Issue
from health import run_health_checks
from lifecycle import WorkflowError, WorkflowOptions, _write_summary, run_lifecycle
from models import get_profile
from ship import NEEDS_HUMAN_LABEL, ShipOptions, _append_run_log, run_ship_with_summary

ADW_TYPES = ("feature", "chore", "bug")
READY_LABEL = "adw-ready"
IN_PROGRESS_LABEL = "adw-in-progress"
SKIP_LABELS = (NEEDS_HUMAN_LABEL, IN_PROGRESS_LABEL)
MAX_COMMENT_DETAIL_CHARS = 1000

SUCCESS_OUTCOMES = ("merged", "handed_over")


class SdlcRefused(Exception):
    """The input isn't something sdlc may work on (a non-owner or closed issue)."""


@dataclass(frozen=True)
class SdlcOptions:
    """Everything an adw_sdlc run needs."""

    prompt: Optional[str]
    issue: Optional[int]
    adw_type: Optional[str]
    plan_profile: str
    build_profile: str
    ship_profile: str
    merge_mode: str
    max_rounds: int
    poll_interval: int
    timeout: int
    working_dir: str


def select_type(explicit: Optional[str], issue: Optional[Issue]) -> str:
    """Pick the workflow type: --type wins, then a bug or chore label, else feature."""
    if explicit:
        return explicit
    if issue is not None:
        if "bug" in issue.labels:
            return "bug"
        if "chore" in issue.labels:
            return "chore"
    return "feature"


def is_ready(issue: Issue, owner: str) -> bool:
    """Return whether backlog pickup may take this issue."""
    return (
        issue.state == "OPEN"
        and issue.author == owner
        and READY_LABEL in issue.labels
        and not any(label in issue.labels for label in SKIP_LABELS)
    )


def next_ready_issue(owner: str, cwd: Optional[str]) -> Optional[Issue]:
    """Return the oldest open, ready issue opened by the owner, or None."""
    ready = [i for i in github.list_issues([READY_LABEL], cwd=cwd) if is_ready(i, owner)]
    return min(ready, key=lambda i: i.number) if ready else None


def outcome_comment(
    outcome: str, adw_id: str, pr_url: Optional[str], reason: Optional[str]
) -> Optional[str]:
    """Build the issue comment for an outcome, or None if there's nothing to say."""
    detail = (reason or "")[:MAX_COMMENT_DETAIL_CHARS]
    if outcome == "handed_over":
        return (
            f"ADW `{adw_id}`: {pr_url} is approved by Claude review and CI is green. "
            "It's waiting for a human merge."
        )
    if outcome in ("escalated", "error", "pr_closed"):
        see = f" See {pr_url} (label `{NEEDS_HUMAN_LABEL}`)." if pr_url else ""
        return f"ADW `{adw_id}` stopped and needs a human: {detail}.{see}"
    if outcome == "build_failed":
        return f"ADW `{adw_id}` couldn't build this issue: {detail}"
    return None


def _best_effort(console: Console, what: str, fn: Callable[..., Any], *args, **kwargs) -> bool:
    """Call a GitHub write. A failure is only a warning."""
    try:
        fn(*args, **kwargs)
        return True
    except GitHubError as e:
        console.print(f"[yellow]Warning: could not {what}: {e}[/yellow]")
        return False


def _comment(console: Console, issue: Optional[Issue], text: Optional[str], cwd: str) -> None:
    if issue is not None and text:
        _best_effort(
            console, f"comment on issue #{issue.number}", github.comment_on_issue,
            issue.number, text, cwd=cwd,
        )


def _preflight(options: SdlcOptions, console: Console) -> str:
    """Check the tree, the input and the ship profile. Return the repo owner."""
    cwd = options.working_dir
    console.print(Rule("[bold yellow]Preflight[/bold yellow]"))
    if not git_ops.is_clean(cwd=cwd):
        raise WorkflowError("Working tree isn't clean. Commit or stash changes first")
    if options.prompt and options.issue:
        raise WorkflowError("Give a prompt or an issue, not both")
    # The lifecycle checks the plan and build profiles; check ship's before a PR exists
    if options.ship_profile not in {options.plan_profile, options.build_profile}:
        failed = [c for c in run_health_checks(options.ship_profile) if not c.ok]
        if failed:
            details = "; ".join(f"{c.name}: {c.detail}" for c in failed)
            raise WorkflowError(f"Health check failed for {options.ship_profile}: {details}")
    return github.repo_owner(cwd=cwd)


def _resolve_issue(options: SdlcOptions, owner: str) -> Optional[Issue]:
    """Fetch and check the --issue. Nothing is written to GitHub here."""
    n = options.issue
    issue = github.get_issue(n, cwd=options.working_dir)
    if issue.author != owner:
        raise SdlcRefused(
            f"Issue #{n} was opened by {issue.author}, not the repo owner {owner}. "
            "Only the owner's issues are worked on."
        )
    if issue.state and issue.state != "OPEN":
        raise SdlcRefused(f"Issue #{n} is closed")
    return issue


def run_sdlc(
    options: SdlcOptions,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> int:
    """Run the whole lifecycle and ship it. Return the process exit code."""
    adw_id = agent.generate_short_id()
    start = now()
    console = Console()
    cwd = options.working_dir
    summary: Dict[str, Any] = {
        "adw_id": adw_id,
        "options": asdict(options),
        "outcome": None,
        "issue": None,
        "pr": None,
        "pr_url": None,
        "type": None,
        "lifecycle": None,
        "ship": None,
    }

    if options.issue:
        source = f"issue #{options.issue}"
    elif options.prompt:
        source = "prompt"
    else:
        source = "next ready backlog issue"
    console.print(
        Panel(
            f"[cyan]ADW ID:[/cyan] {adw_id}\n"
            f"[cyan]Input:[/cyan] {source}\n"
            f"[cyan]Plan:[/cyan] {options.plan_profile} ({get_profile(options.plan_profile).model})\n"
            f"[cyan]Build:[/cyan] {options.build_profile} ({get_profile(options.build_profile).model})\n"
            f"[cyan]Ship:[/cyan] {options.ship_profile} ({get_profile(options.ship_profile).model})\n"
            f"[cyan]Merge:[/cyan] {options.merge_mode}\n"
            f"[cyan]Working Dir:[/cyan] {cwd}",
            title="[bold blue]ADW sdlc[/bold blue]",
            border_style="blue",
        )
    )

    labelled: Optional[int] = None
    issue: Optional[Issue] = None
    code = 1
    try:
        owner = _preflight(options, console)

        if options.issue:
            issue = _resolve_issue(options, owner)
        elif not options.prompt:
            issue = next_ready_issue(owner, cwd)
            if issue is None:
                console.print("[green]No issue is ready[/green]")
                summary["outcome"] = "no_issue"
                code = 0
                return code

        adw_type = select_type(options.adw_type, issue)
        summary["issue"] = issue.number if issue else None
        summary["type"] = adw_type
        if issue:
            console.print(f"[cyan]Issue:[/cyan] #{issue.number} {issue.title}")
            _best_effort(
                console, f"label issue #{issue.number}", github.add_issue_label,
                issue.number, IN_PROGRESS_LABEL, cwd=cwd,
            )
            labelled = issue.number  # Removal is best effort too

        console.print(Rule("[bold yellow]Lifecycle: plan, build, test, PR[/bold yellow]"))
        _, lsum = run_lifecycle(
            WorkflowOptions(
                adw_type=adw_type,
                prompt=None if issue else options.prompt,
                issue=issue.number if issue else None,
                plan_profile=options.plan_profile,
                build_profile=options.build_profile,
                no_pr=False,
                working_dir=cwd,
                draft_on_test_failure=False,
            ),
            adw_id=adw_id,
        )
        summary["lifecycle"] = lsum
        # Failing local tests with a PR opened aren't a build failure: ship fixes CI
        if lsum.get("error") or not lsum.get("pr_url"):
            summary["outcome"] = "build_failed"
            reason = lsum.get("error") or "no PR was opened"
            summary["error"] = reason
            _comment(console, issue, outcome_comment("build_failed", adw_id, None, reason), cwd)
            code = 1
            return code

        pr_url = lsum["pr_url"]
        pr = github.pr_number_from_url(pr_url)
        summary["pr_url"], summary["pr"] = pr_url, pr

        console.print(Rule(f"[bold yellow]Ship PR #{pr}[/bold yellow]"))
        _, ssum = run_ship_with_summary(
            ShipOptions(
                pr=pr,
                profile=options.ship_profile,
                max_rounds=options.max_rounds,
                merge_mode=options.merge_mode,
                poll_interval=options.poll_interval,
                timeout=options.timeout,
                working_dir=cwd,
            ),
            sleep=sleep,
            now=now,
            adw_id=adw_id,
        )
        summary["ship"] = ssum
        outcome = ssum.get("outcome") or "error"
        if outcome == "already_closed":
            outcome = "merged" if github.get_pr(pr, cwd=cwd).state == "MERGED" else "pr_closed"
        summary["outcome"] = outcome

        if outcome == "merged":
            if issue:
                try:
                    still_open = github.get_issue(issue.number, cwd=cwd).state == "OPEN"
                except GitHubError as e:
                    console.print(f"[yellow]Warning: could not re-read issue #{issue.number}: {e}[/yellow]")
                    still_open = False
                if still_open:
                    _best_effort(
                        console, f"close issue #{issue.number}", github.close_issue,
                        issue.number, f"Closed by ADW {adw_id}: merged in {pr_url}", cwd=cwd,
                    )
        elif outcome == "handed_over":
            _comment(console, issue, outcome_comment("handed_over", adw_id, pr_url, None), cwd)
        else:
            reason = ssum.get("escalation_reason") or ssum.get("error") or outcome
            _comment(console, issue, outcome_comment(outcome, adw_id, pr_url, reason), cwd)
        code = 0 if outcome in SUCCESS_OUTCOMES else 1
        console.print(f"[cyan]Outcome:[/cyan] {outcome}")
    except SdlcRefused as e:
        console.print(Panel(str(e), title="[bold red]Refused[/bold red]", border_style="red"))
        summary["outcome"] = "refused"
        summary["error"] = str(e)
        code = 1
    except (GitError, GitHubError, WorkflowError) as e:
        console.print(Panel(str(e), title="[bold red]Failed[/bold red]", border_style="red"))
        summary["outcome"] = "error"
        summary["error"] = str(e)
        if labelled is not None:
            _comment(
                console, issue, outcome_comment("error", adw_id, summary["pr_url"], str(e)), cwd
            )
        code = 1
    finally:
        if labelled is not None:
            _best_effort(
                console, f"remove the {IN_PROGRESS_LABEL} label", github.remove_label,
                labelled, IN_PROGRESS_LABEL, cwd=cwd,
            )
        try:
            branch = git_ops.current_branch(cwd=cwd)
            if git_ops.is_clean(cwd=cwd):
                if branch != git_ops.MAIN_BRANCH:
                    git_ops.return_to_main(cwd=cwd)
            else:
                console.print(f"[yellow]Work left on {branch} with uncommitted changes[/yellow]")
        except GitError as e:
            console.print(f"[yellow]Warning: could not return to main: {e}[/yellow]")

        summary["outcome"] = summary["outcome"] or "error"
        summary["exit_code"] = code
        summary["rounds"] = (summary["ship"] or {}).get("rounds")
        console.print(f"[cyan]Summary:[/cyan] {_write_summary(adw_id, summary, 'sdlc_summary.json')}")
        _append_run_log(
            {
                "adw_id": adw_id,
                "step": "sdlc",
                "issue": summary["issue"],
                "pr": summary["pr"],
                "type": summary["type"],
                "plan_profile": options.plan_profile,
                "build_profile": options.build_profile,
                "ship_profile": options.ship_profile,
                "merge_mode": options.merge_mode,
                "rounds": summary["rounds"],
                "outcome": summary["outcome"],
                "duration_ms": int((now() - start) * 1000),
            }
        )
    return code
