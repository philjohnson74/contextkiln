# Chore: Add a GitHub Actions CI workflow

## Metadata
adw_id: `2df897d2`
prompt: `Add a GitHub Actions CI workflow at .github/workflows/ci.yml. Trigger on pull_request (all branches) and on push to main. One job with id and name 'ci' on ubuntu-latest. Set top-level 'permissions: contents: read' and a concurrency group per ref that cancels in-progress runs. Steps: actions/checkout (pinned major version), astral-sh/setup-uv (pinned major version, with caching keyed on apps/backend/uv.lock), actions/setup-node (pinned major version, Node 22, npm cache keyed on apps/frontend/package-lock.json), set up Python 3.12, then run ./scripts/test.sh. Add a job timeout of 20 minutes. The workflow must not need any secrets: tests fake the LLM provider. Do not use pull_request_target. Also add app_docs/ci.md briefly describing the workflow, what it runs, and how to reproduce it locally with ./scripts/test.sh, and add a one-line pointer to it in CLAUDE.md next to the app-shell.md reference.`

## Chore Description
Add a CI workflow so every PR (and every push to `main`) runs the full test suite via `./scripts/test.sh` (ADW tests, backend pytest, frontend tests). The workflow has a single job `ci` (id and name) on `ubuntu-latest`, a 20-minute timeout, read-only token permissions, and a per-ref concurrency group that cancels in-progress runs. It uses no secrets (tests fake the LLM provider) and must not use `pull_request_target`. Document it in `app_docs/ci.md` and link it from `CLAUDE.md`.

## Relevant Files
Use these files to complete the chore:

- `scripts/test.sh` - The single command CI runs. It runs ADW tests with `uv run --with ...`, backend `uv run pytest`, and `npm ci` (if no `node_modules`) plus `npm test` for the frontend. Needs uv, Python >= 3.12 and Node on the runner. No change needed.
- `apps/backend/uv.lock` - Cache key for the uv cache (`cache-dependency-glob`).
- `apps/backend/pyproject.toml` - Declares `requires-python = ">=3.12"`, matching the Python 3.12 step.
- `apps/frontend/package-lock.json` - Cache key for the npm cache (`cache-dependency-path`).
- `CLAUDE.md` - Add a one-line pointer to `app_docs/ci.md` beside the `app-shell.md` reference (line 11).
- `app_docs/app-shell.md` - Style reference for the new doc (short Markdown).

### New Files
- `.github/workflows/ci.yml` - The CI workflow.
- `app_docs/ci.md` - Short description of the workflow, what it runs, and how to reproduce locally.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Create the workflow
- Create `.github/workflows/ci.yml` with `name: CI`.
- `on:` `pull_request` (no branch filter, so all branches) and `push` with `branches: [main]`. Do not use `pull_request_target`.
- Top-level `permissions: contents: read`.
- Top-level `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`.
- Single job under `jobs:` with id `ci`, `name: ci`, `runs-on: ubuntu-latest`, `timeout-minutes: 20`.
- Steps, in order:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v6` with `enable-cache: true` and `cache-dependency-glob: apps/backend/uv.lock`
  3. `uv python install 3.12` (set up Python 3.12 via uv, which `scripts/test.sh` uses)
  4. `actions/setup-node@v4` with `node-version: 22`, `cache: npm`, `cache-dependency-path: apps/frontend/package-lock.json`
  5. `run: ./scripts/test.sh`
- No `env:` secrets, no `secrets.*` references anywhere.
- Confirm `scripts/test.sh` is executable (`ls -l`); if not, note it and run it via `bash ./scripts/test.sh` rather than changing file modes outside the plan.

### 2. Document the workflow
- Create `app_docs/ci.md` (short): triggers, the `ci` job and its settings (permissions, concurrency, 20-minute timeout, no secrets), what it runs (`./scripts/test.sh`: ADW tests, backend pytest, frontend tests), and how to reproduce locally with `./scripts/test.sh`.

### 3. Link from CLAUDE.md
- Under the existing line `See \`app_docs/app-shell.md\` ...` in `CLAUDE.md`, add one line: ``See `app_docs/ci.md` for the CI workflow and how to reproduce it locally.``

### 4. Validate
- Run the validation commands below.

## Validation Commands
Execute these commands to validate the chore is complete:

- `python3 -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(list(d['jobs']))"` - Workflow parses as YAML and has job `ci` (if PyYAML is missing, use `uv run --with pyyaml python -c ...`)
- `grep -nE "pull_request_target|secrets\." .github/workflows/ci.yml` - Must print nothing
- `./scripts/test.sh` - Full test suite passes locally, same as CI
- `grep -n "ci.md" CLAUDE.md` - Pointer present next to the app-shell reference
- `git status --short` - Only `.github/workflows/ci.yml`, `app_docs/ci.md`, `CLAUDE.md` and this spec changed

## Notes
- The command arguments were mis-parsed into the template variables (`adw_id: Add`, `prompt: a`). The ADW ID `2df897d2` comes from the start of the arguments and matches the current branch name.
- Action versions are pinned to a major tag as requested. Pinning to a commit SHA would be stricter, and is worth considering before the repo goes public.
- `cancel-in-progress` applies per ref, so a newer push to `main` cancels an in-progress `main` run. This is as requested.
- Branch protection is not available (see project memory), so the `ci` check is informational until required checks can be enabled.
