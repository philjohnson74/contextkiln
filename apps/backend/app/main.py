"""The ContextKiln API. Run with: uvicorn --factory app.main:create_app"""

import json
import logging
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from app.config import Settings, load_settings
from app.db import Database
from app.llm import SYSTEM_PROMPT, LLMError, LLMProvider, build_provider

logger = logging.getLogger(__name__)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MAX_DEFAULT_SUMMARY_CHARS = 500


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: NonEmptyText


class EscalationRequest(BaseModel):
    conversation_id: str
    summary: NonEmptyText | None = None


def _event(**fields: str) -> bytes:
    return (json.dumps(fields) + "\n").encode()


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None) -> FastAPI:
    settings = settings or load_settings()
    llm = provider or build_provider(settings)
    db = Database(settings.db_path)
    app = FastAPI(title="ContextKiln")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> StreamingResponse:
        """Stream the reply as NDJSON: one `conversation` event, then `delta`s, then
        `done` or `error`. The status code is sent before the model runs, so a model
        failure can only be reported in the stream."""
        conversation_id = request.conversation_id
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())
            db.create_conversation(conversation_id)
        elif not db.conversation_exists(conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")

        db.add_message(conversation_id, "user", request.message)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *db.list_messages(conversation_id),
        ]

        def stream() -> Iterator[bytes]:
            yield _event(type="conversation", conversation_id=conversation_id)
            reply: list[str] = []
            try:
                for text in llm.stream_reply(messages):
                    reply.append(text)
                    yield _event(type="delta", text=text)
            except LLMError as e:
                logger.error("LLM request failed: %s", e)
                yield _event(type="error", message="The model couldn't reply. Please try again.")
                return
            finally:
                # Keep what the user saw, even if the model or the connection failed midway.
                if reply:
                    db.add_message(conversation_id, "assistant", "".join(reply))
            yield _event(type="done")

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    @app.post("/api/escalations", status_code=201)
    def create_escalation(request: EscalationRequest) -> dict:
        """Record a request for human help. Without a summary, the latest question is used."""
        if not db.conversation_exists(request.conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")

        summary = request.summary
        if summary is None:
            questions = [
                m["content"]
                for m in db.list_messages(request.conversation_id)
                if m["role"] == "user"
            ]
            summary = questions[-1][:MAX_DEFAULT_SUMMARY_CHARS] if questions else "No summary"
        return db.create_escalation(request.conversation_id, summary)

    return app
