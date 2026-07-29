"""Identity: the application singleton, users, and their credentials (SPEC §5.1).

Notes that matter when reading this:

* `username` and `email` are `citext`. A login must not be case-sensitive, and
  enforcing that in the column type means uniqueness is case-insensitive too —
  `Admin` and `admin` cannot both exist. Doing it in Python instead would leave
  the race open between check and insert.
* `totp_secret_encrypted` holds AES-GCM ciphertext, never the Base32 secret.
* Credentials are hashed with Argon2id; nothing here stores a reversible
  password.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rbac import Role


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Instance-wide configuration. Exactly one row (SPEC §5.1).

    `setup_completed_at` is the flag the onboarding gate reads: null means the
    instance has never been set up, and every route outside `/setup/*` answers
    409 until it is stamped.
    """

    __tablename__ = "app_setting"

    # Singleton guard. A second `app_setting` row would make "has setup
    # completed?" ambiguous and the onboarding gate non-deterministic, so the
    # constraint is enforced by the database rather than by convention: the
    # column may only hold TRUE, and TRUE may only appear once.
    is_singleton: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), unique=True
    )

    org_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    org_logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    org_initials: Mapped[str | None] = mapped_column(String(3), nullable=True)
    brand_color: Mapped[str] = mapped_column(
        String(9), nullable=False, default="#22D3EE", server_default="#22D3EE"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Kuala_Lumpur", server_default="Asia/Kuala_Lumpur"
    )
    setup_completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Retention, defaults and notification preferences edited on /admin/settings.
    # Kept as a single jsonb blob rather than a column per knob: these are read
    # as a unit, and adding one should not need a migration.
    preferences: Mapped[dict[str, Any]] = mapped_column(
        nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (CheckConstraint("is_singleton IS TRUE", name="app_setting_is_singleton"),)


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An operator account (SPEC §5.1).

    Soft-deleted rather than removed: `audit_log.actor_id` and
    `alert.acknowledged_by` point here historically, and a deleted user must not
    turn last quarter's audit trail into dangling IDs.
    """

    __tablename__ = "user"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)

    # server_default as well as default throughout, so a row inserted by hand in
    # psql during an incident cannot violate NOT NULL.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    last_login_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Reset to zero on any successful login. `locked_until` in the future means
    # authentication is refused regardless of whether the password is correct.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list[Role]] = relationship(
        secondary="user_role",
        back_populates="users",
        lazy="selectin",  # roles are needed on nearly every request, via /me
    )
    recovery_codes: Mapped[list[RecoveryCode]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Login looks users up by username and immediately checks the lock; the
        # partial index keeps that lookup off soft-deleted rows.
        Index(
            "ix_user_active_username",
            "username",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return self.locked_until > dt.datetime.now(dt.UTC)

    @property
    def initials(self) -> str:
        """Up to two initials from the full name, for the fallback avatar."""
        parts = [part for part in self.full_name.split() if part]
        if not parts:
            return self.username[:2].upper()
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class RecoveryCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use backup code accepted in place of a TOTP code (SPEC §6.2).

    Stored as a hash: a database read must not yield usable second factors.
    `used_at` is what makes a code single-use — rows are marked, never deleted,
    so "was this code already spent" stays answerable.
    """

    __tablename__ = "recovery_code"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="recovery_codes")


class RefreshToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A refresh token, rotated on every use (SPEC §6.2).

    `family_id` is what makes reuse detection possible. Each login starts a
    family; every rotation issues a new row carrying the same `family_id` and
    revokes its predecessor. If an already-revoked token is presented, the
    token was replayed — meaning it leaked — and the entire family is revoked
    at once, logging the legitimate holder out too. That is the intended
    outcome: better a forced re-login than a live session in an attacker's hands.
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 of the opaque token. The plaintext exists only in the client's
    # cookie, so a database disclosure does not hand over live sessions.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        # The sessions screen lists a user's live tokens newest first.
        Index("ix_refresh_token_user_active", "user_id", "revoked_at", "expires_at"),
    )

    @property
    def is_active(self) -> bool:
        now = dt.datetime.now(dt.UTC)
        return self.revoked_at is None and self.expires_at > now


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every mutating action (SPEC §5.1).

    No `updated_at` and no soft delete on purpose — an audit row that can be
    edited is not an audit row. `actor_id` deliberately has no cascade: deleting
    a user must never erase what they did.
    """

    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Denormalised so the trail stays readable after the account is gone.
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    before: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    ua: Mapped[str | None] = mapped_column(String(400), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # The audit screen always filters by entity or actor and sorts newest first.
    # `created_at` already carries a plain btree (index=True above), and Postgres
    # scans a single-column btree backwards just as cheaply, so no separate DESC
    # index is needed.
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)
