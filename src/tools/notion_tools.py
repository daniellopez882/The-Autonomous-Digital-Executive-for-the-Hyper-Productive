from typing import Type, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from src.services.notion_service import NotionService
import logging

logger = logging.getLogger(__name__)

class NotionCreateTaskInput(BaseModel):
    title: str = Field(description="Title of the task")
    status: str = Field(default="Not Started", description="Status of the task (e.g., 'Not Started', 'In Progress', 'Done')")
    priority: str = Field(default="Medium", description="Priority of the task (e.g., 'High', 'Medium', 'Low')")

class NotionCreateTaskTool(BaseTool):
    name: str = "notion_create_task"
    description: str = "Create a new task in the Notion database."
    args_schema: Type[BaseModel] = NotionCreateTaskInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, title: str, status: str = "Not Started", priority: str = "Medium") -> str:
        try:
            properties = {
                "Name": {"title": [{"text": {"content": title}}]},
                "Status": {"select": {"name": status}},
                "Priority": {"select": {"name": priority}}
            }
            response = self.notion_service.create_page(properties)
            if response:
                return f"Task created successfully. ID: {response.get('id')}"
            else:
                return "Failed to create task."
        except Exception as e:
            logger.error(f"Error creating Notion task: {e}")
            return f"Error creating Notion task: {str(e)}"

class NotionListTasksInput(BaseModel):
    status_filter: Optional[str] = Field(default=None, description="Filter tasks by status")

class NotionListTasksTool(BaseTool):
    name: str = "notion_list_tasks"
    description: str = "List tasks from Notion database."
    args_schema: Type[BaseModel] = NotionListTasksInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, status_filter: Optional[str] = None) -> str:
        try:
            query = {}
            if status_filter:
                query["filter"] = {
                    "property": "Status",
                    "select": {
                        "equals": status_filter
                    }
                }
            
            response = self.notion_service.query_database(query)
            results = response.get('results', [])
            
            if not results:
                return "No tasks found."
            
            task_list = []
            for page in results:
                props = page['properties']
                title_list = props.get('Name', {}).get('title', [])
                title = title_list[0]['text']['content'] if title_list else "Untitled"
                status = props.get('Status', {}).get('select', {}).get('name', 'Unknown')
                task_list.append(f"- {title} [{status}]")
            
            return "\n".join(task_list)
            
        except Exception as e:
            logger.error(f"Error listing Notion tasks: {e}")
            return f"Error listing Notion tasks: {str(e)}"

class NotionUpdateTaskInput(BaseModel):
    page_id: str = Field(description="ID of the task (page) to update")
    status: Optional[str] = Field(None, description="New status")
    priority: Optional[str] = Field(None, description="New priority")

class NotionUpdateTaskTool(BaseTool):
    name: str = "notion_update_task"
    description: str = "Update a task's status or priority in Notion."
    args_schema: Type[BaseModel] = NotionUpdateTaskInput
    notion_service: NotionService = Field(default_factory=NotionService)

    def _run(self, page_id: str, status: str = None, priority: str = None) -> str:
        try:
            properties = {}
            if status:
                properties["Status"] = {"select": {"name": status}}
            if priority:
                properties["Priority"] = {"select": {"name": priority}}
            
            if not properties:
                return "No updates provided."

            response = self.notion_service.update_page(page_id, properties)
            if response:
                return f"Task updated successfully."
            else:
                return "Failed to update task."
        except Exception as e:
            logger.error(f"Error updating Notion task: {e}")
            return f"Error updating Notion task: {str(e)}"
