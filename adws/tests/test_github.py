"""Tests for the gh wrapper. The gh subprocess is faked, so nothing reaches GitHub."""

import json
import subprocess

import pytest

import github
from github import GitHubError


@pytest.fixture
def fake_gh(monkeypatch):
    """Record gh calls and answer each with the configured stdout.

    `outputs` and `returncodes`, when set, are consumed one per call, falling back
    to `stdout` and `returncode` once they run out.
    """

    class Fake:
        calls = []
        stdout = ""
        returncode = 0
        outputs = []
        returncodes = []

    Fake.calls = []
    Fake.outputs = []
    Fake.returncodes = []

    def fake_run(cmd, input=None, **kwargs):
        Fake.calls.append({"cmd": cmd, "input": input})
        stdout = Fake.outputs.pop(0) if Fake.outputs else Fake.stdout
        code = Fake.returncodes.pop(0) if Fake.returncodes else Fake.returncode
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="gh said no")

    monkeypatch.setattr(github.subprocess, "run", fake_run)
    return Fake


def test_get_issue(fake_gh):
    fake_gh.stdout = json.dumps(
        {"title": "A bug", "body": "Details", "author": {"login": "someone"}}
    )
    issue = github.get_issue(7)
    assert issue == github.Issue(7, "A bug", "Details", "someone")
    assert fake_gh.calls[0]["cmd"][:4] == ["gh", "issue", "view", "7"]


def test_get_issue_with_empty_body(fake_gh):
    fake_gh.stdout = json.dumps(
        {"title": "A bug", "body": None, "author": {"login": "someone"}}
    )
    assert github.get_issue(7).body == ""


def test_comment_sends_the_body_on_stdin(fake_gh):
    github.comment_on_issue(7, "--not-a-flag")
    call = fake_gh.calls[0]
    assert call["cmd"] == ["gh", "issue", "comment", "7", "--body-file", "-"]
    assert call["input"] == "--not-a-flag"


def test_create_pr_targets_main_and_returns_the_url(fake_gh):
    fake_gh.stdout = "Creating pull request\nhttps://github.com/o/r/pull/9\n"
    url = github.create_pr("chore: x", "Body", "adw/chore-1-x")
    assert url == "https://github.com/o/r/pull/9"
    cmd = fake_gh.calls[0]["cmd"]
    assert cmd[cmd.index("--base") + 1] == "main"
    assert cmd[cmd.index("--head") + 1] == "adw/chore-1-x"
    assert "--draft" not in cmd
    assert fake_gh.calls[0]["input"] == "Body"


def test_create_draft_pr(fake_gh):
    fake_gh.stdout = "https://github.com/o/r/pull/9"
    github.create_pr("chore: x", "Body", "adw/chore-1-x", draft=True)
    assert "--draft" in fake_gh.calls[0]["cmd"]


def test_create_pr_from_main_is_refused(fake_gh):
    with pytest.raises(GitHubError, match="Refusing"):
        github.create_pr("chore: x", "Body", "main")
    assert fake_gh.calls == []


def test_gh_failure_raises_with_its_error(fake_gh):
    fake_gh.returncode = 1
    with pytest.raises(GitHubError, match="gh said no"):
        github.get_issue(7)


def test_missing_gh_raises(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(github.subprocess, "run", missing)
    with pytest.raises(GitHubError, match="isn't installed"):
        github.get_issue(7)


PR_JSON = {
    "number": 7,
    "state": "OPEN",
    "isDraft": False,
    "headRefName": "adw/feature-1-x",
    "headRefOid": "abc123",
    "author": {"login": "owner"},
    "labels": [{"name": "auto-merge"}, {"name": "other"}],
    "files": [{"path": "a.py"}, {"path": ".github/workflows/ci.yml"}],
    "statusCheckRollup": [
        {"__typename": "CheckRun", "name": "ci", "status": "COMPLETED", "conclusion": "FAILURE"},
        {"__typename": "CheckRun", "name": "claude-review", "status": "IN_PROGRESS", "conclusion": ""},
        {"__typename": "CheckRun", "name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"},
        {"__typename": "StatusContext", "context": "legacy", "state": "SUCCESS"},
        {"__typename": "StatusContext", "context": "waiting", "state": "PENDING"},
    ],
    "body": None,
}


def test_get_pr_parses_labels_files_and_checks(fake_gh):
    fake_gh.stdout = json.dumps(PR_JSON)
    pr = github.get_pr(7)
    assert fake_gh.calls[0]["cmd"] == ["gh", "pr", "view", "7", "--json", github.PR_FIELDS]
    assert pr.number == 7
    assert pr.state == "OPEN"
    assert pr.is_draft is False
    assert pr.head_branch == "adw/feature-1-x"
    assert pr.head_sha == "abc123"
    assert pr.author == "owner"
    assert pr.labels == ("auto-merge", "other")
    assert pr.files == ("a.py", ".github/workflows/ci.yml")
    assert pr.checks == {
        "ci": ("COMPLETED", "SUCCESS"),
        "claude-review": ("IN_PROGRESS", None),
        "legacy": ("COMPLETED", "SUCCESS"),
        "waiting": ("IN_PROGRESS", None),
    }
    assert pr.body == ""


def test_merge_pr_matches_the_head_commit(fake_gh):
    github.merge_pr(7, "abc123")
    assert fake_gh.calls[0]["cmd"] == [
        "gh", "pr", "merge", "7", "--squash", "--delete-branch",
        "--match-head-commit", "abc123",
    ]


@pytest.mark.parametrize("sha", ["", "   "])
def test_merge_pr_without_a_sha_is_refused(fake_gh, sha):
    with pytest.raises(GitHubError, match="Refusing"):
        github.merge_pr(7, sha)
    assert fake_gh.calls == []


def test_list_review_comments_flattens_pages(fake_gh):
    fake_gh.stdout = json.dumps([[{"id": 1}], [{"id": 2}]])
    assert github.list_review_comments(7) == [{"id": 1}, {"id": 2}]
    assert fake_gh.calls[0]["cmd"] == [
        "gh", "api", "repos/{owner}/{repo}/pulls/7/comments", "--paginate", "--slurp",
    ]


def test_list_issue_comments_with_no_output(fake_gh):
    assert github.list_issue_comments(7) == []
    assert fake_gh.calls[0]["cmd"][2] == "repos/{owner}/{repo}/issues/7/comments"


def test_failed_ci_log_with_no_run(fake_gh):
    fake_gh.stdout = "[]"
    assert github.failed_ci_log("abc123") == "No CI run found for abc123"
    cmd = fake_gh.calls[0]["cmd"]
    assert cmd[:5] == ["gh", "run", "list", "--workflow", "ci.yml"]
    assert cmd[cmd.index("--commit") + 1] == "abc123"
    assert len(fake_gh.calls) == 1


def test_failed_ci_log_views_the_run(fake_gh):
    fake_gh.outputs = [json.dumps([{"databaseId": 42}]), "boom log"]
    assert github.failed_ci_log("abc123") == "boom log"
    assert fake_gh.calls[1]["cmd"] == ["gh", "run", "view", "42", "--log-failed"]


def test_failed_ci_log_without_a_sha_is_refused(fake_gh):
    with pytest.raises(GitHubError):
        github.failed_ci_log("")
    assert fake_gh.calls == []


def test_add_label_still_adds_when_create_fails(fake_gh):
    fake_gh.returncodes = [1, 0]
    github.add_label(7, "needs-human")
    assert fake_gh.calls[0]["cmd"] == ["gh", "label", "create", "needs-human", "--force"]
    assert fake_gh.calls[1]["cmd"] == ["gh", "pr", "edit", "7", "--add-label", "needs-human"]


def test_reply_to_review_comment(fake_gh):
    github.reply_to_review_comment(7, 123, "Fixed in abc: done")
    assert fake_gh.calls[0]["cmd"] == [
        "gh", "api", "--method", "POST",
        "repos/{owner}/{repo}/pulls/7/comments/123/replies",
        "-f", "body=Fixed in abc: done",
    ]


def test_comment_on_pr_sends_the_body_on_stdin(fake_gh):
    github.comment_on_pr(7, "--hi")
    assert fake_gh.calls[0]["cmd"] == ["gh", "pr", "comment", "7", "--body-file", "-"]
    assert fake_gh.calls[0]["input"] == "--hi"


def test_repo_owner(fake_gh):
    fake_gh.stdout = "owner\n"
    assert github.repo_owner() == "owner"
