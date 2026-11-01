"""LLM providers. The app depends only on the LLMProvider protocol."""

import json
from collections.abc import Iterable, Iterator
from typing import Protocol

import httpx

from app.config import Settings

SYSTEM_PROMPT = """\
You are the ContextKiln tech consultant. You help people with software engineering \
and infrastructure questions: code, architecture, debugging, tooling, deployment and \
operations.

- Politely decline questions outside software and infrastructure.
- Be direct and practical. Say what you would do and why.
- Don't guess. If you are out of your depth, or the stakes are high (such as production \
data loss, a security incident, or a legal or compliance decision), say so and recommend \
the "Talk to a human" button to reach a human engineer.
"""


class LLMError(Exception):
    """The provider couldn't produce a reply."""


class LLMProvider(Protocol):
    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        """Yield the reply's text as it's generated. Raise LLMError on failure."""
        ...


class OpenAICompatibleProvider:
    """Any server with an OpenAI-style /chat/completions, such as Ollama's /v1."""

    def __init__(self, base_url: str, model: str, client: httpx.Client | None = None) -> None:
        self.url = f"{base_url.rstrip('/')}/chat/completions"
        self.model = model
        # Local models can take a long time to load, so only connecting is time-limited.
        self.client = client or httpx.Client(timeout=httpx.Timeout(None, connect=5.0))

    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        body = {"model": self.model, "messages": messages, "stream": True}
        try:
            with self.client.stream("POST", self.url, json=body) as response:
                if response.is_error:
                    response.read()
                    raise LLMError(
                        f"LLM server returned {response.status_code}: {response.text[:200]}"
                    )
                yield from _parse_sse(response.iter_lines())
        except httpx.HTTPError as e:
            raise LLMError(f"Could not reach the LLM server at {self.url}: {e}") from e


def _parse_sse(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return
        try:
            event = json.loads(data)
            choices = event.get("choices") or []
            text = choices[0]["delta"].get("content") if choices else None
        except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
            raise LLMError(f"Unexpected reply from the LLM server: {data[:200]}") from e
        if text:
            yield text


def build_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(settings.llm_base_url, settings.llm_model)
    raise ValueError(f"Unknown CK_LLM_PROVIDER: {settings.llm_provider!r}")
