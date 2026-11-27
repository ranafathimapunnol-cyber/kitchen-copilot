"""campus logo and photo (Phase 2 follow-up, M2)

Revision ID: e2b7c4d9a5f1
Revises: d5e8f0b2a314

Additive: three nullable columns on campuses (current logo and photo storage
keys, last change time). No existing row is changed. The files themselves
live in the private attachment storage, never in the database.

Needs explicit authorization for any database with real records: the API
container runs "alembic upgrade head" at start, so this upgrade refuses
unless KC_AUTHORIZE_MIGRATION=e2b7c4d9a5f1 is set.
"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2b7c4d9a5f1"
down_revision: Union[str, None] = "d5e8f0b2a314"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AUTHORIZATION_ENV = "KC_AUTHORIZE_MIGRATION"


def upgrade() -> None:
    if os.environ.get(AUTHORIZATION_ENV) != revision:
        raise RuntimeError(
            f"Migration {revision} (campus logo and photo) is not authorized for this database. "
            f"After explicit approval and a verified backup, run it with {AUTHORIZATION_ENV}={revision}.")
    op.add_column("campuses", sa.Column("logo_key", sa.String(200), nullable=True))
    op.add_column("campuses", sa.Column("photo_key", sa.String(200), nullable=True))
    op.add_column("campuses", sa.Column("media_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    in_use = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM campuses WHERE logo_key IS NOT NULL OR photo_key IS NOT NULL")).scalar()
    if in_use:
        raise RuntimeError(f"Refusing to downgrade: {in_use} campus(es) have a logo or photo.")
    op.drop_column("campuses", "media_updated_at")
    op.drop_column("campuses", "photo_key")
    op.drop_column("campuses", "logo_key")
