"""
Retry behaviour, and message flattening.

The retry decorator is the piece with the worst failure mode in this codebase:
it wrapped ``create_event`` and ``create_page`` -- non-idempotent writes -- and
retried them on any exception at all.
"""

from __future__ import annotations

import datetime
from typing import ClassVar

import pytest

from src.utils.helpers import (
    get_current_time_iso,
    is_retryable,
    message_text,
    retry_with_backoff,
)
from tests.fakes import HttpErrorLike


class TestRetryClassification:
    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
    def test_transient_statuses_are_retryable(self, status, http_error):
        assert is_retryable(http_error(status)) is True

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
    def test_permanent_statuses_are_not(self, status, http_error):
        """Retrying a 401 three times with sleeps just delays the same failure."""
        assert is_retryable(http_error(status)) is False

    def test_value_error_is_not_retryable(self):
        """ValueError('Notion Database ID is not set.') was retried three times."""
        assert is_retryable(ValueError("NOTION_DATABASE_ID is not set.")) is False

    @pytest.mark.parametrize("exc", [TimeoutError(), ConnectionError()])
    def test_transport_failures_are_retryable(self, exc):
        assert is_retryable(exc) is True

    def test_unknown_exceptions_are_not_retryable(self):
        """Default to permanent: an unrecognised error is not evidence of transience."""
        assert is_retryable(Exception("something")) is False


class TestRetryLoop:
    def test_a_transient_failure_is_retried_then_succeeds(self, no_sleep, http_error):
        calls = {"n": 0}

        @retry_with_backoff(retries=3)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise http_error(503)
            return "ok"

        assert flaky() == "ok"
        assert calls["n"] == 3
        assert len(no_sleep) == 2

    def test_a_permanent_failure_is_not_retried(self, no_sleep, http_error):
        calls = {"n": 0}

        @retry_with_backoff(retries=3)
        def denied():
            calls["n"] += 1
            raise http_error(403)

        with pytest.raises(HttpErrorLike):
            denied()
        assert calls["n"] == 1, "a 403 was attempted more than once"
        assert no_sleep == [], "slept before re-raising an error that cannot succeed"

    def test_retries_are_exhausted_then_the_error_surfaces(self, no_sleep, http_error):
        calls = {"n": 0}

        @retry_with_backoff(retries=2)
        def always_503():
            calls["n"] += 1
            raise http_error(503)

        with pytest.raises(HttpErrorLike):
            always_503()
        assert calls["n"] == 3  # initial attempt + 2 retries

    def test_backoff_is_capped(self, no_sleep, http_error):
        @retry_with_backoff(retries=6, backoff_in_seconds=1.0, max_sleep=4.0)
        def always_503():
            raise http_error(503)

        with pytest.raises(HttpErrorLike):
            always_503()
        assert max(no_sleep) <= 5.0, "sleep exceeded max_sleep + jitter"


class TestNonIdempotentWrites:
    """
    The data-loss case.

    A create whose response is lost has still created the record. Retrying it
    creates a second one, and neither the Calendar nor the Notion API offers a
    request id to deduplicate against.
    """

    def test_a_create_is_never_retried(self, no_sleep):
        attempts = {"n": 0}

        @retry_with_backoff(retries=3, idempotent=False)
        def create_event():
            attempts["n"] += 1
            raise TimeoutError("response lost after the event was created")

        with pytest.raises(TimeoutError):
            create_event()
        assert attempts["n"] == 1, "a create was attempted twice; that duplicates the record"
        assert no_sleep == []

    def test_the_real_create_paths_are_marked_non_idempotent(self):
        """Guard against the flag being dropped from a service method later.

        Asserted on the AST, not on the source text, so a comment mentioning
        ``idempotent=False`` cannot satisfy it.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1]
        expected = {
            "src/services/calendar_service.py": {"create_event", "update_event"},
            "src/services/notion_service.py": {"create_page", "update_page"},
            "src/services/gmail_service.py": {"send_message"},
        }

        for relative, names in expected.items():
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
            found = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    marked = any(
                        kw.arg == "idempotent"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is False
                        for kw in decorator.keywords
                    )
                    if marked:
                        found.add(node.name)
            assert names <= found, f"{relative}: {names - found} may now be retried"


class TestTimestamps:
    def test_the_timestamp_is_timezone_aware(self):
        """utcnow() returns a naive datetime; appending 'Z' asserted a tz it lacked."""
        parsed = datetime.datetime.fromisoformat(get_current_time_iso())
        assert parsed.tzinfo is not None

    def test_it_is_utc(self):
        parsed = datetime.datetime.fromisoformat(get_current_time_iso())
        assert parsed.utcoffset() == datetime.timedelta(0)


class TestMessageText:
    def test_a_plain_string_message(self):
        assert message_text("hello") == "hello"

    def test_a_seed_tuple_has_no_content_attribute(self):
        """The graph is seeded with ("user", text); .content raised on it."""
        assert message_text(("user", "hello")) == "hello"

    def test_gemini_style_content_blocks_are_flattened(self):
        class Msg:
            content: ClassVar[list] = [
                {"type": "text", "text": "part one "},
                {"type": "text", "text": "part two"},
            ]

        assert message_text(Msg()) == "part one part two"

    def test_non_text_blocks_are_dropped(self):
        class Msg:
            content: ClassVar[list] = [
                {"type": "image", "url": "x"},
                {"type": "text", "text": "kept"},
            ]

        assert message_text(Msg()) == "kept"

    def test_a_normal_string_content(self):
        class Msg:
            content = "plain"

        assert message_text(Msg()) == "plain"
