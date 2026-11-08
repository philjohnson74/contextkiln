"""Verdict parsing and marker logic for the automated Claude PR review.

The reviewer's verdict file (`.review/review.md`) is untrusted LLM output, so
it's parsed strictly here: the first non-empty line must be exactly
`VERDICT: APPROVE` or `VERDICT: REQUEST_CHANGES`. The summary comment that the
workflow posts ends with a machine-readable marker:

    <!-- claude-review verdict: APPROVE|REQUEST_CHANGES round: N -->

The summary must also report diff coverage as a `Diff read: N of M lines`
line; an APPROVE without full coverage is downgraded to REQUEST_CHANGES.

Stdlib only.
"""

import re
from typing import Optional

VERDICTS = ("APPROVE", "REQUEST_CHANGES")
MARKER_PREFIX = "<!-- claude-review verdict:"

_MARKER_RE = re.compile(
    r"<!-- claude-review verdict: (APPROVE|REQUEST_CHANGES) round: (\d+) -->"
)
_VERDICT_LINE_RE = re.compile(r"VERDICT:\s*(\S+)")
_COVERAGE_RE = re.compile(r"Diff read: (\d+) of (\d+) lines")

_HEADINGS = {
    "APPROVE": "✅ Approve",
    "REQUEST_CHANGES": "❌ Changes requested",
}


def parse_review_file(text: str) -> tuple[str, str]:
    """Return `(verdict, summary)` from a verdict file, or raise `ValueError`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        match = _VERDICT_LINE_RE.fullmatch(stripped)
        if not match:
            raise ValueError(
                f"first non-empty line is not a verdict line: {stripped[:80]!r}"
            )
        verdict = match.group(1)
        if verdict not in VERDICTS:
            raise ValueError(f"unknown verdict: {verdict[:40]!r}")
        summary = "\n".join(lines[index + 1 :]).strip()
        return verdict, summary
    raise ValueError("review file is empty")


def build_marker(verdict: str, round_number: int) -> str:
    """Return the HTML marker for a verdict and round."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    if (
        not isinstance(round_number, int)
        or isinstance(round_number, bool)
        or round_number < 1
    ):
        raise ValueError(f"round must be an int >= 1, got {round_number!r}")
    return f"<!-- claude-review verdict: {verdict} round: {round_number} -->"


def parse_marker(text: str) -> Optional[tuple[str, int]]:
    """Return `(verdict, round)` from the last marker in `text`, or `None`."""
    matches = _MARKER_RE.findall(text)
    if not matches:
        return None
    verdict, round_text = matches[-1]
    return verdict, int(round_text)


def next_round(comment_bodies: list[str]) -> int:
    """Return 1 + the number of bodies that contain a marker."""
    return 1 + sum(
        1 for body in comment_bodies if parse_marker(body or "") is not None
    )


def format_summary_comment(verdict: str, summary: str, round_number: int) -> str:
    """Build the summary comment. The marker is always its last line."""
    marker = build_marker(verdict, round_number)
    safe_summary = (summary or "").replace(MARKER_PREFIX, "<!-- (marker removed)")
    safe_summary = safe_summary.strip() or "_No summary provided._"
    heading = f"## Claude review — round {round_number}: {_HEADINGS[verdict]}"
    return f"{heading}\n\n{safe_summary}\n\n{marker}\n"


def no_verdict_summary(reason: str) -> str:
    """Explain that the reviewer produced no valid verdict."""
    return (
        "The reviewer produced no valid verdict "
        f"({reason}). The `claude-review` check fails until a re-review "
        "produces one."
    )


def parse_diff_coverage(summary: str) -> Optional[tuple[int, int]]:
    """Return `(N, M)` from the last `Diff read: N of M lines` line, or `None`."""
    found = None
    for line in (summary or "").splitlines():
        match = _COVERAGE_RE.fullmatch(line.strip())
        if match:
            found = (int(match.group(1)), int(match.group(2)))
    return found


def enforce_coverage(verdict: str, summary: str, diff_lines: int) -> tuple[str, str]:
    """Downgrade an APPROVE whose reported diff coverage is missing or short.

    A REQUEST_CHANGES stays as it is, but gets a note when coverage is short.
    A 0-line diff has nothing to read, so the check is skipped.
    """
    if diff_lines == 0:
        return verdict, summary
    coverage = parse_diff_coverage(summary)
    if coverage is None:
        problem = (
            "the reviewer did not report a 'Diff read: N of M lines' line "
            f"for a {diff_lines}-line diff."
        )
    else:
        read, total = coverage
        if total != diff_lines:
            problem = (
                f"the reviewer reported a {total}-line diff, "
                f"but the diff has {diff_lines} lines."
            )
        elif read < diff_lines:
            problem = f"the reviewer reported reading {read} of {diff_lines} diff lines."
        else:
            problem = None
    if problem is None:
        return verdict, summary
    if verdict == "APPROVE":
        note = f"Downgraded: {problem}"
    else:
        note = f"Incomplete diff coverage: {problem}"
    return "REQUEST_CHANGES", ((summary or "").rstrip() + "\n\n" + note).strip()
