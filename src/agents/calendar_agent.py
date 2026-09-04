"""Calendar agent."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from src.agents.llm import get_chat_model
from src.tools.calendar_tools import CalendarCreateTool, CalendarListTool, CalendarUpdateTool
from src.utils.helpers import LangGraphAdapter


def create_calendar_agent() -> LangGraphAdapter:
    tools = [CalendarCreateTool(), CalendarListTool(), CalendarUpdateTool()]
    return LangGraphAdapter(create_react_agent(get_chat_model(), tools))
