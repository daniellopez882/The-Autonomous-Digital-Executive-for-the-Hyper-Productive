"""
The OAuth token file.

``credentials/token.json`` holds a refresh token for ``gmail.send`` and
calendar write access. Anyone who reads that file can send mail as the user
until it is revoked.
"""

from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from src.services.auth_service import SCOPES, GoogleAuthManager, NotionAuthManager


class FakeCreds:
    valid = True
    expired = False
    refresh_token = "refresh-token"

    def to_json(self):
        return json.dumps({"token": "access-token", "refresh_token": "refresh-token"})


class TestTokenPersistence:
    def test_the_token_directory_is_created(self, tmp_path):
        """
        credentials/ is in .gitignore, so it never exists on a fresh checkout.
        open(path, "w") raised FileNotFoundError *after* the browser consent
        completed -- the grant was made and then thrown away.
        """
        target = tmp_path / "credentials" / "token.json"
        assert not target.parent.exists()

        GoogleAuthManager(token_path=str(target))._save_token(FakeCreds())
        assert target.exists()

    def test_the_token_is_written(self, tmp_path):
        target = tmp_path / "credentials" / "token.json"
        GoogleAuthManager(token_path=str(target))._save_token(FakeCreds())
        assert json.loads(target.read_text())["refresh_token"] == "refresh-token"

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
    def test_the_token_is_not_group_or_world_readable(self, tmp_path):
        target = tmp_path / "credentials" / "token.json"
        GoogleAuthManager(token_path=str(target))._save_token(FakeCreds())

        mode = stat.S_IMODE(os.stat(target).st_mode)
        assert not mode & (stat.S_IRGRP | stat.S_IROTH), f"mode is {mode:o}, expected 0600"
        assert not mode & (stat.S_IWGRP | stat.S_IWOTH)

    def test_overwriting_an_existing_token_truncates_it(self, tmp_path):
        target = tmp_path / "token.json"
        target.write_text("x" * 5000)
        GoogleAuthManager(token_path=str(target))._save_token(FakeCreds())
        assert len(target.read_text()) < 500


class TestCorruptToken:
    def test_a_truncated_token_file_does_not_raise(self, tmp_path):
        """
        from_authorized_user_file raised out of authenticate() on malformed
        JSON. The only recovery was knowing to delete the file by hand.
        """
        target = tmp_path / "token.json"
        target.write_text('{"token": "abc"')  # truncated

        manager = GoogleAuthManager(
            credentials_path=str(tmp_path / "absent.json"), token_path=str(target)
        )
        assert manager.authenticate(interactive=False) is None

    def test_an_empty_token_file_does_not_raise(self, tmp_path):
        target = tmp_path / "token.json"
        target.write_text("")
        manager = GoogleAuthManager(
            credentials_path=str(tmp_path / "absent.json"), token_path=str(target)
        )
        assert manager.authenticate(interactive=False) is None

    def test_a_token_of_the_wrong_shape_does_not_raise(self, tmp_path):
        target = tmp_path / "token.json"
        target.write_text('{"unrelated": true}')
        manager = GoogleAuthManager(
            credentials_path=str(tmp_path / "absent.json"), token_path=str(target)
        )
        assert manager.authenticate(interactive=False) is None


class TestNonInteractive:
    def test_no_browser_is_opened_when_interactive_is_false(self, tmp_path, monkeypatch):
        """
        A server or CI process calling authenticate() blocked forever on
        run_local_server, waiting for a consent nobody was there to give.
        """
        client_file = tmp_path / "credentials.json"
        client_file.write_text("{}")

        def explode(*args, **kwargs):
            raise AssertionError("the consent flow was started without a browser")

        monkeypatch.setattr(
            "src.services.auth_service.InstalledAppFlow.from_client_secrets_file", explode
        )
        manager = GoogleAuthManager(
            credentials_path=str(client_file), token_path=str(tmp_path / "token.json")
        )
        assert manager.authenticate(interactive=False) is None

    def test_a_missing_client_file_returns_none(self, tmp_path):
        manager = GoogleAuthManager(
            credentials_path=str(tmp_path / "nope.json"),
            token_path=str(tmp_path / "token.json"),
        )
        assert manager.authenticate() is None


class TestScopes:
    def test_send_is_present_because_a_tool_sends_mail(self):
        assert "https://www.googleapis.com/auth/gmail.send" in SCOPES

    def test_the_full_calendar_scope_is_not_requested(self):
        """
        calendar.events is enough for every call this code makes. The broader
        'calendar' scope also grants deleting calendars and reading ACLs.
        """
        assert "https://www.googleapis.com/auth/calendar" not in SCOPES

    def test_gmail_modify_is_not_requested(self):
        assert not any("gmail.modify" in scope for scope in SCOPES)


class TestNotionAuth:
    def test_an_empty_key_is_not_configured(self):
        assert NotionAuthManager(api_key="").configured is False

    def test_whitespace_is_not_a_key(self):
        assert NotionAuthManager(api_key="   ").configured is False

    def test_a_real_key_is_configured(self):
        assert NotionAuthManager(api_key="secret_abc").configured is True

    def test_headers_carry_the_api_version(self):
        headers = NotionAuthManager(api_key="secret_abc").get_headers()
        assert headers["Notion-Version"] == "2022-06-28"
        assert headers["Authorization"] == "Bearer secret_abc"
