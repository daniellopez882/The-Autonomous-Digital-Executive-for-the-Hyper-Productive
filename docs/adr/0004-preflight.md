# ADR 0004 — The entry point is a preflight that can fail

**Status:** accepted

## Context

`main()` in full:

```python
try:
    gmail_service = GmailService()
    logger.info("Gmail Core initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Gmail Core: {e}")
# ... the same for Calendar and Notion ...
logger.info("Nexus initialization complete. Systems at 100%.")
```

None of it touched a network, a credential or a model. `GmailService()` only
allocates an object; `get_service()` — the call that authenticates — was never
made. `NotionService()` built `Client(auth="")` when the key was unset, and
that counted as success. The three locals were never read again.

Verified on a machine with no credentials: it printed "Systems at 100%",
while `MasterOrchestrator()` on that same machine raised a `ValidationError`.

An unconditional success signal is worse than none. It answers "is this
configured correctly?" with "yes", always, and the person reading it has no
reason to look further.

## Decision

`preflight()` returns a `list[CheckResult]`, one per dependency. Each check
does something that can fail:

| Check | What it does | Required |
|---|---|:-:|
| `configuration` | names every unset credential | yes |
| `gemini` | builds a chat model | yes |
| `notion` | builds the API client, which refuses an empty key | yes |
| `gmail` | authenticates, `interactive=False` | no |
| `calendar` | authenticates, `interactive=False` | no |

`report()` exits `1` when any required check fails. Google is optional: a
missing OAuth token is a degraded start, not a broken one, and the message says
how to fix it (`--authorize`).

`interactive=False` matters. A preflight that opens a browser and waits for a
consent screen is not a preflight — it hangs in a container.

The same command is the container `HEALTHCHECK` and runs twice in CI: once with
no credentials, asserting a non-zero exit, and once with credentials, asserting
zero.

## Consequences

A test asserts, on the AST's string literals, that no code path in `main.py`
contains "100%" or "Systems at" — excluding docstrings by node identity, so the
paragraph in the module docstring that quotes the old message does not satisfy
its own guard.

`--check` is now the first thing the README tells a new user to run.
