# AI Developer Workflows

Executable scripts that combine deterministic Python with Claude Code agents. Each is a single-file [uv script](https://docs.astral.sh/uv/guides/scripts/), so it installs its own dependencies. Run them from the repo root.

| Script | What it does |
|---|---|
| `adw_health_check.py` | Checks the tools and, for `--profile local`, the Ollama server, model, tool calling and context length. Exits 1 if anything fails |
| `adw_prompt.py "<prompt>"` | Runs an ad hoc prompt |
| `adw_slash_command.py /<command> [args]` | Runs one command from `.claude/commands/` |
| `adw_chore_implement.py "<prompt>"` | Plans and builds a chore with `/chore` and `/implement`, then opens a PR |
| `adw_feature_implement.py "<prompt>"` | Plans and builds a feature with `/feature` and `/implement`, then opens a PR |
| `review_verdict.py post ...` | Used by the Claude review workflow. Posts the review summary with its verdict marker, exits 0 on APPROVE and 1 otherwise |

Before starting any workflow, run `adw_health_check.py` to ensure all tools and dependencies are properly configured.

`adw_modules/agent.py` builds the `claude` subprocess call, filters its environment, handles retries and parses the stream-json output.

`adw_modules/git_ops.py` and `adw_modules/github.py` run git and `gh` from Python, so agents don't have to. `git_ops.py` refuses to commit or push on `main`, and checks before each one that an agent hasn't switched branches. `.claude/commands/commit.md` and `pull_request.md` only write the text.

`adw_modules/review.py` parses the reviewer's verdict file and builds and reads the `<!-- claude-review verdict: ... round: N -->` marker. See [claude-review.md](../app_docs/claude-review.md).

## Requirements

The `local` profile needs Ollama running at `LOCAL_BASE_URL` (default `http://localhost:11434`), with the model pulled. See [local_models.md](../ai_docs/local_models.md) for how to start it. The `claude` and `claude-opus` profiles don't need it.

## Lifecycle

The chore and feature ADWs share `adw_modules/lifecycle.py`, which runs these steps in Python:

1. **Health check** for each profile in use.
2. **Sync:** abort if the working tree isn't clean, then fast-forward `main`.
3. **Branch:** create `adw/{type}-{adw_id}-{slug}`.
4. **Plan and build:** run the agents. It fails if the spec file is missing or the build changed nothing, whatever the agent reports.
5. **Verify:** run `scripts/test.sh`.
6. **Commit:** only the subject line of the agent's message is used, and only if it's in conventional format. Otherwise Python writes one.
7. **Push and open a PR:** a failing test run opens a draft, with the output in the body, and the script exits 1.
8. **Return to `main`.**

If a step fails, the checkout stays on the work branch so you can inspect it. Commit, stash or discard that work before the next run. You still review and merge every PR.

| Option | What it does |
|---|---|
| `--issue N` | Uses the issue as the prompt, in place of `<prompt>`. The issue text is passed to agents as untrusted input. The ADW comments on the issue, and the PR closes it |
| `--no-pr` | Commits to a local branch, with no push, PR or issue comments. It still fetches `main` |

## Output

Each run writes to `agents/{adw_id}/{agent_name}/` (gitignored):

| File | Contents |
|---|---|
| `cc_raw_output.jsonl` | Raw stream from Claude Code |
| `cc_raw_output.json` | All messages as a JSON array |
| `cc_final_object.json` | The final result message |
| `custom_summary_output.json` | Summary of the run |

Claude Code's `success` result only means the session ended normally, not that the work got done. Check the outcome separately, for example by running the tests.

Every agent attempt also appends a line to `agents/runs.jsonl`, with `adw_id`, `step`, `profile`, `model`, `duration_ms`, `num_turns` and `success`. Retries get their own lines. `num_turns` is `null` if Claude Code never finished.

An agent is stopped after `ADW_AGENT_TIMEOUT_SECONDS` (default `1800`). Timeouts aren't retried.

## Models

Every script takes `--profile`, which picks the model and the environment that routes Claude Code to it. Without the option, scripts use `ADW_PROFILE` from the environment or `.env`, then `claude`. Profiles are defined in `adw_modules/models.py`.

| Profile | Model | Runs on |
|---|---|---|
| `claude` | `sonnet` | Anthropic |
| `claude-opus` | `opus` | Anthropic |
| `local` | `LOCAL_MODEL`, default `qwen3-coder:30b` | Ollama at `LOCAL_BASE_URL`, default `http://localhost:11434` |

`adw_chore_implement.py` and `adw_feature_implement.py` can use a different profile for each step, for example `--plan-profile claude --build-profile local`. A step without its own option uses `--profile`.

`LOCAL_CONTEXT_LENGTH` (default `65536`) must match `OLLAMA_CONTEXT_LENGTH` on the server. See [local_models.md](../ai_docs/local_models.md) for why.

`ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` set in your shell are ignored, so only the profile decides where a run goes.

## Tests

```bash
./scripts/test.sh
```
