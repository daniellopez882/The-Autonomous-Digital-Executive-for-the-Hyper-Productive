"""
Settings.

Fields were declared as ``os.getenv(...)`` defaults evaluated at class-definition
time, and nothing was validated. Every credential could be empty and the
program started anyway.
"""

from __future__ import annotations

import pytest

from src.utils.config import DEFAULT_MODEL, Settings


def build(**overrides) -> Settings:
    base = {
        "GEMINI_API_KEY": "k",
        "NOTION_API_KEY": "n",
        "NOTION_DATABASE_ID": "d",
        "_env_file": None,  # do not read the developer's .env during tests
    }
    base.update(overrides)
    return Settings(**base)


class TestLogLevel:
    @pytest.mark.parametrize("level", ["debug", "INFO", "Warning", "error", "CRITICAL"])
    def test_a_valid_level_is_normalised_to_upper_case(self, level):
        assert level.upper() == build(LOG_LEVEL=level).LOG_LEVEL

    def test_an_invalid_level_is_refused_at_load(self):
        """logging.basicConfig(level="VERBOSE") raises at startup; catch it here."""
        with pytest.raises(ValueError, match="LOG_LEVEL"):
            build(LOG_LEVEL="VERBOSE")


class TestMissingCredentials:
    def test_a_complete_configuration_reports_nothing_missing(self):
        assert build().missing() == []

    def test_an_empty_gemini_key_is_missing(self):
        assert "GEMINI_API_KEY" in build(GEMINI_API_KEY="").missing()

    def test_whitespace_is_not_a_credential(self):
        assert "GEMINI_API_KEY" in build(GEMINI_API_KEY="   ").missing()

    def test_a_notion_key_without_a_database_id_is_incomplete(self):
        assert "NOTION_DATABASE_ID" in build(NOTION_DATABASE_ID="").missing()

    def test_notion_can_be_excluded_from_the_check(self):
        assert build(NOTION_API_KEY="").missing(notion=False) == []

    def test_production_validation_raises_and_lists_every_gap(self):
        with pytest.raises(ValueError) as excinfo:
            build(GEMINI_API_KEY="", NOTION_API_KEY="").validate_production()
        message = str(excinfo.value)
        assert "GEMINI_API_KEY" in message
        assert "NOTION_API_KEY" in message

    def test_production_validation_passes_when_complete(self):
        build().validate_production()


class TestEnvironment:
    def test_the_default_is_not_production(self):
        assert build().is_production is False

    @pytest.mark.parametrize("value", ["production", "PRODUCTION", " Production "])
    def test_production_is_recognised_however_it_is_written(self, value):
        assert build(ENVIRONMENT=value).is_production is True


class TestModel:
    def test_the_default_model_is_not_the_retired_alias(self):
        """gemini-pro was hardcoded in four places and no longer resolves."""
        assert DEFAULT_MODEL != "gemini-pro"
        assert build().GEMINI_MODEL == DEFAULT_MODEL

    def test_the_model_is_configurable(self):
        assert build(GEMINI_MODEL="gemini-2.0-flash").GEMINI_MODEL == "gemini-2.0-flash"


class TestRecipientAllowlist:
    def test_the_default_is_empty(self):
        assert build().allowed_recipients == frozenset()

    def test_a_comma_separated_list_is_parsed(self):
        allowed = build(NOTIFICATION_ALLOWED_RECIPIENTS="a@x.com, b@y.com").allowed_recipients
        assert allowed == frozenset({"a@x.com", "b@y.com"})

    def test_entries_are_lowercased(self):
        assert "a@x.com" in build(NOTIFICATION_ALLOWED_RECIPIENTS="A@X.CoM").allowed_recipients

    def test_empty_entries_are_dropped(self):
        parsed = build(NOTIFICATION_ALLOWED_RECIPIENTS="a@x.com,,  ,").allowed_recipients
        assert parsed == frozenset({"a@x.com"})


class TestLookahead:
    def test_the_default_window_is_bounded(self):
        assert 1 <= build().CALENDAR_LOOKAHEAD_DAYS <= 365

    @pytest.mark.parametrize("value", [0, -1, 400])
    def test_an_out_of_range_window_is_refused(self, value):
        with pytest.raises(ValueError):
            build(CALENDAR_LOOKAHEAD_DAYS=value)
