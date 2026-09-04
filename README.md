# Nexus AI

A LangGraph agent over three personal-productivity surfaces: Gmail (read),
Google Calendar (read/write) and a Notion task database (read/write). A routing
model picks one of three specialist sub-agents, each holding only the tools for
its own surface.

```
  request ──▶ router ──┬──▶ email agent    ──▶ gmail_read
                       ├──▶ calendar agent ──▶ calendar_list / create / update
                       └──▶ task agent     ──▶ notion_list / create / update

  ambiguous ─▶ ask the user which one they meant
```

## Status

Working, and honest about what it is: a single-user CLI. It is not a service,
has no HTTP surface, and has never been deployed anywhere.

| | |
|---|---|
| Tests | 202 collected: 201 pass, 1 skipped on Windows (POSIX file modes). None touch a network or need a credential. |
| Lint | `ruff check` and `ruff format --check`, clean |
| CI | lint + tests on Python 3.11 and 3.12; bandit; container build and run |
| Container | non-root (uid 10001), multi-stage, preflight as HEALTHCHECK |

## Running it

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then fill in GEMINI_API_KEY and the Notion values
python -m src.main --check
```

`--check` runs a preflight over every dependency and **exits non-zero if a
required one is missing**. Run it first; it is the fastest way to find out
what is not configured.

For Gmail and Calendar, download an OAuth client from the Google Cloud console
to `credentials/credentials.json`, then:

```bash
python -m src.main --authorize
```

That opens a browser once and stores a token at `credentials/token.json`, mode
`0600`. **That file is a credential** — it holds a refresh token that can send
mail as you. It is gitignored; keep it that way.

Then ask it something:

```bash
python -m src.main --ask "what is on my calendar this week?"
```

### Container

```bash
docker build -t nexus-ai .
docker run --rm --env-file .env -v "$PWD/credentials:/app/credentials" nexus-ai --check
```

Mount `credentials/` as a volume. Do not copy it into the image — that writes a
refresh token into a layer.

## Configuration

Every setting, its default and what it does: [.env.example](.env.example).
Two worth calling out:

- **`GEMINI_MODEL`** (default `gemini-2.5-flash`). Was hardcoded as
  `gemini-pro` in four separate places; that alias is retired.
- **`NOTIFICATION_ALLOWED_RECIPIENTS`** — **empty by default, which disables
  the send-email tool.** See below.

## The send-email tool

`gmail_read` puts text written by arbitrary senders into the model's context.
`notification_send` sends mail as you. An agent holding both is an
exfiltration path: anyone who can email you can put instructions in front of
the model, and the model has a way to reply with whatever it has read.

Two controls, both in code rather than in a prompt — an injected message
overrides prompt instructions, which is exactly why they cannot live there:

1. `NOTIFICATION_ALLOWED_RECIPIENTS` is an exact-match allowlist. Empty means
   nothing can be sent. There is no wildcard, and no domain-suffix matching.
2. The tool is not attached to any agent. Wiring it to one that also reads mail
   is a decision to make on purpose. A test asserts it is absent from the email
   agent.

## What changed, and why

This started as a prototype. The full list is in the pull request; the four
that mattered most:

**`python -m src.main` could not fail.** It constructed three service objects
inside three `try` blocks, logged `"<name> Core initialized."` after each, and
finished with `"Nexus initialization complete. Systems at 100%."` Nothing in
that path touched a network, a credential or a model — `GmailService()` only
allocates an object, and `get_service()` (which authenticates) was never
called. `NotionService()` built `Client(auth="")` with no key and that counted
as success. So on a machine with no credentials at all it printed "Systems at
100%", while constructing the orchestrator on that same machine raised.

**`calendar_list` returned your oldest events.** `list_events` passed
`orderBy="startTime"` and `singleEvents=True` with no `timeMin`, so the API
ordered from the beginning of the calendar's history. The tool is described to
the model as listing upcoming events, so "what's on today?" was answered with
ten entries from years ago.

**The retry decorator duplicated data.** It caught bare `Exception` and wrapped
`create_event` and `create_page`. Those are non-idempotent: when a request
reaches the server and the *response* is lost, the retry creates the record
again. Three retries on a flapping connection booked the same meeting four
times. It also retried 401s, 403s and `ValueError("Notion Database ID is not
set.")` — three attempts with sleeps before surfacing an error that was never
going to succeed.

**Routing matched substrings.** `if "EMAIL" in decision`, tested first, over
free model text. `"This is not an EMAIL request; route it to CALENDAR."` went
to the email agent. Routing now requires whole-word tokens and refuses to guess
when the answer names more than one.

Also: `langgraph` was imported by every agent and absent from
`requirements.txt` (it resolved only because `langchain` happens to depend on
it); `requirements.txt` carried no version constraints at all; the OAuth token
was written world-readable into a directory that does not exist on a fresh
checkout, so the write failed *after* consent; tool errors returned
`str(exception)` to the model, which for a `googleapiclient.HttpError` renders
the full request URI.

## Design notes

- [ADR 0001 — retries are opt-out for writes](docs/adr/0001-retry-policy.md)
- [ADR 0002 — one place builds the chat model](docs/adr/0002-model-factory.md)
- [ADR 0003 — an allowlist, not a prompt, guards outbound mail](docs/adr/0003-outbound-mail.md)
- [ADR 0004 — the entry point is a preflight](docs/adr/0004-preflight.md)
- [Threat model](docs/threat-model.md)

## Layout

```
src/
  main.py              preflight, --authorize, --ask
  agents/
    llm.py             the one place a chat model is built
    orchestrator.py    routing + the daily_summary workflow
    {email,calendar,task}_agent.py
    notification_agent.py   the send tool; attached to nothing
  services/            Google and Notion clients
  tools/               LangChain tools, and errors.py
  utils/               settings, retry, message flattening
tests/                 202 tests
benchmarks/            routing latency; needs live credentials
```

## Limits

- Single user, single calendar (`primary`), single Notion database.
- No persistence between invocations; each `--ask` starts fresh.
- `benchmarks/bench_routing.py` needs live credentials and is not run in CI, so
  there are no latency figures in this README.
- The routing model is asked for one word and sometimes answers with a
  sentence. That is handled, not solved: an ambiguous answer asks the user.

## Licence

MIT. See [LICENSE](LICENSE).
