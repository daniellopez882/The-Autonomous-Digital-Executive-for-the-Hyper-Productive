# ADR 0003 — An allowlist in code, not an instruction in a prompt, guards outbound mail

**Status:** accepted

## Context

The repository contains two tools that, together, form a complete data path out
of the user's account:

- `gmail_read` takes message text written by arbitrary senders and places it in
  the model's context.
- `notification_send` sends mail as the user, to whatever address the model
  produces.

The previous `NotificationSendTool._run` passed `recipient` straight to
`messages().send`. Nothing checked it.

The attack needs no access at all. An attacker emails the user. The body becomes
model context on the next read. If both tools are on the same agent, text in
that body can ask for a reply carrying whatever the model has read.

The tool was, in fact, wired to nothing — `create_email_agent` only had
`GmailReadTool`. That is luck, not a control. Nothing recorded the reason, so
the next person adding "let the agent notify me" would wire it up.

## Decision

**`NOTIFICATION_ALLOWED_RECIPIENTS`**, an exact-match allowlist, empty by
default — so the tool is off until an operator turns it on. Matching is on the
full lowercased address. There is no wildcard.

Domain-suffix matching (`@example.com`) is deliberately not offered. It reads
as a safe rule right up to the first attacker-registered lookalike, and a
tested refusal of `owner@example.com.evil.example` is worth more than the
convenience.

**The tool stays unattached.** `create_email_agent` does not import it, and a
test asserts that — on the AST, so a comment naming the tool cannot satisfy it.

Both controls are in code. A prompt instruction ("only send to the user") is
precisely what an injected message overrides, so it cannot be the control.

## Consequences

Someone who genuinely wants agent-sent notifications must set an environment
variable naming each recipient, and must attach the tool themselves. That is
friction on purpose: it is the point where the exfiltration path gets opened,
and it should require a decision.

The allowlist does not prevent an injected message from causing a *legitimate*
recipient to receive attacker-chosen content. It bounds who can be reached, not
what can be said. Bounding content would need a review step that does not exist
here.
