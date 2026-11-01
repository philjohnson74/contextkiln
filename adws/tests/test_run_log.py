"""Tests for the run log and agent timeout. The claude subprocess is faked."""

import json
import subprocess

import pytest

import agent


def request_for(tmp_path, profile="claude"):
    return agent.AgentPromptRequest(
        prompt="hello",
        adw_id="abc12345",
        agent_name="builder",
        profile=profile,
        output_file=str(tmp_path / "out.jsonl"),
    )


def read_log(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture(autouse=True)
def fake_claude_setup(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    monkeypatch.delenv("ADW_AGENT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(agent, "check_claude_installed", lambda: None)
    monkeypatch.setattr(agent, "save_prompt", lambda *args: None)


def test_success_is_logged_from_the_result_message(monkeypatch, tmp_path, runs_log):
    def fake_run(cmd, stdout, **kwargs):
        result = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "done",
            "session_id": "s1",
            "duration_ms": 1234,
            "num_turns": 5,
        }
        stdout.write(json.dumps(result) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stderr="")

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    agent.prompt_claude_code(request_for(tmp_path, profile="local"))

    assert read_log(runs_log) == [
        {
            "adw_id": "abc12345",
            "step": "builder",
            "profile": "local",
            "model": "qwen3-coder:30b",
            "duration_ms": 1234,
            "num_turns": 5,
            "success": True,
        }
    ]


def test_failure_without_a_result_message_is_still_logged(
    monkeypatch, tmp_path, runs_log
):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr="boom")

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    agent.prompt_claude_code(request_for(tmp_path))

    entry = read_log(runs_log)[0]
    assert entry["success"] is False
    assert entry["num_turns"] is None
    assert isinstance(entry["duration_ms"], int)


def test_each_retry_gets_its_own_line(monkeypatch, tmp_path, runs_log):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr="boom")

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)
    agent.prompt_claude_code_with_retry(request_for(tmp_path), max_retries=2)

    assert len(read_log(runs_log)) == 3


def test_log_write_failure_does_not_fail_the_run(monkeypatch, tmp_path):
    def fake_run(cmd, stdout, **kwargs):
        result = {"type": "result", "is_error": False, "result": "done"}
        stdout.write(json.dumps(result) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stderr="")

    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    monkeypatch.setattr(agent, "RUNS_LOG", str(blocker / "runs.jsonl"))
    monkeypatch.setattr(agent.subprocess, "run", fake_run)

    assert agent.prompt_claude_code(request_for(tmp_path)).success


def test_timeout_is_applied_logged_and_not_retried(monkeypatch, tmp_path, runs_log):
    timeouts = []

    def fake_run(cmd, timeout, **kwargs):
        timeouts.append(timeout)
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setenv("ADW_AGENT_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    monkeypatch.setattr(agent.time, "sleep", lambda seconds: None)

    response = agent.prompt_claude_code_with_retry(request_for(tmp_path))

    assert timeouts == [7]
    assert response.retry_code == agent.RetryCode.TIMEOUT_ERROR
    assert "7 seconds" in response.output
    assert read_log(runs_log)[0]["success"] is False
