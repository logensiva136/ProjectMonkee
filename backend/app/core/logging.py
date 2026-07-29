"""Structured logging (SPEC §2, §10).

Everything — application logs, uvicorn access logs, SQLAlchemy warnings, Celery
output — is routed through a single structlog pipeline so the output stream is
uniformly JSON in production and readable colour in development.

Secrets must never reach a log line (SPEC §10). `_redact` drops values whose key
looks sensitive; it is a backstop, not a licence to log credentials.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.config import Settings
from app.core.context import get_actor_id, get_request_id

# Substrings that mark a value as unsafe to emit.
_SENSITIVE_HINTS = (
    "password",
    "token",
    "secret",
    "authorization",
    "api_key",
    "apikey",
    "credential",
    "totp",
    "cookie",
)

_REDACTED = "***redacted***"


def _redact(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Blank out values whose key suggests they hold a secret."""
    for key in list(event_dict):
        lowered = key.lower()
        if any(hint in lowered for hint in _SENSITIVE_HINTS) and event_dict[key] is not None:
            event_dict[key] = _REDACTED
    return event_dict


def _add_correlation(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    """Attach the ambient request/actor IDs to every line."""
    request_id = get_request_id()
    if request_id:
        event_dict.setdefault("request_id", request_id)
    actor_id = get_actor_id()
    if actor_id:
        event_dict.setdefault("actor_id", actor_id)
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Install the structlog pipeline and route stdlib logging into it.

    Safe to call more than once (the API process and the Celery process each call
    it at start-up; tests call it per session).
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Processors applied to events originating from structlog loggers.
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_correlation,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _redact,
    ]

    structlog.configure(
        processors=[
            *shared,
            # Hands the event dict to the stdlib formatter below rather than
            # rendering here, so structlog and stdlib records share one format.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # Applied only to records that came from stdlib logging, bringing them
        # up to parity with structlog-native events before rendering.
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # uvicorn installs its own handlers; clearing them prevents double output.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.app.trace"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # These are chatty at INFO and say nothing we do not already log ourselves.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger. Prefer module-level `log = get_logger(__name__)`."""
    return structlog.stdlib.get_logger(name)
