# ADR 0002 — One place builds the chat model

**Status:** accepted

## Context

`ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=settings.GEMINI_API_KEY)`
appeared four times: in `MasterOrchestrator.__init__` and in each of the three
agent factories.

Three consequences.

- `gemini-pro` is a retired alias. Changing it meant four edits; missing one
  left a live path calling a model that no longer resolves.
- Construction required a real API key, eagerly. `MasterOrchestrator()` built
  four model clients and every tool before doing anything, so instantiating it
  at all needed Gemini, Google and Notion credentials simultaneously. This is
  why the repository's only test asserted that a constructor sets an attribute:
  nothing else could be constructed without secrets.
- The key was read from a settings object frozen at import time.

## Decision

`src/agents/llm.py` holds `get_chat_model()`. Everything else calls it. The
model name comes from `settings.GEMINI_MODEL`.

`set_model_factory(factory)` installs a replacement, and the test suite uses it
with `GenericFakeChatModel`. This is the seam, and it is deliberately a module
global rather than constructor injection: the agent factories are called from
`create_react_agent`, several frames below anything a test can reach.

`MasterOrchestrator` also builds its sub-agents lazily, on first route to them.
A user who has configured Notion but not Google can still use the task agent.

## Consequences

202 tests, none of which need a credential or a network. `LLMNotConfigured`
carries a message naming the setting and the URL to get a key, rather than a
pydantic `ValidationError` about an internal field.

The module global means a test that forgets to reset it leaks into the next
one. An autouse fixture in `conftest.py` clears it after every test.
