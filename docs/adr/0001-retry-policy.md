# ADR 0001 — Retries are opt-out for writes, and only transient errors qualify

**Status:** accepted

## Context

`retry_with_backoff` was applied to every service method, including
`CalendarService.create_event` and `NotionService.create_page`. It caught bare
`Exception` and retried three times with 1s, 2s and 4s sleeps.

Two separate problems.

**Non-idempotent writes.** When a create request reaches the server and the
*response* is lost — a read timeout, a dropped connection, a proxy hiccup — the
record exists. Retrying creates a second one. Three retries on a flapping link
produced up to four copies of one meeting. Neither the Google Calendar API nor
the Notion API accepts a client-supplied request id, so there is no way to
deduplicate after the fact.

**Permanent errors.** A 401 (bad credentials), a 403 (missing scope), a 404 (no
such event) and `ValueError("Notion Database ID is not set.")` were each
retried three times before the caller saw the error they were always going to
get. That is seven seconds of sleeping to reach a conclusion available
immediately.

## Decision

Two rules.

1. `is_retryable(exc)` returns true only for a recognised transient signal: an
   HTTP status in {408, 429, 500, 502, 503, 504}, or a transport exception
   (`TimeoutError`, `ConnectionError`, `OSError`). **Anything unrecognised is
   permanent.** Defaulting the other way is what produced the sleeping-on-a-401
   behaviour.

2. `retry_with_backoff(idempotent=False)` disables retrying entirely, and every
   method that creates or sends carries it: `create_event`, `update_event`,
   `create_page`, `update_page`, `send_message`.

## Consequences

A create that fails on a genuinely transient error now surfaces to the user
instead of silently succeeding on the second attempt. That is the trade we
want: a human deciding whether to re-book a meeting is cheap, and a duplicate
in someone's calendar is expensive and easy to miss.

`update_event` is included even though a repeated PATCH with the same body is
idempotent in effect. It is grouped with the writes because the reasoning is
about intent, and because splitting the rule invites the next person to
mis-classify a method.

An AST test (`tests/test_helpers.py`) asserts the flag is present on each of
those five methods, so dropping it fails CI rather than silently restoring the
old behaviour.
