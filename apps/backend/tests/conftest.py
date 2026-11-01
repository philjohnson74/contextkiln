from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.llm import LLMError
from app.main import create_app


class FakeProvider:
    """Replays a scripted reply, and optionally fails after it."""

    def __init__(self) -> None:
        self.chunks = ["Hello", " there"]
        self.error: LLMError | None = None
        self.calls: list[list[dict[str, str]]] = []

    def stream_reply(self, messages: list[dict[str, str]]) -> Iterator[str]:
        self.calls.append(messages)
        yield from self.chunks
        if self.error:
            raise self.error


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def db(db_path: Path) -> Database:
    return Database(db_path)


@pytest.fixture
def client(db_path: Path, provider: FakeProvider) -> TestClient:
    return TestClient(create_app(Settings(db_path=db_path), provider))
