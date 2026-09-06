"""
Shared helpers.

Two things here were wrong in a way that costs real data:

``retry_with_backoff`` caught bare ``Exception`` and retried anything. It wrapped
``CalendarService.create_event`` and ``NotionService.create_page``. Those are
non-idempotent writes: when the request reaches the server and the *response* is
lost -- a read timeout, a dropped connection -- the retry creates the record a
second time. Three retries on a flapping link produced up to four copies of the
same calendar event.

It also retried permanent failures. A 401 (bad credentials), a 403 (missing
scope), a 404 (no such event) and even ``ValueError("Notion Database ID is not
set.")`` were each retried three times with 1s, 2s and 4s sleeps before the
caller saw the error it was always going to get.

``get_current_time_iso`` used ``datetime.utcnow()``, which is deprecated in
Python 3.12 and returns a *naive* datetime; appending ``"Z"`` to it asserts a
timezone the object does not carry.
"""

from __future__ import annotations

import datetime
import logging
import random
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP statuses where trying the same request again can plausibly succeed.
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def get_current_time_iso() -> str:
    """Current UTC time as a timezone-aware ISO 8601 string."""
    return datetime.datetime.now(datetime.UTC).isoformat()


def _status_of(exc: BaseException) -> int | None:
    """HTTP status carried by an exception, if it carries one."""
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    response = getattr(exc, "resp", None)  # googleapiclient.errors.HttpError
    status = getattr(response, "status", None)
    if isinstance(status, int):
        return status
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return None


def is_retryable(exc: BaseException) -> bool:
    """
    Whether retrying ``exc`` could plausibly succeed.

    Anything without a recognisable transient signal is treated as permanent.
    Retrying a permanent error only delays the failure.
    """
    if isinstance(exc, (ValueError, TypeError, KeyError, AttributeError)):
        return False
    status = _status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def retry_with_backoff(
    retries: int = 3,
    backoff_in_seconds: float = 1.0,
    *,
    idempotent: bool = True,
    max_sleep: float = 8.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry ``func`` on transient failures only.

    ``idempotent=False`` disables retrying entirely. Callers that create
    records pass it, because a retried create that already reached the server
    produces a duplicate: a second calendar event, a second Notion task. There
    is no request-id on these APIs to deduplicate against, so the only correct
    behaviour is to surface the error and let a human decide.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not idempotent:
                        logger.error(
                            "%s failed and is not safe to retry (a retry could "
                            "duplicate the record): %s",
                            func.__name__,
                            type(exc).__name__,
                        )
                        raise
                    if not is_retryable(exc):
                        logger.error(
                            "%s failed permanently (%s); not retrying",
                            func.__name__,
                            type(exc).__name__,
                        )
                        raise
                    if attempt >= retries:
                        logger.error("%s failed after %d retries", func.__name__, retries)
                        raise
                    sleep = min(backoff_in_seconds * 2**attempt, max_sleep)
                    sleep += random.uniform(0, 1)  # noqa: S311 - jitter, not crypto
                    logger.warning(
                        "%s failed (%s); retrying in %.2fs",
                        func.__name__,
                        type(exc).__name__,
                        sleep,
                    )
                    time.sleep(sleep)
                    attempt += 1

        return wrapper

    return decorator


def message_text(message: Any) -> str:
    """
    Text of a LangChain message, whatever shape it arrives in.

    ``LangGraphAdapter`` used to reach straight for ``.content``. Two ways that
    broke: the seed message is a ``("user", text)`` tuple, which has no
    ``.content``; and Gemini returns ``content`` as a list of blocks, so the
    caller got ``"[{'type': 'text', ...}]"`` rendered into the reply.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, tuple) and len(message) == 2:
        return str(message[1])

    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


class LangGraphAdapter:
    """Presents a LangGraph graph with the ``invoke({"input": ...}) -> {"output": ...}``
    shape the orchestrator expects."""

    def __init__(self, graph: Any) -> None:
        self.graph = graph

    def invoke(self, inputs: dict) -> dict:
        user_input = inputs.get("input")
        if not user_input or not str(user_input).strip():
            return {"output": "No input provided"}

        state = self.graph.invoke({"messages": [("user", str(user_input))]})

        messages = state.get("messages") if isinstance(state, dict) else None
        if not messages:
            return {"output": "No response generated"}

        text = message_text(messages[-1])
        return {"output": text if text.strip() else "No response generated"}
