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

Scripts currently accept `--model sonnet|opus`. Phase 3 of `PLAN.md` adds `--profile claude|claude-opus|local`, along with `models.py`, `git_ops.py` and `github.py`.
