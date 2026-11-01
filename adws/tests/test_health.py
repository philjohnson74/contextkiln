"""Tests for health checks. The Ollama API is faked, so no server is needed."""

import urllib.error

import pytest

import health

MODEL = "qwen3-coder:30b"


class FakeOllama:
    """Answers the Ollama API paths that the health checks call."""

    def __init__(self, pulled=(MODEL), capabilities=("tools",), context=65536):
        self.pulled = [pulled] if isinstance(pulled, str) else list(pulled)
        self.capabilities = list(capabilities)
        self.context = context
        self.loaded = False
        self.paths = []

    def __call__(self, base_url, path, body=None, timeout=None):
        self.paths.append(path)
        if path == "/api/version":
            return {"version": "0.40.6"}
        if path == "/api/tags":
            return {"models": [{"name": name} for name in self.pulled]}
        if path == "/api/show":
            return {"capabilities": self.capabilities}
        if path == "/api/generate":
            self.loaded = True
            return {}
        if path == "/api/ps":
            if not self.loaded:
                return {"models": []}
            return {"models": [{"name": MODEL, "context_length": self.context}]}
        raise AssertionError(f"Unexpected path: {path}")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("LOCAL_MODEL", "LOCAL_BASE_URL", "LOCAL_CONTEXT_LENGTH"):
        monkeypatch.delenv(name, raising=False)


def by_name(checks):
    return {check.name: check for check in checks}


def test_all_local_checks_pass_and_model_is_loaded(monkeypatch):
    fake = FakeOllama()
    monkeypatch.setattr(health, "_ollama", fake)
    checks = health.check_local_server("local")
    assert all(check.ok for check in checks)
    assert "/api/generate" in fake.paths
    assert set(by_name(checks)) == {"server", "model", "tool calling", "context length"}


def test_already_loaded_model_is_not_reloaded(monkeypatch):
    fake = FakeOllama()
    fake.loaded = True
    monkeypatch.setattr(health, "_ollama", fake)
    assert all(check.ok for check in health.check_local_server("local"))
    assert "/api/generate" not in fake.paths


def test_unreachable_server_fails(monkeypatch):
    def refuse(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(health, "_ollama", refuse)
    checks = health.check_local_server("local")
    assert [check.name for check in checks] == ["server"]
    assert not checks[0].ok


def test_missing_model_fails_with_the_pull_command(monkeypatch):
    monkeypatch.setattr(health, "_ollama", FakeOllama(pulled=["other:1b"]))
    check = by_name(health.check_local_server("local"))["model"]
    assert not check.ok
    assert f"ollama pull {MODEL}" in check.detail


def test_model_without_tools_fails(monkeypatch):
    monkeypatch.setattr(health, "_ollama", FakeOllama(capabilities=["completion"]))
    assert not by_name(health.check_local_server("local"))["tool calling"].ok


@pytest.mark.parametrize("context", [4096, 32768, None])
def test_context_too_small_for_the_profile_fails(monkeypatch, context):
    monkeypatch.setattr(health, "_ollama", FakeOllama(context=context))
    assert not by_name(health.check_local_server("local"))["context length"].ok


def test_larger_server_context_passes(monkeypatch):
    monkeypatch.setattr(health, "_ollama", FakeOllama(context=98304))
    assert by_name(health.check_local_server("local"))["context length"].ok


def test_claude_profile_skips_the_local_server(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("claude profile must not call Ollama")

    monkeypatch.setattr(health, "_ollama", fail)
    monkeypatch.setattr(health, "check_claude_installed", lambda: None)
    checks = health.run_health_checks("claude")
    assert [check.name for check in checks] == ["claude", "uv"]
