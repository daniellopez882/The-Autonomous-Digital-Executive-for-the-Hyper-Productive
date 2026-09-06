"""
Entry point.

What this file used to do, in full: construct three service objects inside
three ``try`` blocks, log "<name> Core initialized." after each, and finish with
"Nexus initialization complete. Systems at 100%."

None of that touched a network, a credential or a model. ``GmailService()`` only
allocates an object -- ``get_service()``, which is what authenticates, was never
called. ``NotionService()`` built ``Client(auth="")`` when the key was unset and
that counted as success too. The three locals it bound were never used again.

So the program's only success signal was unconditional. It printed "Systems at
100%" on a machine with no credentials of any kind, on which constructing the
orchestrator raises. That is worse than no check: it answers the question
"is this configured correctly?" with "yes", always.

``preflight`` replaces it. Every check can fail, failures are counted, and the
process exits non-zero when a required one does -- so a container orchestrator
or a CI job can tell.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from src.agents.llm import LLMNotConfigured, get_chat_model
from src.services.calendar_service import CalendarService
from src.services.gmail_service import GmailService
from src.services.notion_service import NotionService
from src.utils.config import settings

logger = logging.getLogger("nexus")

EXIT_OK = 0
EXIT_FAILED_CHECKS = 1
EXIT_CONFIG = 78  # EX_CONFIG


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    detail: str


def check_settings() -> CheckResult:
    missing = settings.missing()
    if missing:
        return CheckResult("configuration", False, True, "missing: " + ", ".join(missing))
    return CheckResult("configuration", True, True, f"environment={settings.ENVIRONMENT}")


def check_model() -> CheckResult:
    """Build a chat model. Constructing it validates the key's presence and shape."""
    try:
        get_chat_model()
    except LLMNotConfigured as exc:
        return CheckResult("gemini", False, True, str(exc))
    except Exception as exc:
        return CheckResult("gemini", False, True, f"{type(exc).__name__}: {exc}")
    return CheckResult("gemini", True, True, f"model={settings.GEMINI_MODEL}")


def check_google(name: str, service) -> CheckResult:
    """
    Actually authenticate, without opening a browser.

    ``interactive=False`` matters: a preflight that blocks on a consent screen
    is not a preflight.
    """
    try:
        handle = service.get_service(interactive=False)
    except Exception as exc:
        return CheckResult(name, False, False, f"{type(exc).__name__}: {exc}")
    if handle is None:
        return CheckResult(
            name, False, False, "no stored OAuth token; run `python -m src.main --authorize`"
        )
    return CheckResult(name, True, False, "authenticated")


def check_notion() -> CheckResult:
    service = NotionService()
    if not service.configured:
        return CheckResult("notion", False, True, "NOTION_API_KEY or NOTION_DATABASE_ID is unset")
    try:
        service.client  # noqa: B018 - constructing the client is the check
    except Exception as exc:
        return CheckResult("notion", False, True, f"{type(exc).__name__}: {exc}")
    return CheckResult("notion", True, True, "client built")


def preflight() -> list[CheckResult]:
    return [
        check_settings(),
        check_model(),
        check_notion(),
        check_google("gmail", GmailService()),
        check_google("calendar", CalendarService()),
    ]


def report(results: list[CheckResult]) -> int:
    for result in results:
        mark = "ok  " if result.ok else ("FAIL" if result.required else "warn")
        logger.info("%s  %-14s %s", mark, result.name, result.detail)

    failed = [r for r in results if not r.ok and r.required]
    if failed:
        logger.error(
            "%d required check(s) failed: %s",
            len(failed),
            ", ".join(r.name for r in failed),
        )
        return EXIT_FAILED_CHECKS

    degraded = [r for r in results if not r.ok]
    if degraded:
        logger.warning("starting without: %s", ", ".join(r.name for r in degraded))
    logger.info("preflight passed")
    return EXIT_OK


def authorize() -> int:
    """Run the Google consent flow once and store the token."""
    from src.services.auth_service import GoogleAuthManager

    creds = GoogleAuthManager().authenticate(interactive=True)
    if creds is None:
        logger.error("authorization did not complete")
        return EXIT_CONFIG
    logger.info("token stored at %s", settings.GOOGLE_TOKEN_PATH)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus", description="Nexus AI")
    parser.add_argument("--authorize", action="store_true", help="run the Google OAuth flow")
    parser.add_argument("--check", action="store_true", help="run preflight and exit")
    parser.add_argument(
        "--ask", metavar="REQUEST", help="route a single request and print the reply"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    if args.authorize:
        return authorize()

    exit_code = report(preflight())
    if args.check or exit_code != EXIT_OK:
        return exit_code

    if args.ask:
        from src.agents.orchestrator import MasterOrchestrator

        print(MasterOrchestrator().route_request(args.ask))
        return EXIT_OK

    parser.print_help()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
