from typing import Type, Optional
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from src.services.calendar_service import CalendarService
import logging

logger = logging.getLogger(__name__)

class CalendarCreateInput(BaseModel):
    summary: str = Field(description="Title of the event")
    start_time: str = Field(description="Start time in ISO format (e.g., '2023-10-27T10:00:00Z')")
    end_time: str = Field(description="End time in ISO format (e.g., '2023-10-27T11:00:00Z')")
    description: Optional[str] = Field(default="", description="Description of the event")

class CalendarCreateTool(BaseTool):
    name: str = "calendar_create"
    description: str = "Create a new event in the primary calendar."
    args_schema: Type[BaseModel] = CalendarCreateInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(self, summary: str, start_time: str, end_time: str, description: str = "") -> str:
        try:
            event_body = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start_time},
                'end': {'dateTime': end_time},
            }
            event = self.calendar_service.create_event(event_body)
            if event:
                return f"Event created: {event.get('htmlLink')}"
            else:
                return "Failed to create event."
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return f"Error creating event: {str(e)}"

class CalendarListInput(BaseModel):
    max_results: int = Field(default=10, description="Max number of events to list")

class CalendarListTool(BaseTool):
    name: str = "calendar_list"
    description: str = "List upcoming events from the calendar."
    args_schema: Type[BaseModel] = CalendarListInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(self, max_results: int = 10) -> str:
        try:
            events = self.calendar_service.list_events(max_results=max_results)
            if not events:
                return "No upcoming events found."
            
            event_list = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'No Title')
                event_list.append(f"{start}: {summary}")
            
            return "\n".join(event_list)
        except Exception as e:
            logger.error(f"Error listing events: {e}")
            return f"Error listing events: {str(e)}"

class CalendarUpdateInput(BaseModel):
    event_id: str = Field(description="ID of the event to update")
    summary: Optional[str] = Field(None, description="New title of the event")
    description: Optional[str] = Field(None, description="New description of the event")
    start_time: Optional[str] = Field(None, description="New start time in ISO format")
    end_time: Optional[str] = Field(None, description="New end time in ISO format")

class CalendarUpdateTool(BaseTool):
    name: str = "calendar_update"
    description: str = "Update an existing event in the calendar."
    args_schema: Type[BaseModel] = CalendarUpdateInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(self, event_id: str, summary: str = None, description: str = None, start_time: str = None, end_time: str = None) -> str:
        try:
            updates = {}
            if summary: updates['summary'] = summary
            if description: updates['description'] = description
            if start_time: updates['start'] = {'dateTime': start_time}
            if end_time: updates['end'] = {'dateTime': end_time}
            
            if not updates:
                return "No updates provided."

            updated_event = self.calendar_service.update_event(event_id, updates)
            if updated_event:
                return f"Event updated: {updated_event.get('htmlLink')}"
            else:
                return "Failed to update event."
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            return f"Error updating event: {str(e)}"

