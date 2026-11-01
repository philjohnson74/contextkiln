"""Tests for the gh wrapper. The gh subprocess is faked, so nothing reaches GitHub."""

import json
import subprocess

import pytest

import github
from github import GitHubError


@pytest.fixture
def fake_gh(monkeypatch):
    """Record gh calls and answer each with the configured stdout."""

    class Fake:
        calls = []
        stdout = ""
        returncode = 0

    Fake.calls = []

    def fake_run(cmd, input=None, **kwargs):
        Fake.calls.append({"cmd": cmd, "input": input})
        return subprocess.CompletedProcess(
            cmd, Fake.returncode, stdout=Fake.stdout, stderr="gh said no"
        )

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
