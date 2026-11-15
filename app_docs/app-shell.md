# App shell

A chat page for software engineering and infrastructure questions, with a "Talk to a human" button. There's no auth, payment or human dashboard yet.

## Conversation sidebar

The left-hand sidebar lists past conversations (newest first) and allows switching between them. Clicking one loads its messages into the chat and makes it the active conversation. A "New conversation" button resets the chat to the empty state. After the first reply in a new conversation finishes, the list refreshes so the new conversation appears at the top, highlighted. On screens under 640px the sidebar sits above the chat.

The sidebar is implemented in `Sidebar.tsx` and uses the following API helpers:
- `listConversations()` - fetches the conversation list from `/api/conversations`
- `getMessages(id)` - fetches messages for a specific conversation from `/api/conversations/{id}/messages`

## Run it

Start Ollama and pull the default model (`ollama pull qwen3:4b`), then:

```bash
./scripts/start.sh
```

Open http://127.0.0.1:5173. Stop the servers with `./scripts/stop.sh`. Logs are in `.run/`.

## Settings

Set these in `.env` or the environment. All are optional.

| Variable | Default | Purpose |
|---|---|---|
| `CK_LLM_PROVIDER` | `openai_compatible` | Which provider to use. It's the only one so far. |
| `CK_LLM_MODEL` | `qwen3:4b` | Model name sent to the server. |
| `CK_LLM_BASE_URL` | `http://localhost:11434/v1` | Base URL of the OpenAI-compatible API. |
| `CK_DB_PATH` | `apps/backend/contextkiln.db` | SQLite file. |

## API

- `GET /health` returns `{"status": "ok"}`.
- `POST /api/chat` takes `{conversation_id?, message}` and streams NDJSON: a `conversation` event, then `delta` events, then `done` or `error`. An unknown `conversation_id` returns 404.
- `GET /api/conversations` returns `{conversations}`, newest first (ties: the later-created one first), where each is `{id, created_at, title, message_count}`. `title` is the first user message cut to 60 characters with a trailing `…`, or `New conversation` if there are no messages. `message_count` counts user and assistant messages. No conversations returns an empty list.
- `GET /api/conversations/{conversation_id}/messages` returns `{conversation_id, messages}`, where each message is `{role, content, created_at}`, oldest first. An unknown id returns 404 and an empty conversation returns an empty list.
- `POST /api/escalations` takes `{conversation_id, summary?}` and returns the new row with status `open`. Without a summary, it uses the latest user message.

## See escalations

Escalations are only rows in the database for now:

```bash
sqlite3 apps/backend/contextkiln.db "SELECT * FROM escalations"
```

## Code

- `apps/backend/app/llm.py`: the `LLMProvider` protocol, `OpenAICompatibleProvider` and the system prompt. Add new providers to `build_provider`.
- `apps/backend/app/db.py`: the `conversations`, `messages` and `escalations` tables.
- `apps/backend/app/main.py`: the routes.
- `apps/frontend/src/api.ts` and `App.tsx`: the stream parser and the chat page.
