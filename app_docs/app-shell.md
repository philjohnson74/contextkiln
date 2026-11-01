# App shell

A chat page for software engineering and infrastructure questions, with a "Talk to a human" button. There's no auth, payment or human dashboard yet.

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
