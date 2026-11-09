# Feature: adw_sdlc.py, the composed plan → build → test → PR → ship workflow

## Metadata
adw_id: `198c3482`
prompt: `Add adws/adw_sdlc.py, the composed workflow from PLAN.md Phase 5c: plan → build → test → PR → ship, end to end, from a prompt or a GitHub issue. Also fix a known stale-head gap in adw_ship. Control flow stays deterministic Python; agents only edit code and write text. (Full prompt: 1. stale-head fix in ship.py with expected_head; 2. run_ship adw_id + run_ship_with_summary, run_lifecycle, WorkflowOptions.draft_on_test_failure, github.pr_number_from_url; 3. adws/adw_sdlc.py + adws/adw_modules/sdlc.py with prompt / --issue / next-backlog-issue modes, owner-only issue trust, adw-ready / adw-in-progress labels, outcomes, sdlc_summary.json and a runs.jsonl "sdlc" line; 4. protect adw_sdlc.py and sdlc.py; 5. tests with fakes only; 6. docs. Do not change .claude/settings.json, the workflows, review_pr.md, review_verdict.py or review.py.)`

## Feature Description
`./adws/adw_sdlc.py` runs the whole software lifecycle for one piece of work, without a human touching it:

1. **Plan, build, test and open a PR** with the existing lifecycle (`adws/adw_modules/lifecycle.py`).
2. **Ship the PR** with the existing babysitter (`adws/adw_modules/ship.py`): wait for `ci` and `claude-review`, fix CI failures and review comments, keep it up to date with `main`, then merge or hand over.
3. **Close the loop on the issue**: close it once merged, or comment when it's handed over or escalated.

Input is one of three modes: a free-text prompt, `--issue N`, or nothing (pick the oldest ready backlog issue). Only issues authored by the repo owner are worked on, because the repo may go public. One sdlc run shares one `adw_id`, so every artefact lands in one `agents/{adw_id}/` folder, and it writes a `step: "sdlc"` line to `agents/runs.jsonl` with the build profile and the number of fix rounds. That gives PLAN.md's key metric: rounds-to-approval per build profile.

The feature also fixes a stale-head race in `adw_ship`: right after a push, `gh pr view` can still report the old head for a few seconds, so the loop used to decide on the old head's (failed) checks and crash in `_checkout_head` with "branch moved since the PR was read".

## User Story
As the owner of ContextKiln
I want to label an issue `adw-ready` (or pass a prompt) and have an ADW plan, build, test, open, fix and merge the PR, then close the issue
So that routine work reaches `main` without me, while I compare local and Claude build profiles by rounds-to-approval

## Problem Statement
- The lifecycle (`run_workflow`) and the babysitter (`run_ship`) exist but can't be composed: both generate their own `adw_id`, neither returns its summary, and the lifecycle opens a **draft** PR when local tests fail, which `adw_ship` immediately escalates.
- There's no backlog pickup, no issue trust rule for a public repo, no issue closing and no per-build-profile rounds metric.
- `adw_ship` reads a stale head right after its own push and fails the run.
- The lifecycle has no commit type for `bug`, so `fallback_subject("bug", ...)` would raise `KeyError`.

## Solution Statement
- **Ship fix:** track `expected_head` on `_Run`, set from the SHA of every push (`_fix_round` already returns it; `_update_branch` will too). While GitHub reports a different head for an open PR, the loop WAITs (same per-head timeout) instead of deciding.
- **Reuse:** `run_ship_with_summary(..., adw_id=None) -> (code, summary)` and `run_lifecycle(options, adw_id=None) -> (code, summary)`. `run_ship` and `run_workflow` become thin wrappers with unchanged behaviour. `WorkflowOptions.draft_on_test_failure` (default `True`) lets sdlc always open a ready PR.
- **Composition in Python:** `adws/adw_modules/sdlc.py` holds `run_sdlc` and small pure helpers (`select_type`, `is_ready`, `next_ready_issue`, `pr_outcome_comment`). It runs preflight, labels the issue `adw-in-progress`, calls `run_lifecycle`, then `run_ship_with_summary`, then acts on the outcome, and always cleans up and logs in a `finally`.
- **GitHub wrappers:** `pr_number_from_url`, `list_issues`, `close_issue`, `add_issue_label`, `remove_label`; `Issue` gains `labels` and `state` with defaults so existing callers keep working.
- **CLI:** `adws/adw_sdlc.py`, a single-file uv script with click, in the same style as `adw_ship.py`.
- **Safety:** both new files join `PROTECTED_FILES`, so a PR changing them is never auto-merged.

## Relevant Files
Use these files to implement the feature:

- `PLAN.md` - Section "5c. Composed workflow and a trust ramp" gives the intent. Don't edit it.
- `CLAUDE.md` - Add a Commands row and an `app_docs/sdlc.md` pointer.
- `adws/adw_modules/ship.py` - Stale-head fix (`_Run.expected_head`, `_update_branch` return value, the WAIT branch in `_ship`), `run_ship_with_summary` with `adw_id`, `PROTECTED_FILES`. `_append_run_log` is reused by sdlc.
- `adws/adw_ship.py` - Must keep working unchanged (it calls `run_ship`). No edit needed.
- `adws/adw_modules/lifecycle.py` - `run_lifecycle`, `WorkflowOptions.draft_on_test_failure`, `COMMIT_TYPES["bug"]`. `issue_prompt` already frames issue text as untrusted. `_write_summary` is reused by sdlc.
- `adws/adw_modules/github.py` - `Issue` fields, `get_issue`, and new `list_issues`, `close_issue`, `add_issue_label`, `remove_label`, `pr_number_from_url`.
- `adws/adw_modules/git_ops.py` - Reuse `is_clean`, `current_branch`, `return_to_main`, `head_sha`, `MAIN_BRANCH`. No changes.
- `adws/adw_modules/agent.py` - `generate_short_id`, `RUNS_LOG`. No changes.
- `adws/adw_modules/health.py` - `run_health_checks`, used by sdlc preflight for the ship profile.
- `adws/adw_modules/models.py` - `PROFILE_NAMES`, `DEFAULT_PROFILE`, `get_profile`.
- `adws/adw_feature_implement.py` - Header/docstring style for the uv script.
- `.claude/commands/bug.md` - Exists, writes `specs/bug-{adw_id}-*.md`, so `find_plan("bug", ...)` works.
- `adws/tests/test_ship.py` - Extend `ShipHarness` and add stale-head tests.
- `adws/tests/test_lifecycle.py` - Add `draft_on_test_failure=False`, `run_lifecycle` and bug-type tests.
- `adws/tests/test_github.py` - Add argument-construction tests for the new wrappers.
- `adws/tests/conftest.py` - Already redirects `agent.RUNS_LOG` to `tmp_path` and blocks real agents.
- `app_docs/ship.md` - Protected paths list and the stale-head wait.
- `app_docs/claude-review.md` - Background on the `claude-review` check. Don't edit.
- `adws/README.md` - Add an `adw_sdlc.py` row.

### New Files
- `adws/adw_sdlc.py` - The CLI (single-file uv script, click).
- `adws/adw_modules/sdlc.py` - The composed workflow logic.
- `adws/tests/test_sdlc.py` - Scenario tests with every dependency faked.
- `app_docs/sdlc.md` - What it does and how to use it.

## Implementation Plan
### Phase 1: Foundation
Add the GitHub wrappers and the `Issue` fields, add the `bug` commit type, and make the lifecycle and ship callable with a shared `adw_id` and a returned summary. Fix the stale-head race. All existing tests must still pass after this phase.

### Phase 2: Core Implementation
Write `adws/adw_modules/sdlc.py` (pure helpers plus `run_sdlc`) and the `adws/adw_sdlc.py` CLI.

### Phase 3: Integration
Protect the new files in `ship.py`, write `adws/tests/test_sdlc.py`, and update `app_docs/sdlc.md`, `app_docs/ship.md`, `adws/README.md` and `CLAUDE.md`.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. GitHub wrappers in `adws/adw_modules/github.py`
- Add `import re` and `_PR_URL_RE = re.compile(r"/pull/(\d+)/?$")`.
- Extend `Issue` with defaulted fields, keeping positional construction (`Issue(7, "t", "b", "someone")`) working:
  ```python
  labels: Tuple[str, ...] = ()
  state: str = ""  # OPEN or CLOSED; "" when not fetched
  ```
- Add a private `_issue_from_json(data, number=None) -> Issue` that reads `number`, `title`, `body` (None → `""`), `author.login`, `labels[].name` (missing → `()`), `state` (missing → `""`).
- `get_issue`: request `--json title,body,author,labels,state` and build via `_issue_from_json(data, number)`. With the old test JSON (no labels/state) it must still equal `Issue(7, "A bug", "Details", "someone")`.
- `list_issues(labels: Iterable[str], state: str = "open", cwd=None) -> List[Issue]`: run
  `["issue", "list", "--state", state, "--json", "number,title,body,author,labels,state", "--limit", "200"]` plus `["--label", label]` for each label (gh ANDs repeated `--label`). Parse the JSON list (empty output → `[]`). Don't filter by author here; callers do, because that's the trust boundary.
- `close_issue(number, comment, cwd=None)`: `["issue", "close", str(number), "--comment", comment]`.
- `add_issue_label(number, label, cwd=None)`: like `add_label` (try `label create --force`, ignore its failure) but `["issue", "edit", str(number), "--add-label", label]`.
- `remove_label(number, label, cwd=None)`: `["issue", "edit", str(number), "--remove-label", label]`. Docstring: for issues; callers treat it as best effort.
- `pr_number_from_url(url: str) -> int`: match `_PR_URL_RE` on `url.strip()`; raise `GitHubError(f"Not a pull request URL: {url!r}")` if no match.
- Update the module docstring to mention listing and closing issues.

### 2. Tests for the wrappers in `adws/tests/test_github.py`
- `test_get_issue_reads_labels_and_state`: JSON with `labels: [{"name": "bug"}]`, `state: "OPEN"` → `issue.labels == ("bug",)`, `issue.state == "OPEN"`; the `--json` arg contains `labels` and `state`.
- Existing `test_get_issue` and `test_get_issue_with_empty_body` stay unchanged and pass.
- `test_list_issues_builds_label_filters`: `fake_gh.stdout` = a JSON list of two issues; call `list_issues(["adw-ready"])`; assert cmd starts `["gh", "issue", "list", "--state", "open"]`, contains `"--label", "adw-ready"`, and the result has two `Issue`s with labels parsed.
- `test_list_issues_with_no_output` → `[]`.
- `test_close_issue_passes_the_comment`: cmd == `["gh", "issue", "close", "7", "--comment", "Closed by ADW x"]`.
- `test_add_issue_label_uses_issue_edit` (also when label create fails, using `returncodes = [1, 0]`).
- `test_remove_label`: cmd == `["gh", "issue", "edit", "7", "--remove-label", "adw-in-progress"]`.
- `test_pr_number_from_url` parametrized: `https://github.com/o/r/pull/9` → 9, trailing slash → 9; `https://github.com/o/r/issues/9`, `""`, `"pull/abc"` → `GitHubError`.

### 3. Lifecycle changes in `adws/adw_modules/lifecycle.py`
- `COMMIT_TYPES = {"chore": "chore", "feature": "feat", "bug": "fix"}`.
- Add `draft_on_test_failure: bool = True` as the last field of `WorkflowOptions` (it has a default, so it must come after the others).
- In `_lifecycle`, open the PR with `draft=(not tests.passed) and options.draft_on_test_failure`. The return code is unchanged (`0 if tests.passed else 1`), so existing ADWs behave exactly as today.
- Split `run_workflow`:
  ```python
  def run_lifecycle(options, adw_id: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
      """Run the lifecycle and return the exit code and the summary."""
      # body of today's run_workflow, with adw_id = adw_id or agent.generate_short_id()
      return code, summary

  def run_workflow(options) -> int:
      return run_lifecycle(options)[0]
  ```
  The summary already holds `adw_id`, `branch`, `plan_path`, `changed_files`, `tests_passed`, `commit_subject`, `pr_url`, `error` (on failure) and `exit_code`. Import `Tuple`.

### 4. Lifecycle tests in `adws/tests/test_lifecycle.py`
- Extend `Harness.execute_template` to write a plan for `"/bug"` as well as `/chore` and `/feature`.
- Add `draft_on_test_failure=True` and `adw_id=None` parameters to `Harness.run`; when `adw_id` is given, call `lifecycle.run_lifecycle(options, adw_id=adw_id)` and return the tuple; otherwise keep calling `run_workflow`.
- `test_draft_on_test_failure_false_opens_a_ready_pr`: `tests = TestResult(False, "boom")`, run with `draft_on_test_failure=False` → `prs[0]["draft"] is False`, `"**failed**"` in the body, exit 1.
- `test_run_lifecycle_returns_the_summary_and_uses_the_given_adw_id`: `code, summary = harness.run(adw_id="sdlc1234")` → `code == 0`, `summary["adw_id"] == "sdlc1234"`, `summary["pr_url"] == "https://github.com/o/r/pull/9"`, `summary["tests_passed"] is True`, `summary["plan_path"].startswith("specs/chore-sdlc1234-")`, `"thing.txt" in summary["changed_files"]`, every request's `adw_id == "sdlc1234"`, and `agents/sdlc1234/workflow_summary.json` exists.
- `test_bug_workflow_uses_bug_commands`: `adw_type="bug"`, garbage `/commit` output → first command `/bug`, PR title starts `fix: `, branch starts `adw/bug-`.
- All existing lifecycle tests stay unchanged and pass.

### 5. Stale-head fix and reuse in `adws/adw_modules/ship.py`
- `_Run`: add `expected_head: Optional[str] = None`.
- `_update_branch`: after `git_ops.push_branch(...)`, `sha = git_ops.head_sha(cwd=cwd)`; record `"sha": sha` in the `updates` entry; `return sha` (return type `str`).
- In `_ship`'s loop, right after the `pr.author != run.owner` check and before `list_issue_comments`:
  ```python
  if run.expected_head and pr.state == "OPEN" and pr.head_sha != run.expected_head:
      reason = f"waiting for GitHub to report {run.expected_head[:7]}"
      console.print(Rule(f"{Action.WAIT.value}: {reason}"))
      summary["decisions"].append({"action": Action.WAIT.value, "reason": reason, "head_sha": pr.head_sha})
      if now() >= deadline:
          raise _Escalate(f"timed out {reason}")
      sleep(options.poll_interval)
      continue
  ```
  Only open PRs wait; a merged or closed PR still reaches `decide` (DONE). Once heads match, keep comparing (never cleared); it's harmless.
- `FIX_CI`/`ADDRESS_REVIEW` branch: `run.expected_head = _fix_round(...)`. `UPDATE_BRANCH` branch: `run.expected_head = _update_branch(run, pr)`. The deadline still resets after each push.
- Rename `run_ship`'s body to:
  ```python
  def run_ship_with_summary(options, sleep=time.sleep, now=time.monotonic, adw_id: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
      adw_id = adw_id or agent.generate_short_id()
      ...  # unchanged body
      return code, summary

  def run_ship(options, sleep=time.sleep, now=time.monotonic, adw_id: Optional[str] = None) -> int:
      """Babysit one PR and return the process exit code."""
      return run_ship_with_summary(options, sleep=sleep, now=now, adw_id=adw_id)[0]
  ```
  The ship summary file (`ship_summary.json`) and the `step: "ship"` run-log line are unchanged.
- `PROTECTED_FILES`: add `"adws/adw_sdlc.py"` and `"adws/adw_modules/sdlc.py"`.
- Update the module docstring to mention the stale-head wait.

### 6. Ship tests in `adws/tests/test_ship.py`
- Harness: add `self.update_sha = SHA_B` and `self.merged_head = None`. Fake `head_sha` returns `self.local_head or self.merged_head or self.last_pr.head_sha`. Replace the `merge_main_into` fake with a method that, when `self.merge_ok`, sets `self.merged_head = self.update_sha`, and returns `self.merge_ok`. `return_to_main` also resets `self.merged_head = None`. This keeps `test_update_branch_pushes_without_a_round` passing (its next PR head is `SHA_B`).
- `test_stale_head_after_a_fix_push_waits`: `prs = [pr(review=RED), pr(review=RED), pr(sha=NEW_SHA)]` (the second read is stale: old `SHA_A`, old failed checks), review comments/marker as in `test_b`; `run(merge="never") == 0`; `len(harness.requests) == 1`; `harness.names().count("checkout_pr_branch") == 1`; `harness.sleeps == [60]`; the `ship_summary.json` decisions include a `wait` whose reason is `"waiting for GitHub to report abc1234"`; run log `rounds == 1`, `outcome == "handed_over"`.
- `test_stale_head_after_an_update_waits`: `prs = [pr(), pr(), pr(sha=SHA_B)]`, `up_to_date = [False, True, True]`; `run(merge="auto", max_rounds=0) == 0`; `harness.pushes == ["adw/feature-1-x"]` (one update, not two); `harness.sleeps == [60]`; `harness.merges == [(7, SHA_B)]`.
- `test_stale_head_times_out`: `prs = [pr(ci=RED), pr(ci=RED)]` (GitHub never reports `NEW_SHA`), `run(timeout=120, poll=60) == 1`; one agent request; the escalation comment contains `"timed out waiting for GitHub to report abc1234"`.
- `test_run_ship_with_summary_uses_the_given_adw_id`: call `ship.run_ship_with_summary(ShipOptions(...), sleep=..., now=..., adw_id="sdlc1234")` → `(0, summary)` with `summary["outcome"] == "handed_over"`, `summary["adw_id"] == "sdlc1234"`, run-log line `adw_id == "sdlc1234"`, and `agents/sdlc1234/ship_summary.json` exists. Add a small `harness.options(...)` helper if useful, keeping `harness.run` as is.
- The existing parametrized `test_protected_paths_escalate` covers the two new protected files automatically.

### 7. `adws/adw_modules/sdlc.py`
- Module docstring: composes the lifecycle and ship; control flow is Python; issue text is untrusted and only owner-authored issues are worked on.
- Imports: `time`, `dataclasses`, typing, rich `Console`/`Panel`/`Rule`, `agent`, `git_ops`, `github`, `from git_ops import GitError`, `from github import GitHubError, Issue`, `from health import run_health_checks`, `from lifecycle import WorkflowError, WorkflowOptions, _write_summary, run_lifecycle`, `from ship import NEEDS_HUMAN_LABEL, ShipOptions, _append_run_log, run_ship_with_summary`, `from models import get_profile`.
- Constants: `ADW_TYPES = ("feature", "chore", "bug")`, `READY_LABEL = "adw-ready"`, `IN_PROGRESS_LABEL = "adw-in-progress"`, `SKIP_LABELS = (NEEDS_HUMAN_LABEL, IN_PROGRESS_LABEL)`, `MAX_COMMENT_DETAIL_CHARS = 1000`.
- `class SdlcRefused(Exception)`: the input isn't something sdlc may work on (non-owner or closed issue).
- `@dataclass(frozen=True) class SdlcOptions`: `prompt: Optional[str]`, `issue: Optional[int]`, `adw_type: Optional[str]`, `plan_profile`, `build_profile`, `ship_profile`, `merge_mode`, `max_rounds: int`, `poll_interval: int`, `timeout: int`, `working_dir: str`.
- Pure helpers:
  - `select_type(explicit: Optional[str], issue: Optional[Issue]) -> str`: `explicit` wins; else for an issue, `"bug"` in labels → `"bug"`, `"chore"` → `"chore"` (bug checked first); else `"feature"`.
  - `is_ready(issue: Issue, owner: str) -> bool`: `issue.state == "OPEN"`, `issue.author == owner`, `READY_LABEL in issue.labels`, and no label in `SKIP_LABELS`.
  - `next_ready_issue(owner, cwd) -> Optional[Issue]`: `github.list_issues([READY_LABEL], cwd=cwd)`, keep `is_ready`, return the one with the lowest `number` (oldest), or `None`.
  - `outcome_comment(outcome, adw_id, pr_url, reason) -> Optional[str]`: text for `handed_over` ("ADW `<id>`: <url> is approved by Claude review and CI is green. It's waiting for a human merge."), `escalated`/`error`/`pr_closed` ("ADW `<id>` stopped and needs a human: <reason>. See <url> (label `needs-human`)."), `build_failed` ("ADW `<id>` couldn't build this issue: <reason>"). Truncate `reason` to `MAX_COMMENT_DETAIL_CHARS`.
- `_best_effort(console, what, fn, *args, **kwargs)`: call, and on `GitHubError` print a yellow warning; return whether it succeeded. Used for every issue label/comment/close.
- `run_sdlc(options, sleep=time.sleep, now=time.monotonic) -> int`:
  1. `adw_id = agent.generate_short_id()`, `start = now()`, `console = Console()`, `summary = {"adw_id": adw_id, "options": asdict(options), "outcome": None, "issue": None, "pr": None, "pr_url": None, "type": None, "lifecycle": None, "ship": None}`. Header panel with the ID, input, profiles (with `get_profile(...).model`), merge mode.
  2. `labelled: Optional[int] = None` (the issue number we added `adw-in-progress` to); `issue = None`; `code = 1`.
  3. `try:`
     - **Preflight:** `if not git_ops.is_clean(cwd)`: raise `WorkflowError("Working tree isn't clean. Commit or stash changes first")`. If `options.prompt and options.issue`: raise `WorkflowError`. If `options.ship_profile` isn't in `{plan_profile, build_profile}`, run `run_health_checks(ship_profile)` and raise `WorkflowError` on failures (the lifecycle checks the other two), so no PR is opened that can't be shipped. `owner = github.repo_owner(cwd=cwd)`.
     - **Resolve input:** `--issue N` → `issue = github.get_issue(N)`; if `issue.author != owner` → raise `SdlcRefused(f"Issue #{N} was opened by {issue.author}, not the repo owner {owner}. Only the owner's issues are worked on.")`; if `issue.state and issue.state != "OPEN"` → `SdlcRefused("Issue #N is closed")`. No prompt and no issue → `issue = next_ready_issue(owner, cwd)`; `None` → print "No issue is ready", `summary["outcome"] = "no_issue"`, `code = 0`, `return code` (the `finally` still runs). Both checks happen before any GitHub write.
     - `adw_type = select_type(options.adw_type, issue)`; record `summary["issue"]`, `summary["type"]`.
     - **Claim:** for an issue, `_best_effort(... github.add_issue_label, issue.number, IN_PROGRESS_LABEL ...)` and set `labelled = issue.number` regardless of success (removal is best effort too).
     - **Build:** `lcode, lsum = run_lifecycle(WorkflowOptions(adw_type=adw_type, prompt=None if issue else options.prompt, issue=issue.number if issue else None, plan_profile=..., build_profile=..., no_pr=False, working_dir=cwd, draft_on_test_failure=False), adw_id=adw_id)`; `summary["lifecycle"] = lsum`. If `lsum.get("error")` or not `lsum.get("pr_url")` → `outcome = "build_failed"`, comment on the issue with `outcome_comment("build_failed", ..., lsum.get("error") or "no PR was opened")`, `return 1`. Failing local tests with a PR opened are **not** a build failure: the PR is ready and ship's FIX_CI round repairs it.
     - **Ship:** `pr_url = lsum["pr_url"]`, `pr = github.pr_number_from_url(pr_url)`; `scode, ssum = run_ship_with_summary(ShipOptions(pr=pr, profile=options.ship_profile, max_rounds=..., merge_mode=..., poll_interval=..., timeout=..., working_dir=cwd), sleep=sleep, now=now, adw_id=adw_id)`; `summary["ship"] = ssum`; `outcome = ssum.get("outcome", "error")`.
     - **already_closed:** if ship says `already_closed`, re-read `github.get_pr(pr)`; `MERGED` → treat as `merged`, otherwise `outcome = "pr_closed"`.
     - **Act on the outcome** (issue only):
       - `merged`: `fresh = github.get_issue(issue.number)`; if `fresh.state == "OPEN"` → `_best_effort(github.close_issue, issue.number, f"Closed by ADW {adw_id}: merged in {pr_url}")`. `code = 0`.
       - `handed_over`: comment `outcome_comment("handed_over", ...)`. `code = 0`.
       - anything else (`escalated`, `error`, `pr_closed`): comment with `ssum.get("escalation_reason") or ssum.get("error") or outcome`. `code = 1`.
       - For a prompt, only the exit code applies (0 for merged/handed_over, else 1).
  4. `except SdlcRefused as e`: red panel, `summary["outcome"] = "refused"`, `summary["error"] = str(e)`, `code = 1`. No GitHub writes.
  5. `except (GitError, GitHubError, WorkflowError) as e`: red panel, `outcome = "error"`, `summary["error"]`, and if `labelled` comment on the issue (best effort). `code = 1`.
  6. `finally:`
     - If `labelled`: `_best_effort(github.remove_label, labelled, IN_PROGRESS_LABEL)`.
     - Return to main if clean: `branch = git_ops.current_branch(cwd)`; if `git_ops.is_clean(cwd)` and `branch != MAIN_BRANCH` → `git_ops.return_to_main(cwd)`; else if dirty print where the work was left. Catch `GitError` and warn.
     - `summary.setdefault`/set `outcome` (default `"error"`), `exit_code`, `rounds = (summary["ship"] or {}).get("rounds")` (None if ship never ran), and write `_write_summary(adw_id, summary, "sdlc_summary.json")`.
     - `_append_run_log({"adw_id", "step": "sdlc", "issue", "pr", "type", "plan_profile", "build_profile", "ship_profile", "merge_mode", "rounds", "outcome", "duration_ms": int((now() - start) * 1000)})`.
  7. Return `code`.

### 8. `adws/adw_sdlc.py`
- Same header as `adw_ship.py` (`#!/usr/bin/env -S uv run --script`, `pydantic`, `python-dotenv`, `click`, `rich`), a docstring with Usage and Examples (`"PROMPT"`, `--issue 12`, no argument, `--build-profile local --merge label`).
- `sys.path.insert(0, .../adw_modules)`, then `from models import DEFAULT_PROFILE, PROFILE_NAMES`, `from ship import MERGE_MODES`, `from sdlc import ADW_TYPES, SdlcOptions, run_sdlc`.
- Click: `@click.argument("prompt", required=False)`, `--issue` (`IntRange(min=1)`), `--type` (`Choice(ADW_TYPES)`, dest `adw_type`), `--profile` (envvar `ADW_PROFILE`, default `DEFAULT_PROFILE`), `--plan-profile`, `--build-profile`, `--ship-profile` (each `Choice(PROFILE_NAMES)`, default `--profile`), `--merge` (`Choice(MERGE_MODES)`, default `never`), `--max-rounds` (`IntRange(min=0)`, 3), `--poll-interval` (`IntRange(min=1)`, 60), `--timeout` (`IntRange(min=1)`, 1800), `--working-dir` (as in `adw_ship.py`).
- `if prompt and issue: raise click.UsageError("Give a PROMPT or --issue, not both")`. Then `sys.exit(run_sdlc(SdlcOptions(...)))`.
- `chmod +x adws/adw_sdlc.py` (match the other scripts' mode).

### 9. `adws/tests/test_sdlc.py`
A `SdlcHarness` that fakes everything: `github.repo_owner` (→ `"owner"`), `github.get_issue` (pops from a list of `Issue`s, last one repeats), `github.list_issues`, `github.comment_on_issue`, `github.add_issue_label`, `github.remove_label`, `github.close_issue`, `github.get_pr`, `git_ops.is_clean`, `git_ops.current_branch`, `git_ops.return_to_main`, `sdlc.run_health_checks`, `sdlc.run_lifecycle` (records `(options, adw_id)`, returns a configurable `(code, summary)`, default `(0, {"pr_url": "https://github.com/o/r/pull/9", "tests_passed": True})`), `sdlc.run_ship_with_summary` (records `(options, adw_id)`, returns configurable `(code, summary)`, default `(0, {"outcome": "merged", "rounds": 2})`). Every GitHub write is recorded in `harness.writes`. `harness.run(prompt=None, issue=None, adw_type=None, build_profile="local", merge="auto")` calls `sdlc.run_sdlc` with fake `sleep`/`now`.
Tests:
- `test_select_type`: explicit wins over labels; `bug` label → bug (also with `chore` present); `chore` → chore; no label → feature; prompt (no issue) → feature.
- `test_non_owner_issue_is_refused_before_any_github_write`: issue author `"someone"` → exit 1, `harness.writes == []`, lifecycle and ship not called, run-log `outcome == "refused"`, no `remove_label` call.
- `test_closed_issue_is_refused`.
- `test_next_issue_picks_the_oldest_ready_owner_issue`: list with #5 (owner, ready, needs-human), #3 (someone else, ready), #8 (owner, ready), #6 (owner, ready, adw-in-progress), #4 (owner, ready) → lifecycle runs with `issue == 4`; `list_issues` called with `["adw-ready"]`.
- `test_no_ready_issue_exits_0`: empty list (or only filtered ones) → exit 0, prints "No issue is ready", no lifecycle call, run-log `outcome == "no_issue"`.
- `test_prompt_happy_path_merges`: prompt → exit 0; lifecycle options have `prompt`, `issue is None`, `adw_type == "feature"`, `no_pr is False`, `draft_on_test_failure is False`; lifecycle and ship got the same `adw_id` as the run-log line; ship options `pr == 9`, `profile` = ship profile, `merge_mode == "auto"`; run-log line has `step == "sdlc"`, `build_profile == "local"`, `rounds == 2`, `outcome == "merged"`, and exactly the documented keys; `agents/{adw_id}/sdlc_summary.json` has `lifecycle`, `ship`, `outcome`.
- `test_merged_with_issue_still_open_closes_it`: get_issue returns OPEN twice → `close_issue(7, "Closed by ADW <id>: merged in https://github.com/o/r/pull/9")`; label added then removed.
- `test_merged_with_issue_already_closed_doesnt_close`: second get_issue returns `state="CLOSED"` → no `close_issue`.
- `test_handed_over_comments_and_exits_0`: ship `(0, {"outcome": "handed_over", "rounds": 1})` → one issue comment mentioning a human merge and the PR URL; exit 0.
- `test_escalated_comments_and_exits_1`: ship `(1, {"outcome": "escalated", "escalation_reason": "round limit reached", "rounds": 3})` → comment contains the reason and the PR URL; exit 1; run-log `rounds == 3`.
- `test_lifecycle_failure_skips_ship`: lifecycle `(1, {"error": "Planning failed"})` → ship not called, issue comment contains "Planning failed", outcome `build_failed`, exit 1, `rounds is None`.
- `test_lifecycle_with_failing_tests_still_ships`: lifecycle `(1, {"pr_url": ..., "tests_passed": False})` → ship called.
- `test_in_progress_label_removed_in_every_case`: parametrized over merged / handed_over / escalated / lifecycle failure / `run_lifecycle` raising `GitHubError` → `("remove_label", 7, "adw-in-progress")` in writes, after `("add_issue_label", 7, "adw-in-progress")`.
- `test_label_failures_are_best_effort`: `add_issue_label` and `remove_label` raise `GitHubError` → run still completes with exit 0.
- `test_dirty_tree_stops_before_github`: `is_clean` False → exit 1, `repo_owner` not called, no writes.
- `test_returns_to_main_when_clean`: `current_branch` → `"adw/x"`, clean → `return_to_main` called.
- `test_type_label_reaches_lifecycle`: issue with `bug` label → lifecycle `adw_type == "bug"`, run-log `type == "bug"`.

### 10. Docs
- `app_docs/sdlc.md` (new, short): what `adw_sdlc.py` does (lifecycle then ship, one `adw_id`); usage for the three input modes; the options table; the issue trust rule (owner-authored only, checked before any GitHub write; issue text reaches agents as untrusted input); labels (`adw-ready` = pick me up, `adw-in-progress` = claimed while running and removed afterwards, `needs-human` = skipped by backlog pickup and set by ship on escalation, `auto-merge` = merged under `--merge label`); type selection; the always-ready PR (`draft_on_test_failure=False`) and why; outcomes (`merged`, `handed_over`, `escalated`, `error`, `build_failed`, `pr_closed`, `refused`, `no_issue`) and exit codes (0 for merged, handed_over, no_issue; 1 otherwise); outputs (`agents/{adw_id}/workflow_summary.json`, `ship_summary.json`, `sdlc_summary.json`, the `step: "sdlc"` line); the trust ramp (`never` → `label` → `auto`); the metric with
  `jq -s 'map(select(.step == "sdlc" and .rounds != null)) | group_by(.build_profile) | map({build_profile: .[0].build_profile, runs: length, avg_rounds: (map(.rounds) | add / length)})' agents/runs.jsonl`.
  Note that `adw_sdlc.py` and `adw_modules/sdlc.py` are protected paths.
- `app_docs/ship.md`: add `adws/adw_sdlc.py` and `adws/adw_modules/sdlc.py` to the protected-paths sentence; add a "Stale head" note under Rounds (after a push the script waits until GitHub reports the pushed SHA, within the same `--timeout`, before deciding again); mention `run_ship_with_summary` and the shared `adw_id` in one line; link `sdlc.md`.
- `adws/README.md`: a table row for `adw_sdlc.py ["<prompt>" | --issue N]` and a line that `adw_modules/sdlc.py` composes the lifecycle and ship (see `app_docs/sdlc.md`).
- `CLAUDE.md`: Commands row `| Ship an issue end to end | ./adws/adw_sdlc.py --issue <N> |` after "Ship a PR", and `See app_docs/sdlc.md for adw_sdlc.py, the end-to-end workflow, its issue trust rule, labels and outcomes.` after the ship.md pointer.

### 11. Validate
- Run the validation commands below and fix any failure.

## Testing Strategy
### Unit Tests
- `test_github.py`: argument construction and parsing for `get_issue` (labels/state), `list_issues`, `close_issue`, `add_issue_label`, `remove_label`, `pr_number_from_url`.
- `test_lifecycle.py`: ready PR when tests fail with `draft_on_test_failure=False`; `run_lifecycle` returns the summary and honours `adw_id`; `bug` type uses `/bug` and `fix:`.
- `test_ship.py`: stale head after a fix push, after an update, and timing out; `run_ship_with_summary` with a given `adw_id`; all existing scenarios still pass.
- `test_sdlc.py`: everything in step 9. No real gh, git, agents or sleeping.

### Edge Cases
- Issue from a non-owner, or a closed issue → refused, no GitHub writes, no label to remove.
- Backlog with only non-owner, `needs-human` or `adw-in-progress` issues → "No issue is ready", exit 0.
- Lifecycle exits 1 only because local tests failed, with a PR opened → ship still runs.
- Lifecycle error or no `pr_url` → no ship, `build_failed`.
- PR merged and the `Closes #N` already closed the issue → no `close_issue`.
- Ship returns `already_closed` → re-read the PR; merged counts as `merged`, closed is `pr_closed`.
- Label add/remove/comment/close failing → warning only.
- GitHub keeps reporting the old head → escalate after `--timeout`.
- A merged/closed PR with a stale `expected_head` → no wait; `decide` returns DONE.
- Both `PROMPT` and `--issue` → click usage error.
- `--type` given for an issue with a conflicting label → `--type` wins.

## Acceptance Criteria
- `./adws/adw_sdlc.py --help` lists all options in the prompt.
- `adw_ship.py`, `adw_chore_implement.py` and `adw_feature_implement.py` behave as before; all existing tests pass unchanged (except the `ShipHarness` fakes extended in step 6).
- After a fix or update push, `adw_ship` waits for GitHub to report the pushed SHA instead of failing with "branch moved since the PR was read".
- A non-owner issue is refused before any GitHub write; the next-issue mode picks the oldest ready owner issue or exits 0.
- An sdlc run uses one `adw_id` across lifecycle and ship, opens a ready PR even when local tests fail, writes `agents/{adw_id}/sdlc_summary.json`, and appends a `step: "sdlc"` line with `build_profile` and `rounds`.
- Merged → issue closed if still open; handed over → comment, exit 0; escalated/error → comment, exit 1; `adw-in-progress` is removed in every case where it was added.
- `adws/adw_sdlc.py` and `adws/adw_modules/sdlc.py` are in `PROTECTED_FILES` and in `app_docs/ship.md`.
- `app_docs/sdlc.md` exists; `app_docs/ship.md`, `adws/README.md` and `CLAUDE.md` are updated.
- `.claude/settings.json`, `.github/workflows/`, `.claude/commands/review_pr.md`, `adws/review_verdict.py` and `adws/adw_modules/review.py` are untouched.

## Validation Commands
Execute these commands to validate the feature is complete:

- `uv run --with pytest --with pydantic --with python-dotenv --with click --with rich pytest adws/tests -q` - Run all ADW tests from the repo root (same invocation as `./scripts/test.sh`)
- `./scripts/test.sh` - Run the full test suite (backend, frontend and ADWs)
- `./adws/adw_sdlc.py --help` - The CLI loads and lists every option
- `./adws/adw_ship.py --help` - The ship CLI still loads
- `git diff --stat main -- .claude/settings.json .github adws/review_verdict.py adws/adw_modules/review.py .claude/commands/review_pr.md` - Must print nothing

## Notes
- No new dependencies.
- The lifecycle's exit code is deliberately unchanged when tests fail (1), so existing ADWs stay identical. sdlc decides "build failed" from the summary (`error` or missing `pr_url`), not the exit code.
- `github.add_label` stays PR-only (`gh pr edit`); `add_issue_label` is the issue equivalent, since `gh pr edit` doesn't apply to issues.
- The lifecycle re-fetches the issue itself and posts its own "working on" and "opened PR" comments; sdlc adds the outcome comment.
- PLAN.md lists `--merge auto` as the eventual default; this feature keeps `never` as the default, as asked, and `app_docs/sdlc.md` describes the ramp.
- `lifecycle.py` isn't added to `PROTECTED_FILES` (not asked); consider it in a later chore, since it now feeds the merging workflow.
