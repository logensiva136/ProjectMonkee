"""Roles, permissions and panel visibility (SPEC §5.1, §6.3).

Two separate mechanisms, deliberately not conflated:

* **Permissions** are `resource:action` strings and are the *security* boundary.
  Every mutating endpoint declares one via `Depends(require("vendor:write"))`,
  and the backend enforces it without reference to what the UI shows.
* **Panel visibility** decides which sidebar entries a role sees. It is *UX*.
  Hiding a panel hides a link; it does not protect the endpoints behind it.

SPEC §6.3 is explicit about this: "hiding a panel is UX, not security". Anyone
adding a screen must add both the panel row and the permission dependency.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.identity import User


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single `resource:action` capability, e.g. `vendor:write`.

    Rows are seeded from code, not created by operators — a permission only
    means anything if an endpoint declares it.
    """

    __tablename__ = "permission"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    resource: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")

    roles: Mapped[list[Role]] = relationship(
        secondary="role_permission", back_populates="permissions"
    )


class Role(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A named set of permissions and visible panels.

    `is_system` marks the four seeded roles from SPEC §6.3. They can be
    inspected and their panel visibility tuned, but they cannot be deleted —
    removing Super Admin would strand the instance with no way back in.
    """

    __tablename__ = "role"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    permissions: Mapped[list[Permission]] = relationship(
        secondary="role_permission",
        back_populates="roles",
        lazy="selectin",  # resolved on every authenticated request
    )
    users: Mapped[list[User]] = relationship(secondary="user_role", back_populates="roles")
    panels: Mapped[list[RolePanel]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )


class RolePermission(Base):
    """Join table: which permissions a role grants."""

    __tablename__ = "role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """Join table: which roles a user holds. A user may hold several."""

    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )


class Panel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A navigable screen, as the sidebar understands it (SPEC §5.1).

    Adding a screen means adding a row here as well as a route in the frontend;
    `GET /me` returns the panels the caller's roles can view, and the sidebar is
    built purely from that.
    """

    __tablename__ = "panel"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    route: Mapped[str] = mapped_column(String(200), nullable=False)
    icon: Mapped[str] = mapped_column(
        String(50), nullable=False, default="circle", server_default="circle"
    )
    nav_group: Mapped[str] = mapped_column(
        String(50), nullable=False, default="General", server_default="General"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0"), index=True
    )


class RolePanel(TimestampMixin, Base):
    """Whether a role sees a panel in its sidebar (SPEC §5.1).

    Keyed by `panel_key` rather than `panel_id` so seeding a new panel and
    granting it to roles is one insert against a stable, human-readable key.
    """

    __tablename__ = "role_panel"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    panel_key: Mapped[str] = mapped_column(
        ForeignKey("panel.key", ondelete="CASCADE"), primary_key=True
    )
    can_view: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    role: Mapped[Role] = relationship(back_populates="panels")

    # No UniqueConstraint here: the composite primary key above already enforces
    # one row per (role, panel), and a second identical constraint would only
    # create a redundant index.
