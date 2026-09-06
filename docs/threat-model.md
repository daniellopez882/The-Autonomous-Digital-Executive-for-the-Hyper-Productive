# Threat model

Scope: this repository as it runs — a single-user CLI on the user's own
machine, or in a container the user runs. There is no server, no HTTP surface
and no multi-tenancy.

## What it holds

| Asset | Where | Why it matters |
|---|---|---|
| Google OAuth refresh token | `credentials/token.json` | Grants `gmail.readonly`, `gmail.send`, `calendar.events` until revoked. Sending mail as the user is the worst of these. |
| Google OAuth client secret | `credentials/credentials.json` | Lets an attacker run the consent flow as this application. |
| Gemini API key | `.env` | Billable. |
| Notion integration token | `.env` | Read/write on the connected database. |
| Mail contents | in memory, in the model's context | Third-party text, and the user's own. |

Both `credentials/` and `.env` are gitignored, and a CI job fails if either is
ever tracked.

## Trust boundaries

```
  user ─────────────▶ CLI              trusted
  Gemini ───────────▶ CLI              semi-trusted: shapes tool calls
  Gmail message body ▶ model context   UNTRUSTED: written by anyone
  Notion page text ──▶ model context   semi-trusted: the user wrote it
```

The one that matters is the third. Anyone who can email the user can put text
in front of the model.

## Threats

### T1 — Prompt injection from email into outbound mail *(highest)*

**Path.** Attacker emails the user → `gmail_read` puts the body into the
model's context → the body asks for a reply containing what the model has read
→ `notification_send` sends it.

**Controls.**
- `notification_send` is attached to no agent; `create_email_agent` holds only
  `GmailReadTool`. A test asserts this on the AST.
- `NOTIFICATION_ALLOWED_RECIPIENTS` is an exact-match allowlist, empty by
  default. No wildcard, no domain-suffix matching.
- Message bodies are prefixed with an explicit "this is third-party text"
  marker and truncated.

**Residual.** The marker is a hint to the model, not a boundary — it can be
argued past. The allowlist is the real control, and it bounds *who* can be
reached, not *what* is said. If an operator adds a recipient, an injected
message can still cause attacker-chosen content to go to that address. See
[ADR 0003](adr/0003-outbound-mail.md).

### T2 — Prompt injection into calendar and Notion writes

**Path.** Same entry, different exit: an injected instruction asks for an event
or a task to be created.

**Controls.** Bounded, not prevented. `calendar_create` validates timestamps,
refuses `end <= start`, and refuses anything spanning more than 30 days.
`daily_summary` fences gathered text in `<data>` and tells the synthesis step
not to follow instructions inside it.

**Residual.** A plausible-looking event or task can still be created. There is
no human approval step. For a single-user tool over the user's own calendar,
the blast radius is a spurious entry the user will see.

### T3 — Token theft from the local filesystem

**Path.** Another account on the machine, or another process, reads
`credentials/token.json`.

**Controls.** The file is created with `os.open(..., 0o600)` — restrictive from
the moment it exists, rather than widened after the secret is on disk — and
`chmod` is re-applied. The container runs as uid 10001, and `credentials/` is a
mounted volume, never baked into a layer.

**Residual.** Anything running as the same user can read it. This is the normal
limit of a desktop OAuth application. Rotate at
<https://myaccount.google.com/permissions> if the file is ever exposed.

### T4 — Over-broad OAuth scope

The previous version requested `https://www.googleapis.com/auth/calendar`,
which also grants deleting calendars and reading ACLs. Nothing in the code
needs that. The scope list is now `gmail.readonly`, `gmail.send`,
`calendar.events`, and a test asserts the broad `calendar` scope is absent.

`gmail.send` remains, because a tool sends mail. It is the widest grant in the
list; T1 is the reason it is guarded the way it is.

### T5 — Provider error text reaching the user

`str()` of a `googleapiclient.HttpError` renders the full request URI including
its query string; Notion's error renders the raw response body. Every tool used
to return that string to the model, and from there usually to the user.

`src/tools/errors.py` logs the exception with `exc_info` and returns a sentence
plus an 8-character correlation id. An AST test asserts no handler in
`src/tools` or `src/agents` returns a value that renders the caught exception as
text.

### T6 — Unbounded input filling the context window

One large newsletter could occupy the whole context and push the user's actual
request out of it. Snippets are capped at 500 characters, headers at 200, and
`max_results` at 50 by the tool schema.

### T7 — Supply chain

`requirements.txt` previously carried no version constraints, so an install
resolved to whatever PyPI served that day. It also omitted `langgraph`, which
every agent imports directly — that import worked only because `langchain` 1.x
happens to depend on it. Everything is now pinned exactly, and `pip-audit` runs
in CI.

## Not addressed

- No secret manager. Keys live in `.env`, appropriate for a single-user CLI and
  not for anything shared.
- No audit log of tool calls. If an injected instruction did create an event,
  there is no record beyond application logs.
- No rate limiting on model spend.
- The token is not encrypted at rest beyond filesystem permissions.
