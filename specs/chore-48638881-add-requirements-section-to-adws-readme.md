# Chore: Add a Requirements section to adws/README.md

## Metadata
adw_id: `48638881`
prompt: `Add a Requirements section to adws/README.md saying the local profile needs Ollama running.`

## Chore Description
Add a short `## Requirements` section to `adws/README.md` stating that the `local` profile needs Ollama running. It should say the server must be reachable at `LOCAL_BASE_URL` (default `http://localhost:11434`) and point to `ai_docs/local_models.md` for how to start it. Keep it brief, with no other content changes.

Note: the command's variable block was parsed incorrectly (`adw_id: Add`, `prompt: a`). The command arguments and the branch name `adw/chore-48638881-...` show the intended `adw_id` is `48638881`.

## Relevant Files
Use these files to complete the chore:

- `adws/README.md` - the file to edit. The new section goes after the intro and script table, before `## Lifecycle`.
- `ai_docs/local_models.md` - already documents starting Ollama (`ollama serve`) and its settings. The new section links to it. Do not edit it.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add the Requirements section
- In `adws/README.md`, insert a `## Requirements` heading between the paragraph ending `...properly configured.` (line 13) and the `adw_modules/agent.py` paragraph (line 15), or, if that reads awkwardly, directly before `## Lifecycle`. Prefer directly before `## Lifecycle`, so the module paragraphs stay under the intro.
- Content: "The `local` profile needs Ollama running at `LOCAL_BASE_URL` (default `http://localhost:11434`), with the model pulled. See [local_models.md](../ai_docs/local_models.md) for how to start it. The `claude` and `claude-opus` profiles don't need it."
- Do not change any other text.

### 2. Validate
- Run the validation commands below.

## Validation Commands
- `grep -n "## Requirements" adws/README.md` - the heading exists exactly once
- `git diff --stat` - only `adws/README.md` changed (the spec file is new and untracked)
- `./scripts/test.sh` - the ADW tests still pass

## Notes
- `CLAUDE.md` asks for `app_docs/` updates after a feature. This is a docs-only chore, so no `app_docs/` change is needed.
