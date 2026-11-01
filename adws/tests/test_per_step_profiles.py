"""Tests for per-step profiles in the composed ADWs. Agents are faked."""

import importlib.util
import json
import os

import pytest
from click.testing import CliRunner

import agent

ADWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_adw(kind):
    path = os.path.join(ADWS_DIR, f"adw_{kind}_implement.py")
    spec = importlib.util.spec_from_file_location(f"adw_{kind}_implement", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_adw(kind, monkeypatch, tmp_path, *options):
    """Run a composed ADW and return its requests and workflow summary."""
    requests = []

    def fake_execute_template(request):
        requests.append(request)
        os.makedirs(f"./agents/{request.adw_id}/{request.agent_name}", exist_ok=True)
        return agent.AgentPromptResponse(
            output=f"specs/{kind}-{request.adw_id}-test.md", success=True
        )

    module = load_adw(kind)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADW_PROFILE", raising=False)
    monkeypatch.delenv("LOCAL_MODEL", raising=False)
    monkeypatch.setattr(module, "execute_template", fake_execute_template)

    result = CliRunner().invoke(module.main, ["do a thing", *options])
    assert result.exit_code == 0, result.output

    summary_path = f"./agents/{requests[0].adw_id}/workflow_summary.json"
    with open(summary_path) as f:
        return requests, json.load(f)


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_each_step_uses_its_own_profile(kind, monkeypatch, tmp_path):
    requests, summary = run_adw(
        kind,
        monkeypatch,
        tmp_path,
        "--plan-profile",
        "claude-opus",
        "--build-profile",
        "local",
    )
    assert [r.profile for r in requests] == ["claude-opus", "local"]
    assert summary["plan_profile"] == "claude-opus"
    assert summary["plan_model"] == "opus"
    assert summary["build_profile"] == "local"
    assert summary["build_model"] == "qwen3-coder:30b"


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_steps_fall_back_to_profile(kind, monkeypatch, tmp_path):
    requests, _ = run_adw(kind, monkeypatch, tmp_path, "--profile", "local")
    assert [r.profile for r in requests] == ["local", "local"]


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_one_step_override_leaves_the_other_on_profile(kind, monkeypatch, tmp_path):
    requests, _ = run_adw(
        kind, monkeypatch, tmp_path, "--profile", "local", "--plan-profile", "claude"
    )
    assert [r.profile for r in requests] == ["claude", "local"]
