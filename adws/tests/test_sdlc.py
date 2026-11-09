"""Tests for adw_sdlc. Lifecycle, ship, gh and git are all faked."""

import json

import pytest

import git_ops
import github
import sdlc
from github import GitHubError, Issue
from health import Check
from sdlc import SdlcOptions

OWNER = "owner"
PR_URL = "https://github.com/o/r/pull/9"
RUN_LOG_KEYS = {
    "adw_id", "step", "issue", "pr", "type", "plan_profile", "build_profile",
    "ship_profile", "merge_mode", "rounds", "outcome", "duration_ms",
}


def issue(number=7, author=OWNER, labels=("adw-ready",), state="OPEN"):
    return Issue(number, f"Issue {number}", "Body", author, tuple(labels), state)


class SdlcHarness:
    """Fakes every dependency of run_sdlc and records what it did."""

    def __init__(self, monkeypatch, tmp_path):
        self.cwd = tmp_path / "repo"
        self.cwd.mkdir()
        self.issues = [issue()]
        self.backlog = []
        self.list_calls = []
        self.writes = []
        self.calls = []
        self.clean = True
        self.branch = "main"
        self.returned_to_main = False
        self.health = [Check("tool", True, "ok")]
        self.lifecycle_calls = []
        self.lifecycle_result = (0, {"pr_url": PR_URL, "tests_passed": True})
        self.lifecycle_error = None
        self.ship_calls = []
        self.ship_result = (0, {"outcome": "merged", "rounds": 2})
        self.pr_state = "MERGED"
        self.fail_labels = False

        mp = monkeypatch
        mp.setattr(github, "repo_owner", self.repo_owner)
        mp.setattr(github, "get_issue", self.get_issue)
        mp.setattr(github, "list_issues", self.list_issues)
        mp.setattr(github, "comment_on_issue", self.write("comment_on_issue"))
        mp.setattr(github, "add_issue_label", self.write("add_issue_label", label=True))
        mp.setattr(github, "remove_label", self.write("remove_label", label=True))
        mp.setattr(github, "close_issue", self.write("close_issue"))
        mp.setattr(github, "get_pr", self.get_pr)
        mp.setattr(git_ops, "is_clean", lambda cwd=None: self.clean)
        mp.setattr(git_ops, "current_branch", lambda cwd=None: self.branch)
        mp.setattr(git_ops, "return_to_main", self.return_to_main)
        mp.setattr(sdlc, "run_health_checks", lambda profile: self.health)
        mp.setattr(sdlc, "run_lifecycle", self.run_lifecycle)
        mp.setattr(sdlc, "run_ship_with_summary", self.run_ship)

    def repo_owner(self, cwd=None):
        self.calls.append("repo_owner")
        return OWNER

    def get_issue(self, number, cwd=None):
        self.calls.append(("get_issue", number))
        return self.issues.pop(0) if len(self.issues) > 1 else self.issues[0]

    def list_issues(self, labels, state="open", cwd=None):
        self.list_calls.append(list(labels))
        return self.backlog

    def write(self, name, label=False):
        def fake(*args, cwd=None):
            self.writes.append((name, *args))
            if label and self.fail_labels:
                raise GitHubError("gh issue edit failed")
        return fake

    def get_pr(self, number, cwd=None):
        class PR:
            state = self.pr_state
        return PR()

    def return_to_main(self, cwd=None):
        self.returned_to_main = True
        self.branch = "main"

    def run_lifecycle(self, options, adw_id=None):
        self.lifecycle_calls.append((options, adw_id))
        if self.lifecycle_error:
            raise self.lifecycle_error
        return self.lifecycle_result

    def run_ship(self, options, sleep=None, now=None, adw_id=None):
        self.ship_calls.append((options, adw_id))
        return self.ship_result

    def run(
        self,
        prompt=None,
        issue=None,
        adw_type=None,
        build_profile="local",
        merge="auto",
        ship_profile="claude",
    ):
        return sdlc.run_sdlc(
            SdlcOptions(
                prompt=prompt,
                issue=issue,
                adw_type=adw_type,
                plan_profile="claude",
                build_profile=build_profile,
                ship_profile=ship_profile,
                merge_mode=merge,
                max_rounds=3,
                poll_interval=60,
                timeout=1800,
                working_dir=str(self.cwd),
            ),
            sleep=lambda s: None,
            now=lambda: 0.0,
        )

    def names(self):
        return [w[0] for w in self.writes]


@pytest.fixture
def harness(monkeypatch, tmp_path):
    return SdlcHarness(monkeypatch, tmp_path)


def run_log(runs_log):
    return [json.loads(line) for line in runs_log.read_text().splitlines()]


def test_select_type():
    assert sdlc.select_type("chore", issue(labels=("bug",))) == "chore"
    assert sdlc.select_type(None, issue(labels=("bug",))) == "bug"
    assert sdlc.select_type(None, issue(labels=("chore", "bug"))) == "bug"
    assert sdlc.select_type(None, issue(labels=("chore",))) == "chore"
    assert sdlc.select_type(None, issue(labels=())) == "feature"
    assert sdlc.select_type(None, None) == "feature"


def test_non_owner_issue_is_refused_before_any_github_write(harness, runs_log):
    harness.issues = [issue(author="someone")]
    assert harness.run(issue=7) == 1
    assert harness.writes == []
    assert harness.lifecycle_calls == []
    assert harness.ship_calls == []
    assert run_log(runs_log)[-1]["outcome"] == "refused"


def test_closed_issue_is_refused(harness, runs_log):
    harness.issues = [issue(state="CLOSED")]
    assert harness.run(issue=7) == 1
    assert harness.writes == []
    assert harness.lifecycle_calls == []
    assert run_log(runs_log)[-1]["outcome"] == "refused"


def test_next_issue_picks_the_oldest_ready_owner_issue(harness):
    harness.backlog = [
        issue(5, labels=("adw-ready", "needs-human")),
        issue(3, author="someone"),
        issue(8),
        issue(6, labels=("adw-ready", "adw-in-progress")),
        issue(4),
    ]
    assert harness.run() == 0
    assert harness.list_calls == [["adw-ready"]]
    assert harness.lifecycle_calls[0][0].issue == 4


def test_no_ready_issue_exits_0(harness, runs_log, capsys):
    harness.backlog = [issue(3, author="someone"), issue(5, labels=("adw-ready", "needs-human"))]
    assert harness.run() == 0
    assert "No issue is ready" in capsys.readouterr().out
    assert harness.lifecycle_calls == []
    assert harness.writes == []
    assert run_log(runs_log)[-1]["outcome"] == "no_issue"


def test_prompt_happy_path_merges(harness, runs_log):
    assert harness.run(prompt="Add the thing") == 0

    options, adw_id = harness.lifecycle_calls[0]
    assert options.prompt == "Add the thing"
    assert options.issue is None
    assert options.adw_type == "feature"
    assert options.no_pr is False
    assert options.draft_on_test_failure is False
    ship_options, ship_adw_id = harness.ship_calls[0]
    assert ship_adw_id == adw_id
    assert ship_options.pr == 9
    assert ship_options.profile == "claude"
    assert ship_options.merge_mode == "auto"

    entry = run_log(runs_log)[-1]
    assert set(entry) == RUN_LOG_KEYS
    assert entry["adw_id"] == adw_id
    assert entry["step"] == "sdlc"
    assert entry["build_profile"] == "local"
    assert entry["rounds"] == 2
    assert entry["outcome"] == "merged"
    assert entry["pr"] == 9

    summary = json.loads((runs_log.parent / adw_id / "sdlc_summary.json").read_text())
    assert {"lifecycle", "ship", "outcome"} <= set(summary)
    assert summary["outcome"] == "merged"
    assert harness.writes == []


def test_merged_with_issue_still_open_closes_it(harness, runs_log):
    harness.issues = [issue(), issue()]
    assert harness.run(issue=7) == 0
    adw_id = run_log(runs_log)[-1]["adw_id"]
    assert ("close_issue", 7, f"Closed by ADW {adw_id}: merged in {PR_URL}") in harness.writes
    assert harness.names() == ["add_issue_label", "close_issue", "remove_label"]


def test_merged_with_issue_already_closed_doesnt_close(harness):
    harness.issues = [issue(), issue(state="CLOSED")]
    assert harness.run(issue=7) == 0
    assert "close_issue" not in harness.names()


def test_already_closed_pr_that_merged_counts_as_merged(harness, runs_log):
    harness.ship_result = (0, {"outcome": "already_closed", "rounds": 0})
    assert harness.run(prompt="x") == 0
    assert run_log(runs_log)[-1]["outcome"] == "merged"


def test_already_closed_pr_that_was_closed_is_pr_closed(harness, runs_log):
    harness.ship_result = (0, {"outcome": "already_closed", "rounds": 0})
    harness.pr_state = "CLOSED"
    assert harness.run(issue=7) == 1
    assert run_log(runs_log)[-1]["outcome"] == "pr_closed"
    assert "comment_on_issue" in harness.names()


def test_handed_over_comments_and_exits_0(harness):
    harness.ship_result = (0, {"outcome": "handed_over", "rounds": 1})
    assert harness.run(issue=7) == 0
    comments = [w for w in harness.writes if w[0] == "comment_on_issue"]
    assert len(comments) == 1
    assert "human merge" in comments[0][2]
    assert PR_URL in comments[0][2]


def test_escalated_comments_and_exits_1(harness, runs_log):
    harness.ship_result = (
        1, {"outcome": "escalated", "escalation_reason": "round limit reached", "rounds": 3}
    )
    assert harness.run(issue=7) == 1
    comment = [w for w in harness.writes if w[0] == "comment_on_issue"][0][2]
    assert "round limit reached" in comment
    assert PR_URL in comment
    assert run_log(runs_log)[-1]["rounds"] == 3


def test_lifecycle_failure_skips_ship(harness, runs_log):
    harness.lifecycle_result = (1, {"error": "Planning failed"})
    assert harness.run(issue=7) == 1
    assert harness.ship_calls == []
    comment = [w for w in harness.writes if w[0] == "comment_on_issue"][0][2]
    assert "Planning failed" in comment
    entry = run_log(runs_log)[-1]
    assert entry["outcome"] == "build_failed"
    assert entry["rounds"] is None


def test_lifecycle_with_failing_tests_still_ships(harness):
    harness.lifecycle_result = (1, {"pr_url": PR_URL, "tests_passed": False})
    assert harness.run(prompt="x") == 0
    assert len(harness.ship_calls) == 1


@pytest.mark.parametrize(
    "setup",
    [
        lambda h: None,
        lambda h: setattr(h, "ship_result", (0, {"outcome": "handed_over", "rounds": 0})),
        lambda h: setattr(h, "ship_result", (1, {"outcome": "escalated", "rounds": 3})),
        lambda h: setattr(h, "lifecycle_result", (1, {"error": "boom"})),
        lambda h: setattr(h, "lifecycle_error", GitHubError("gh down")),
    ],
    ids=["merged", "handed_over", "escalated", "lifecycle_failure", "lifecycle_raises"],
)
def test_in_progress_label_removed_in_every_case(harness, setup):
    setup(harness)
    harness.run(issue=7)
    added = harness.writes.index(("add_issue_label", 7, "adw-in-progress"))
    removed = harness.writes.index(("remove_label", 7, "adw-in-progress"))
    assert added < removed


def test_label_failures_are_best_effort(harness):
    harness.fail_labels = True
    assert harness.run(issue=7) == 0
    assert "remove_label" in harness.names()


def test_dirty_tree_stops_before_github(harness, runs_log):
    harness.clean = False
    assert harness.run(prompt="x") == 1
    assert "repo_owner" not in harness.calls
    assert harness.writes == []
    assert harness.lifecycle_calls == []
    assert run_log(runs_log)[-1]["outcome"] == "error"


def test_failed_ship_profile_health_check_stops_before_a_pr(harness, runs_log):
    harness.health = [Check("server", False, "down")]
    assert harness.run(prompt="x", ship_profile="claude-opus") == 1
    assert harness.lifecycle_calls == []
    assert run_log(runs_log)[-1]["outcome"] == "error"


def test_ship_profile_shared_with_build_isnt_checked_again(harness):
    harness.health = [Check("server", False, "down")]  # The lifecycle checks it instead
    assert harness.run(prompt="x") == 0
    assert len(harness.lifecycle_calls) == 1


def test_returns_to_main_when_clean(harness):
    harness.branch = "adw/x"
    harness.run(prompt="x")
    assert harness.returned_to_main is True


def test_type_label_reaches_lifecycle(harness, runs_log):
    harness.issues = [issue(labels=("adw-ready", "bug"))]
    harness.run(issue=7)
    assert harness.lifecycle_calls[0][0].adw_type == "bug"
    assert run_log(runs_log)[-1]["type"] == "bug"
