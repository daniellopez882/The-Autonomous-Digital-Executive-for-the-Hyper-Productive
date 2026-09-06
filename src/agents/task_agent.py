"""Task agent: Notion database."""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from src.agents.llm import get_chat_model
from src.tools.notion_tools import (
    NotionCreateTaskTool,
    NotionListTasksTool,
    NotionUpdateTaskTool,
)
from src.utils.helpers import LangGraphAdapter


def create_task_agent() -> LangGraphAdapter:
    tools = [NotionCreateTaskTool(), NotionListTasksTool(), NotionUpdateTaskTool()]
    return LangGraphAdapter(create_react_agent(get_chat_model(), tools))
