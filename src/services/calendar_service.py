"""
Google Calendar.

The headline defect was in ``list_events``. It passed ``orderBy="startTime"``
and ``singleEvents=True`` but no ``timeMin``, so the Calendar API returned
events from the beginning of the calendar's history. The tool built on it is
described to the model as "List upcoming events", and the agent presented the
result as the user's schedule -- so a calendar with any history answered
"what's on today?" with its ten *oldest* entries.

``create_event`` was also wrapped in a retry that treated it as idempotent. It
is not: a lost response on a create leaves the event on the server, and the
retry books it again.
"""

from __future__ import annotations

import datetime
import logging

from googleapiclient.discovery import build

from src.services.auth_service import GoogleAuthManager
from src.utils.config import settings
from src.utils.helpers import retry_with_backoff

logger = logging.getLogger(__name__)


class CalendarService:
    def __init__(self, auth_manager: GoogleAuthManager | None = None) -> None:
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.service = None

    def get_service(self, *, interactive: bool = True):
        if not self.service:
            creds = self.auth_manager.authenticate(interactive=interactive)
            if creds:
                self.service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return self.service

    @retry_with_backoff(retries=3)
    def list_events(
        self,
        max_results: int = 10,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> list[dict]:
        """
        Events starting at or after ``time_min`` (default: now).

        ``time_min`` is what makes this "upcoming". Without it the API orders
        from the earliest event the calendar has ever held.
        """
        service = self.get_service()
        if not service:
            return []

        now = datetime.datetime.now(datetime.UTC)
        start = time_min or now.isoformat()
        end = (
            time_max
            or (now + datetime.timedelta(days=settings.CALENDAR_LOOKAHEAD_DAYS)).isoformat()
        )

        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start,
                timeMax=end,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return response.get("items", [])

    @retry_with_backoff(retries=3, idempotent=False)
    def create_event(self, event_body: dict) -> dict | None:
        """
        Create an event. Never retried -- see ``retry_with_backoff``.

        A retry after a lost response books the meeting twice, and nothing in
        this API lets us tell the two cases apart.
        """
        service = self.get_service()
        if not service:
            return None
        return service.events().insert(calendarId="primary", body=event_body).execute()

    @retry_with_backoff(retries=3, idempotent=False)
    def update_event(self, event_id: str, event_body: dict) -> dict | None:
        """
        Apply a partial update.

        The previous implementation issued a ``get`` and then a full ``update``
        (a PUT) with the merged body. Between those two calls any change made
        elsewhere -- a guest replying, another client editing -- was read into
        the local copy and written straight back, silently reverting it. ``patch``
        sends only the changed fields and lets the server do the merge.
        """
        service = self.get_service()
        if not service:
            return None
        return (
            service.events()
            .patch(calendarId="primary", eventId=event_id, body=event_body)
            .execute()
        )
