import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings, settings_from
from app.llm import LLMError, OpenAICompatibleProvider, build_provider

MESSAGES = [{"role": "user", "content": "Hi"}]


def provider_with(handler) -> OpenAICompatibleProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider("http://llm.test/v1/", "test-model", client)


def sse(*events: dict) -> str:
    lines = [f"data: {json.dumps(e)}\n\n" for e in events]
    return "".join(lines) + "data: [DONE]\n\n"


def delta(**fields) -> dict:
    return {"choices": [{"delta": fields}]}


def test_streams_content_and_sends_the_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=sse(delta(content="Hel"), delta(content="lo")))

    assert list(provider_with(handler).stream_reply(MESSAGES)) == ["Hel", "lo"]
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert seen["body"] == {"model": "test-model", "messages": MESSAGES, "stream": True}


def test_skips_events_without_content():
    body = sse(delta(role="assistant"), delta(reasoning="hmm"), delta(content="Hi"), {"choices": []})
    provider = provider_with(lambda request: httpx.Response(200, text=body))

    assert list(provider.stream_reply(MESSAGES)) == ["Hi"]


def test_error_status_raises_llm_error():
    provider = provider_with(lambda request: httpx.Response(404, text="model not found"))

    with pytest.raises(LLMError, match="404: model not found"):
        list(provider.stream_reply(MESSAGES))


def test_connection_failure_raises_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="Could not reach"):
        list(provider_with(handler).stream_reply(MESSAGES))


def test_malformed_event_raises_llm_error():
    provider = provider_with(lambda request: httpx.Response(200, text="data: {oops\n\n"))

    with pytest.raises(LLMError, match="Unexpected reply"):
        list(provider.stream_reply(MESSAGES))


def test_build_provider_uses_settings():
    provider = build_provider(Settings(llm_base_url="http://x/v1", llm_model="m"))

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.url == "http://x/v1/chat/completions"
    assert provider.model == "m"


def test_build_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="CK_LLM_PROVIDER"):
        build_provider(Settings(llm_provider="nope"))


def test_settings_read_env_vars_and_ignore_empty_values():
    settings = settings_from(
        {"CK_LLM_MODEL": "m", "CK_LLM_BASE_URL": "", "CK_DB_PATH": "/tmp/x.db"}
    )

    assert settings.llm_model == "m"
    assert settings.llm_base_url == Settings().llm_base_url
    assert settings.db_path == Path("/tmp/x.db")
