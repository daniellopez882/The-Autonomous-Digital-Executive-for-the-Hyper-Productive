"""
Notion.

``__init__`` built ``Client(auth=self.auth_manager.api_key)`` unconditionally.
With ``NOTION_API_KEY`` unset that is ``Client(auth="")`` -- an object that
constructs happily and fails on first use, which is why ``main()`` was able to
log "Notion Core initialized." on a machine with no Notion credentials at all.
The client is now built lazily and refuses to build without a key.

``create_page`` was retried. Creating a task twice because a response was lost
is a data defect, not a transient one.
"""

from __future__ import annotations

import logging

from notion_client import Client

from src.services.auth_service import NotionAuthManager
from src.utils.config import settings
from src.utils.helpers import retry_with_backoff

logger = logging.getLogger(__name__)


class NotionService:
    def __init__(
        self,
        auth_manager: NotionAuthManager | None = None,
        client: Client | None = None,
    ) -> None:
        self.auth_manager = auth_manager or NotionAuthManager()
        self.database_id = settings.NOTION_DATABASE_ID
        self._client = client

    @property
    def configured(self) -> bool:
        return self.auth_manager.configured and bool(self.database_id.strip())

    @property
    def client(self) -> Client:
        if self._client is None:
            if not self.auth_manager.configured:
                raise ValueError("NOTION_API_KEY is not set. The Notion client cannot be built.")
            self._client = Client(auth=self.auth_manager.api_key)
        return self._client

    def _require_database(self) -> None:
        if not self.database_id.strip():
            raise ValueError("NOTION_DATABASE_ID is not set.")

    @retry_with_backoff(retries=3, idempotent=False)
    def create_page(self, properties: dict) -> dict:
        """Create a task. Never retried: a retry duplicates the task."""
        self._require_database()
        return self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
        )

    @retry_with_backoff(retries=3)
    def query_database(self, query: dict | None = None) -> dict:
        self._require_database()
        return self.client.databases.query(database_id=self.database_id, **(query or {}))

    @retry_with_backoff(retries=3, idempotent=False)
    def update_page(self, page_id: str, properties: dict) -> dict:
        return self.client.pages.update(page_id=page_id, properties=properties)
