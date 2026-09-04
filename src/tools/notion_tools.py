"""
Notion tools.

``notion_list_tasks`` read the API response with direct indexing::

    props = page['properties']
    title = title_list[0]['text']['content']

Both raise. ``properties`` is absent on any non-page object the query returns,
and a title made of anything other than plain typed text -- a mention, a date, an
equation, all of which Notion permits in a title -- has no ``'text'`` key at
all. A single task whose title contained an @-mention made the whole listing
fail with "Error listing Notion tasks: 'text'".

Notion gives every rich-text item a ``plain_text`` rendering. Use that.
"""

from __future__ import annotations

import logging

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.notion_service import NotionService
from src.tools.errors import tool_error

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 2000


def rich_text_to_plain(items: list) -> str:
    """
    Flatten a Notion rich-text array.

    ``plain_text`` is present on every item type; ``text.content`` is present
    only on the ``text`` type.
    """
    parts: list[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        plain = item.get("plain_text")
        if isinstance(plain, str):
            parts.append(plain)
            continue
        content = item.get("text", {})
        if isinstance(content, dict) and isinstance(content.get("content"), str):
            parts.append(content["content"])
    return "".join(parts)


def _select_name(props: dict, field: str) -> str:
    """
    Read a select property, tolerating null.

    ``props.get('Status', {}).get('select', {}).get('name', 'Unknown')`` looks
    safe but is not: an unset select is ``{"select": None}``, so the middle
    ``.get`` returns ``None`` and the next ``.get`` raises AttributeError.
    """
    entry = props.get(field)
    if not isinstance(entry, dict):
        return "Unknown"
    select = entry.get("select") or entry.get("status")
    if not isinstance(select, dict):
        return "Unset"
    return str(select.get("name") or "Unset")


class NotionCreateTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS, description="Title of the task")
    status: str = Field(default="Not Started", description="Status of the task")
    priority: str = Field(default="Medium", description="Priority of the task")


class NotionCreateTaskTool(BaseTool):
    name: str = "notion_create_task"
    description: str = "Create a new task in the Notion database."
    args_schema: type[BaseModel] = NotionCreateTaskInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, title: str, status: str = "Not Started", priority: str = "Medium") -> str:
        try:
            response = self.notion_service.create_page(
                {
                    "Name": {"title": [{"text": {"content": title[:MAX_TITLE_CHARS]}}]},
                    "Status": {"select": {"name": status}},
                    "Priority": {"select": {"name": priority}},
                }
            )
            if not response:
                return "Could not create the task: Notion returned no page."
            return f"Task created successfully. ID: {response.get('id', '(no id returned)')}"
        except ValueError as exc:
            # Configuration, not a transport failure: say which setting.
            return f"Could not create the task: {exc}"
        except Exception as exc:
            return tool_error("create the Notion task", exc)


class NotionListTasksInput(BaseModel):
    status_filter: str | None = Field(default=None, description="Filter tasks by status")


class NotionListTasksTool(BaseTool):
    name: str = "notion_list_tasks"
    description: str = "List tasks from the Notion database."
    args_schema: type[BaseModel] = NotionListTasksInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, status_filter: str | None = None) -> str:
        query: dict = {}
        if status_filter:
            query["filter"] = {"property": "Status", "select": {"equals": status_filter}}

        try:
            response = self.notion_service.query_database(query)
            results = (response or {}).get("results", [])
            if not results:
                return "No tasks found."

            lines: list[str] = []
            for page in results:
                if not isinstance(page, dict):
                    continue
                props = page.get("properties") or {}
                title_prop = props.get("Name") or {}
                title = rich_text_to_plain(title_prop.get("title", [])) or "Untitled"
                lines.append(f"- {title} [{_select_name(props, 'Status')}]")

            return "\n".join(lines) if lines else "No tasks found."
        except ValueError as exc:
            return f"Could not list tasks: {exc}"
        except Exception as exc:
            return tool_error("list the Notion tasks", exc)


class NotionUpdateTaskInput(BaseModel):
    page_id: str = Field(min_length=1, description="ID of the task (page) to update")
    status: str | None = Field(None, description="New status")
    priority: str | None = Field(None, description="New priority")


class NotionUpdateTaskTool(BaseTool):
    name: str = "notion_update_task"
    description: str = "Update a task's status or priority in Notion."
    args_schema: type[BaseModel] = NotionUpdateTaskInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, page_id: str, status: str | None = None, priority: str | None = None) -> str:
        properties: dict = {}
        if status:
            properties["Status"] = {"select": {"name": status}}
        if priority:
            properties["Priority"] = {"select": {"name": priority}}

        if not properties:
            return "No updates provided."

        try:
            response = self.notion_service.update_page(page_id, properties)
            if not response:
                return "Could not update the task: Notion returned no page."
            return "Task updated successfully."
        except ValueError as exc:
            return f"Could not update the task: {exc}"
        except Exception as exc:
            return tool_error("update the Notion task", exc)
