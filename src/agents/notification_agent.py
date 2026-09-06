"""
The send-email tool.

This one deserves care. The chain that exists in this repository is:

    gmail_read  ->  puts text written by arbitrary senders into the prompt
    notification_send  ->  sends mail as the user, to any address, no confirmation

An attacker only needs to email the user. The message body becomes model
context, and if both tools are on the same agent, text in that body can ask for
a reply containing whatever the model has read. Nothing in the previous version
stood in the way: ``recipient`` went straight to ``messages().send``.

Two controls, both here rather than in a prompt, because prompt instructions are
exactly what an injected message overrides:

* ``NOTIFICATION_ALLOWED_RECIPIENTS`` is an explicit allowlist. Empty by
  default, which disables the tool. There is no wildcard.
* The tool is not attached to any agent by ``build_agents``. Wiring it to an
  agent that also reads mail is a decision to make deliberately.

An allowlist is the control, not this docstring.
"""

from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.gmail_service import GmailService
from src.tools.errors import tool_error
from src.utils.config import settings

logger = logging.getLogger(__name__)

MAX_SUBJECT_CHARS = 300
MAX_BODY_CHARS = 20_000


def is_allowed_recipient(recipient: str) -> bool:
    """
    Whether ``recipient`` is on the configured allowlist.

    Matching is exact on the full address, lowercased. Domain suffix matching
    is deliberately not offered: ``@example.com`` reads as a safe rule right
    up to the first attacker-registered lookalike.
    """
    allowed = settings.allowed_recipients
    if not allowed:
        return False
    return recipient.strip().lower() in allowed


class NotificationSendInput(BaseModel):
    recipient: str = Field(description="Email address to notify")
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT_CHARS)
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)


class NotificationSendTool(BaseTool):
    name: str = "notification_send"
    description: str = (
        "Send an email notification to a pre-approved recipient. Only addresses on "
        "the operator's allowlist can be reached."
    )
    args_schema: type[BaseModel] = NotificationSendInput
    gmail_service: GmailService = Field(default_factory=GmailService)

    def _run(self, recipient: str, subject: str, body: str) -> str:
        if not is_allowed_recipient(recipient):
            logger.warning(
                "notification_send refused: %r is not on NOTIFICATION_ALLOWED_RECIPIENTS",
                recipient,
            )
            return (
                f"Refused: {recipient} is not on the approved recipient list. "
                "The operator must add it to NOTIFICATION_ALLOWED_RECIPIENTS."
            )

        try:
            message = MIMEText(body)
            message["to"] = recipient
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

            sent = self.gmail_service.send_message(raw)
            if not sent:
                return "Could not send: Gmail is not authenticated."
            logger.info("notification sent to an allowlisted recipient, id=%s", sent.get("id"))
            return f"Notification sent. Id: {sent.get('id', '(no id returned)')}"
        except Exception as exc:
            return tool_error("send the notification", exc)
