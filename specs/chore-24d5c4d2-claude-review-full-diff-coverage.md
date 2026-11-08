# Chore: Make the Claude PR reviewer read the whole diff, and enforce it in the verdict step

## Metadata
adw_id: `24d5c4d2`
prompt:

````text
Make the Claude PR reviewer read the whole diff, and make the verdict step enforce it.

Problem: on PR #10 the reviewer approved after reading only the first 883 lines of `.review/diff.patch` (the Read tool returns large files in parts and it didn't continue). A reviewer must never approve code it hasn't read.

Change exactly these things:

1. `.github/workflows/claude-review.yml`, "Prepare review context" step:
   - Write the diff WITHOUT the specs directory: `git diff "$BASE_SHA...$HEAD_SHA" -- . ':(exclude)specs/' > .review/diff.patch`. The reviewer reads the spec file itself, in full, from the workspace.
   - Keep `.review/files.txt` listing ALL changed files (including specs).
   - Write the diff's line count to `.review/diff_lines.txt` (just the integer, e.g. `wc -l < .review/diff.patch | tr -d ' '`).
   - In the "Post verdict" step, pass `--diff-lines "$(cat .review/diff_lines.txt 2>/dev/null || echo 0)"` to `review_verdict.py post`.
   - Raise `--max-turns` from 30 to 40 (chunked reading needs more turns).

2. `.claude/commands/review_pr.md`:
   - Step 2: read `.review/diff_lines.txt` first to learn the total line count M, then read `.review/diff.patch` IN FULL using the Read tool's `offset` and `limit` in chunks of at most 400 lines, continuing until you have read line M. Do not judge the PR before you have read every chunk.
   - Note that `specs/` is excluded from the diff; read the spec file itself in full.
   - Output section: the summary must contain a line exactly of the form `Diff read: N of M lines` (N = last diff line you actually read). If you could not read the whole diff (turn limit, errors), say so, and the verdict must be `REQUEST_CHANGES` with a blocking issue "incomplete review". Update the example to include the `Diff read:` line.

3. `adws/adw_modules/review.py`:
   - Add `parse_diff_coverage(summary: str) -> Optional[tuple[int, int]]` that returns (N, M) from the last `Diff read: N of M lines` line, or None.
   - Add `enforce_coverage(verdict: str, summary: str, diff_lines: int) -> tuple[str, str]`: if `diff_lines` is 0, return unchanged (nothing to read). Otherwise if the verdict is APPROVE and the coverage line is missing, or N < diff_lines, or M != diff_lines, downgrade to REQUEST_CHANGES and append a short note to the summary explaining why (e.g. "Downgraded: the reviewer reported reading 883 of 1043 diff lines."). REQUEST_CHANGES stays REQUEST_CHANGES (still append the note if coverage is short, so it's visible).

4. `adws/review_verdict.py post`: add a required `--diff-lines` int option (min 0) and apply `enforce_coverage` to a valid verdict before building the comment. The exit code follows the final verdict.

5. Tests in `adws/tests/test_review.py`: parse_diff_coverage (present, absent, last one wins); enforce_coverage for full coverage approve (unchanged), short coverage approve (downgraded), missing line approve (downgraded), M mismatch (downgraded), diff_lines 0 (unchanged), request-changes stays; CLI: approve with full coverage exits 0, approve with short coverage exits 1 and the posted body says downgraded. Update existing CLI tests for the new required option.

6. Docs: update `app_docs/claude-review.md` (full diff reading, specs excluded from the diff, the `Diff read:` line and the downgrade rule, max-turns 40) and the matching parts of the PR #10 spec are NOT to be edited; write a new spec for this chore as usual.

Do not change anything else (no round-counting changes, no adw_ship.py, no `.claude/settings.json`).
````

## Chore Description
On PR #10 the automated reviewer approved after reading only the first 883 lines of `.review/diff.patch`: the `Read` tool returns large files in parts and the reviewer never asked for the rest. A reviewer must never approve code it hasn't read.

This chore fixes that on two layers:

1. **Make the diff smaller and the reading explicit.** The workflow drops `specs/` from `.review/diff.patch` (the reviewer reads the spec itself from the workspace), records the diff's line count in `.review/diff_lines.txt`, and gives the reviewer 40 turns instead of 30. The prompt tells the reviewer to read the diff in chunks of at most 400 lines with `offset`/`limit` until the last line, and to report `Diff read: N of M lines` in its summary.
2. **Enforce it deterministically.** `adws/review_verdict.py post` takes a required `--diff-lines` count and runs a new `review.enforce_coverage`. An APPROVE whose summary lacks a correct, complete `Diff read:` line is downgraded to REQUEST_CHANGES, with a note appended to the summary. The exit code (and so the `claude-review` check) follows the final verdict.

Nothing else changes: round counting, marker format, `adws/adw_ship.py` and `.claude/settings.json` stay as they are, and the PR #10 spec (`specs/feature-f42d8282-claude-pr-review.md`) is not edited.

## Relevant Files
Use these files to complete the chore:

- `.github/workflows/claude-review.yml` - "Prepare review context" step writes `.review/diff.patch` and `.review/files.txt` (lines 47-48); "Run Claude review" has `--max-turns 30` (line 83); "Post verdict" runs `review_verdict.py post` (line 93). All three change.
- `.claude/commands/review_pr.md` - The reviewer prompt. Instruction step 2 (reads the diff), step 3 (finds the spec, currently "or a spec added in the diff"), the `Output` section and its example change.
- `adws/adw_modules/review.py` - Stdlib-only verdict/marker module. Add `parse_diff_coverage` and `enforce_coverage`.
- `adws/review_verdict.py` - The `post` CLI command. Add the required `--diff-lines` option and call `enforce_coverage` on a valid verdict.
- `adws/tests/test_review.py` - Existing tests for the module and CLI (gh faked via `monkeypatch` of `post_comment`). Add new tests; update `run_post` to pass `--diff-lines`.
- `app_docs/claude-review.md` - Feature doc. Update "How it works", add the coverage rule, update "Cost" (max-turns 40) and the `.review/` file list.
- `specs/feature-f42d8282-claude-pr-review.md` - The PR #10 spec. Context only; do NOT edit.

### New Files
- `specs/chore-24d5c4d2-claude-review-full-diff-coverage.md` - This plan.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add coverage logic to `adws/adw_modules/review.py`
- Add a compiled regex for the coverage line, matched against each stripped line of the summary with `fullmatch`:
  `_COVERAGE_RE = re.compile(r"Diff read: (\d+) of (\d+) lines")`
- Add `parse_diff_coverage(summary: str) -> Optional[tuple[int, int]]`:
  - Iterate over `(summary or "").splitlines()`, `strip()` each line, `fullmatch` against `_COVERAGE_RE`, keep the last match.
  - Return `(int(N), int(M))` from the last match, or `None` if no line matches.
- Add `enforce_coverage(verdict: str, summary: str, diff_lines: int) -> tuple[str, str]`:
  - If `diff_lines == 0`: return `(verdict, summary)` unchanged.
  - `coverage = parse_diff_coverage(summary)`.
  - Work out a `problem` string (or `None`):
    - coverage is `None` → `f"the reviewer did not report a 'Diff read: N of M lines' line for a {diff_lines}-line diff."`
    - `M != diff_lines` → `f"the reviewer reported a {M}-line diff, but the diff has {diff_lines} lines."`
    - `N < diff_lines` → `f"the reviewer reported reading {N} of {diff_lines} diff lines."`
    - otherwise `None` (full coverage).
  - If `problem` is `None`: return `(verdict, summary)` unchanged.
  - If `verdict == "APPROVE"`: return `("REQUEST_CHANGES", summary_with_note)` where the note is `f"Downgraded: {problem}"` (the note starts with `Downgraded:` so the posted body says it was downgraded).
  - If `verdict == "REQUEST_CHANGES"`: return `("REQUEST_CHANGES", summary_with_note)` where the note is `f"Incomplete diff coverage: {problem}"` (visible, verdict unchanged).
  - Append the note as a new paragraph: `(summary.rstrip() + "\n\n" + note).strip()` so an empty summary yields just the note.
- Update the module docstring with one sentence describing the coverage check.
- Keep the module stdlib only.

### 2. Wire `--diff-lines` into `adws/review_verdict.py`
- Add to the `post` command: `@click.option("--diff-lines", type=click.IntRange(min=0), required=True, help="Line count of .review/diff.patch; 0 means nothing to read.")`, and a `diff_lines` parameter.
- After a successful `review.parse_review_file(text)` (i.e. only when `valid` is true), run `verdict, summary = review.enforce_coverage(verdict, summary, diff_lines)`. Do not apply it to the no-verdict path (already REQUEST_CHANGES).
- Leave the comment building, posting and `sys.exit(0 if verdict == "APPROVE" else 1)` as they are, so the exit code follows the final (possibly downgraded) verdict. The `click.echo(verdict)` line prints the final verdict.
- Update the module docstring's `Usage` block to include `--diff-lines 1043` and mention in the exit-code list that an APPROVE without full diff coverage is downgraded and exits 1.

### 3. Update tests in `adws/tests/test_review.py`
- `parse_diff_coverage`:
  - present: `"Spec: x\n\nDiff read: 120 of 120 lines\n\nNits: 0"` → `(120, 120)`.
  - absent: `"No coverage here"` → `None`; also `""` → `None`.
  - last one wins: two lines `Diff read: 400 of 900 lines` then `Diff read: 900 of 900 lines` → `(900, 900)`.
- `enforce_coverage`:
  - full coverage approve: `("APPROVE", "Diff read: 50 of 50 lines", 50)` → returned unchanged.
  - short coverage approve: `("APPROVE", "Diff read: 883 of 1043 lines", 1043)` → verdict `REQUEST_CHANGES`, summary contains `"Downgraded"` and `"883 of 1043"`, and still contains the original line.
  - missing line approve: `("APPROVE", "Looks fine.", 10)` → `REQUEST_CHANGES`, summary contains `"Downgraded"`.
  - M mismatch: `("APPROVE", "Diff read: 900 of 900 lines", 1043)` → `REQUEST_CHANGES`, summary contains `"Downgraded"`.
  - diff_lines 0: `("APPROVE", "No diff line.", 0)` → unchanged.
  - request-changes stays: `("REQUEST_CHANGES", "Diff read: 10 of 100 lines", 100)` → verdict `REQUEST_CHANGES`, summary has a note appended (contains `"10 of 100"` twice is not required; assert the summary is longer than the input and does not contain `"Downgraded"`); and `("REQUEST_CHANGES", "Diff read: 100 of 100 lines", 100)` → unchanged.
- CLI:
  - Change `run_post` to accept `diff_lines=0` and pass `"--diff-lines", str(diff_lines)`. Default 0 keeps every existing CLI test's behaviour unchanged.
  - New: approve with full coverage: review text `"VERDICT: APPROVE\nfine\n\nDiff read: 30 of 30 lines"`, `diff_lines=30` → exit 0, body ends with the APPROVE round-1 marker.
  - New: approve with short coverage: review text `"VERDICT: APPROVE\nfine\n\nDiff read: 883 of 1043 lines"`, `diff_lines=1043` → exit 1, one comment posted, body contains `"Downgraded"`, `review.parse_marker(body) == ("REQUEST_CHANGES", 1)`.
  - New: missing `--diff-lines` → non-zero exit (click usage error, code 2) and nothing posted. Invoke `CliRunner().invoke` directly without the option.
  - New: negative `--diff-lines` (`-1`) → click usage error, nothing posted.

### 4. Update `.github/workflows/claude-review.yml`
- In "Prepare review context", replace the diff line with:
  `git diff "$BASE_SHA...$HEAD_SHA" -- . ':(exclude)specs/' > .review/diff.patch`
- Keep `git diff --name-only "$BASE_SHA...$HEAD_SHA" > .review/files.txt` unchanged (all files, including specs).
- Add after the diff line: `wc -l < .review/diff.patch | tr -d ' ' > .review/diff_lines.txt`
- In "Run Claude review", change `--max-turns 30` to `--max-turns 40`.
- In "Post verdict", append `--diff-lines "$(cat .review/diff_lines.txt 2>/dev/null || echo 0)"` to the `review_verdict.py post` command. Keep all `${{ }}` values passed via `env:` as now; don't add any to `run:`.
- Change nothing else in the workflow (triggers, permissions, concurrency, tools, model, timeout).

### 5. Update `.claude/commands/review_pr.md`
- Instruction step 2: read `.review/pr.json` and `.review/files.txt`; then read `.review/diff_lines.txt` to learn the total diff line count M; then read `.review/diff.patch` IN FULL with the `Read` tool's `offset` and `limit`, in chunks of at most 400 lines (offset 1, 401, 801, …), continuing until you have read line M. Do not judge the PR before you have read every chunk. If M is 0, there is no diff to read.
- Add to step 2 (or right after it): `specs/` is excluded from `.review/diff.patch`; changed spec files are still listed in `.review/files.txt`.
- Step 3: find the spec via the PR body or a `specs/{chore|feature|bug}-*.md` path in `.review/files.txt` (not "added in the diff", since specs are no longer in the diff). Read the spec file itself in full from the workspace (use `offset`/`limit` if it is long). Keep the existing missing-spec rule.
- `Output` section: add a bullet to the summary list: a line exactly of the form `Diff read: N of M lines`, where N is the last diff line you actually read and M is the value from `.review/diff_lines.txt`, with no Markdown formatting on that line. Add: if you could not read the whole diff (turn limit, errors), say so, and the verdict must be `VERDICT: REQUEST_CHANGES` with a blocking issue "incomplete review". Add one sentence that the verdict step downgrades an APPROVE whose `Diff read:` line is missing or short.
- Update the example `.review/review.md` to include `Diff read: 412 of 412 lines` (e.g. after the `Spec:` line).
- Leave the rest of the prompt (untrusted input, what to check, inline comments, verdict rule) unchanged.

### 6. Update `app_docs/claude-review.md`
- "How it works" step 1: `.review/diff.patch` excludes `specs/`; `.review/files.txt` lists all changed files including specs; `.review/diff_lines.txt` holds the diff's line count.
- Step 3: the reviewer reads the whole diff in chunks of at most 400 lines and reads the spec in full from the workspace.
- Step 4: `review_verdict.py post` takes `--diff-lines` and applies the coverage rule before posting.
- Add a short "Diff coverage" section: the summary must contain `Diff read: N of M lines`; an APPROVE is downgraded to REQUEST_CHANGES (note starts with "Downgraded:") if that line is missing, N is less than the diff's line count, or M differs from it; a REQUEST_CHANGES with short coverage gets a note but stays REQUEST_CHANGES; a 0-line diff (e.g. a specs-only PR) skips the check. Mention that the logic lives in `adws/adw_modules/review.py` (`parse_diff_coverage`, `enforce_coverage`).
- "Cost": `--max-turns 40`.
- Update the "Run the verdict step locally" section only if needed so the help example still makes sense (no change required beyond the above).

### 7. Validate
- Run the validation commands below and fix any failures.
- `git diff --stat` should show only: `.github/workflows/claude-review.yml`, `.claude/commands/review_pr.md`, `adws/adw_modules/review.py`, `adws/review_verdict.py`, `adws/tests/test_review.py`, `app_docs/claude-review.md`, plus this new spec. Confirm `specs/feature-f42d8282-claude-pr-review.md`, `adws/adw_ship.py` and `.claude/settings.json` are untouched.

## Validation Commands
Execute these commands to validate the chore is complete:

- `./scripts/test.sh` - Run all tests (ADW tests, including `adws/tests/test_review.py`, plus backend and frontend).
- `uv run adws/review_verdict.py post --help` - Confirm `--diff-lines` is listed as a required option.
- `uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/claude-review.yml'))"` - Confirm the workflow is still valid YAML.
- `grep -n "max-turns 40" .github/workflows/claude-review.yml && grep -n "exclude)specs/" .github/workflows/claude-review.yml && grep -n "diff_lines.txt" .github/workflows/claude-review.yml` - Confirm the workflow changes are present.
- `git diff --stat main -- specs/feature-f42d8282-claude-pr-review.md adws/adw_ship.py .claude/settings.json` - Must print nothing.

## Notes
- `wc -l` counts newline characters. `git diff` output ends with a newline, so it equals the number of lines the `Read` tool shows. An empty diff (e.g. a specs-only PR) gives 0, and the coverage check is skipped.
- The coverage line is matched strictly (whole stripped line, `fullmatch`). A bolded or reworded line counts as missing and downgrades an APPROVE. That's the safe failure direction: the check goes red and a re-review fixes it.
- The coverage check only trusts what the reviewer reports; it can't prove the reads happened. It catches the observed failure (stopping early and approving anyway) and makes the reported coverage visible in every summary comment.
- `--diff-lines` falls back to 0 in the workflow if `diff_lines.txt` is missing. That only happens if "Prepare review context" failed, in which case the job has already failed under `set -euo pipefail`.
- Inline comments on spec files are still possible on GitHub, but the reviewer only sees spec content through the workspace now; no prompt change is needed for that beyond step 3.
- Round counting and the marker format are unchanged.
