"""
Notion response parsing.

The listing tool read the API response with direct indexing. Two of those
indexes raise on shapes Notion returns routinely.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.notion_service import NotionService
from src.tools.notion_tools import (
    NotionCreateTaskTool,
    NotionListTasksTool,
    NotionUpdateTaskTool,
    rich_text_to_plain,
)


class FakeNotionService(NotionService):
    def __init__(self, results=None, error=None):
        super().__init__()
        self.created = None
        self.updated = None
        self._results = results if results is not None else []
        self._error = error

    def create_page(self, properties):
        if self._error:
            raise self._error
        self.created = properties
        return {"id": "page-1"}

    def query_database(self, query=None):
        if self._error:
            raise self._error
        self.last_query = query
        return {"results": self._results}

    def update_page(self, page_id, properties):
        if self._error:
            raise self._error
        self.updated = (page_id, properties)
        return {"id": page_id}


def page(title_items, status=None):
    props = {"Name": {"title": title_items}}
    if status is not None:
        props["Status"] = status
    return {"properties": props}


class TestRichText:
    def test_plain_typed_text(self):
        assert rich_text_to_plain([{"plain_text": "Ship the release"}]) == "Ship the release"

    def test_a_mention_has_no_text_content_key(self):
        """
        title_list[0]['text']['content'] raised KeyError on a mention. Notion
        allows mentions, dates and equations inside a title.
        """
        items = [{"type": "mention", "plain_text": "@Daniel", "mention": {"type": "user"}}]
        assert rich_text_to_plain(items) == "@Daniel"

    def test_segments_are_joined(self):
        items = [{"plain_text": "Review "}, {"plain_text": "the PR"}]
        assert rich_text_to_plain(items) == "Review the PR"

    def test_a_legacy_text_shape_still_works(self):
        assert rich_text_to_plain([{"text": {"content": "legacy"}}]) == "legacy"

    def test_an_empty_title_is_empty(self):
        assert rich_text_to_plain([]) == ""

    def test_junk_items_are_skipped(self):
        assert rich_text_to_plain([None, "x", {"plain_text": "kept"}]) == "kept"


class TestList:
    def test_a_mention_in_a_title_does_not_break_the_listing(self):
        results = [
            page([{"type": "mention", "plain_text": "@Daniel"}]),
            page([{"plain_text": "Ship it"}]),
        ]
        result = NotionListTasksTool(notion_service=FakeNotionService(results))._run()
        assert "@Daniel" in result
        assert "Ship it" in result

    def test_an_unset_select_does_not_raise(self):
        """
        {"select": None} is what Notion returns for an unset select.
        .get('select', {}).get('name') then called .get on None.
        """
        results = [page([{"plain_text": "Task"}], status={"select": None})]
        result = NotionListTasksTool(notion_service=FakeNotionService(results))._run()
        assert "Task" in result
        assert "Unset" in result

    def test_a_page_with_no_properties_does_not_raise(self):
        """page['properties'] raised KeyError on any non-page object returned."""
        results = [{"object": "page"}, page([{"plain_text": "Real"}])]
        result = NotionListTasksTool(notion_service=FakeNotionService(results))._run()
        assert "Real" in result

    def test_a_status_type_property_is_read(self):
        """Notion's newer 'status' property type is distinct from 'select'."""
        results = [page([{"plain_text": "T"}], status={"status": {"name": "In progress"}})]
        assert (
            "In progress" in NotionListTasksTool(notion_service=FakeNotionService(results))._run()
        )

    def test_an_empty_database_says_so(self):
        assert NotionListTasksTool(notion_service=FakeNotionService([]))._run() == "No tasks found."

    def test_a_status_filter_is_sent(self):
        service = FakeNotionService([])
        NotionListTasksTool(notion_service=service)._run(status_filter="Done")
        assert service.last_query["filter"]["select"]["equals"] == "Done"

    def test_a_missing_setting_names_the_setting(self):
        service = FakeNotionService(error=ValueError("NOTION_DATABASE_ID is not set."))
        assert "NOTION_DATABASE_ID" in NotionListTasksTool(notion_service=service)._run()

    def test_an_api_failure_does_not_leak_the_response(self, http_error):
        service = FakeNotionService(error=http_error(403))
        result = NotionListTasksTool(notion_service=service)._run()
        assert "SECRET" not in result
        assert "googleapis.com" not in result


class TestCreate:
    def test_a_task_is_created(self):
        service = FakeNotionService()
        assert "page-1" in NotionCreateTaskTool(notion_service=service)._run("Buy milk")
        assert service.created["Name"]["title"][0]["text"]["content"] == "Buy milk"

    def test_an_empty_title_is_rejected_by_the_schema(self):
        from src.tools.notion_tools import NotionCreateTaskInput

        with pytest.raises(ValidationError):
            NotionCreateTaskInput(title="")


class TestUpdate:
    def test_no_fields_means_no_call(self):
        service = FakeNotionService()
        assert NotionUpdateTaskTool(notion_service=service)._run("page-1") == "No updates provided."
        assert service.updated is None

    def test_a_status_change_is_sent(self):
        service = FakeNotionService()
        NotionUpdateTaskTool(notion_service=service)._run("page-1", status="Done")
        assert service.updated[1]["Status"]["select"]["name"] == "Done"
