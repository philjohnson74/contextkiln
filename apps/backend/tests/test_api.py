import json

from app.llm import SYSTEM_PROMPT, LLMError


def chat(client, **body) -> list[dict]:
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_streams_events_in_order(client):
    events = chat(client, message="How do I index this?")

    assert [e["type"] for e in events] == ["conversation", "delta", "delta", "done"]
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Hello", " there"]


def test_chat_stores_both_messages(client, db):
    events = chat(client, message="How do I index this?")

    assert db.list_messages(events[0]["conversation_id"]) == [
        {"role": "user", "content": "How do I index this?"},
        {"role": "assistant", "content": "Hello there"},
    ]


def test_chat_sends_system_prompt_and_history_to_the_provider(client, provider):
    conversation_id = chat(client, message="First")[0]["conversation_id"]
    events = chat(client, conversation_id=conversation_id, message="Second")

    assert events[0]["conversation_id"] == conversation_id
    assert provider.calls[-1] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Hello there"},
        {"role": "user", "content": "Second"},
    ]


def test_chat_unknown_conversation_is_404(client, provider):
    response = client.post("/api/chat", json={"conversation_id": "nope", "message": "Hi"})

    assert response.status_code == 404
    assert provider.calls == []


def test_chat_rejects_blank_message(client, provider):
    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 422
    assert provider.calls == []


def test_chat_reports_provider_failure_without_leaking_details(client, provider, db):
    provider.chunks = []
    provider.error = LLMError("secret internal url")

    events = chat(client, message="Hi")

    assert [e["type"] for e in events] == ["conversation", "error"]
    assert "secret" not in events[-1]["message"]
    assert db.list_messages(events[0]["conversation_id"]) == [{"role": "user", "content": "Hi"}]


def test_chat_keeps_partial_reply_when_provider_fails_midway(client, provider, db):
    provider.chunks = ["Partial"]
    provider.error = LLMError("boom")

    events = chat(client, message="Hi")

    assert [e["type"] for e in events] == ["conversation", "delta", "error"]
    assert db.list_messages(events[0]["conversation_id"])[-1] == {
        "role": "assistant",
        "content": "Partial",
    }


def test_escalation_creates_open_row(client):
    conversation_id = chat(client, message="Prod is down")[0]["conversation_id"]

    response = client.post(
        "/api/escalations",
        json={"conversation_id": conversation_id, "summary": "Needs an engineer"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert body["summary"] == "Needs an engineer"
    assert body["status"] == "open"
    assert body["id"] > 0


def test_escalation_summary_defaults_to_latest_question(client):
    conversation_id = chat(client, message="First")[0]["conversation_id"]
    chat(client, conversation_id=conversation_id, message="Second")

    response = client.post("/api/escalations", json={"conversation_id": conversation_id})

    assert response.json()["summary"] == "Second"


def test_escalation_unknown_conversation_is_404(client):
    response = client.post("/api/escalations", json={"conversation_id": "nope"})

    assert response.status_code == 404
