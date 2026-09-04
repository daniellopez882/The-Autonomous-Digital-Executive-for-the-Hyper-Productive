"""
Calendar tool input handling.

The create tool sent ``{"dateTime": start_time}`` verbatim. Google rejects a
dateTime that carries neither an offset nor a sibling ``timeZone`` field, and
a model asked for "tomorrow at 10am" writes ``2026-09-05T10:00:00`` far more
often than the Z-suffixed form the field description shows.
"""

from __future__ import annotations

import datetime

import pytest

from src.services.calendar_service import CalendarService
from src.tools.calendar_tools import (
    CalendarCreateTool,
    CalendarListTool,
    CalendarUpdateTool,
    normalise_datetime,
)


class FakeCalendarService(CalendarService):
    """Subclasses the real service: the tool fields are typed, and a stand-in
    that does not satisfy the type would not prove the tool wiring works."""

    def __init__(self, events=None, error=None):
        super().__init__()
        self.created = None
        self.updated = None
        self._events = events if events is not None else []
        self._error = error

    def create_event(self, body):
        if self._error:
            raise self._error
        self.created = body
        return {"htmlLink": "https://calendar.example/evt"}

    def list_events(self, max_results=10):
        if self._error:
            raise self._error
        return self._events

    def update_event(self, event_id, body):
        if self._error:
            raise self._error
        self.updated = (event_id, body)
        return {"htmlLink": "https://calendar.example/evt"}


class TestNormaliseDatetime:
    def test_a_naive_timestamp_gains_an_offset(self):
        """This is the input that produced a 400 from the API."""
        result = normalise_datetime("2026-09-05T10:00:00")
        assert datetime.datetime.fromisoformat(result).tzinfo is not None

    def test_a_naive_timestamp_is_read_as_utc(self):
        parsed = datetime.datetime.fromisoformat(normalise_datetime("2026-09-05T10:00:00"))
        assert parsed.utcoffset() == datetime.timedelta(0)

    def test_a_trailing_z_is_accepted(self):
        parsed = datetime.datetime.fromisoformat(normalise_datetime("2026-09-05T10:00:00Z"))
        assert parsed.utcoffset() == datetime.timedelta(0)

    def test_a_lowercase_z_is_accepted(self):
        assert normalise_datetime("2026-09-05T10:00:00z")

    def test_an_explicit_offset_is_preserved(self):
        parsed = datetime.datetime.fromisoformat(normalise_datetime("2026-09-05T10:00:00+02:00"))
        assert parsed.utcoffset() == datetime.timedelta(hours=2)

    @pytest.mark.parametrize("bad", ["", "   ", "tomorrow", "10am", "2026-13-45T99:00:00"])
    def test_unparseable_values_raise(self, bad):
        with pytest.raises(ValueError):
            normalise_datetime(bad)


class TestCreate:
    def _tool(self, **kwargs):
        service = FakeCalendarService(**kwargs)
        return CalendarCreateTool(calendar_service=service), service

    def test_the_sent_start_time_carries_an_offset(self):
        tool, service = self._tool()
        tool._run("Standup", "2026-09-05T10:00:00", "2026-09-05T10:30:00")
        assert "+00:00" in service.created["start"]["dateTime"]

    def test_a_junk_timestamp_gives_a_usable_message(self):
        tool, service = self._tool()
        result = tool._run("Standup", "tomorrow at 10", "later")
        assert "ISO 8601" in result
        assert service.created is None, "an unparseable time still reached the API"

    def test_an_end_before_the_start_is_refused(self):
        tool, service = self._tool()
        result = tool._run("Standup", "2026-09-05T11:00:00Z", "2026-09-05T10:00:00Z")
        assert "after start_time" in result
        assert service.created is None

    def test_a_zero_length_event_is_refused(self):
        tool, _ = self._tool()
        assert "after start_time" in tool._run(
            "Standup", "2026-09-05T10:00:00Z", "2026-09-05T10:00:00Z"
        )

    def test_an_implausibly_long_event_is_refused(self):
        """A model mis-parsing a year gives a multi-month block on the calendar."""
        tool, service = self._tool()
        result = tool._run("Standup", "2026-09-05T10:00:00Z", "2027-09-05T10:00:00Z")
        assert "Confirm the dates" in result
        assert service.created is None

    def test_the_link_is_returned_on_success(self):
        tool, _ = self._tool()
        assert "https://calendar.example/evt" in tool._run(
            "Standup", "2026-09-05T10:00:00Z", "2026-09-05T10:30:00Z"
        )

    def test_an_api_failure_does_not_leak_the_request_uri(self, http_error):
        tool, _ = self._tool(error=http_error(403))
        result = tool._run("Standup", "2026-09-05T10:00:00Z", "2026-09-05T10:30:00Z")
        assert "googleapis.com" not in result
        assert "SECRET" not in result


class TestList:
    def test_an_event_with_no_start_does_not_break_the_listing(self):
        """
        A cancelled instance of a recurring event has no "start". event['start']
        raised KeyError, which surfaced as "Error listing events: 'start'" and
        lost every other event in the response.
        """
        events = [
            {"summary": "cancelled instance"},
            {"start": {"dateTime": "2026-09-05T10:00:00Z"}, "summary": "standup"},
        ]
        tool = CalendarListTool(calendar_service=FakeCalendarService(events=events))
        result = tool._run()
        assert "standup" in result
        assert "cancelled instance" in result

    def test_an_all_day_event_uses_its_date(self):
        events = [{"start": {"date": "2026-09-05"}, "summary": "holiday"}]
        tool = CalendarListTool(calendar_service=FakeCalendarService(events=events))
        assert "2026-09-05: holiday" in tool._run()

    def test_an_event_with_no_summary_is_still_listed(self):
        events = [{"start": {"dateTime": "2026-09-05T10:00:00Z"}}]
        tool = CalendarListTool(calendar_service=FakeCalendarService(events=events))
        assert "No Title" in tool._run()

    def test_an_empty_calendar_says_so(self):
        tool = CalendarListTool(calendar_service=FakeCalendarService(events=[]))
        assert tool._run() == "No upcoming events found."

    def test_the_tool_description_matches_what_it_returns(self):
        """
        The description said "List upcoming events" while the service returned
        the oldest ones. The model has only the description to go on.
        """
        assert "from now" in CalendarListTool().description


class TestUpdate:
    def test_clearing_a_description_is_sent(self):
        """`if description:` dropped an empty string, so a description could
        never be cleared -- the tool reported success and changed nothing."""
        service = FakeCalendarService()
        tool = CalendarUpdateTool(calendar_service=service)
        tool._run("evt-1", description="")
        assert service.updated[1] == {"description": ""}

    def test_no_fields_means_no_call(self):
        service = FakeCalendarService()
        tool = CalendarUpdateTool(calendar_service=service)
        assert tool._run("evt-1") == "No updates provided."
        assert service.updated is None

    def test_a_bad_time_is_refused_before_the_call(self):
        service = FakeCalendarService()
        tool = CalendarUpdateTool(calendar_service=service)
        assert "ISO 8601" in tool._run("evt-1", start_time="whenever")
        assert service.updated is None
