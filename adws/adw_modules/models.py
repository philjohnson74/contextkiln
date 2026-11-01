"""Named model profiles: which model an agent runs on and the env it needs."""

import os
from dataclasses import dataclass, field
from typing import Dict, Final, Tuple

DEFAULT_PROFILE: Final[str] = "claude"
PROFILE_NAMES: Final[Tuple[str, ...]] = ("claude", "claude-opus", "local")

DEFAULT_LOCAL_MODEL: Final[str] = "qwen3-coder:30b"
DEFAULT_LOCAL_BASE_URL: Final[str] = "http://localhost:11434"
# Must match OLLAMA_CONTEXT_LENGTH on the server. See ai_docs/local_models.md.
DEFAULT_LOCAL_CONTEXT_LENGTH: Final[str] = "65536"


@dataclass(frozen=True)
class Profile:
    """A model name plus the env vars that route Claude Code to it."""

    name: str
    model: str
    env: Dict[str, str] = field(default_factory=dict)


def get_profile(name: str) -> Profile:
    """Return the named profile. Local settings are read from the env on each call.

    Raises:
        ValueError: If the profile name is unknown
    """
    if name == "claude":
        return Profile(name=name, model="sonnet")
    if name == "claude-opus":
        return Profile(name=name, model="opus")
    if name == "local":
        return Profile(
            name=name,
            model=os.getenv("LOCAL_MODEL", DEFAULT_LOCAL_MODEL),
            env={
                "ANTHROPIC_BASE_URL": os.getenv(
                    "LOCAL_BASE_URL", DEFAULT_LOCAL_BASE_URL
                ),
                "ANTHROPIC_AUTH_TOKEN": "ollama",
                "ANTHROPIC_API_KEY": "",
                "CLAUDE_CODE_MAX_CONTEXT_TOKENS": os.getenv(
                    "LOCAL_CONTEXT_LENGTH", DEFAULT_LOCAL_CONTEXT_LENGTH
                ),
            },
        )
    raise ValueError(
        f"Unknown profile '{name}'. Expected one of: {', '.join(PROFILE_NAMES)}"
    )
