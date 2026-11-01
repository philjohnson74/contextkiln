# Pull Request Text

Write the title and summary for a pull request from the current branch into `main`. You only write the text. The ADW's Python code opens the PR, and adds the spec link, test result and run details to the body.

## Variables
spec_path: $1
prompt: $2

## Instructions

- Read the plan at `spec_path`, then read the changes with `git log main..HEAD` and `git diff main...HEAD`.
- Don't run `git push`, `gh` or any other command that changes the repo or GitHub.
- Write the title as `<type>: <description>`, under 72 characters.
- Write the summary as a short Markdown bullet list of what changed and why.
- Describe what actually changed in the diff. If something the plan asked for is missing, say so.
- Never include secrets or the contents of `.env`.

## Report

Return only this JSON, with no code fences or commentary:

{"title": "<title>", "summary": "<summary>"}
