"""Health checks for the tools and local model server that ADWs depend on."""

import json
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent import check_claude_installed
from models import get_profile

# Claude Code's system prompt and tools alone take ~20k tokens
MIN_CONTEXT_LENGTH = 32768

# Loading a large model from a cold disk can take a while
LOAD_TIMEOUT_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Check:
    """The outcome of one health check."""

    name: str
    ok: bool
    detail: str


def _ollama(
    base_url: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Call an Ollama API path. GET without a body, POST with one."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{base_url}{path}", data=data)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _loaded_context_length(base_url: str, model: str) -> Optional[int]:
    """Return the context length of a model if it's loaded on the server."""
    for loaded in _ollama(base_url, "/api/ps").get("models", []):
        if loaded.get("name") == model:
            return loaded.get("context_length")
    return None


def check_tools() -> List[Check]:
    """Check that the claude and uv command line tools are available."""
    claude_error = check_claude_installed()
    uv_path = shutil.which("uv")
    return [
        Check("claude", claude_error is None, claude_error or "installed"),
        Check("uv", uv_path is not None, uv_path or "not found on PATH"),
    ]


def check_local_server(profile_name: str) -> List[Check]:
    """Check the server, model and context length for a locally routed profile.

    The context length is only reported for a loaded model, so this loads the
    model if it isn't loaded already.
    """
    profile = get_profile(profile_name)
    base_url = profile.env["ANTHROPIC_BASE_URL"]
    expected = int(profile.env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"])
    model = profile.model

    try:
        version = _ollama(base_url, "/api/version").get("version", "unknown")
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [Check("server", False, f"not reachable at {base_url}: {e}")]
    checks = [Check("server", True, f"Ollama {version} at {base_url}")]

    try:
        pulled = [m.get("name") for m in _ollama(base_url, "/api/tags").get("models", [])]
        if model not in pulled:
            checks.append(
                Check("model", False, f"{model} not pulled. Run: ollama pull {model}")
            )
            return checks
        checks.append(Check("model", True, f"{model} is pulled"))

        capabilities = _ollama(base_url, "/api/show", {"model": model}).get(
            "capabilities", []
        )
        has_tools = "tools" in capabilities
        checks.append(
            Check(
                "tool calling",
                has_tools,
                "supported" if has_tools else f"{model} doesn't support tools",
            )
        )

        context = _loaded_context_length(base_url, model)
        if context is None:
            _ollama(
                base_url,
                "/api/generate",
                {"model": model, "stream": False},
                timeout=LOAD_TIMEOUT_SECONDS,
            )
            context = _loaded_context_length(base_url, model)
    except (urllib.error.URLError, OSError, ValueError) as e:
        checks.append(Check("model", False, f"Ollama request failed: {e}"))
        return checks

    if context is None:
        detail = "server didn't report one. Is OLLAMA_CONTEXT_LENGTH set?"
        checks.append(Check("context length", False, detail))
    elif context < MIN_CONTEXT_LENGTH:
        detail = f"{context} is below the minimum of {MIN_CONTEXT_LENGTH}"
        checks.append(Check("context length", False, detail))
    elif context < expected:
        detail = (
            f"server has {context}, but LOCAL_CONTEXT_LENGTH is {expected}. "
            "Claude Code would overrun the server's context"
        )
        checks.append(Check("context length", False, detail))
    else:
        checks.append(Check("context length", True, f"{context} tokens"))
    return checks


def run_health_checks(profile_name: str) -> List[Check]:
    """Run every check that applies to a profile."""
    checks = check_tools()
    if "ANTHROPIC_BASE_URL" in get_profile(profile_name).env:
        checks.extend(check_local_server(profile_name))
    return checks
