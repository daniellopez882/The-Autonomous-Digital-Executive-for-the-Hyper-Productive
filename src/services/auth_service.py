"""
Google OAuth and Notion auth.

Three defects, all in the handling of ``credentials/token.json`` -- the file
that holds a refresh token granting ``gmail.send`` and full calendar access:

1. The directory it is written to is in ``.gitignore`` and therefore never
   exists on a fresh checkout. ``open(self.token_path, "w")`` raised
   ``FileNotFoundError`` *after* the browser consent completed, so the user
   granted access, lost the token, and had to consent again on every run.

2. It was written with the process umask, normally ``0644`` -- readable by
   every account on the machine. It is now created ``0600``.

3. ``Credentials.from_authorized_user_file`` was called without a guard. A
   truncated or hand-edited token file raised ``ValueError``/``JSONDecodeError``
   out of ``authenticate()``, and the only recovery was to know to delete the
   file. A malformed token is now discarded and the consent flow re-runs.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from src.utils.config import settings

logger = logging.getLogger(__name__)

# gmail.send is here because notification_agent.py sends mail. It is the widest
# grant in the list: anything holding this token can send as the user.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleAuthManager:
    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> None:
        self.credentials_path = Path(credentials_path or settings.GOOGLE_CREDENTIALS_PATH)
        self.token_path = Path(token_path or settings.GOOGLE_TOKEN_PATH)
        self.creds: Credentials | None = None

    # -- token file -----------------------------------------------------------

    def _load_token(self) -> Credentials | None:
        if not self.token_path.exists():
            return None
        try:
            return Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            logger.warning(
                "Token file at %s is unreadable (%s); discarding it and re-authenticating.",
                self.token_path,
                type(exc).__name__,
            )
            return None

    def _save_token(self, creds: Credentials) -> None:
        """Write the token 0600, creating its directory if needed."""
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

        # Create with restrictive permissions rather than widening them after
        # the secret is already on disk.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.token_path, flags, stat.S_IRUSR | stat.S_IWUSR)
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            os.close(fd)
            raise
        with handle:
            handle.write(creds.to_json())

        try:
            os.chmod(self.token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover - filesystems without POSIX modes
            logger.debug("Could not set 0600 on %s", self.token_path)

    # -- flow -----------------------------------------------------------------

    def authenticate(self, *, interactive: bool = True) -> Credentials | None:
        """
        Return usable credentials, or ``None`` when none can be obtained.

        ``interactive=False`` never opens a browser. Servers and CI use it: the
        old code would block forever on ``run_local_server`` waiting for a
        consent that nobody was there to give.
        """
        self.creds = self._load_token()

        if self.creds and self.creds.valid:
            return self.creds

        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_token(self.creds)
                return self.creds
            except Exception as exc:
                logger.warning(
                    "Token refresh failed (%s); falling back to consent.", type(exc).__name__
                )
                self.creds = None

        if not self.credentials_path.exists():
            logger.warning(
                "OAuth client file not found at %s; Google APIs are unavailable.",
                self.credentials_path,
            )
            return None

        if not interactive:
            logger.warning(
                "No valid token at %s and interactive consent is disabled.",
                self.token_path,
            )
            return None

        flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
        self.creds = flow.run_local_server(port=0)

        # Save before returning. The previous order let a write failure discard
        # a consent the user had just granted.
        self._save_token(self.creds)
        return self.creds


class NotionAuthManager:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.NOTION_API_KEY

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
