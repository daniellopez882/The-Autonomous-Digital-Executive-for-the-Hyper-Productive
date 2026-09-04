"""Stand-ins for third-party objects, so no test needs a network or a credential."""

from __future__ import annotations


class HttpErrorLike(Exception):
    """A googleapiclient.errors.HttpError without needing the real class.

    The real one renders the full request URI -- query string included -- in
    ``str(e)``. That is exactly what src/tools/errors.py exists to keep out of
    the model's context, so this stand-in does the same.
    """

    def __init__(self, status: int, uri: str = "https://www.googleapis.com/x?key=SECRET"):
        class _Resp:
            def __init__(self, value):
                self.status = value

        self.resp = _Resp(status)
        self.uri = uri
        super().__init__(f"<HttpError {status} when requesting {uri} returned 'denied'>")
