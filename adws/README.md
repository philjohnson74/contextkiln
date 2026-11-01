# AI Developer Workflows

Executable scripts that combine deterministic Python with Claude Code agents. Each is a single-file [uv script](https://docs.astral.sh/uv/guides/scripts/), so it installs its own dependencies. Run them from the repo root.

| Script | What it does |
|---|---|
| `adw_prompt.py "<prompt>"` | Runs an ad hoc prompt |
| `adw_slash_command.py /<command> [args]` | Runs one command from `.claude/commands/` |
| `adw_chore_implement.py "<prompt>"` | Runs `/chore`, then `/implement` on the resulting plan |
| `adw_feature_implement.py "<prompt>"` | Runs `/feature`, then `/implement` on the resulting plan |

`adw_modules/agent.py` builds the `claude` subprocess call, filters its environment, handles retries and parses the stream-json output.

## Output

Each run writes to `agents/{adw_id}/{agent_name}/` (gitignored):

| File | Contents |
|---|---|
| `cc_raw_output.jsonl` | Raw stream from Claude Code |
| `cc_raw_output.json` | All messages as a JSON array |
| `cc_final_object.json` | The final result message |
| `custom_summary_output.json` | Summary of the run |

Claude Code's `success` result only means the session ended normally, not that the work got done. Check the outcome separately, for example by running the tests.

## Models

Every script takes `--profile`, which picks the model and the environment that routes Claude Code to it. Without the option, scripts use `ADW_PROFILE` from the environment or `.env`, then `claude`. Profiles are defined in `adw_modules/models.py`.

| Profile | Model | Runs on |
|---|---|---|
| `claude` | `sonnet` | Anthropic |
| `claude-opus` | `opus` | Anthropic |
| `local` | `LOCAL_MODEL`, default `qwen3-coder:30b` | Ollama at `LOCAL_BASE_URL`, default `http://localhost:11434` |

`LOCAL_CONTEXT_LENGTH` (default `65536`) must match `OLLAMA_CONTEXT_LENGTH` on the server. See [local_models.md](../ai_docs/local_models.md) for why.

`ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` set in your shell are ignored, so only the profile decides where a run goes.

## Tests

```bash
uv run --with pytest --with pydantic --with python-dotenv pytest adws/tests
```

Phase 3 of `PLAN.md` still has to add `git_ops.py` and `github.py`.
