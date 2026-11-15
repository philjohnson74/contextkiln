"""SQLite storage.

Each call opens its own connection, because a streaming response runs across
several threads and a sqlite3 connection belongs to the thread that opened it.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations (id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations (id),
    summary TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

TITLE_MAX_CHARS = 60
NEW_CONVERSATION_TITLE = "New conversation"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def create_conversation(self, conversation_id: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO conversations (id) VALUES (?)", (conversation_id,))

    def conversation_exists(self, conversation_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return row is not None

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                (conversation_id, role, content),
            )

    def list_messages(self, conversation_id: str) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def list_messages_with_timestamps(self, conversation_id: str) -> list[dict[str, str]]:
        """Like `list_messages` plus `created_at`; that one stays role and content only because it goes to the model."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [
            {"role": row["role"], "content": row["content"], "created_at": row["created_at"]}
            for row in rows
        ]

    def list_conversations(self) -> list[dict]:
        """List conversations newest first, ties broken by insertion order, one query for all conversations."""
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT c.id, c.created_at,
                       (SELECT m.content FROM messages m
                         WHERE m.conversation_id = c.id AND m.role = 'user'
                         ORDER BY m.id LIMIT 1) AS first_message,
                       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                FROM conversations c
                ORDER BY c.created_at DESC, c.rowid DESC
            """).fetchall()

        conversations = []
        for row in rows:
            # Process title according to rules
            first_message = row["first_message"]
            if first_message is None:
                title = NEW_CONVERSATION_TITLE
            elif len(first_message) <= TITLE_MAX_CHARS:
                title = first_message
            else:
                title = first_message[:TITLE_MAX_CHARS - 1] + "…"

            conversations.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "title": title,
                "message_count": row["message_count"]
            })

        return conversations

    def create_escalation(self, conversation_id: str, summary: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO escalations (conversation_id, summary) VALUES (?, ?) "
                "RETURNING id, conversation_id, summary, status, created_at",
                (conversation_id, summary),
            ).fetchone()
        return dict(row)
