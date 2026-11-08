"""Tests for adw_ship: the pure decision logic, the parsers and scripted run_ship runs.

Everything outside Python is faked: gh, git, agents, tests, health checks and time.
"""

import json

import pytest

import agent
import git_ops
import github
import ship
from github import PullRequest
from health import Check
from lifecycle import TestResult
from ship import Action, ShipOptions, ShipState, decide

OWNER = "owner"
BOT = ship.BOT_LOGIN
GREEN = ("COMPLETED", "SUCCESS")
RED = ("COMPLETED", "FAILURE")
PENDING = ("IN_PROGRESS", None)
SHA_A = "a" * 40
SHA_B = "b" * 40
NEW_SHA = "abc1234" + "0" * 33
MARKER_CHANGES = "<!-- claude-review verdict: REQUEST_CHANGES round: 1 -->"
MARKER_APPROVE = "<!-- claude-review verdict: APPROVE round: 2 -->"


# --- decide -------------------------------------------------------------------


def state(**overrides):
    defaults = dict(
        pr_state="OPEN",
        is_draft=False,
        ci=GREEN,
        review=GREEN,
        up_to_date=True,
        reviewer_infra_failure=False,
        labels=(),
        files=("apps/backend/x.py",),
        rounds_used=0,
        max_rounds=3,
        merge_mode="never",
    )
    defaults.update(overrides)
    return ShipState(**defaults)


def test_merged_and_closed_are_done():
    assert decide(state(pr_state="MERGED")) == (Action.DONE, "PR is already merged")
    assert decide(state(pr_state="CLOSED")) == (Action.DONE, "PR is already closed")


def test_draft_escalates():
    action, reason = decide(state(is_draft=True, ci=None))
    assert action == Action.ESCALATE
    assert "draft" in reason


def test_missing_or_running_checks_wait():
    action, reason = decide(state(ci=None))
    assert action == Action.WAIT
    assert "ci (missing)" in reason
    action, reason = decide(state(review=PENDING))
    assert action == Action.WAIT
    assert "claude-review (IN_PROGRESS)" in reason


@pytest.mark.parametrize("conclusion", ["SKIPPED", "CANCELLED", "TIMED_OUT"])
@pytest.mark.parametrize("check", ["ci", "review"])
def test_other_conclusions_escalate(conclusion, check):
    action, reason = decide(state(**{check: ("COMPLETED", conclusion), "rounds_used": 0}))
    assert action == Action.ESCALATE
    assert conclusion in reason


def test_no_conclusion_escalates():
    assert decide(state(ci=("COMPLETED", None)))[0] == Action.ESCALATE


def test_infra_failure_escalates_without_a_round():
    action, reason = decide(state(ci=RED, review=RED, reviewer_infra_failure=True))
    assert action == Action.ESCALATE
    assert "infrastructure" in reason
    action, reason = decide(
        state(review=RED, reviewer_infra_failure=True, rounds_used=3)
    )
    assert "infrastructure" in reason


def test_failures_pick_a_fix():
    assert decide(state(ci=RED))[0] == Action.FIX_CI
    assert decide(state(ci=RED, review=RED))[0] == Action.FIX_CI
    assert decide(state(review=RED))[0] == Action.ADDRESS_REVIEW


def test_round_limit_escalates():
    action, reason = decide(state(review=RED, rounds_used=3, max_rounds=3))
    assert action == Action.ESCALATE
    assert "round limit reached (3 of 3)" in reason
    assert "claude-review still failing" in reason
    assert decide(state(ci=RED, max_rounds=0))[0] == Action.ESCALATE


def test_not_up_to_date_updates_even_with_rounds_exhausted():
    action, _ = decide(state(up_to_date=False, rounds_used=3, max_rounds=3))
    assert action == Action.UPDATE_BRANCH


@pytest.mark.parametrize(
    "path",
    [".github/workflows/ci.yml", ".claude/commands/x.md", *ship.PROTECTED_FILES],
)
def test_protected_paths_escalate(path):
    action, reason = decide(state(files=("a.py", path), merge_mode="auto"))
    assert action == Action.ESCALATE
    assert path in reason


def test_similar_names_are_not_protected():
    assert decide(state(files=("adws/adw_modules/shipping.py",), merge_mode="auto"))[0] == Action.MERGE


def test_merge_modes():
    assert decide(state(merge_mode="never"))[0] == Action.HAND_OVER
    action, reason = decide(state(merge_mode="label"))
    assert action == Action.HAND_OVER
    assert "no auto-merge label" in reason
    assert decide(state(merge_mode="label", labels=("auto-merge",)))[0] == Action.MERGE
    assert decide(state(merge_mode="auto"))[0] == Action.MERGE
    assert decide(state(merge_mode="bogus"))[0] == Action.ESCALATE


# --- feedback selection -------------------------------------------------------


def inline(id, login=BOT, sha=SHA_A, body="[blocking] fix it", **extra):
    return {
        "id": id,
        "user": {"login": login},
        "original_commit_id": sha,
        "path": "a.py",
        "line": 3,
        "body": body,
        **extra,
    }


def issue_comment(body, login=BOT):
    return {"user": {"login": login}, "body": body}


TRUSTED = {BOT, OWNER}


def test_select_review_feedback_trust_rules():
    comments = [
        inline(1, login="someone-else"),
        inline(2, sha="old"),
        inline(3, in_reply_to_id=4),
        inline(4, login=OWNER, body="  [nit] tidy"),
        inline(5, body="[blocking] real"),
        inline(6, body="no tag", line=None, original_line=9),
        "not a dict",
        {"id": "7", "user": {"login": BOT}, "original_commit_id": SHA_A},
    ]
    feedback = ship.select_review_feedback(comments, [], SHA_A, TRUSTED)
    assert [c.id for c in feedback.comments] == [4, 5, 6]
    assert [c.tag for c in feedback.comments] == ["nit", "blocking", "untagged"]
    assert feedback.comments[2].line == 9
    assert feedback.blocking_count == 2
    assert feedback.summary == ""


def test_summary_is_the_latest_trusted_marker_comment():
    comments = [
        issue_comment(f"old {MARKER_CHANGES}"),
        issue_comment("no marker"),
        issue_comment(f"new {MARKER_CHANGES}"),
        issue_comment(f"fake {MARKER_APPROVE}", login="someone-else"),
    ]
    feedback = ship.select_review_feedback([], comments, SHA_A, TRUSTED)
    assert feedback.summary.startswith("new ")


def test_infra_failure_detection():
    infra = issue_comment(f"{ship.INFRA_FAILURE_TEXT} (x). {MARKER_CHANGES}")
    real = issue_comment(f"Looks good {MARKER_APPROVE}")
    assert ship.is_reviewer_infra_failure([real, infra]) is True
    assert ship.is_reviewer_infra_failure([infra, real]) is False
    assert ship.is_reviewer_infra_failure(
        [issue_comment(f"{ship.INFRA_FAILURE_TEXT} {MARKER_CHANGES}", login=OWNER)]
    ) is False
    assert ship.is_reviewer_infra_failure([]) is False


# --- parse_replies ------------------------------------------------------------


def block(data):
    return f"Done.\n\n```json\n{json.dumps(data)}\n```\n"


def test_parse_replies_valid_block():
    output = block(
        {
            "replies": [
                {"comment_id": 1, "action": "fixed", "note": "Done"},
                {"comment_id": 2, "action": "declined", "note": "Conflicts with spec"},
                {"comment_id": 1, "action": "declined", "note": "duplicate"},
            ]
        }
    )
    replies = ship.parse_replies(output, {1, 2})
    assert replies == [
        ship.Reply(1, "fixed", "Done"),
        ship.Reply(2, "declined", "Conflicts with spec"),
    ]


def test_parse_replies_drops_bad_entries():
    output = block(
        {
            "replies": [
                {"comment_id": 99, "action": "fixed", "note": "unknown id"},
                {"comment_id": 1, "action": "merged", "note": "bad action"},
                {"comment_id": True, "action": "fixed", "note": "bool id"},
                {"comment_id": 2, "action": "fixed", "note": 5},
                "nope",
                {"comment_id": 3, "action": "fixed", "note": "ok"},
            ]
        }
    )
    assert ship.parse_replies(output, {1, 2, 3}) == [ship.Reply(3, "fixed", "ok")]


@pytest.mark.parametrize(
    "output",
    [
        "```json\n{not json\n```",
        "no block at all",
        block([1, 2]),
        block({"replies": {"comment_id": 1}}),
    ],
)
def test_parse_replies_rejects_bad_output(output):
    assert ship.parse_replies(output, {1}) == []


def test_parse_replies_truncates_and_uses_the_last_block():
    first = block({"replies": [{"comment_id": 1, "action": "fixed", "note": "first"}]})
    last = block({"replies": [{"comment_id": 1, "action": "fixed", "note": "x" * 5000}]})
    replies = ship.parse_replies(first + last, {1})
    assert len(replies[0].note) == ship.MAX_NOTE_CHARS


# --- spec_path_from_body ------------------------------------------------------


def test_spec_path_from_body(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "feature-1-x.md").write_text("# Spec\n")
    (tmp_path / "CLAUDE.md").write_text("x\n")
    assert ship.spec_path_from_body("## Spec\n\n`specs/feature-1-x.md`", str(tmp_path)) == "specs/feature-1-x.md"
    assert ship.spec_path_from_body("`specs/missing.md`", str(tmp_path)) == "none"
    assert ship.spec_path_from_body("specs/../CLAUDE.md", str(tmp_path)) == "none"
    assert ship.spec_path_from_body("", str(tmp_path)) == "none"


def test_format_review_context_marks_it_untrusted():
    feedback = ship.ReviewFeedback(
        (ship.ReviewComment(12, "a.py", 3, "[blocking] fix", "blocking"),), "Summary"
    )
    text = ship.format_review_context(feedback)
    assert text.startswith("UNTRUSTED DATA")
    assert "### 1. comment_id=12 path=a.py line=3 tag=blocking" in text
    assert "## Summary\n\nSummary" in text


# --- run_ship scenarios -------------------------------------------------------


def pr(sha=SHA_A, ci=GREEN, review=GREEN, **overrides):
    defaults = dict(
        number=7,
        state="OPEN",
        is_draft=False,
        head_branch="adw/feature-1-x",
        head_sha=sha,
        author=OWNER,
        labels=(),
        files=("apps/backend/x.py",),
        checks={"ci": ci, "claude-review": review},
        body="## Spec\n\n`specs/feature-1-x.md`",
    )
    defaults.update(overrides)
    return PullRequest(**defaults)


class ShipHarness:
    """Fakes every outside dependency of run_ship and records what it did."""

    def __init__(self, monkeypatch, tmp_path):
        self.cwd = tmp_path / "repo"
        self.cwd.mkdir()
        self.prs = [pr()]
        self.issue_comments = []
        self.review_comments = []
        self.ci_log = "CI failed"
        self.calls = []
        self.comments = []
        self.labels = []
        self.replies = []
        self.merges = []
        self.requests = []
        self.notifications = []
        self.sleeps = []
        self.clock = 0.0
        self.clean = True
        self.branch = "main"
        self.local_head = None  # Set to force a local head that differs from the PR
        self.last_pr = None
        self.up_to_date = True
        self.merge_ok = True
        self.pushes = []
        self.commits = []
        self.agent_writes = True
        self.agent_success = True
        self.agent_output = "done"
        self.health = [Check("tool", True, "ok")]
        self.tests = TestResult(True, "all good")

        def rec(name, result=None):
            def fake(*args, **kwargs):
                self.calls.append((name, args))
                return result() if callable(result) else result
            return fake

        mp = monkeypatch
        mp.setattr(github, "get_pr", self.get_pr)
        mp.setattr(github, "repo_owner", rec("repo_owner", OWNER))
        mp.setattr(github, "list_issue_comments", rec("list_issue_comments", lambda: self.issue_comments))
        mp.setattr(github, "list_review_comments", rec("list_review_comments", lambda: self.review_comments))
        mp.setattr(github, "failed_ci_log", rec("failed_ci_log", lambda: self.ci_log))
        mp.setattr(github, "reply_to_review_comment", self.reply)
        mp.setattr(github, "comment_on_pr", lambda n, body, cwd=None: self.comments.append(body))
        mp.setattr(github, "add_label", lambda n, label, cwd=None: self.labels.append((n, label)))
        mp.setattr(github, "merge_pr", lambda n, sha, cwd=None: self.merges.append((n, sha)))

        mp.setattr(git_ops, "is_clean", lambda cwd=None: self.clean)
        mp.setattr(git_ops, "current_branch", lambda cwd=None: self.branch)
        mp.setattr(git_ops, "checkout_pr_branch", self.checkout)
        mp.setattr(git_ops, "head_sha", lambda cwd=None: self.local_head or self.last_pr.head_sha)
        mp.setattr(git_ops, "is_up_to_date_with_main", self.is_up_to_date)
        mp.setattr(git_ops, "merge_main_into", lambda branch, cwd=None: self.merge_ok)
        mp.setattr(git_ops, "ensure_on_work_branch", lambda branch, cwd=None: None)
        mp.setattr(git_ops, "commit_all", self.commit_all)
        mp.setattr(git_ops, "push_branch", lambda branch, cwd=None: self.pushes.append(branch))
        mp.setattr(git_ops, "return_to_main", self.return_to_main)
        mp.setattr(git_ops, "sync_main", rec("sync_main"))

        mp.setattr(ship, "execute_template", self.execute_template)
        mp.setattr(ship, "run_tests", lambda cwd: self.tests)
        mp.setattr(ship, "run_health_checks", lambda profile: self.health)
        mp.setattr(ship, "_notify", self.notifications.append)

    def get_pr(self, number, cwd=None):
        self.calls.append(("get_pr", (number,)))
        self.last_pr = self.prs.pop(0) if len(self.prs) > 1 else self.prs[0]
        return self.last_pr

    def is_up_to_date(self, sha, cwd=None):
        if isinstance(self.up_to_date, list):
            return self.up_to_date.pop(0)
        return self.up_to_date

    def reply(self, n, comment_id, body, cwd=None):
        self.replies.append((comment_id, body))

    def checkout(self, branch, cwd=None):
        self.calls.append(("checkout_pr_branch", (branch,)))
        self.branch = branch

    def commit_all(self, message, adw_id, branch, cwd=None):
        self.commits.append(message)
        self.clean = True
        return NEW_SHA

    def return_to_main(self, cwd=None):
        self.branch = "main"

    def execute_template(self, request):
        self.requests.append(request)
        if self.agent_writes:
            self.clean = False
        return agent.AgentPromptResponse(output=self.agent_output, success=self.agent_success)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds

    def now(self):
        return self.clock

    def run(self, merge="never", max_rounds=3, timeout=1800, poll=60):
        return ship.run_ship(
            ShipOptions(
                pr=7,
                profile="claude",
                max_rounds=max_rounds,
                merge_mode=merge,
                poll_interval=poll,
                timeout=timeout,
                working_dir=str(self.cwd),
            ),
            sleep=self.sleep,
            now=self.now,
        )

    def names(self):
        return [name for name, _ in self.calls]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    return ShipHarness(monkeypatch, tmp_path)


def run_log(runs_log):
    return [json.loads(line) for line in runs_log.read_text().splitlines()]


def summary_file(runs_log, adw_id):
    return json.loads((runs_log.parent / adw_id / "ship_summary.json").read_text())


def test_a_pending_then_green_hands_over(harness, runs_log):
    harness.prs = [pr(review=PENDING), pr()]
    assert harness.run(merge="never") == 0
    assert harness.sleeps == [60]
    assert harness.merges == []
    assert len(harness.comments) == 1
    assert "Ready for a human merge (--merge=never)" in harness.comments[0]
    entry = run_log(runs_log)[-1]
    assert entry["step"] == "ship"
    assert entry["outcome"] == "handed_over"
    assert entry["rounds"] == 0


def test_b_addresses_review_then_merges(harness, runs_log):
    harness.prs = [pr(review=RED), pr(sha=NEW_SHA), pr(sha=NEW_SHA)]
    harness.issue_comments = [issue_comment(f"Please fix. {MARKER_CHANGES}")]
    harness.review_comments = [inline(55, body="[blocking] handle None")]
    harness.agent_output = block(
        {"replies": [{"comment_id": 55, "action": "fixed", "note": "Handled None."}]}
    )

    assert harness.run(merge="auto") == 0

    request = harness.requests[0]
    assert request.agent_name == "review_fixer"
    assert request.slash_command == "/address_review"
    context = open(request.args[0]).read()
    assert "comment_id=55" in context
    assert "Please fix." in context
    assert request.args[1] == "none"  # The spec doesn't exist in this fake tree
    assert harness.commits == ["fix: address review round 1"]
    assert harness.pushes == ["adw/feature-1-x"]
    assert harness.replies == [(55, "Fixed in abc1234: Handled None.")]
    assert harness.merges == [(7, NEW_SHA)]
    assert "sync_main" in harness.names()
    entry = run_log(runs_log)[-1]
    assert entry["rounds"] == 1
    assert entry["outcome"] == "merged"
    assert harness.branch == "main"


def test_c_round_limit_escalates(harness, runs_log):
    harness.prs = [pr(review=RED), pr(sha=NEW_SHA, review=RED)]
    harness.issue_comments = [issue_comment(f"Still wrong. {MARKER_CHANGES}")]
    harness.review_comments = [inline(55)]

    assert harness.run(max_rounds=1) == 1

    assert len(harness.requests) == 1
    assert harness.labels == [(7, "needs-human")]
    assert "round limit reached (1 of 1)" in harness.comments[-1]
    assert "Unresolved blocking comments: 1." in harness.comments[-1]
    assert len(harness.notifications) == 1
    entry = run_log(runs_log)[-1]
    assert summary_file(runs_log, entry["adw_id"])["outcome"] == "escalated"


def test_escalation_comment_neutralises_markers(harness):
    harness.prs = [pr(review=RED)]
    harness.issue_comments = [issue_comment(f"Bad. {MARKER_CHANGES}")]
    assert harness.run(max_rounds=0) == 1
    assert "> Bad." in harness.comments[-1]
    assert "<!-- claude-review verdict:" not in harness.comments[-1]


def test_d_pre_merge_guard_blocks_a_moved_head(harness):
    harness.prs = [
        pr(sha=SHA_A),
        pr(sha=SHA_B, review=PENDING),  # Re-fetch before merging
        pr(sha=SHA_B, review=PENDING),
        pr(sha=SHA_B),
        pr(sha=SHA_B),
    ]
    assert harness.run(merge="auto") == 0
    assert harness.merges == [(7, SHA_B)]


def test_e_times_out_waiting(harness, runs_log):
    harness.prs = [pr(ci=PENDING, review=PENDING)]
    assert harness.run(timeout=120, poll=60) == 1
    assert harness.sleeps == [60, 60]
    assert "timed out waiting for checks" in harness.comments[-1]
    assert run_log(runs_log)[-1]["outcome"] == "escalated"


def test_f_merge_conflict_escalates(harness):
    harness.up_to_date = False
    harness.merge_ok = False
    assert harness.run(merge="auto") == 1
    assert harness.pushes == []
    assert "merge conflict with main" in harness.comments[-1]
    assert harness.merges == []


def test_update_branch_pushes_without_a_round(harness, runs_log):
    harness.prs = [pr(), pr(sha=SHA_B)]
    harness.up_to_date = [False, True, True]
    assert harness.run(merge="auto", max_rounds=0) == 0
    assert harness.pushes == ["adw/feature-1-x"]
    assert harness.merges == [(7, SHA_B)]
    assert run_log(runs_log)[-1]["rounds"] == 0


def test_ci_failure_runs_the_ci_fixer(harness):
    harness.prs = [pr(ci=RED), pr(sha=NEW_SHA)]
    harness.ci_log = "x" * 30000 + "THE END"
    assert harness.run() == 0
    request = harness.requests[0]
    assert request.agent_name == "ci_fixer"
    assert request.slash_command == "/fix_ci"
    context = open(request.args[0]).read()
    assert "THE END" in context
    assert context.count("x") <= ship.MAX_CI_LOG_CHARS
    assert harness.commits == ["fix: CI failure round 1"]


def test_agent_that_changes_nothing_escalates(harness):
    harness.prs = [pr(ci=RED)]
    harness.agent_writes = False
    assert harness.run() == 1
    assert "changed nothing" in harness.comments[-1]
    assert harness.pushes == []


def test_failed_agent_escalates(harness):
    harness.prs = [pr(ci=RED)]
    harness.agent_success = False
    harness.agent_output = "boom"
    assert harness.run() == 1
    assert "the ci_fixer agent failed: boom" in harness.comments[-1]


def test_branch_moved_is_an_error_with_no_agent(harness, runs_log):
    harness.prs = [pr(ci=RED)]
    harness.local_head = SHA_B
    assert harness.run() == 1
    assert harness.requests == []
    assert run_log(runs_log)[-1]["outcome"] == "error"


def test_infra_failure_escalates_with_no_agent(harness, runs_log):
    harness.prs = [pr(review=RED)]
    harness.issue_comments = [issue_comment(f"{ship.INFRA_FAILURE_TEXT} (crash). {MARKER_CHANGES}")]
    assert harness.run() == 1
    assert harness.requests == []
    assert "infrastructure" in harness.comments[-1]
    assert run_log(runs_log)[-1]["rounds"] == 0


def test_protected_file_is_never_auto_merged(harness):
    harness.prs = [pr(files=(".claude/commands/review_pr.md",))]
    assert harness.run(merge="auto") == 1
    assert harness.merges == []
    assert harness.labels == [(7, "needs-human")]


def test_already_merged(harness, runs_log):
    harness.prs = [pr(state="MERGED")]
    assert harness.run() == 0
    assert run_log(runs_log)[-1]["outcome"] == "already_closed"


def test_dirty_tree_at_start(harness, runs_log):
    harness.clean = False
    harness.branch = "some-branch"
    assert harness.run() == 1
    assert harness.calls == []
    assert harness.requests == []
    assert harness.branch == "some-branch"
    assert run_log(runs_log)[-1]["outcome"] == "error"


def test_non_owner_pr_escalates(harness):
    harness.prs = [pr(author="someone-else", ci=RED)]
    assert harness.run() == 1
    assert harness.requests == []
    assert "repo owner" in harness.comments[-1]


def test_failed_health_check(harness):
    harness.health = [Check("claude", False, "missing")]
    assert harness.run() == 1
    assert harness.calls == []


def test_finally_returns_to_main_when_clean(harness):
    harness.prs = [pr(ci=RED)]
    harness.agent_writes = False  # Escalates while on the PR branch
    harness.run()
    assert harness.branch == "main"


def test_summary_and_run_log_fields(harness, runs_log):
    assert harness.run() == 0
    entry = run_log(runs_log)[-1]
    assert set(entry) == {"adw_id", "step", "pr", "rounds", "profile", "outcome", "duration_ms"}
    assert entry["pr"] == 7
    assert entry["profile"] == "claude"
    summary = summary_file(runs_log, entry["adw_id"])
    assert summary["exit_code"] == 0
    assert summary["decisions"][0]["action"] == "hand_over"
