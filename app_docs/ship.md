# adw_ship: the PR babysitter

`./adws/adw_ship.py <PR>` drives an open PR to "approved and green":

1. It waits for the head commit's `ci` and `claude-review` checks.
2. It fixes what's wrong: CI failures, requested changes, or a branch that's behind `main`.
3. It pushes the fix and waits again.
4. Once both checks pass, it merges or hands the PR to you.

Every decision is made by deterministic Python (`decide()` in `adws/adw_modules/ship.py`). Agents only edit files and write text. Python runs all git and gh commands. See [claude-review.md](claude-review.md) for the review pipeline it reacts to.

`adw_sdlc.py` reuses it through `run_ship_with_summary`, passing its own `adw_id` so all of a run's artefacts share one folder. See [sdlc.md](sdlc.md).

## Usage

```bash
./adws/adw_ship.py 12                                  # fix, then hand over
./adws/adw_ship.py 12 --merge auto                     # fix, then merge
./adws/adw_ship.py 12 --merge label --max-rounds 2     # merge only with the auto-merge label
```

Start it from a clean checkout. It switches to the PR branch for each fix and returns to `main` afterwards.

| Option | Default | What it does |
|---|---|---|
| `PR` | | The PR number |
| `--profile` | `ADW_PROFILE`, then `claude` | Model profile for the fix agents |
| `--max-rounds` | `3` | Fix rounds allowed before escalating |
| `--merge` | `never` | `never`, `label` or `auto` (see below) |
| `--poll-interval` | `60` | Seconds between polls |
| `--timeout` | `1800` | Seconds to wait for the checks on each head |
| `--working-dir` | current directory | Repo checkout to work in |

## Decision table

`decide` applies these rules in order. The first one that matches wins.

| # | Condition | Action |
|---|---|---|
| 1 | PR merged or closed | DONE (exit 0) |
| 1 | PR is a draft | ESCALATE |
| 2 | Either check is missing or not completed | WAIT |
| 3 | Either check concluded something other than SUCCESS or FAILURE (SKIPPED, CANCELLED, TIMED_OUT and so on) | ESCALATE |
| 4 | Review failed because the reviewer produced no valid verdict | ESCALATE (no round spent) |
| 5 | CI or review failed, and the round limit is reached | ESCALATE |
| 5 | CI failed (even if the review failed too) | FIX_CI (`/fix_ci`) |
| 5 | Review failed | ADDRESS_REVIEW (`/address_review`) |
| 6 | Both green, but the head doesn't contain `origin/main` | UPDATE_BRANCH (merge `origin/main`) |
| 7 | Both green and up to date, but the PR touches a protected path | ESCALATE |
| 7 | `--merge never` | HAND_OVER |
| 7 | `--merge label` | MERGE with the `auto-merge` label, otherwise HAND_OVER |
| 7 | `--merge auto` | MERGE |

The script escalates rather than spending a fix round on an infrastructure failure. The `claude-review` summary comment then contains "The reviewer produced no valid verdict".

## Trust rules

- Only `github-actions[bot]` and the repo owner are trusted. Comments from anyone else are ignored.
- Only top-level inline comments on the current head (`original_commit_id`) count. Replies, including the script's own, don't.
- The summary is the latest trusted comment carrying a review marker.
- Only PRs opened by the repo owner are shipped. Others escalate, and no agent runs on their branch.
- Review text and CI logs reach agents as files under `agents/`, marked as untrusted data. The agent's replies block is parsed strictly. Unknown comment ids, bad actions and malformed JSON are dropped, and notes are cut to 1000 characters.

## Protected paths

A PR that changes the reviewer or the shipper would be judged by its own new code. So any PR that touches `.github/`, `.claude/`, `adws/review_verdict.py`, `adws/adw_modules/review.py`, `adws/adw_modules/ship.py`, `adws/adw_ship.py`, `adws/adw_sdlc.py` or `adws/adw_modules/sdlc.py` is never merged by the script. Once it's approved and green, it gets `needs-human`.

## Rounds

- Only fix pushes (FIX_CI, ADDRESS_REVIEW) count as rounds. Infrastructure failures and branch updates don't.
- Rounds are counted per run. Running the script again on the same PR starts again at 0.
- `--timeout` bounds each wait for checks. It restarts after every push.
- **Stale head:** right after a push, GitHub can still report the old head and its checks for a few seconds. So after each push the script waits, within the same `--timeout`, until GitHub reports the pushed SHA before deciding again. If it never does, the PR escalates with "timed out waiting for GitHub to report <sha>".

## Merge modes and the trust ramp

Follow PLAN.md 5c: start with `never` (you merge), move to `label` (you opt PRs in with `auto-merge`), then `auto` once the rounds-to-approval numbers justify it.

## Pre-merge guard

There's no branch protection on `main`, so this guard is the only protection. Before merging, the script:

1. Re-fetches the PR.
2. Checks that the head SHA is unchanged and the PR is still open.
3. Checks that `ci` and `claude-review` are both COMPLETED/SUCCESS on that head, and that no protected path is touched.
4. Checks that `git merge-base --is-ancestor origin/main <head>` passes.
5. Runs `gh pr merge --squash --delete-branch --match-head-commit <head>`.

If any check fails, it doesn't merge and goes back to polling.

## Escalation

The script adds the `needs-human` label, then posts a comment with the reason, the rounds used, the unresolved blocking count and the last review summary (quoted, with markers neutralised). It sends a macOS notification and exits 1.

## Outputs

- `agents/{adw_id}/ship/round_N/ci_context.md` or `review_context.md`: what the agent was given.
- `agents/{adw_id}/{ci_fixer|review_fixer}/`: the agent's raw output.
- `agents/{adw_id}/ship_summary.json`: options, every decision, round details and the outcome.
- `agents/runs.jsonl`: one `step: "ship"` line with `adw_id`, `pr`, `rounds`, `profile`, `outcome` (`merged`, `handed_over`, `escalated`, `already_closed` or `error`) and `duration_ms`.

## Limits

- Draft PRs aren't supported yet.
- Merge conflicts with `main` escalate rather than being resolved automatically, for now.
- Local test results are recorded, but a fix is pushed even if they fail. CI and the review judge it.
