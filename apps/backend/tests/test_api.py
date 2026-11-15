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


def test_get_messages_returns_the_chat_turn_in_order(client):
    events = chat(client, message="How do I index this?")
    conversation_id = events[0]["conversation_id"]

    response = client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert [(m["role"], m["content"]) for m in body["messages"]] == [
        ("user", "How do I index this?"),
        ("assistant", "Hello there"),
    ]
    for message in body["messages"]:
        assert isinstance(message["created_at"], str) and message["created_at"]


def test_get_messages_unknown_conversation_is_404(client):
    response = client.get("/api/conversations/nope/messages")

    assert response.status_code == 404
    assert response.json() == {"detail": "Conversation not found"}


def test_get_messages_empty_conversation_returns_empty_list(client, db):
    db.create_conversation("empty")

    response = client.get("/api/conversations/empty/messages")

    assert response.status_code == 200
    assert response.json() == {"conversation_id": "empty", "messages": []}


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


def test_list_conversations_returns_newest_first_with_title_and_count(client, db):
    # Create two conversations with different messages
    events1 = chat(client, message="First question")
    conversation_id_1 = events1[0]["conversation_id"]

    events2 = chat(client, message="Second question")
    conversation_id_2 = events2[0]["conversation_id"]

    # Set the first conversation's created_at to a specific time to control ordering
    with db._connect() as conn:
        conn.execute(
            "UPDATE conversations SET created_at = '2000-01-01 00:00:00' WHERE id = ?",
            (conversation_id_1,)
        )

    response = client.get("/api/conversations")

    assert response.status_code == 200
    body = response.json()

    # Should return conversations newest first (the second one created)
    assert len(body["conversations"]) == 2
    assert body["conversations"][0]["id"] == conversation_id_2
    assert body["conversations"][1]["id"] == conversation_id_1

    # Check titles and counts
    assert body["conversations"][0]["title"] == "Second question"
    assert body["conversations"][1]["title"] == "First question"
    assert body["conversations"][0]["message_count"] == 2
    assert body["conversations"][1]["message_count"] == 2
    assert body["conversations"][0]["created_at"]
    assert body["conversations"][1]["created_at"]


def test_list_conversations_breaks_created_at_ties_by_creation_order(client, db):
    # Create two conversations with same created_at
    db.create_conversation("a")
    db.create_conversation("b")

    # Set both to same created_at time
    with db._connect() as conn:
        conn.execute(
            "UPDATE conversations SET created_at = '2000-01-01 00:00:00' WHERE id IN (?, ?)",
            ("a", "b")
        )

    response = client.get("/api/conversations")

    assert response.status_code == 200
    body = response.json()

    # Should return conversations by insertion order (the later-created one first)
    assert len(body["conversations"]) == 2
    assert body["conversations"][0]["id"] == "b"  # Later created
    assert body["conversations"][1]["id"] == "a"   # Earlier created


def test_list_conversations_cuts_long_titles_to_60_characters(client, db):
    # Create a conversation with a long first message
    long_message = "é" * 61  # 61 non-ASCII characters
    db.create_conversation("long")
    db.add_message("long", "user", long_message)

    response = client.get("/api/conversations")

    assert response.status_code == 200
    body = response.json()

    # Title should be truncated to 60 chars with "…" at the end
    assert len(body["conversations"][0]["title"]) == 60
    assert body["conversations"][0]["title"] == long_message[:59] + "…"
    assert body["conversations"][0]["message_count"] == 1


def test_list_conversations_keeps_a_60_character_title_unchanged(client, db):
    db.create_conversation("exact")
    db.add_message("exact", "user", "B" * 60)

    response = client.get("/api/conversations")

    assert response.status_code == 200
    assert response.json()["conversations"][0]["title"] == "B" * 60


def test_list_conversations_title_is_the_first_user_message(client, db):
    # Create conversation with user, assistant, then user message
    db.create_conversation("multi")
    db.add_message("multi", "user", "First question")
    db.add_message("multi", "assistant", "Answer")
    db.add_message("multi", "user", "Second question")

    response = client.get("/api/conversations")

    assert response.status_code == 200
    body = response.json()

    # Title should be the first user message
    assert body["conversations"][0]["title"] == "First question"
    assert body["conversations"][0]["message_count"] == 3


def test_list_conversations_empty_conversation_is_new_conversation(client, db):
    # Create conversation with no messages
    db.create_conversation("empty")

    response = client.get("/api/conversations")

    assert response.status_code == 200
    body = response.json()

    # Title should be "New conversation" and count should be 0
    assert body["conversations"][0]["title"] == "New conversation"
    assert body["conversations"][0]["message_count"] == 0


def test_list_conversations_with_none_returns_empty_list(client):
    response = client.get("/api/conversations")

    assert response.status_code == 200
    assert response.json() == {"conversations": []}