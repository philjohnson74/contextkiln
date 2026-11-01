"""Shared test setup. Keeps tests away from real agents and the real run log."""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "adw_modules")
)

import agent


@pytest.fixture(autouse=True)
def no_real_agents(monkeypatch):
    """Point at a missing CLI, so a test that forgets to fake an agent can't start one."""
    monkeypatch.setattr(agent, "CLAUDE_PATH", "/nonexistent/claude-blocked-in-tests")


@pytest.fixture(autouse=True)
def runs_log(monkeypatch, tmp_path):
    path = tmp_path / "agents" / "runs.jsonl"
    monkeypatch.setattr(agent, "RUNS_LOG", str(path))
    return path
