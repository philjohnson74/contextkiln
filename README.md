# ContextKiln

An AI tech consultancy app, built through agentic developer workflows.

ContextKiln has two layers:

- **Application layer** (`apps/`): an LLM chat for software engineering and infrastructure questions, with a "talk to a human" escalation path. This arrives in Phase 4 of [PLAN.md](PLAN.md).
- **Agentic layer** (`specs/`, `.claude/commands/`, `adws/`): the prompts and workflows that build the application. Each workflow is designed to run on Claude or on a local open model, so the two can be compared on real work.

## How the agentic layer works

1. An **AI Developer Workflow** (ADW) in `adws/` is a Python script that runs Claude Code headlessly.
2. It runs a **planning command** from `.claude/commands/` (`/chore`, `/feature` or `/bug`), which writes a plan to `specs/`.
3. It then runs `/implement` on that plan.
4. Raw output from each run goes to `agents/{adw_id}/`, which is gitignored.

```bash
./adws/adw_chore_implement.py "add a /health endpoint"
```

See [adws/README.md](adws/README.md) for the scripts and [CLAUDE.md](CLAUDE.md) for the conventions agents follow.

## Layout

| Path | Contents |
|---|---|
| `apps/backend/` | FastAPI + SQLite |
| `apps/frontend/` | Vite + React + TypeScript |
| `adws/` | Workflow scripts and their modules |
| `.claude/commands/` | Slash command prompts |
| `specs/` | Plans written by agents |
| `ai_docs/` | Reference notes for agents, including [local model experiments](ai_docs/local_models.md) |
| `app_docs/` | Feature documentation |
| `agents/` | Run output (gitignored) |

## Setup

You need [uv](https://docs.astral.sh/uv/), the [Claude Code CLI](https://code.claude.com/docs) and the [GitHub CLI](https://cli.github.com/). Local model runs also need [Ollama](https://ollama.com/).

```bash
cp .env.sample .env
```

Then add your `ANTHROPIC_API_KEY` to `.env`.

## Status

See [PLAN.md](PLAN.md) for the roadmap. Model profiles and the Git/PR lifecycle come next, in Phase 3.

## Licence

ContextKiln is source-available under the [Functional Source License 1.1, MIT Future License](LICENSE) (FSL-1.1-MIT). Each version becomes available under MIT two years after its release.
