"""Gmail reads and sends."""

from __future__ import annotations

import logging

from googleapiclient.discovery import build

from src.services.auth_service import GoogleAuthManager
from src.utils.helpers import retry_with_backoff

logger = logging.getLogger(__name__)


class GmailService:
    def __init__(self, auth_manager: GoogleAuthManager | None = None) -> None:
        self.auth_manager = auth_manager or GoogleAuthManager()
        self.service = None

    def get_service(self, *, interactive: bool = True):
        if not self.service:
            creds = self.auth_manager.authenticate(interactive=interactive)
            if creds:
                # cache_discovery writes to the working directory and warns
                # under any non-oauth2client credentials.
                self.service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self.service

    @retry_with_backoff(retries=3)
    def list_messages(self, query: str = "", max_results: int = 10) -> list[dict]:
        service = self.get_service()
        if not service:
            return []
        response = (
            service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
        )
        return response.get("messages", [])

    @retry_with_backoff(retries=3)
    def get_message(self, msg_id: str) -> dict | None:
        service = self.get_service()
        if not service:
            return None
        return service.users().messages().get(userId="me", id=msg_id).execute()

    @retry_with_backoff(retries=3, idempotent=False)
    def send_message(self, raw_message: str) -> dict | None:
        """
        Send. Never retried: a retry on a lost response sends the mail twice.

        Unlike a duplicated calendar event, a duplicated send cannot be undone.
        """
        service = self.get_service()
        if not service:
            return None
        return service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
