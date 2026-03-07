"""add investigations table

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-03-07 00:00:00.000000

Adds:
- investigations table (UUID PK, JSONB project_context, JSONB stage_statuses)

Indexes:
- idx_investigations_created  (created_at DESC)
- idx_investigations_project  (project_uuid)
- idx_investigations_status   (status)
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column(
            "investigation_id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
            comment="Universal unique identifier for this investigation",
        ),
        sa.Column(
            "project_uuid",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("projects.project_uuid", ondelete="SET NULL"),
            nullable=True,
            comment="Linked project row — NULL until concordance resolves",
        ),
        sa.Column(
            "raw_project_name",
            sa.Text,
            nullable=False,
            comment="Project name exactly as the user entered it",
        ),
        sa.Column(
            "user_notes",
            sa.Text,
            nullable=True,
            comment="Optional free-text context provided by the user",
        ),
        sa.Column(
            "project_context",
            JSONB,
            nullable=True,
            comment="Full ProjectContext JSON from PerplexityEnrichmentService",
        ),
        sa.Column(
            "context_confirmed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="True once the user has reviewed and confirmed the enriched context",
        ),
        sa.Column(
            "context_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when context was confirmed",
        ),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'created'"),
            comment="Top-level investigation status",
        ),
        sa.Column(
            "stage_statuses",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Per-stage status map e.g. {egp_scrape: complete, nca_scrape: pending}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "idx_investigations_created",
        "investigations",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_investigations_project",
        "investigations",
        ["project_uuid"],
    )
    op.create_index(
        "idx_investigations_status",
        "investigations",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("idx_investigations_status", table_name="investigations")
    op.drop_index("idx_investigations_project", table_name="investigations")
    op.drop_index("idx_investigations_created", table_name="investigations")
    op.drop_table("investigations")
