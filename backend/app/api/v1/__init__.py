"""API v1 router aggregation.

One router module per domain (SPEC §11). Register each here; `create_app`
mounts only this aggregate, so adding a domain is a one-line change in one file.
"""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)

__all__ = ["api_router"]
