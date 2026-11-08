# Claude PR review

A GitHub Actions workflow in `.github/workflows/claude-review.yml` has Claude review each PR against `CLAUDE.md`, the PR's spec and the diff. Its job result is the `claude-review` status check.

## Triggers

- `pull_request` events: `opened`, `synchronize`, `reopened`, `ready_for_review`.
- Skipped for drafts, PRs from forks and PRs not opened by the repo owner.
- It never uses `pull_request_target`.
- Concurrency is per PR. A newer push cancels a review still in progress.

## The `claude-review` check

- **Green:** the verdict is APPROVE.
- **Red:** the verdict is REQUEST_CHANGES, the reviewer produced no valid verdict, or the summary comment couldn't be posted.
- **Skipped:** draft, fork or other-author PRs. A skipped check is neither passed nor failed.

## How it works

1. **Prepare review context:** writes `.review/pr.json` (from `gh pr view`), `.review/diff.patch`, `.review/files.txt` and `.review/comments.json` (the PR's existing comments). `.review/` is gitignored.
2. **Load review prompt:** reads `.claude/commands/review_pr.md`.
3. **Run Claude review:** `anthropics/claude-code-action@v1` with tools `Read`, `Glob`, `Grep`, `Write` and `mcp__github_inline_comment__create_inline_comment`. Claude posts inline comments tagged `[blocking]` or `[nit]` (as `claude[bot]`) and writes `.review/review.md`. The step has `continue-on-error: true`, so a crash or timeout still reaches the next step.
4. **Post verdict:** `adws/review_verdict.py post` parses the verdict, posts the summary comment (as `github-actions[bot]`) and exits 0 on APPROVE, 1 otherwise.

## Verdict file and marker

The first non-empty line of `.review/review.md` must be exactly `VERDICT: APPROVE` or `VERDICT: REQUEST_CHANGES`. Anything else counts as no valid verdict. A Markdown summary follows.

The summary comment's last line is a marker:

```
<!-- claude-review verdict: APPROVE|REQUEST_CHANGES round: N -->
```

- Round = 1 + the number of earlier `github-actions[bot]` comments that contain a marker. Markers in other users' comments don't count.
- Marker-like text in the reviewer's summary is neutralised, so each comment has exactly one marker.
- To read the latest verdict, take the last marker in the PR's `github-actions[bot]` comments.

The parsing and marker logic live in `adws/adw_modules/review.py`.

## Why the reviewer doesn't use gh

The action runs Claude Code inside this repo, so `.claude/settings.json` applies, and it denies `Bash(gh:*)` and git writes. The workflow prepares the context instead, and deterministic Python posts the verdict.

## Setup

- Add the repo secret `CLAUDE_CODE_OAUTH_TOKEN`. Create it with `claude setup-token`, or with `/install-github-app` in an interactive Claude Code session.
- Install the Claude GitHub App on the repo. The action's OIDC token exchange uses the job's `id-token: write` permission.

## Cost

Sonnet, `--max-turns 30`, a 20-minute timeout, drafts skipped, and a newer push cancels the older run. Each push to a ready PR is one paid review.

## Changing the reviewer

Edit `.claude/commands/review_pr.md`, and `adws/adw_modules/review.py` for the format, through a PR. That PR is reviewed by its own new prompt, because the workflow checks out the PR head.

## Run the verdict step locally

```bash
uv run adws/review_verdict.py post --help
./scripts/test.sh   # includes adws/tests/test_review.py
```
