# Bug Planning

Create a plan to resolve the bug using the specified markdown `Plan Format`. Research the codebase and create a thorough plan. You are writing the plan, not fixing the bug.

## Variables
adw_id: $1
prompt: $2

## Instructions

- If the adw_id or prompt is not provided, stop and ask the user to provide them.
- Create a plan to resolve the bug described in the `prompt`
- The plan should fix the root cause with the minimal number of changes, and prevent regressions
- Create the plan in the `specs/` directory with filename: `bug-{adw_id}-{descriptive-name}.md`
  - Replace `{descriptive-name}` with a short, descriptive name based on the bug (e.g., "fix-chat-stream", "resolve-timeout")
- Research the codebase starting with `README.md` and `CLAUDE.md`, then reproduce the bug if you can
- Replace every <placeholder> in the `Plan Format` with the requested value

## Codebase Structure

- `README.md` - What ContextKiln is and how the agentic layer works (start here)
- `CLAUDE.md` - Stack, run and test commands, conventions you must follow
- `apps/backend/` - FastAPI + SQLite API, managed with uv
- `apps/frontend/` - Vite + React + TypeScript chat UI
- `scripts/` - `start.sh`, `stop.sh` and `test.sh` for the application layer
- `adws/` - AI Developer Workflow scripts and modules
- `.claude/commands/` - Slash command templates
- `specs/` - Plans written by agents
- `ai_docs/` - Reference notes for agents, including `local_models.md`
- `app_docs/` - Feature documentation, updated after each feature

## Plan Format

```md
# Bug: <bug name>

## Metadata
adw_id: `{adw_id}`
prompt: `{prompt}`

## Bug Description
<describe the symptoms, and the expected and actual behavior>

## Steps to Reproduce
<list the exact steps to reproduce the bug>

## Root Cause Analysis
<explain the root cause of the bug>

## Solution Statement
<describe the fix and why it addresses the root cause>

## Relevant Files
Use these files to fix the bug:

<list files relevant to the bug with bullet points explaining why. Include new files to be created under an h3 'New Files' section if needed>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

<list step by step tasks as h3 headers with bullet points. Include a test that fails before the fix and passes after it. Last step should validate the work>

### 1. <First Task Name>
- <specific action>
- <specific action>

## Validation Commands
Execute these commands to validate the bug is fixed with zero regressions:

<list specific commands to validate the work. Be precise about what to run>
- Example: `cd apps/backend && uv run pytest` - Run the backend tests
- Example: `cd apps/frontend && npm test` - Run the frontend tests

## Notes
<optional additional context or considerations>
```

## Bug
Use the bug description from the `prompt` variable.

## Report

Return the path to the plan file created.
