"""security and agent tables (Stages 10 and 12)

Revision ID: c4d7e9a1f203
Revises: b8e4c2a9d175

Additive only. No existing row is changed or deleted; no permission row,
grant, role or enum changes.

Stage 10 (security):
1. login_attempts: one row per sign-in attempt (email, IP, succeeded,
   user when known); used for throttling (interim rule for Q19: 5 failures
   per email or 30 per IP in 15 minutes) and the Admin security view.
2. users.sessions_revoked_at and users.last_login_at (nullable).

Stage 12 (agent):
3. agent_conversations, agent_messages, agent_steps, agent_proposals.

Stage 11 (organisations, SUPER_ADMIN) is the separate migration M1
(d5e8f0b2a314), which needs its own explicit authorization.

The downgrade refuses while any agent conversation exists.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d7e9a1f203"
down_revision: Union[str, None] = "b8e4c2a9d175"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_login_attempts_email_created", "login_attempts", ["email", "created_at"])
    op.create_index("ix_login_attempts_ip_created", "login_attempts", ["ip_address", "created_at"])
    op.add_column("users", sa.Column("sessions_revoked_at", TS, nullable=True))
    op.add_column("users", sa.Column("last_login_at", TS, nullable=True))

    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    op.create_index("ix_agent_conversations_owner", "agent_conversations", ["campus_id", "user_id", "updated_at"])
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_agent_messages_conversation_id", "agent_messages", ["conversation_id"])
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("agent_messages.id"), nullable=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_agent_steps_conversation_id", "agent_steps", ["conversation_id"])
    op.create_table(
        "agent_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("agent_messages.id"), nullable=True),
        sa.Column("workflow", sa.String(40), nullable=False),
        sa.Column("action_type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("required_permission", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", TS, nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_agent_proposals_conversation_id", "agent_proposals", ["conversation_id"])
    op.create_index("ix_agent_proposals_campus_status", "agent_proposals", ["campus_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM agent_conversations")).scalar():
        raise RuntimeError("Refusing to downgrade: agent conversations exist.")
    for table in ("agent_proposals", "agent_steps", "agent_messages", "agent_conversations"):
        op.drop_table(table)
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "sessions_revoked_at")
    op.drop_table("login_attempts")
