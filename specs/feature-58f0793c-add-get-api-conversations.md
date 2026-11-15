# Feature: Add GET /api/conversations

## Metadata
adw_id: `58f0793c`
prompt: `Work on GitHub issue #16. Add GET /api/conversations, a read-only endpoint that lists conversations newest first, each with id, created_at, title (first user message, cut to 60 characters with a trailing "…", or "New conversation" if there are no messages) and message_count. Backend only: apps/backend/app/main.py and apps/backend/app/db.py. Use a single SQL query for the list. Add tests in apps/backend/tests/test_api.py with the fake provider, and document the endpoint in the API section of app_docs/app-shell.md.`

## Feature Description
A read-only endpoint, `GET /api/conversations`, that returns `{"conversations": [...]}` with every conversation, newest first by `created_at`. When two conversations have the same `created_at`, the one created later comes first. Each item is `{"id", "created_at", "title", "message_count"}`.

- `title` is the conversation's first user message. If it is longer than 60 characters it is cut to its first 59 characters plus `…`, so the title is exactly 60 characters. A message of exactly 60 characters is not cut. A conversation with no messages has the title `"New conversation"`.
- `message_count` counts user and assistant messages.
- With no conversations it returns 200 with `{"conversations": []}`.

This is the second backend piece of the conversation history sidebar (PLAN.md Phase 6, item 1), after #14. No frontend changes.

## User Story
As a ContextKiln user
I want to see a list of my past conversations
So that I can find one and pick up where I left off

## Problem Statement
Conversations are stored in SQLite, but nothing lists them. The frontend can fetch one conversation's messages (`GET /api/conversations/{id}/messages`) only if it already knows the id.

## Solution Statement
Add a `Database.list_conversations()` method that runs one SQL query. It selects from `conversations` and uses two correlated subqueries per row: the first user message (`ORDER BY id LIMIT 1`) and the message count. It orders by `created_at DESC, rowid DESC`. `created_at` comes from `datetime('now')`, which has one-second resolution, so ties are common. `conversations` has a TEXT primary key but is still a rowid table, so `rowid` grows with insertion order and is the "created later" tiebreaker. A single query means there is no per-conversation query (no N+1).

Title shaping (cut to 60, fallback text) is presentation logic and is done in Python in the same method, on the rows from that one query. `len` and slicing on a Python `str` count characters (code points), so the 60-character rule is exact, including for non-ASCII text. Define the numbers as module constants, `TITLE_MAX_CHARS = 60` and `NEW_CONVERSATION_TITLE = "New conversation"`.

The route in `create_app` returns `{"conversations": db.list_conversations()}`. `/api/conversations` and `/api/conversations/{conversation_id}/messages` are different paths, so there is no routing conflict.

## Relevant Files
Use these files to implement the feature:

- `apps/backend/app/db.py` - Add `list_conversations` after `list_messages_with_timestamps`, plus the two constants. Schema is unchanged.
- `apps/backend/app/main.py` - Add the route in `create_app`, next to the other conversation route.
- `apps/backend/tests/test_api.py` - Add the endpoint tests. Reuse the `chat` helper and the `client`, `db` and `db_path` fixtures. The fake provider is already wired into `client`.
- `app_docs/app-shell.md` - Add the endpoint to the API section.

## Implementation Plan
### Phase 1: Foundation
Add `TITLE_MAX_CHARS` and `NEW_CONVERSATION_TITLE` to `db.py`. Add `Database.list_conversations() -> list[dict]` running this one query:

```sql
SELECT c.id, c.created_at,
       (SELECT m.content FROM messages m
         WHERE m.conversation_id = c.id AND m.role = 'user'
         ORDER BY m.id LIMIT 1) AS first_message,
       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
FROM conversations c
ORDER BY c.created_at DESC, c.rowid DESC
```

Build each result as `{"id", "created_at", "title", "message_count"}`. The title is `NEW_CONVERSATION_TITLE` when `first_message` is `None`; `first_message` when `len <= 60`; otherwise `first_message[:59] + "…"`.

### Phase 2: Core Implementation
Add `@app.get("/api/conversations")` in `create_app`, with a one-line docstring, returning `{"conversations": db.list_conversations()}`.

### Phase 3: Integration
Tests and docs. No change to the chat flow, the schema, the frontend or `list_messages`.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Add the database method
- In `apps/backend/app/db.py`, add the two constants below `SCHEMA`.
- Add `list_conversations` after `list_messages_with_timestamps`, using the single query above and the title rules in Phase 1.
- Give it a one-line docstring: newest first, ties broken by insertion order, one query for all conversations.

### 2. Add the route
- In `apps/backend/app/main.py`, add `@app.get("/api/conversations")` before the `/messages` route.
- Return `{"conversations": db.list_conversations()}`.

### 3. Add tests
In `apps/backend/tests/test_api.py`. Where a test needs specific `created_at` values, create the conversations with `db.create_conversation` and `db.add_message`, then set `created_at` with a direct `sqlite3.connect(db_path)` `UPDATE` (import `sqlite3`; the `db_path` fixture is available).
- `test_list_conversations_returns_newest_first_with_title_and_count`: run `chat(client, message="First question")`, then another `chat` with a different message. Set the first conversation's `created_at` to `2000-01-01 00:00:00` so the order doesn't depend on the clock. Assert 200, that the ids come back newest first, the titles are the two first messages, `message_count` is 2 for both (user plus assistant), and `created_at` is a non-empty string.
- `test_list_conversations_breaks_created_at_ties_by_creation_order`: create `a` then `b` with `db.create_conversation`, set the same `created_at` on both, and assert the order is `["b", "a"]`.
- `test_list_conversations_cuts_long_titles_to_60_characters`: a first message of 61 characters gives a 60-character title equal to its first 59 characters plus `…`. A first message of exactly 60 characters comes back unchanged. Use `db.add_message` to set up both.
- `test_list_conversations_title_is_the_first_user_message`: add a user message and an assistant message, and then a second user message. Assert the title is the first user message and `message_count` is 3.
- `test_list_conversations_empty_conversation_is_new_conversation`: `db.create_conversation("empty")`. Assert title `"New conversation"` and `message_count` 0.
- `test_list_conversations_with_none_returns_empty_list`: assert 200 and `{"conversations": []}`.

### 4. Update the docs
- In `app_docs/app-shell.md`, add a bullet to the API section after the `/messages` one: `GET /api/conversations` returns `{conversations}`, newest first (ties: the later-created one first), where each is `{id, created_at, title, message_count}`. `title` is the first user message cut to 60 characters with a trailing `…`, or `New conversation` if there are no messages. `message_count` counts user and assistant messages. No conversations returns an empty list.
- Update the `db.py` bullet in the Code section only if it needs it (it doesn't).

## Testing Strategy
### Unit Tests
The endpoint tests in Step 3, all through the `client` fixture with the fake provider, so no model or API key is needed.

### Edge Cases
- Empty database: 200 with `[]`.
- Conversation with no messages: `"New conversation"`, count 0.
- Title length 59, 60 (unchanged), 61 (cut to 59 + `…`).
- Same-second `created_at`: later-created conversation first.
- First user message isn't the first message overall, or more than one user message: the earliest user message wins.
- Multi-byte characters count as one character each (Python `str` semantics). Covered by choosing a non-ASCII character in the 61-character case if convenient.

## Acceptance Criteria
- `GET /api/conversations` returns 200 with `{"conversations": [...]}`, newest first, ties by later creation first.
- Each item has exactly `id`, `created_at`, `title`, `message_count`.
- Titles follow the 60-character rule and the `"New conversation"` fallback.
- `message_count` counts both roles.
- The list is built by one SQL query, not one per conversation.
- Only `db.py`, `main.py`, `test_api.py` and `app_docs/app-shell.md` change.
- All backend tests pass.

## Validation Commands
Execute these commands to validate the feature is complete:

- `cd apps/backend && uv run pytest tests/test_api.py -k conversations` - Run the new tests
- `cd apps/backend && uv run pytest` - Run the backend tests
- `./scripts/test.sh` - Run all tests

## Notes
- No new libraries are needed.
- `messages.conversation_id` has no index, so the correlated subqueries scan `messages` once per conversation. That's fine at this scale. If the list gets slow, add `CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id)` in a follow-up; it's out of scope here.
- There is no pagination yet. Add `limit`/`before` parameters when the sidebar needs them.
