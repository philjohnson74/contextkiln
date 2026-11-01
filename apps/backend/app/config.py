"""Settings, read from CK_* environment variables and the repo's .env file."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "openai_compatible"
    llm_model: str = "qwen3:4b"
    llm_base_url: str = "http://localhost:11434/v1"
    db_path: Path = BACKEND_DIR / "contextkiln.db"


def settings_from(values: Mapping[str, str | None]) -> Settings:
    """Build settings from a mapping, using the default for anything unset or empty."""
    defaults = Settings()
    return Settings(
        llm_provider=values.get("CK_LLM_PROVIDER") or defaults.llm_provider,
        llm_model=values.get("CK_LLM_MODEL") or defaults.llm_model,
        llm_base_url=values.get("CK_LLM_BASE_URL") or defaults.llm_base_url,
        db_path=Path(values.get("CK_DB_PATH") or defaults.db_path),
    )


def load_settings() -> Settings:
    """Load settings. Real environment variables win over .env."""
    return settings_from({**dotenv_values(REPO_ROOT / ".env"), **os.environ})
