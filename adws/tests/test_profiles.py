"""Tests for model profiles. The claude subprocess is faked, so no model is needed."""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "adw_modules")
)

import agent
from models import PROFILE_NAMES, get_profile


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("LOCAL_MODEL", "LOCAL_BASE_URL", "LOCAL_CONTEXT_LENGTH"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "name,model", [("claude", "sonnet"), ("claude-opus", "opus")]
)
def test_claude_profiles_set_no_routing_env(name, model):
    profile = get_profile(name)
    assert profile.model == model
    assert profile.env == {}


def test_local_profile_defaults():
    profile = get_profile("local")
    assert profile.model == "qwen3-coder:30b"
    assert profile.env["ANTHROPIC_BASE_URL"] == "http://localhost:11434"
    assert profile.env["ANTHROPIC_AUTH_TOKEN"] == "ollama"
    assert profile.env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "65536"


def test_local_profile_reads_env(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL", "gpt-oss:20b")
    monkeypatch.setenv("LOCAL_CONTEXT_LENGTH", "98304")
    profile = get_profile("local")
    assert profile.model == "gpt-oss:20b"
    assert profile.env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "98304"


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="Unknown profile"):
        get_profile("nope")


def test_every_listed_profile_resolves():
    for name in PROFILE_NAMES:
        assert get_profile(name).name == name


def test_local_env_blanks_the_real_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-key")
    env = agent.get_safe_subprocess_env("local")
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:11434"


def test_claude_env_ignores_routing_vars_from_the_shell(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ollama")
    monkeypatch.setenv("CLAUDE_CODE_MAX_CONTEXT_TOKENS", "65536")
    env = agent.get_safe_subprocess_env("claude")
    assert env["ANTHROPIC_API_KEY"] == "placeholder-key"
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "CLAUDE_CODE_MAX_CONTEXT_TOKENS" not in env


def test_prompt_passes_profile_model_and_env_to_claude(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, stdout, env, **kwargs):
        calls["cmd"] = cmd
        calls["env"] = env
        result = {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "done",
            "session_id": "s1",
        }
        stdout.write(json.dumps(result) + "\n")
        return subprocess.CompletedProcess(cmd, 0, stderr="")

    monkeypatch.setattr(agent, "check_claude_installed", lambda: None)
    monkeypatch.setattr(agent, "save_prompt", lambda *args: None)
    monkeypatch.setattr(agent.subprocess, "run", fake_run)

    response = agent.prompt_claude_code(
        agent.AgentPromptRequest(
            prompt="hello",
            adw_id="abc12345",
            profile="local",
            output_file=str(tmp_path / "out.jsonl"),
        )
    )

    assert response.success
    assert calls["cmd"][calls["cmd"].index("--model") + 1] == "qwen3-coder:30b"
    assert calls["env"]["ANTHROPIC_BASE_URL"] == "http://localhost:11434"
