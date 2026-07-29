"""SQLAlchemy models.

Every model module must be imported here. Alembic's autogenerate only sees
tables that have been registered on `Base.metadata` by import time, so a model
that is not reachable from this file silently produces an empty migration — or
worse, a migration that drops the tables it cannot see.
"""

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.identity import AppSetting, AuditLog, RecoveryCode, RefreshToken, User
from app.models.rbac import Panel, Permission, Role, RolePanel, RolePermission, UserRole

__all__ = [
    "AppSetting",
    "AuditLog",
    "Base",
    "Panel",
    "Permission",
    "RecoveryCode",
    "RefreshToken",
    "Role",
    "RolePanel",
    "RolePermission",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "utcnow",
]
