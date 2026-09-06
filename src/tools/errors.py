"""
What a tool says when it fails.

Every tool used to end with::

    except Exception as e:
        return f"Error reading emails: {str(e)}"

The returned string goes into the model's context and usually into the reply
the user reads. ``str(e)`` on a ``googleapiclient.errors.HttpError`` renders the
full request URI -- path, query string and all -- and Notion's ``APIResponseError``
renders the raw response body. So an authorisation failure answered the user
with the internals of the request that failed.

This module keeps the detail in the logs, where it is useful, and hands the
model a short sentence plus a correlation id.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)

_ADVICE = {
    401: "the stored Google credentials are no longer valid; re-run authentication",
    403: "the account is not permitted to do that, or the OAuth scope is missing",
    404: "the item was not found",
    429: "the API rate limit was hit; try again shortly",
}


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    status = getattr(getattr(exc, "resp", None), "status", None)
    if isinstance(status, int):
        return status
    if isinstance(status, str) and status.isdigit():
        return int(status)
    return None


def tool_error(action: str, exc: BaseException) -> str:
    """
    Log the exception in full; return a sentence safe to put in a prompt.

    ``action`` reads as the end of "Could not {action}" -- e.g. "read emails".
    """
    correlation_id = uuid.uuid4().hex[:8]
    # exc_info=exc, not logger.exception(): the latter reads the *ambient*
    # exception, which is only set inside an active except block. Called from
    # a helper like this one it logs "NoneType: None" and the detail -- the
    # entire reason this function exists -- is lost.
    logger.error("tool failure [%s] while trying to %s", correlation_id, action, exc_info=exc)

    status = _status_of(exc)
    reason = _ADVICE.get(status) if status else None
    if reason is None:
        reason = "the request failed"

    return f"Could not {action}: {reason} (ref {correlation_id})."
