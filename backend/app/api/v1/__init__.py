"""API v1 router aggregation.

One router module per domain (SPEC §11). Register each here; `create_app`
mounts only this aggregate, so adding a domain is a one-line change in one file.
"""

from fastapi import APIRouter

from app.api.v1 import audit, auth, collection, health, me, roles, settings, setup, users

api_router = APIRouter()

# System first: probes must resolve before anything that could shadow them.
api_router.include_router(health.router)
api_router.include_router(setup.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(audit.router)
api_router.include_router(settings.router)
api_router.include_router(collection.router)

__all__ = ["api_router"]
