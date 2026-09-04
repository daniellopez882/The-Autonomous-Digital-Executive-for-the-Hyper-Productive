"""
Calendar tools.

``calendar_create`` sent ``{"dateTime": start_time}`` with no ``timeZone`` and
no validation. The Google Calendar API rejects a ``dateTime`` that carries
neither a UTC offset nor an accompanying ``timeZone``, and a model asked for
"tomorrow at 10am" emits ``2026-09-05T10:00:00`` far more often than it emits
the ``Z``-suffixed form in the field description. Those requests came back 400
and the user was told "Error creating event: <400 body>".

The times are now parsed and normalised here, before the call, so a bad value
produces a sentence the model can act on rather than an API error.
"""

from __future__ import annotations

import datetime
import logging

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from src.services.calendar_service import CalendarService
from src.tools.errors import tool_error

logger = logging.getLogger(__name__)

MAX_EVENT_DURATION = datetime.timedelta(days=30)


def normalise_datetime(value: str) -> str:
    """
    An ISO 8601 instant with an explicit offset.

    Accepts a trailing ``Z``, which ``datetime.fromisoformat`` only learned to
    parse in Python 3.11. A naive value is interpreted as UTC and stamped as
    such, because sending it bare is what produced the 400.
    """
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"

    parsed = datetime.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return parsed.isoformat()


class CalendarCreateInput(BaseModel):
    summary: str = Field(min_length=1, max_length=500, description="Title of the event")
    start_time: str = Field(
        description="Start time in ISO 8601, e.g. '2026-09-05T10:00:00Z' or "
        "'2026-09-05T10:00:00+02:00'. A value with no offset is read as UTC."
    )
    end_time: str = Field(description="End time in ISO 8601, same format as start_time")
    description: str | None = Field(default="", max_length=8000)


class CalendarCreateTool(BaseTool):
    name: str = "calendar_create"
    description: str = "Create a new event in the primary calendar."
    args_schema: type[BaseModel] = CalendarCreateInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: str = "",
    ) -> str:
        try:
            start = normalise_datetime(start_time)
            end = normalise_datetime(end_time)
        except ValueError:
            return (
                "Could not create the event: start_time and end_time must be ISO 8601 "
                "timestamps such as '2026-09-05T10:00:00Z'."
            )

        start_dt = datetime.datetime.fromisoformat(start)
        end_dt = datetime.datetime.fromisoformat(end)
        if end_dt <= start_dt:
            # Google accepts this and creates a zero- or negative-length event
            # that renders as a point on the calendar. Refuse it here.
            return "Could not create the event: end_time must be after start_time."
        if end_dt - start_dt > MAX_EVENT_DURATION:
            return (
                f"Could not create the event: it would span "
                f"{(end_dt - start_dt).days} days. Confirm the dates."
            )

        try:
            event = self.calendar_service.create_event(
                {
                    "summary": summary,
                    "description": description or "",
                    "start": {"dateTime": start},
                    "end": {"dateTime": end},
                }
            )
            if not event:
                return "Could not create the event: Google Calendar is not authenticated."
            return f"Event created: {event.get('htmlLink', '(no link returned)')}"
        except Exception as exc:
            return tool_error("create the event", exc)


class CalendarListInput(BaseModel):
    max_results: int = Field(default=10, ge=1, le=50, description="Max number of events to list")


class CalendarListTool(BaseTool):
    name: str = "calendar_list"
    description: str = (
        "List events starting from now, in chronological order, from the primary calendar."
    )
    args_schema: type[BaseModel] = CalendarListInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(self, max_results: int = 10) -> str:
        try:
            events = self.calendar_service.list_events(max_results=max_results)
            if not events:
                return "No upcoming events found."

            lines: list[str] = []
            for event in events:
                # A cancelled instance of a recurring event has no "start".
                # Indexing it raised KeyError, which the old blanket handler
                # turned into "Error listing events: 'start'".
                start = event.get("start") or {}
                when = start.get("dateTime") or start.get("date") or "(no start time)"
                lines.append(f"{when}: {event.get('summary', 'No Title')}")

            return "\n".join(lines)
        except Exception as exc:
            return tool_error("list calendar events", exc)


class CalendarUpdateInput(BaseModel):
    event_id: str = Field(min_length=1, description="ID of the event to update")
    summary: str | None = Field(None, description="New title of the event")
    description: str | None = Field(None, description="New description of the event")
    start_time: str | None = Field(None, description="New start time, ISO 8601")
    end_time: str | None = Field(None, description="New end time, ISO 8601")


class CalendarUpdateTool(BaseTool):
    name: str = "calendar_update"
    description: str = "Update an existing event in the calendar."
    args_schema: type[BaseModel] = CalendarUpdateInput
    calendar_service: CalendarService = Field(default_factory=CalendarService)

    def _run(
        self,
        event_id: str,
        summary: str | None = None,
        description: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        updates: dict = {}
        if summary:
            updates["summary"] = summary
        # `is not None` rather than truthiness: clearing a description by
        # passing "" was silently dropped before.
        if description is not None:
            updates["description"] = description

        try:
            if start_time:
                updates["start"] = {"dateTime": normalise_datetime(start_time)}
            if end_time:
                updates["end"] = {"dateTime": normalise_datetime(end_time)}
        except ValueError:
            return "Could not update the event: times must be ISO 8601 timestamps."

        if not updates:
            return "No updates provided."

        try:
            updated = self.calendar_service.update_event(event_id, updates)
            if not updated:
                return "Could not update the event: Google Calendar is not authenticated."
            return f"Event updated: {updated.get('htmlLink', '(no link returned)')}"
        except Exception as exc:
            return tool_error("update the event", exc)
