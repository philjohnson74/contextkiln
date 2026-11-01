# Commit Message

Write a conventional commit message for the current uncommitted changes. You only write the message. The ADW's Python code stages and commits.

## Variables
adw_type: $1
prompt: $2

## Instructions

- Read the changes with `git status` and `git diff`. New files only appear in `git status`, so read them too.
- Don't run `git add`, `git commit` or any other command that changes the repo.
- Use the format `<type>: <description>`
  - Use `feat` for a feature, `fix` for a bug and `chore` for a chore, based on `adw_type`
  - Use `docs` or `test` instead if the changes only touch documentation or tests
- Keep the first line under 72 characters, in the imperative mood, with no full stop.
- Add a short body after a blank line only if the first line can't explain the change.
- Describe what actually changed in the diff, not only what the `prompt` asked for.
- Don't add trailers. The ADW adds them.

## Report

Return only the commit message, with no code fences or commentary.
