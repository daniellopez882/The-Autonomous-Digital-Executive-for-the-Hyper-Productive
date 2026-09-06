"""
What a failing tool tells the model.

Every tool ended with ``return f"Error ...: {str(e)}"``. That string becomes
model context and usually reaches the user. ``str()`` of a googleapiclient
``HttpError`` renders the full request URI including its query string.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from src.tools.errors import tool_error

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestMessage:
    def test_the_exception_text_is_not_included(self, http_error):
        exc = http_error(403, uri="https://www.googleapis.com/gmail/v1/x?key=AIzaSyLEAKED")
        message = tool_error("read emails", exc)
        assert "AIzaSyLEAKED" not in message
        assert "googleapis.com" not in message

    def test_the_action_is_named(self, http_error):
        assert "read emails" in tool_error("read emails", http_error(500))

    def test_a_reference_is_included(self, http_error):
        assert "ref " in tool_error("read emails", http_error(500))

    def test_each_failure_gets_its_own_reference(self, http_error):
        first = tool_error("read emails", http_error(500))
        second = tool_error("read emails", http_error(500))
        assert first != second

    @pytest.mark.parametrize(
        "status,phrase",
        [
            (401, "re-run authentication"),
            (403, "not permitted"),
            (404, "not found"),
            (429, "rate limit"),
        ],
    )
    def test_known_statuses_get_actionable_advice(self, status, phrase, http_error):
        assert phrase in tool_error("do the thing", http_error(status))

    def test_an_unknown_error_still_produces_a_message(self):
        assert "Could not" in tool_error("do the thing", RuntimeError("opaque"))

    def test_the_full_detail_is_logged(self, caplog, http_error):
        """The detail is not discarded -- it goes where an operator can read it."""
        with caplog.at_level("ERROR"):
            tool_error("read emails", http_error(403, uri="https://x/y?key=SEEN_IN_LOG"))
        assert "SEEN_IN_LOG" in caplog.text


class TestNoToolReturnsRawExceptionText:
    def test_no_tool_interpolates_an_exception_into_its_return(self):
        """
        Guard against the pattern coming back. Asserted on the AST: inside an
        ``except`` handler in src/tools or src/agents, a ``return`` whose value
        renders the caught exception as text -- an f-string containing it, or
        ``str(exc)``.

        Passing the exception to ``tool_error(action, exc)`` is the intended
        path and is not flagged: that function logs the detail and returns a
        redacted sentence.

        ``except ValueError`` is also permitted. Those are raised by this
        codebase with a message naming a missing setting; nothing in them comes
        from a provider.
        """
        offenders: list[str] = []
        for path in sorted(
            list((ROOT / "src" / "tools").rglob("*.py"))
            + list((ROOT / "src" / "agents").rglob("*.py"))
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
                if handler.name is None or _catches_only(handler, "ValueError"):
                    continue
                for node in ast.walk(handler):
                    if (
                        isinstance(node, ast.Return)
                        and node.value is not None
                        and _renders_exception(node.value, handler.name)
                    ):
                        offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, f"exception text returned to the model at: {offenders}"


def _catches_only(handler: ast.ExceptHandler, name: str) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == name


def _mentions(node: ast.AST, name: str) -> bool:
    return any(isinstance(inner, ast.Name) and inner.id == name for inner in ast.walk(node))


def _renders_exception(value: ast.AST, name: str) -> bool:
    """Whether ``value`` turns the exception bound to ``name`` into text."""
    for node in ast.walk(value):
        # f"...{exc}..."
        if isinstance(node, ast.JoinedStr) and _mentions(node, name):
            return True
        # str(exc), "{}".format(exc), repr(exc)
        if isinstance(node, ast.Call):
            func = node.func
            named = isinstance(func, ast.Name) and func.id in {"str", "repr"}
            formatted = isinstance(func, ast.Attribute) and func.attr == "format"
            if (named or formatted) and any(_mentions(arg, name) for arg in node.args):
                return True
        # "..." % exc
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Mod)
            and _mentions(node.right, name)
        ):
            return True
    return False
