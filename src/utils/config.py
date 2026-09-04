"""
Configuration.

The previous version declared pydantic fields whose *defaults* were
``os.getenv(...)`` calls evaluated at class-definition time. That makes
``BaseSettings`` redundant -- it reads the environment itself -- and it means
the values are frozen at first import, so a test that sets an environment
variable after importing anything gets the old value.

It also validated nothing. Every key could be the empty string and the program
would start anyway: ``NotionService`` built ``Client(auth="")`` and reported
"Notion Core initialized."
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Google retired the ``gemini-pro`` alias that was hardcoded in four places.
DEFAULT_MODEL = "gemini-2.5-flash"

_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    ENVIRONMENT: str = "development"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    NOTION_API_KEY: str = ""
    NOTION_DATABASE_ID: str = ""
    GEMINI_API_KEY: str = ""

    # Was hardcoded as "gemini-pro" in the orchestrator and all three agents.
    GEMINI_MODEL: str = DEFAULT_MODEL

    LOG_LEVEL: str = "INFO"

    # Paths the OAuth flow reads and writes. The token file holds a refresh
    # token for gmail.send and full calendar access.
    GOOGLE_CREDENTIALS_PATH: str = "credentials/credentials.json"
    GOOGLE_TOKEN_PATH: str = "credentials/token.json"  # noqa: S105 - a path, not a secret

    # Calendar reads were unbounded in the past direction; see
    # CalendarService.list_events.
    CALENDAR_LOOKAHEAD_DAYS: int = Field(default=30, ge=1, le=365)

    # notification_send can email anyone. Empty means the tool is unavailable.
    NOTIFICATION_ALLOWED_RECIPIENTS: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    @property
    def allowed_recipients(self) -> frozenset[str]:
        raw = self.NOTIFICATION_ALLOWED_RECIPIENTS
        return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())

    @model_validator(mode="after")
    def _normalise(self) -> Settings:
        level = self.LOG_LEVEL.strip().upper()
        if level not in _LOG_LEVELS:
            raise ValueError(
                f"LOG_LEVEL={self.LOG_LEVEL!r} is not one of {sorted(_LOG_LEVELS)}. "
                "logging.basicConfig raised on this at startup."
            )
        object.__setattr__(self, "LOG_LEVEL", level)
        return self

    def missing(self, *, notion: bool = True, gemini: bool = True) -> list[str]:
        """Names of the credentials that are absent for the requested surfaces."""
        gaps: list[str] = []
        if gemini and not self.GEMINI_API_KEY.strip():
            gaps.append("GEMINI_API_KEY")
        if notion and not self.NOTION_API_KEY.strip():
            gaps.append("NOTION_API_KEY")
        if notion and not self.NOTION_DATABASE_ID.strip():
            gaps.append("NOTION_DATABASE_ID")
        return gaps

    def validate_production(self) -> None:
        """Refuse to start production on a configuration that cannot work."""
        problems = [f"{name} is not set." for name in self.missing()]
        if problems:
            raise ValueError("Invalid production configuration:\n  - " + "\n  - ".join(problems))


settings = Settings()
