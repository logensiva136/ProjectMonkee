"""Shared Celery task plumbing: the async bridge and the instrumented base task.

**The async bridge.** Celery tasks are ordinary synchronous functions, but the
database layer is async. The naive fix — `asyncio.run(...)` inside each task —
is wrong here: `asyncio.run` creates and then *closes* a fresh event loop every
call, while SQLAlchemy's connection pool holds connections bound to the loop that
opened them. The second task in a worker would find its pooled connections
attached to a closed loop and fail. So each worker process keeps one long-lived
loop, and `run_async` drives coroutines on it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import reset_request_id, set_request_id
from app.core.logging import get_logger
from app.core.metrics import TASK_DURATION, TASK_RUNS
from app.db import get_sessionmaker

log = get_logger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def get_loop() -> asyncio.AbstractEventLoop:
    """The worker process's persistent event loop."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from synchronous task code, preserving its return type."""
    return get_loop().run_until_complete(coro)


def close_loop() -> None:
    """Tear the loop down on worker shutdown."""
    global _loop
    if _loop is not None and not _loop.is_closed():
        _loop.close()
    _loop = None


@asynccontextmanager
async def session_context() -> AsyncIterator[AsyncSession]:
    """Transactional session for task code.

    Mirrors the `get_session` FastAPI dependency: commit on success, roll back on
    exception, always close.

        async def _work() -> int:
            async with session_context() as session:
                ...
        run_async(_work())
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


class AppTask(Task):
    """Base task adding correlation IDs, timing metrics and structured logging.

    Registered as the Celery app's `Task` class, so every task gets this without
    opting in.
    """

    # Retry defaults; individual tasks override where SPEC §8 demands otherwise.
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True  # spread retries so failures do not resynchronise
    max_retries = 3

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # `self.request.id` is the Celery task ID; reusing it as the correlation
        # ID means log lines from the task join up with the run that scheduled it.
        token = set_request_id(self.request.id)
        started = time.perf_counter()
        outcome = "success"

        log.info("task_started", task=self.name, task_id=self.request.id)
        try:
            return super().__call__(*args, **kwargs)
        except Exception as exc:
            outcome = "failure"
            log.error("task_failed", task=self.name, error=str(exc), exc_info=exc)
            raise
        finally:
            duration = time.perf_counter() - started
            TASK_DURATION.labels(self.name, outcome).observe(duration)
            TASK_RUNS.labels(self.name, outcome).inc()
            if outcome == "success":
                log.info(
                    "task_finished",
                    task=self.name,
                    duration_ms=round(duration * 1000, 2),
                )
            reset_request_id(token)
