"""Enable the Postgres extensions the schema depends on

Revision ID: a1f0c3d21b47
Revises:
Create Date: 2026-07-29

The whole schema is built on top of these, so they are the first migration:

  citext     case-insensitive text, for the unique `username` and `email`
             columns in SPEC §5.1 — a login must not be case-sensitive.
  pg_trgm    trigram similarity, the fuzzy fallback for vendor keyword matching
             in SPEC §5.4 and the accelerator for ILIKE searches.
  btree_gin  lets a single GIN index cover a scalar column alongside a tsvector
             or jsonb one, e.g. (source_id, search_vector) on `signal`.

All three are "trusted" extensions in Postgres 13+, so the database owner can
create them without superuser rights.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a1f0c3d21b47"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("citext", "pg_trgm", "btree_gin")


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')


def downgrade() -> None:
    # Dropped in reverse order for symmetry. This will fail loudly if any object
    # still depends on an extension, which is the correct outcome.
    for extension in reversed(EXTENSIONS):
        op.execute(f'DROP EXTENSION IF EXISTS "{extension}"')
