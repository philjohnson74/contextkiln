"""Shared test setup. Keeps tests from writing to the real run log."""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "adw_modules")
)

import agent


@pytest.fixture(autouse=True)
def runs_log(monkeypatch, tmp_path):
    path = tmp_path / "agents" / "runs.jsonl"
    monkeypatch.setattr(agent, "RUNS_LOG", str(path))
    return path
