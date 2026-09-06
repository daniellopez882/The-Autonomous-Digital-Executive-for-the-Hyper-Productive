"""
The calendar defect a user would actually notice.

``list_events`` asked for ``orderBy="startTime"`` with ``singleEvents=True`` and
no ``timeMin``. The Calendar API then orders from the first event the calendar
has ever contained. The tool built on this call is described to the model as
listing upcoming events, so "what's on today?" was answered with the ten oldest
entries in the account.
"""

from __future__ import annotations

import datetime

import pytest

from src.services.calendar_service import CalendarService


class FakeEvents:
    """Records the kwargs the service passes to the Calendar API."""

    def __init__(self, items=None):
        self.list_kwargs = None
        self.insert_kwargs = None
        self.patch_kwargs = None
        self.update_called = False
        self.get_called = False
        self._items = items if items is not None else []

    def list(self, **kwargs):
        self.list_kwargs = kwargs
        return _Exec({"items": self._items})

    def insert(self, **kwargs):
        self.insert_kwargs = kwargs
        return _Exec({"id": "evt-1", "htmlLink": "https://calendar.example/evt-1"})

    def patch(self, **kwargs):
        self.patch_kwargs = kwargs
        return _Exec({"id": kwargs.get("eventId"), "htmlLink": "https://calendar.example/x"})

    def update(self, **kwargs):
        self.update_called = True
        return _Exec({})

    def get(self, **kwargs):
        self.get_called = True
        return _Exec({"summary": "existing", "description": "written by someone else"})


class _Exec:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeApi:
    def __init__(self, events):
        self._events = events

    def events(self):
        return self._events


@pytest.fixture
def service():
    def build(items=None):
        events = FakeEvents(items)
        svc = CalendarService()
        svc.service = FakeApi(events)
        return svc, events

    return build


class TestListEventsIsUpcoming:
    def test_a_time_lower_bound_is_sent(self, service):
        """Without timeMin the API returns the calendar's oldest events."""
        svc, events = service()
        svc.list_events()
        assert "timeMin" in events.list_kwargs

    def test_the_lower_bound_is_now_not_the_epoch(self, service):
        svc, events = service()
        before = datetime.datetime.now(datetime.UTC)
        svc.list_events()
        sent = datetime.datetime.fromisoformat(events.list_kwargs["timeMin"])
        assert sent >= before - datetime.timedelta(seconds=5)

    def test_the_lower_bound_is_timezone_aware(self, service):
        """A naive timeMin is rejected by the API with a 400."""
        svc, events = service()
        svc.list_events()
        assert datetime.datetime.fromisoformat(events.list_kwargs["timeMin"]).tzinfo is not None

    def test_an_upper_bound_bounds_the_window(self, service):
        svc, events = service()
        svc.list_events()
        assert "timeMax" in events.list_kwargs
        low = datetime.datetime.fromisoformat(events.list_kwargs["timeMin"])
        high = datetime.datetime.fromisoformat(events.list_kwargs["timeMax"])
        assert high > low

    def test_ordering_is_still_chronological(self, service):
        svc, events = service()
        svc.list_events()
        assert events.list_kwargs["orderBy"] == "startTime"
        assert events.list_kwargs["singleEvents"] is True

    def test_an_explicit_time_min_is_honoured(self, service):
        svc, events = service()
        svc.list_events(time_min="2026-01-01T00:00:00+00:00")
        assert events.list_kwargs["timeMin"] == "2026-01-01T00:00:00+00:00"

    def test_items_are_returned(self, service):
        svc, _ = service([{"summary": "standup"}])
        assert svc.list_events() == [{"summary": "standup"}]

    def test_no_service_yields_an_empty_list(self):
        svc = CalendarService()
        svc.service = None
        svc.auth_manager = type("A", (), {"authenticate": lambda self, **k: None})()
        assert svc.list_events() == []


class TestUpdateUsesPatch:
    def test_update_does_not_read_then_overwrite(self, service):
        """
        The old path was get() then update() with the merged body -- a full PUT.
        A change made between the two calls was read into the local copy and
        written straight back, reverting it.
        """
        svc, events = service()
        svc.update_event("evt-1", {"summary": "new title"})
        assert events.patch_kwargs is not None
        assert events.update_called is False
        assert events.get_called is False

    def test_only_the_changed_fields_are_sent(self, service):
        svc, events = service()
        svc.update_event("evt-1", {"summary": "new title"})
        assert events.patch_kwargs["body"] == {"summary": "new title"}


class TestCreateIsNotRetried:
    def test_a_lost_response_does_not_book_the_event_twice(self, service, no_sleep, monkeypatch):
        svc, _ = service()
        attempts = {"n": 0}

        class Boom:
            def events(self_inner):
                class E:
                    def insert(self_e, **kwargs):
                        class X:
                            def execute(self_x):
                                attempts["n"] += 1
                                raise TimeoutError("response lost")

                        return X()

                return E()

        svc.service = Boom()
        with pytest.raises(TimeoutError):
            svc.create_event({"summary": "one meeting"})
        assert attempts["n"] == 1, "the create was retried; the meeting is now booked twice"
