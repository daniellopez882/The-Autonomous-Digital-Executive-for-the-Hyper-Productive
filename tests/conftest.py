"""
Shared fixtures.

The repository had one test, which asserted that ``GoogleAuthManager()`` sets
``self.credentials_path``. Nothing else was testable: every agent factory
constructed ``ChatGoogleGenerativeAI`` eagerly, so importing one without a
Gemini key raised a pydantic ``ValidationError``.

``set_model_factory`` (src/agents/llm.py) is the seam that fixes that. No test
in this suite reaches the network or needs a credential.
"""

from __future__ import annotations

import os

import pytest

# Set before importing anything that reads settings.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
os.environ.setdefault("NOTION_API_KEY", "test-notion-key-not-real")
os.environ.setdefault("NOTION_DATABASE_ID", "test-database-id")

from langchain_core.language_models.fake_chat_models import (
    GenericFakeChatModel,
)

from src.agents import llm
from tests.fakes import HttpErrorLike


@pytest.fixture
def fake_model():
    """A chat model that replays a fixed sequence of replies."""

    def build(*replies: str):
        model = GenericFakeChatModel(messages=iter(replies))
        llm.set_model_factory(lambda: model)
        return model

    yield build
    llm.set_model_factory(None)


@pytest.fixture(autouse=True)
def _no_real_model():
    """No test may construct a real provider client."""
    yield
    llm.set_model_factory(None)


@pytest.fixture
def no_sleep(monkeypatch):
    """Run the retry decorator's backoff without actually waiting."""
    slept: list[float] = []
    monkeypatch.setattr("src.utils.helpers.time.sleep", slept.append)
    return slept


@pytest.fixture
def http_error():
    return HttpErrorLike
