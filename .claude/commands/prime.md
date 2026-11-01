# Prime
Execute the `Run`, `Read` and `Report` sections to understand the codebase then summarize your understanding.

## Run
git ls-files

## Read
README.md
CLAUDE.md
adws/README.md

## Codebase Structure

- `apps/backend/` - FastAPI + SQLite API, managed with uv
- `apps/frontend/` - Vite + React + TypeScript chat UI
- `scripts/` - `start.sh`, `stop.sh` and `test.sh` for the application layer
- `adws/` - AI Developer Workflow scripts and modules
- `.claude/commands/` - Slash command templates
- `specs/` - Plans written by agents
- `ai_docs/` - Reference notes for agents, including `local_models.md`
- `app_docs/` - Feature documentation, updated after each feature

## Report
Summarize your understanding of the codebase.
