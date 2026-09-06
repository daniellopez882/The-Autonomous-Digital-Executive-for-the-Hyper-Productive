"""
One place that builds a chat model.

``ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=...)`` was written
out four times: once in the orchestrator and once in each of the three agent
factories. That had three consequences.

* ``gemini-pro`` is a retired alias. Changing it meant four edits, and missing
  one left a code path calling a model that no longer exists.
* Constructing any agent required a real API key, so there was no way to test
  routing or tool wiring without one. That is why the repository's only test
  asserted that a constructor sets an attribute.
* The key was read at construction time from a settings object frozen at import.

``set_model_factory`` is the seam the test suite substitutes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.utils.config import settings

logger = logging.getLogger(__name__)

ModelFactory = Callable[[], Any]

_factory: ModelFactory | None = None


class LLMNotConfigured(RuntimeError):
    """Raised when a model is needed and no credentials are available."""


def set_model_factory(factory: ModelFactory | None) -> None:
    """Install (or with ``None``, remove) the factory used to build chat models."""
    global _factory
    _factory = factory


def get_chat_model(**overrides: Any) -> Any:
    """
    Build the chat model.

    Raises ``LLMNotConfigured`` rather than letting pydantic's validation error
    surface: the previous failure mode was a ``ValidationError`` naming an
    internal field, which told the operator nothing about the missing setting.
    """
    if _factory is not None:
        return _factory()

    api_key = settings.GEMINI_API_KEY.strip()
    if not api_key:
        raise LLMNotConfigured(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add a key "
            "from https://aistudio.google.com/apikey"
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    params: dict[str, Any] = {
        "model": settings.GEMINI_MODEL,
        "google_api_key": api_key,
        "temperature": 0.0,
    }
    params.update(overrides)
    return ChatGoogleGenerativeAI(**params)
