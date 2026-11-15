# Feature: Add GET /api/conversations/{id}/messages

## Metadata
adw_id: `b73819c7`
prompt: `Work on GitHub issue #14. Add GET /api/conversations/{conversation_id}/messages, a read-only endpoint that returns a conversation's messages (oldest first, with created_at). Backend only: apps/backend/app/main.py and apps/backend/app/db.py. Keep Database.list_messages returning role and content only. Add tests in apps/backend/tests/test_api.py with the fake provider, and document the endpoint in the API section of app_docs/app-shell.md.`

## Feature Description
A read-only endpoint that returns the stored messages of one conversation as `{"conversation_id": "...", "messages": [{"role", "content", "created_at"}, ...]}`, oldest first. An unknown conversation returns 404 with `{"detail": "Conversation not found"}`, matching `POST /api/chat`. A conversation with no messages returns 200 with an empty list. This is the first backend piece of the conversation history sidebar (PLAN.md Phase 6, item 1). No frontend changes.

## User Story
As a ContextKiln user
I want to reload a past conversation's messages
So that I can pick up a conversation where I left off

## Problem Statement
Messages are stored in SQLite, but nothing exposes them. The only reader, `Database.list_messages`, feeds the model and returns role and content only. The frontend can't show history without an API and timestamps.

## Solution Statement
Add a second `Database` method that returns role, content and `created_at`, and leave `list_messages` unchanged, since `/api/chat` and `/api/escalations` pass its result straight on. Add a route in `create_app` that checks `conversation_exists`, raises the same 404 as `/api/chat`, and returns the new method's rows. Order by `id`, as `list_messages` does, which is stable even when timestamps tie (SQLite `datetime('now')` has one-second resolution).

## Relevant Files
Use these files to implement the feature:

- `apps/backend/app/db.py` - Add the new method next to `list_messages`.
- `apps/backend/app/main.py` - Add the route in `create_app`; reuse the 404 pattern from `chat`.
- `apps/backend/tests/test_api.py` - Add the endpoint tests; reuse the `chat` helper and the `client` and `db` fixtures.
- `app_docs/app-shell.md` - Add the endpoint to the API section.

## Implementation Plan
### Phase 1: Foundation
Add `Database.list_messages_with_timestamps(conversation_id)`, which returns `list[dict[str, str]]` with `role`, `content` and `created_at`, ordered by `id`. Don't change `list_messages`.

### Phase 2: Core Implementation
Add `GET /api/conversations/{conversation_id}/messages` to `create_app`. Return 404 `Conversation not found` if the conversation doesn't exist. Otherwise return `{"conversation_id": conversation_id, "messages": db.list_messages_with_timestamps(conversation_id)}`.

### Phase 3: Integration
Tests and docs. No change to the chat flow, the frontend or the schema.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add the database method
- In `apps/backend/app/db.py`, add `list_messages_with_timestamps` after `list_messages`, selecting `role, content, created_at` with `WHERE conversation_id = ? ORDER BY id`.
- Give it a one-line docstring saying `list_messages` stays role and content only because it goes to the model.

### 2. Add the route
- In `apps/backend/app/main.py`, add `@app.get("/api/conversations/{conversation_id}/messages")` after `chat`.
- Raise `HTTPException(status_code=404, detail="Conversation not found")` for an unknown id.
- Return the dict described in Phase 2.

### 3. Add tests
In `apps/backend/tests/test_api.py`:
- `test_get_messages_returns_the_chat_turn_in_order`: run `chat(client, message="How do I index this?")`, GET the messages, and assert status 200, the `conversation_id`, the roles and contents (`user` then `assistant`, "Hello there"), and that each message has a non-empty string `created_at`. Compare role and content separately from the timestamp.
- `test_get_messages_unknown_conversation_is_404`: assert 404 and `{"detail": "Conversation not found"}`.
- `test_get_messages_empty_conversation_returns_empty_list`: call `db.create_conversation("empty")`, GET, and assert 200 with `{"conversation_id": "empty", "messages": []}`.
- `test_list_messages_still_returns_role_and_content_only` is already covered by `test_chat_stores_both_messages`. Leave that test unchanged.

### 4. Update the docs
- In `app_docs/app-shell.md`, add a bullet to the API section: `GET /api/conversations/{conversation_id}/messages` returns `{conversation_id, messages}`, where each message is `{role, content, created_at}`, oldest first. An unknown id returns 404 and an empty conversation returns an empty list.

### 5. Validate
- Run the validation commands below.

## Testing Strategy
### Unit Tests
The three endpoint tests above, using the fake provider from `conftest.py`. They never need a running model or an API key.

### Edge Cases
- Unknown conversation id returns 404 with the exact detail.
- Existing conversation with no messages returns 200 and `[]`.
- Messages written in the same second keep their order, because of `ORDER BY id`.
- `list_messages` output is unchanged, so the provider-call assertions in the existing tests still pass.

## Acceptance Criteria
- `GET /api/conversations/{id}/messages` returns 200 with `conversation_id` and a `messages` list of `{role, content, created_at}`, oldest first.
- An unknown id returns 404 with `{"detail": "Conversation not found"}`.
- An empty conversation returns 200 with an empty list.
- `Database.list_messages` still returns role and content only.
- Only `main.py`, `db.py`, `test_api.py` and `app-shell.md` change (plus this plan).
- All backend tests pass.

## Validation Commands
Execute these commands to validate the feature is complete:

- `cd apps/backend && uv run pytest` - Run the backend tests
- `./scripts/test.sh` - Run all tests

## Notes
- `created_at` is returned as stored by SQLite (`YYYY-MM-DD HH:MM:SS`, UTC, no timezone marker). Changing the format is out of scope; the frontend issue can decide how to display it.
- No new dependencies.
