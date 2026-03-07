"""
Investigation model — tracks a single-project investigation from enrichment
through to final report.

Each investigation is created when a user nominates a project for auditing.
It owns the ProjectContext JSON and holds stage-level pipeline state so the
frontend can poll progress.
"""

import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.models.base import Base, TimestampMixin


class InvestigationStatus(str, enum.Enum):
    """Top-level investigation lifecycle states."""

    CREATED = "created"
    ENRICHING = "enriching"
    ENRICHED = "enriched"
    SCRAPING = "scraping"
    PARSING = "parsing"
    CONCORDANCE = "concordance"
    GEOLOCATING = "geolocating"
    SATELLITE = "satellite"
    SCORING = "scoring"
    COMPLETE = "complete"
    FAILED = "failed"


class Investigation(Base, TimestampMixin):
    """
    Investigation record — one row per user-initiated project audit.

    project_uuid is NULL until ConcordanceService links the scraped
    procurement records to a Project row (after the scraping stage).
    """

    __tablename__ = "investigations"

    # ── Primary key ──────────────────────────────────────────────────────────
    investigation_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal unique identifier for this investigation",
    )

    # ── Link to resolved project (set post-concordance) ──────────────────────
    project_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Linked project row — NULL until concordance resolves",
    )

    # ── User input ───────────────────────────────────────────────────────────
    raw_project_name = Column(
        Text,
        nullable=False,
        comment="Project name exactly as the user entered it",
    )

    user_notes = Column(
        Text,
        nullable=True,
        comment="Optional free-text context provided by the user",
    )

    # ── Enriched context ─────────────────────────────────────────────────────
    project_context = Column(
        JSONB,
        nullable=True,
        comment="Full ProjectContext JSON populated by PerplexityEnrichmentService",
    )

    context_confirmed = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True once the user has reviewed and confirmed the enriched context",
    )

    context_confirmed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when context was confirmed",
    )

    # ── Pipeline state ───────────────────────────────────────────────────────
    status = Column(
        String(50),
        default=InvestigationStatus.CREATED.value,
        nullable=False,
        index=True,
        comment="Top-level investigation status",
    )

    stage_statuses = Column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Per-stage status map e.g. {egp_scrape: complete, nca_scrape: pending}",
    )

    # ── Relationships ────────────────────────────────────────────────────────
    project = relationship("Project", foreign_keys=[project_uuid], lazy="select")
