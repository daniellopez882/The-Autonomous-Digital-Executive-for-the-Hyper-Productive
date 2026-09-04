"""
Preflight.

What ``main()`` did before: constructed three service objects in three try
blocks, logged "<name> Core initialized." after each, then printed "Nexus
initialization complete. Systems at 100%."

Nothing in that path could fail. ``GmailService()`` allocates an object;
``get_service()`` -- the call that authenticates -- was never made.
``NotionService()`` built ``Client(auth="")`` with no key and that counted as
success. So on a machine with no credentials at all, the program answered "is
this configured?" with "Systems at 100%", while constructing the orchestrator
on that same machine raised.
"""

from __future__ import annotations

import ast
import pathlib

from src import main as main_module
from src.main import EXIT_FAILED_CHECKS, EXIT_OK, CheckResult, report

ROOT = pathlib.Path(__file__).resolve().parents[1]


def ok(name="x", required=True):
    return CheckResult(name, True, required, "fine")


def bad(name="x", required=True):
    return CheckResult(name, False, required, "broken")


class TestExitCodes:
    def test_all_checks_passing_exits_zero(self):
        assert report([ok("a"), ok("b")]) == EXIT_OK

    def test_a_failed_required_check_exits_non_zero(self):
        """The old main() had no way to signal failure at all."""
        assert report([ok("a"), bad("b")]) == EXIT_FAILED_CHECKS

    def test_a_failed_optional_check_still_exits_zero(self):
        """Google OAuth not yet granted is a degraded start, not a broken one."""
        assert report([ok("a"), bad("b", required=False)]) == EXIT_OK

    def test_several_failures_are_all_reported(self, caplog):
        with caplog.at_level("ERROR"):
            report([bad("a"), bad("b")])
        assert "2 required check(s) failed" in caplog.text
        assert "a" in caplog.text and "b" in caplog.text


class TestChecksCanFail:
    def test_the_model_check_fails_without_a_key(self, monkeypatch):
        monkeypatch.setattr("src.agents.llm.settings.GEMINI_API_KEY", "")
        result = main_module.check_model()
        assert result.ok is False
        assert "GEMINI_API_KEY" in result.detail

    def test_the_notion_check_fails_without_a_key(self, monkeypatch):
        monkeypatch.setattr("src.services.notion_service.settings.NOTION_DATABASE_ID", "")
        result = main_module.check_notion()
        assert result.ok is False

    def test_the_settings_check_names_what_is_missing(self, monkeypatch):
        monkeypatch.setattr("src.main.settings.GEMINI_API_KEY", "")
        result = main_module.check_settings()
        assert result.ok is False
        assert "GEMINI_API_KEY" in result.detail

    def test_a_google_check_without_a_token_is_not_required(self):
        class NoAuth:
            def get_service(self, interactive=True):
                return None

        result = main_module.check_google("gmail", NoAuth())
        assert result.ok is False
        assert result.required is False
        assert "--authorize" in result.detail

    def test_a_google_check_does_not_open_a_browser(self):
        """A preflight that blocks on a consent screen is not a preflight."""
        seen = {}

        class Recorder:
            def get_service(self, interactive=True):
                seen["interactive"] = interactive
                return None

        main_module.check_google("gmail", Recorder())
        assert seen["interactive"] is False

    def test_an_exception_in_a_check_is_a_failure_not_a_crash(self):
        class Boom:
            def get_service(self, interactive=True):
                raise RuntimeError("network unreachable")

        result = main_module.check_google("gmail", Boom())
        assert result.ok is False
        assert "RuntimeError" in result.detail


class TestNoUnconditionalSuccess:
    def test_the_module_makes_no_unconditional_success_claim(self):
        """
        Asserted on string literals in the AST rather than on the file text, so
        the paragraph above explaining the old behaviour cannot satisfy it.
        """
        tree = ast.parse((ROOT / "src" / "main.py").read_text(encoding="utf-8"))

        # Docstrings are string literals too, and the module docstring above
        # quotes the old message in order to explain it. Exclude them by node
        # identity rather than by value.
        docstring_nodes = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
                continue
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

        code_literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_nodes
        ]

        assert code_literals, "no string literals found; the test is not checking anything"
        assert not any("100%" in text for text in code_literals)
        assert not any("Systems at" in text for text in code_literals)

    def test_preflight_returns_a_result_per_dependency(self, monkeypatch):
        monkeypatch.setattr(
            "src.main.check_google",
            lambda name, service: CheckResult(name, True, False, "stubbed"),
        )
        names = {result.name for result in main_module.preflight()}
        assert {"configuration", "gemini", "notion", "gmail", "calendar"} <= names


class TestCli:
    def test_check_exits_non_zero_when_a_required_check_fails(self, monkeypatch):
        monkeypatch.setattr("src.main.preflight", lambda: [bad("gemini")])
        assert main_module.main(["--check"]) == EXIT_FAILED_CHECKS

    def test_check_exits_zero_when_everything_passes(self, monkeypatch):
        monkeypatch.setattr("src.main.preflight", lambda: [ok("gemini")])
        assert main_module.main(["--check"]) == EXIT_OK

    def test_ask_is_not_reached_when_preflight_fails(self, monkeypatch):
        """Routing a request through a broken configuration produces a
        traceback, not an answer."""
        monkeypatch.setattr("src.main.preflight", lambda: [bad("gemini")])

        def explode(*args, **kwargs):
            raise AssertionError("a request was routed despite a failed preflight")

        monkeypatch.setattr("src.agents.orchestrator.MasterOrchestrator.route_request", explode)
        assert main_module.main(["--ask", "hello"]) == EXIT_FAILED_CHECKS
