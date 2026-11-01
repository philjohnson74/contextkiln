"""Tests for the composed ADWs' command lines. The workflow itself is faked."""

import importlib.util
import os

import pytest
from click.testing import CliRunner

import lifecycle

ADWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def invoke(kind, monkeypatch, *args):
    """Run a composed ADW's CLI and return its exit code and workflow options."""
    captured = []

    def fake_run_workflow(options):
        captured.append(options)
        return 0

    monkeypatch.delenv("ADW_PROFILE", raising=False)
    monkeypatch.setattr(lifecycle, "run_workflow", fake_run_workflow)

    path = os.path.join(ADWS_DIR, f"adw_{kind}_implement.py")
    spec = importlib.util.spec_from_file_location(f"adw_{kind}_implement", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = CliRunner().invoke(module.main, list(args))
    return result.exit_code, captured[0] if captured else None


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_each_step_uses_its_own_profile(kind, monkeypatch):
    code, options = invoke(
        kind,
        monkeypatch,
        "do a thing",
        "--plan-profile",
        "claude-opus",
        "--build-profile",
        "local",
    )
    assert code == 0
    assert options.adw_type == kind
    assert (options.plan_profile, options.build_profile) == ("claude-opus", "local")


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_steps_fall_back_to_profile(kind, monkeypatch):
    _, options = invoke(kind, monkeypatch, "do a thing", "--profile", "local")
    assert (options.plan_profile, options.build_profile) == ("local", "local")


@pytest.mark.parametrize("kind", ["chore", "feature"])
def test_one_step_override_leaves_the_other_on_profile(kind, monkeypatch):
    _, options = invoke(
        kind, monkeypatch, "do a thing", "--profile", "local", "--plan-profile", "claude"
    )
    assert (options.plan_profile, options.build_profile) == ("claude", "local")


def test_issue_and_no_pr_options(monkeypatch):
    _, options = invoke("chore", monkeypatch, "--issue", "7", "--no-pr")
    assert options.issue == 7
    assert options.prompt is None
    assert options.no_pr is True


@pytest.mark.parametrize("args", [[], ["do a thing", "--issue", "7"]])
def test_needs_exactly_one_of_prompt_and_issue(monkeypatch, args):
    code, options = invoke("chore", monkeypatch, *args)
    assert code == 2
    assert options is None
