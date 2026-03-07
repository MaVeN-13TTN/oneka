"""
Pydantic schemas for Investigation resources.

Covers the full investigation lifecycle:
  - ProjectContext — the central enriched context object passed to all scrapers
  - CreateInvestigationRequest — user's initial submission
  - InvestigationResponse — API response after create
  - PatchContextRequest — user corrections to enriched context
  - EnrichedContextResponse — API response after Perplexity enrichment
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── ProjectContext ─────────────────────────────────────────────────────────────


class ProjectContext(BaseModel):
    """
    The central context object that drives all targeted scrapers and parsers.

    Populated in two stages:
      1. User seed (project_name + optional user_notes)
      2. Perplexity enrichment (all remaining fields)

    Passed as-is to EGPScraper, NCAScraper, PPIPScraper, CoBPoller, and
    KMHFLScraper. Also passed to IntelligentCoBParser.
    """

    # ── User-provided seed ──────────────────────────────────────────────────
    project_name: str = Field(..., description="Raw project name as entered by user")
    user_notes: Optional[str] = Field(None, description="Free-text notes from user")

    # ── Perplexity-enriched fields ──────────────────────────────────────────
    canonical_name: Optional[str] = Field(
        None,
        description="Normalised official name as it appears in government documents",
    )
    county: Optional[str] = Field(None, description="Kenya county name")
    constituency: Optional[str] = Field(None, description="Constituency name")
    ward: Optional[str] = Field(None, description="Ward name")
    coordinates: Optional[tuple[float, float]] = Field(
        None, description="(latitude, longitude) if located by Perplexity"
    )
    project_type: Optional[str] = Field(
        None,
        description="Project category: HEALTH | ROADS | EDUCATION | WATER | MARKETS | OTHER",
    )
    estimated_value_kes: Optional[float] = Field(
        None, description="Estimated contract value in KES"
    )
    contractor_name: Optional[str] = Field(None, description="Name of contractor")
    procuring_entity: Optional[str] = Field(
        None, description="Full name of government entity procuring the project"
    )
    award_date: Optional[str] = Field(
        None, description="Contract award date (ISO 8601 or YYYY)"
    )
    fiscal_years: list[str] = Field(
        default_factory=list,
        description='Fiscal years the project spans e.g. ["2021/2022", "2022/2023"]',
    )
    source_urls: list[str] = Field(
        default_factory=list,
        description="Source URLs Perplexity found when researching this project",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative name forms (e-GP title, NCA listing, etc.)",
    )

    # ── Scraper targeting hints ─────────────────────────────────────────────
    search_terms: list[str] = Field(
        default_factory=list,
        description="Derived search strings passed directly to EGP / NCA search boxes",
    )
    ministry: Optional[str] = Field(
        None, description="Ministry name for COB vote head lookup"
    )
    vote_head: Optional[int] = Field(
        None, description="Explicit COB vote head number if known"
    )

    # ── Enrichment metadata ─────────────────────────────────────────────────
    enrichment_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description="Perplexity confidence score 0.0–1.0",
    )
    enrichment_source: str = Field(
        "user",
        description='How context was populated: "user" | "perplexity" | "hybrid"',
    )
    enriched_at: Optional[datetime] = Field(
        None, description="Timestamp when Perplexity enrichment completed"
    )

    class Config:
        from_attributes = True


# ── Request schemas ────────────────────────────────────────────────────────────


class CreateInvestigationRequest(BaseModel):
    """POST /api/v1/investigations — initial user submission."""

    project_name: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Project name as the user knows it",
    )
    user_notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional free-text context the user can provide",
    )


class PatchContextRequest(BaseModel):
    """
    PATCH /api/v1/investigations/{id}/context

    Allows the user to correct Perplexity-enriched fields before scraping
    begins. All fields are optional — only provided fields are updated.
    """

    canonical_name: Optional[str] = None
    county: Optional[str] = None
    constituency: Optional[str] = None
    ward: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    project_type: Optional[str] = None
    estimated_value_kes: Optional[float] = None
    contractor_name: Optional[str] = None
    procuring_entity: Optional[str] = None
    award_date: Optional[str] = None
    fiscal_years: Optional[list[str]] = None
    aliases: Optional[list[str]] = None
    search_terms: Optional[list[str]] = None
    ministry: Optional[str] = None
    vote_head: Optional[int] = None
    context_confirmed: Optional[bool] = None


# ── Response schemas ───────────────────────────────────────────────────────────


class InvestigationResponse(BaseModel):
    """Response after POST /api/v1/investigations (create)."""

    investigation_id: UUID
    status: str
    raw_project_name: str
    created_at: datetime

    class Config:
        from_attributes = True


class EnrichedContextResponse(BaseModel):
    """Response after POST /api/v1/investigations/{id}/enrich."""

    investigation_id: UUID
    status: str
    context: ProjectContext
    enrichment_warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings e.g. low confidence score",
    )

    class Config:
        from_attributes = True


class InvestigationStatusResponse(BaseModel):
    """Response for GET /api/v1/investigations/{id}/status."""

    investigation_id: UUID
    status: str
    stage_statuses: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime

    class Config:
        from_attributes = True


class InvestigationScrapeResponse(BaseModel):
    """Response for POST /api/v1/investigations/{id}/scrape."""

    investigation_id: UUID
    status: str
    task_id: Optional[str] = None
    detail: str = "Investigation pipeline enqueued"

    class Config:
        from_attributes = True


class InvestigationReportResponse(BaseModel):
    """
    Response for GET /api/v1/investigations/{id}/report.

    Returns all evidence gathered during the investigation alongside the
    concordance-resolved project card (if available).
    """

    investigation_id: UUID
    status: str
    raw_project_name: str
    project_uuid: Optional[UUID] = None
    context: Optional[ProjectContext] = None
    stage_statuses: dict[str, Any] = Field(default_factory=dict)
    # Concordance-resolved project card (None until concordance completes)
    project: Optional[dict[str, Any]] = None
    procurement_count: int = 0
    financial_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
