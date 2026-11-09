# adw_sdlc: plan → build → test → PR → ship

`./adws/adw_sdlc.py` takes one piece of work from a prompt or a GitHub issue all the way to `main`:

1. **Lifecycle** (`adws/adw_modules/lifecycle.py`): plan, build, run `scripts/test.sh`, commit and open a PR.
2. **Ship** (`adws/adw_modules/ship.py`, see [ship.md](ship.md)): wait for `ci` and `claude-review`, fix failures and review comments, keep the branch up to date, then merge or hand over.
3. **Close the loop:** close the issue once the PR is merged, or comment on it.

Both steps share one `adw_id`, so everything a run produces lands in `agents/{adw_id}/`. The control flow is Python in `adws/adw_modules/sdlc.py`. Agents only edit code and write text.

## Usage

```bash
./adws/adw_sdlc.py "Add a health endpoint"           # from a prompt
./adws/adw_sdlc.py --issue 12                        # from an issue
./adws/adw_sdlc.py                                   # the oldest ready backlog issue
./adws/adw_sdlc.py --issue 12 --build-profile local --merge label
```

Start it from a clean checkout. Give a prompt or `--issue`, not both.

| Option | Default | What it does |
|---|---|---|
| `PROMPT` | | Free-text description of the work |
| `--issue` | | Work on this issue |
| `--type` | from labels | `feature`, `chore` or `bug` |
| `--profile` | `ADW_PROFILE`, then `claude` | Default for the three profiles below |
| `--plan-profile` | `--profile` | Model profile for planning |
| `--build-profile` | `--profile` | Model profile for building, committing and PR text |
| `--ship-profile` | `--profile` | Model profile for ship's fix agents |
| `--merge` | `never` | `never`, `label` or `auto`, as in ship |
| `--max-rounds` | `3` | Ship fix rounds before escalating |
| `--poll-interval` | `60` | Seconds between check polls |
| `--timeout` | `1800` | Seconds to wait for checks on each head |
| `--working-dir` | current directory | Repo checkout to work in |

**Type selection:** `--type` wins. Otherwise an issue labelled `bug` is a bug (checked first), one labelled `chore` is a chore, and anything else, including a prompt, is a feature.

## Issue trust rule

The repo may go public, so only issues **opened by the repo owner** are worked on. For `--issue N` the author and state are checked before any GitHub write: a non-owner or closed issue is refused (`refused`, exit 1) with nothing labelled or commented. Backlog pickup filters the same way. The issue text still reaches agents marked as untrusted input.

## Labels

| Label | Meaning |
|---|---|
| `adw-ready` | Pick me up. Backlog mode takes the lowest-numbered open owner issue with it |
| `adw-in-progress` | Added while a run works on the issue and removed afterwards in every case. Backlog mode skips it |
| `needs-human` | Set by ship on escalation. Backlog mode skips it |
| `auto-merge` | On the PR: merged under `--merge label` |

Label, comment and close calls are best effort: a failure prints a warning and the run goes on.

## Always a ready PR

sdlc runs the lifecycle with `draft_on_test_failure=False`, so the PR opens ready for review even when local tests fail. Ship escalates draft PRs, but on a ready one its FIX_CI round repairs the failure. Only a lifecycle error, or no PR at all, counts as `build_failed`.

## Outcomes

| Outcome | What happened | Issue | Exit |
|---|---|---|---|
| `merged` | Ship merged the PR (or it was already merged) | Closed, if `Closes #N` hasn't already | 0 |
| `handed_over` | Approved and green, waiting for a human merge | Comment | 0 |
| `no_issue` | Backlog mode found nothing ready | | 0 |
| `escalated` | Ship needs a human (see its `needs-human` comment) | Comment with the reason | 1 |
| `pr_closed` | The PR was closed without merging | Comment | 1 |
| `error` | A git, gh or workflow error | Comment | 1 |
| `build_failed` | Planning or building failed, or no PR was opened. Ship doesn't run | Comment | 1 |
| `refused` | Non-owner or closed issue | Nothing | 1 |

## Outputs

- `agents/{adw_id}/workflow_summary.json`: the lifecycle's summary.
- `agents/{adw_id}/ship_summary.json`: ship's summary, decisions and rounds.
- `agents/{adw_id}/sdlc_summary.json`: options, both summaries, the outcome, rounds and exit code.
- `agents/runs.jsonl`: one `step: "sdlc"` line with `adw_id`, `issue`, `pr`, `type`, `plan_profile`, `build_profile`, `ship_profile`, `merge_mode`, `rounds` (`null` if ship never ran), `outcome` and `duration_ms`, as well as the usual `step: "ship"` line and agent lines.

## Rounds to approval per build profile

PLAN.md's key metric:

```bash
jq -s 'map(select(.step == "sdlc" and .rounds != null)) | group_by(.build_profile) | map({build_profile: .[0].build_profile, runs: length, avg_rounds: (map(.rounds) | add / length)})' agents/runs.jsonl
```

## Trust ramp

Start with `--merge never` (the default: you merge), move to `--merge label` (you opt PRs in with `auto-merge`), then `--merge auto` once the rounds-to-approval numbers justify it.

## Safety

`adws/adw_sdlc.py` and `adws/adw_modules/sdlc.py` are protected paths in ship, so a PR that changes them is never merged automatically.
