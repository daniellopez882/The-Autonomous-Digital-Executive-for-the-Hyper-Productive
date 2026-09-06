"""
Reading mail.

This tool moves text written by arbitrary senders into the model's context.
Two consequences the previous version did not handle: unbounded length, and no
marker separating that text from the operator's own instructions.
"""

from __future__ import annotations

from pydantic import ValidationError

from src.services.gmail_service import GmailService
from src.tools.gmail_tools import (
    MAX_HEADER_CHARS,
    MAX_SNIPPET_CHARS,
    UNTRUSTED_NOTE,
    GmailReadTool,
)


def message(sender="a@example.com", subject="Hello", snippet="Body text", msg_id="1"):
    return {
        "id": msg_id,
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
            ]
        },
    }


class FakeGmailService(GmailService):
    def __init__(self, messages=None, error=None):
        super().__init__()
        self._messages = messages if messages is not None else []
        self._error = error

    def list_messages(self, query="", max_results=10):
        if self._error:
            raise self._error
        self.last_query = query
        return [{"id": m["id"]} for m in self._messages]

    def get_message(self, msg_id):
        if self._error:
            raise self._error
        return next((m for m in self._messages if m["id"] == msg_id), None)


class TestReading:
    def test_messages_are_rendered(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([message()]))
        result = tool._run("is:unread")
        assert "a@example.com" in result
        assert "Hello" in result

    def test_an_empty_inbox_says_so(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([]))
        assert tool._run("is:unread") == "No emails found matching the query."

    def test_headers_are_matched_case_insensitively(self):
        """Gmail returns 'From' but the header name casing is not guaranteed."""
        msg = message()
        msg["payload"]["headers"] = [{"name": "from", "value": "b@example.com"}]
        tool = GmailReadTool(gmail_service=FakeGmailService([msg]))
        assert "b@example.com" in tool._run("is:unread")

    def test_a_missing_header_falls_back(self):
        msg = message()
        msg["payload"]["headers"] = []
        tool = GmailReadTool(gmail_service=FakeGmailService([msg]))
        result = tool._run("is:unread")
        assert "Unknown Sender" in result
        assert "No Subject" in result

    def test_a_message_that_cannot_be_fetched_is_skipped(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([message(msg_id="1")]))
        tool.gmail_service.get_message = lambda msg_id: None
        assert tool._run("is:unread") == "No readable emails found matching the query."


class TestBounds:
    def test_a_long_snippet_is_truncated(self):
        """One newsletter could otherwise fill the context window and push the
        user's actual request out of it."""
        tool = GmailReadTool(gmail_service=FakeGmailService([message(snippet="x" * 50_000)]))
        assert len(tool._run("is:unread")) < MAX_SNIPPET_CHARS + 2_000

    def test_a_long_subject_is_truncated(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([message(subject="y" * 10_000)]))
        assert "y" * (MAX_HEADER_CHARS + 1) not in tool._run("is:unread")

    def test_max_results_is_capped_by_the_schema(self):
        import pytest

        from src.tools.gmail_tools import GmailReadInput

        with pytest.raises(ValidationError):
            GmailReadInput(query="is:unread", max_results=10_000)


class TestUntrustedContent:
    def test_the_content_is_labelled_as_third_party_text(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([message()]))
        assert UNTRUSTED_NOTE in tool._run("is:unread")

    def test_the_label_comes_before_the_content(self):
        tool = GmailReadTool(gmail_service=FakeGmailService([message(snippet="INSTRUCTIONS")]))
        result = tool._run("is:unread")
        assert result.index(UNTRUSTED_NOTE) < result.index("INSTRUCTIONS")


class TestErrors:
    def test_an_api_failure_does_not_leak_the_request_uri(self, http_error):
        tool = GmailReadTool(gmail_service=FakeGmailService(error=http_error(401)))
        result = tool._run("is:unread")
        assert "googleapis.com" not in result
        assert "SECRET" not in result

    def test_the_failure_message_says_what_to_do(self, http_error):
        tool = GmailReadTool(gmail_service=FakeGmailService(error=http_error(401)))
        assert "re-run authentication" in tool._run("is:unread")

    def test_the_failure_message_carries_a_reference(self, http_error):
        tool = GmailReadTool(gmail_service=FakeGmailService(error=http_error(500)))
        assert "ref " in tool._run("is:unread")
