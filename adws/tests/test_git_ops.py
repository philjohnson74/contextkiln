"""Tests for git_ops, using real git repos with a local bare remote."""

import subprocess

import pytest

import git_ops
from git_ops import GitError

BRANCH = "adw/chore-abc12345-test"


def git(cwd, *args):
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def remote_branches(remote):
    return git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads")


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    path.mkdir()
    git(path, "init", "--bare", "-q", "-b", "main")
    return path


@pytest.fixture
def repo(tmp_path, remote):
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    (path / ".gitignore").write_text("ignored.txt\n")
    (path / "README.md").write_text("hello\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "initial")
    git(path, "remote", "add", "origin", str(remote))
    git(path, "push", "-q", "-u", "origin", "main")
    return path


def test_commit_on_main_is_refused(repo):
    (repo / "new.txt").write_text("x\n")
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(GitError, match="Refusing"):
        git_ops.commit_all("chore: x", "abc12345", "main", cwd=repo)
    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "diff", "--cached", "--name-only") == ""


def test_commit_refused_if_agent_switched_back_to_main(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    git(repo, "checkout", "-q", "main")
    (repo / "new.txt").write_text("x\n")
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(GitError, match="Refusing"):
        git_ops.commit_all("chore: x", "abc12345", BRANCH, cwd=repo)
    assert git(repo, "rev-parse", "HEAD") == before


def test_commit_refused_on_an_unexpected_branch(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    git(repo, "checkout", "-q", "-b", "other")
    (repo / "new.txt").write_text("x\n")
    with pytest.raises(GitError, match="Expected to be on"):
        git_ops.commit_all("chore: x", "abc12345", BRANCH, cwd=repo)


def test_commit_refused_on_detached_head(repo):
    git(repo, "checkout", "-q", "--detach")
    (repo / "new.txt").write_text("x\n")
    with pytest.raises(GitError, match="detached"):
        git_ops.commit_all("chore: x", "abc12345", BRANCH, cwd=repo)


def test_push_on_main_is_refused(repo, remote):
    before = git(remote, "rev-parse", "main")
    with pytest.raises(GitError, match="Refusing"):
        git_ops.push_branch("main", cwd=repo)
    assert git(remote, "rev-parse", "main") == before


def test_push_refused_if_agent_switched_back_to_main(repo, remote):
    git_ops.create_branch(BRANCH, cwd=repo)
    git(repo, "checkout", "-q", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "sneaky")
    before = git(remote, "rev-parse", "main")
    with pytest.raises(GitError, match="Refusing"):
        git_ops.push_branch(BRANCH, cwd=repo)
    assert git(remote, "rev-parse", "main") == before


def test_commit_stages_changes_skips_ignored_and_adds_trailer(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    (repo / "new.txt").write_text("x\n")
    (repo / "ignored.txt").write_text("secret\n")
    sha = git_ops.commit_all("chore: add new file", "abc12345", BRANCH, cwd=repo)
    assert sha == git(repo, "rev-parse", "HEAD")
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == "new.txt"
    message = git(repo, "log", "-1", "--format=%B")
    assert message.startswith("chore: add new file")
    assert "ADW-Id: abc12345" in message


def test_nothing_to_commit_fails(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    with pytest.raises(GitError, match="Nothing to commit"):
        git_ops.commit_all("chore: x", "abc12345", BRANCH, cwd=repo)


def test_empty_message_fails(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    (repo / "new.txt").write_text("x\n")
    with pytest.raises(GitError, match="empty message"):
        git_ops.commit_all("  \n", "abc12345", BRANCH, cwd=repo)


def test_push_sends_only_the_work_branch(repo, remote):
    before = git(remote, "rev-parse", "main")
    git_ops.create_branch(BRANCH, cwd=repo)
    (repo / "new.txt").write_text("x\n")
    sha = git_ops.commit_all("chore: x", "abc12345", BRANCH, cwd=repo)
    git_ops.push_branch(BRANCH, cwd=repo)
    assert git(remote, "rev-parse", BRANCH) == sha
    assert git(remote, "rev-parse", "main") == before
    assert git(repo, "rev-parse", "--abbrev-ref", "@{upstream}") == f"origin/{BRANCH}"


def test_sync_main_refuses_a_dirty_tree(repo):
    (repo / "README.md").write_text("changed\n")
    with pytest.raises(GitError, match="isn't clean"):
        git_ops.sync_main(cwd=repo)


def test_ignored_files_dont_make_the_tree_dirty(repo):
    (repo / "ignored.txt").write_text("x\n")
    assert git_ops.is_clean(cwd=repo)


def test_sync_main_pulls_latest_from_a_work_branch(repo, remote, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "config", "user.name", "Test")
    git(other, "config", "user.email", "test@example.com")
    git(other, "commit", "-q", "--allow-empty", "-m", "newer")
    git(other, "push", "-q", "origin", "main")

    git_ops.create_branch(BRANCH, cwd=repo)
    git_ops.sync_main(cwd=repo)

    assert git_ops.current_branch(cwd=repo) == "main"
    assert git(repo, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")


def test_sync_main_fails_if_main_has_diverged(repo, remote, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    git(other, "config", "user.name", "Test")
    git(other, "config", "user.email", "test@example.com")
    git(other, "commit", "-q", "--allow-empty", "-m", "theirs")
    git(other, "push", "-q", "origin", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "ours")

    with pytest.raises(GitError):
        git_ops.sync_main(cwd=repo)


def test_create_branch_refuses_main(repo):
    with pytest.raises(GitError, match="Refusing"):
        git_ops.create_branch("main", cwd=repo)


def test_return_to_main(repo):
    git_ops.create_branch(BRANCH, cwd=repo)
    git_ops.return_to_main(cwd=repo)
    assert git_ops.current_branch(cwd=repo) == "main"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Add a /health endpoint!", "add-a-health-endpoint"),
        ("../../etc --force", "etc-force"),
        ("!!!", "task"),
        ("x" * 100, "x" * 40),
    ],
)
def test_slugify(text, expected):
    assert git_ops.slugify(text) == expected


def test_branch_name():
    name = git_ops.branch_name("chore", "a1b2c3d4", "Health endpoint")
    assert name == "adw/chore-a1b2c3d4-health-endpoint"
