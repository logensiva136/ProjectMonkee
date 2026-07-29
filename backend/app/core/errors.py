"""RFC 7807 `application/problem+json` error handling (SPEC §7).

Every error the API emits — raised deliberately, raised by FastAPI, or entirely
unexpected — leaves as the same JSON shape, carrying the request ID so a user
report can be tied straight to a log line.

Service code raises the `AppError` subclasses below; routers do not build error
responses by hand.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id
from app.core.logging import get_logger

log = get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
_PROBLEM_BASE = "https://hayabusa.invalid/problems"


class AppError(Exception):
    """Base class for errors that map onto a deliberate HTTP response."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    title: str = "Internal Server Error"
    problem_type: str = "internal-error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        self.detail = detail or self.title
        self.headers = headers or {}
        self.extra = extra
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    title = "Bad Request"
    problem_type = "bad-request"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Unauthorized"
    problem_type = "unauthorized"


class ForbiddenError(AppError):
    """Authenticated, but lacking the permission the endpoint declares (SPEC §6.3)."""

    status_code = status.HTTP_403_FORBIDDEN
    title = "Forbidden"
    problem_type = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Not Found"
    problem_type = "not-found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    title = "Conflict"
    problem_type = "conflict"


class SetupRequiredError(AppError):
    """Raised while the instance has not been onboarded (SPEC §6.1)."""

    status_code = status.HTTP_409_CONFLICT
    title = "Setup Required"
    problem_type = "setup-required"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(
            detail or "This instance has not been set up yet. Complete onboarding at /setup.",
            **extra,
        )


class SetupAlreadyCompleteError(AppError):
    """Raised by `/setup/*` once onboarding has happened — permanently gone (SPEC §6.1)."""

    status_code = status.HTTP_410_GONE
    title = "Gone"
    problem_type = "setup-already-complete"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        super().__init__(detail or "Setup has already been completed.", **extra)


class UnprocessableError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    title = "Unprocessable Entity"
    problem_type = "unprocessable"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    title = "Too Many Requests"
    problem_type = "rate-limited"

    def __init__(self, detail: str | None = None, *, retry_after: int | None = None, **extra: Any):
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
        super().__init__(detail, headers=headers, retry_after=retry_after, **extra)


class ServiceUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    title = "Service Unavailable"
    problem_type = "service-unavailable"


# --------------------------------------------------------------------------- #
# Response construction
# --------------------------------------------------------------------------- #

_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    410: "Gone",
    413: "Payload Too Large",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    problem_type: str = "about:blank",
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    type_uri = problem_type if problem_type == "about:blank" else f"{_PROBLEM_BASE}/{problem_type}"
    body: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    request_id = get_request_id() or getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    body.update({key: value for key, value in extra.items() if value is not None})

    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the problem+json handlers. Called once from `create_app`."""

    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app_error", problem=exc.problem_type, detail=exc.detail, exc_info=exc)
        else:
            log.info("app_error", problem=exc.problem_type, status=exc.status_code)
        return problem_response(
            request,
            status_code=exc.status_code,
            title=exc.title,
            detail=exc.detail,
            problem_type=exc.problem_type,
            headers=exc.headers,
            **exc.extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = _TITLES.get(exc.status_code, "Error")
        return problem_response(
            request,
            status_code=exc.status_code,
            title=title,
            detail=str(exc.detail) if exc.detail else title,
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Flatten Pydantic's error list into something a UI can bind to fields.
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or str(error["loc"][0]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation Error",
            detail="The request body or parameters failed validation.",
            problem_type="validation-error",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        # Log the traceback, but never leak internals to the caller.
        log.exception("unhandled_exception", path=request.url.path, method=request.method)
        return problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            detail="An unexpected error occurred. The request ID identifies it in the logs.",
            problem_type="internal-error",
        )
