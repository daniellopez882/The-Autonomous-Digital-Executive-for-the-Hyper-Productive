"""Email agent: read-only Gmail access."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from src.agents.llm import get_chat_model
from src.tools.gmail_tools import GmailReadTool
from src.utils.helpers import LangGraphAdapter


def create_email_agent() -> LangGraphAdapter:
    # notification_send is deliberately absent: an agent that both reads
    # attacker-supplied mail and sends mail is an exfiltration path. See
    # src/agents/notification_agent.py.
    graph = create_react_agent(get_chat_model(), [GmailReadTool()])
    return LangGraphAdapter(graph)
