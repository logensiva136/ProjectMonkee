"""SQLAlchemy models.

Every model module must be imported here. Alembic's autogenerate only sees
tables that have been registered on `Base.metadata` by import time, so a model
that is not reachable from this file silently produces an empty migration.
"""

from app.models.base import Base

__all__ = ["Base"]
