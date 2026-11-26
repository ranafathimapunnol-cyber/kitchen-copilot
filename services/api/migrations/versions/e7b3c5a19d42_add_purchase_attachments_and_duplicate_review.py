"""add purchase bill attachments and duplicate invoice review (PUR01)

Revision ID: e7b3c5a19d42
Revises: d4e8a91b2c70

Approved 18 November 2026.

- purchase_attachments: one row per file attached to a supplier bill, with
  the metadata ADR-008 requires (campus, bill, object key, original name,
  content type, size, uploader, upload time, checksum). The file itself is
  kept in private storage, never in the database. Attachments are
  permanent: there is no delete path, and the same file (checksum) can be
  attached to a bill only once.
- purchases.duplicate_reviewed_at / _by / _note: the outcome of reviewing
  a bill flagged as a possible duplicate invoice ("not a duplicate").

Additive only: no existing table, column, constraint or row is changed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b3c5a19d42"
down_revision: Union[str, Sequence[str], None] = "d4e8a91b2c70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ---------------------------------------------------------
    # 1. BILL ATTACHMENTS (ADR-008)
    # ---------------------------------------------------------

    op.create_table(
        "purchase_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("remarks", sa.String(length=500), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("campus_id", sa.Integer(), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_purchase_attachment_size"),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key", name="uq_purchase_attachment_object_key"),
        sa.UniqueConstraint(
            "purchase_id", "checksum_sha256", name="uq_purchase_attachment_file"
        ),
    )
    op.create_index(
        op.f("ix_purchase_attachments_campus_id"),
        "purchase_attachments", ["campus_id"], unique=False,
    )
    op.create_index(
        op.f("ix_purchase_attachments_purchase_id"),
        "purchase_attachments", ["purchase_id"], unique=False,
    )

    # ---------------------------------------------------------
    # 2. DUPLICATE INVOICE REVIEW
    # ---------------------------------------------------------

    op.add_column(
        "purchases",
        sa.Column("duplicate_reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "purchases",
        sa.Column("duplicate_reviewed_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "purchases",
        sa.Column("duplicate_review_note", sa.String(length=500), nullable=True),
    )
    op.create_foreign_key(
        "fk_purchases_duplicate_reviewed_by_users",
        "purchases", "users", ["duplicate_reviewed_by"], ["id"],
    )
    op.create_check_constraint(
        "ck_purchase_duplicate_review_complete",
        "purchases",
        "(duplicate_reviewed_at IS NULL) = (duplicate_reviewed_by IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_purchase_duplicate_review_complete", "purchases", type_="check"
    )
    op.drop_constraint(
        "fk_purchases_duplicate_reviewed_by_users", "purchases", type_="foreignkey"
    )
    op.drop_column("purchases", "duplicate_review_note")
    op.drop_column("purchases", "duplicate_reviewed_by")
    op.drop_column("purchases", "duplicate_reviewed_at")

    op.drop_index(
        op.f("ix_purchase_attachments_purchase_id"), table_name="purchase_attachments"
    )
    op.drop_index(
        op.f("ix_purchase_attachments_campus_id"), table_name="purchase_attachments"
    )
    op.drop_table("purchase_attachments")
