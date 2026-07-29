"""Per-request / per-task correlation context.

A `ContextVar` is the async equivalent of thread-local storage: each request
handled by the event loop sees its own value, and anything awaited from within
that request inherits it. That lets a log line emitted five layers deep in the
service layer carry the request ID without every function signature growing a
`request_id` parameter.

The same variables are bound by Celery task wrappers, so a collection run can be
traced from the HTTP call that triggered it through to the delivery it produced.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_actor_id: ContextVar[str | None] = ContextVar("actor_id", default=None)


def get_request_id() -> str | None:
    """Correlation ID of the request or task currently being handled."""
    return _request_id.get()


def set_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_actor_id() -> str | None:
    """ID of the authenticated user driving the current request, if any."""
    return _actor_id.get()


def set_actor_id(value: str | None) -> Token[str | None]:
    return _actor_id.set(value)


def reset_actor_id(token: Token[str | None]) -> None:
    _actor_id.reset(token)
