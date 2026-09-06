"""
The send-email tool.

This is the one tool in the repository that can act outside it irreversibly.
The exposure is concrete: ``gmail_read`` puts text written by arbitrary senders
into the model's context, and ``notification_send`` used to accept whatever
``recipient`` the model produced.
"""

from __future__ import annotations

import pytest

from src.agents.notification_agent import NotificationSendTool, is_allowed_recipient
from src.services.gmail_service import GmailService


class FakeGmailService(GmailService):
    def __init__(self, error=None):
        super().__init__()
        self.sent = None
        self._error = error

    def send_message(self, raw_message):
        if self._error:
            raise self._error
        self.sent = raw_message
        return {"id": "msg-1"}


@pytest.fixture
def allowlist(monkeypatch):
    def apply(value: str):
        monkeypatch.setattr(
            "src.agents.notification_agent.settings.NOTIFICATION_ALLOWED_RECIPIENTS", value
        )

    return apply


class TestAllowlist:
    def test_the_default_allows_nobody(self, allowlist):
        """Empty means the tool is off. There is no wildcard."""
        allowlist("")
        assert is_allowed_recipient("anyone@example.com") is False

    def test_a_listed_address_is_allowed(self, allowlist):
        allowlist("owner@example.com")
        assert is_allowed_recipient("owner@example.com") is True

    def test_matching_ignores_case(self, allowlist):
        allowlist("owner@example.com")
        assert is_allowed_recipient("Owner@Example.COM") is True

    def test_surrounding_whitespace_is_ignored(self, allowlist):
        allowlist("owner@example.com, second@example.com")
        assert is_allowed_recipient("  second@example.com  ") is True

    def test_an_unlisted_address_is_refused(self, allowlist):
        allowlist("owner@example.com")
        assert is_allowed_recipient("attacker@evil.example") is False

    def test_a_lookalike_domain_is_refused(self, allowlist):
        """Suffix matching is not offered; this is why."""
        allowlist("owner@example.com")
        assert is_allowed_recipient("owner@example.com.evil.example") is False

    def test_a_local_part_prefix_is_refused(self, allowlist):
        allowlist("owner@example.com")
        assert is_allowed_recipient("owner@example.co") is False


class TestSending:
    def test_an_unlisted_recipient_is_never_sent_to(self, allowlist):
        allowlist("owner@example.com")
        service = FakeGmailService()
        result = NotificationSendTool(gmail_service=service)._run(
            "attacker@evil.example", "Your data", "everything I read"
        )
        assert service.sent is None, "mail was sent to an address not on the allowlist"
        assert "Refused" in result

    def test_the_refusal_names_the_setting_to_change(self, allowlist):
        allowlist("")
        result = NotificationSendTool(gmail_service=FakeGmailService())._run(
            "someone@example.com", "s", "b"
        )
        assert "NOTIFICATION_ALLOWED_RECIPIENTS" in result

    def test_an_allowlisted_recipient_is_sent_to(self, allowlist):
        allowlist("owner@example.com")
        service = FakeGmailService()
        result = NotificationSendTool(gmail_service=service)._run("owner@example.com", "s", "b")
        assert service.sent is not None
        assert "msg-1" in result

    def test_a_send_failure_does_not_leak_the_request_uri(self, allowlist, http_error):
        allowlist("owner@example.com")
        service = FakeGmailService(error=http_error(403))
        result = NotificationSendTool(gmail_service=service)._run("owner@example.com", "s", "b")
        assert "googleapis.com" not in result
        assert "SECRET" not in result


class TestWiring:
    def test_the_send_tool_is_not_attached_to_the_reading_agent(self):
        """
        An agent that both reads attacker-supplied mail and sends mail is an
        exfiltration path. Asserted on the AST so a comment naming the tool
        cannot satisfy it.
        """
        import ast
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parents[1] / "src" / "agents" / "email_agent.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert "NotificationSendTool" not in referenced
