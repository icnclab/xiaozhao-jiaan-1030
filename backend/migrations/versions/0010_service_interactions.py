"""Add isolated service-interaction grouping and explicit read grants.

Revision ID: 0010_service_interactions
Revises: 0009_fieldtest_participants

This migration is additive.  It intentionally does not add a foreign key from
qa_items.conversation_id because existing QA rows use standalone UUID threads.
The API treats a UUID as a managed Interaction only when a matching
service_interactions row exists.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_service_interactions"
down_revision = "0009_fieldtest_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_interactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("start_request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "start_request_id"),
    )
    op.create_index("ix_service_interactions_org_id", "service_interactions", ["org_id"], unique=False)
    op.create_index("ix_service_interactions_owner_id", "service_interactions", ["owner_id"], unique=False)

    op.create_table(
        "interaction_read_grants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interaction_id", sa.UUID(), nullable=False),
        sa.Column("viewer_id", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=False),
        sa.Column("responsible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["interaction_id"], ["service_interactions.id"]),
        sa.ForeignKeyConstraint(["viewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interaction_id", "viewer_id"),
    )
    op.create_index(
        "ix_interaction_read_grants_interaction_id",
        "interaction_read_grants",
        ["interaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_interaction_read_grants_viewer_id",
        "interaction_read_grants",
        ["viewer_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_read_grants_viewer_id", table_name="interaction_read_grants")
    op.drop_index("ix_interaction_read_grants_interaction_id", table_name="interaction_read_grants")
    op.drop_table("interaction_read_grants")
    op.drop_index("ix_service_interactions_owner_id", table_name="service_interactions")
    op.drop_index("ix_service_interactions_org_id", table_name="service_interactions")
    op.drop_table("service_interactions")
