"""
Investigations API endpoints.

POST   /api/v1/investigations                      — create a new investigation
POST   /api/v1/investigations/{id}/enrich          — enrich with Perplexity
PATCH  /api/v1/investigations/{id}/context         — user corrections to context
POST   /api/v1/investigations/{id}/scrape          — trigger full pipeline
GET    /api/v1/investigations/{id}/status          — poll pipeline stage statuses
GET    /api/v1/investigations/{id}/report          — fetch full investigation report
"""

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.investigation import Investigation, InvestigationStatus
from src.models.financial import FinancialRecord
from src.models.procurement import ProcurementRecord
from src.rate_limit import limiter
from src.schemas.investigation import (
    CreateInvestigationRequest,
    EnrichedContextResponse,
    InvestigationReportResponse,
    InvestigationResponse,
    InvestigationScrapeResponse,
    InvestigationStatusResponse,
    PatchContextRequest,
    ProjectContext,
)
from src.services.concordance_service import ConcordanceService
from src.services.perplexity_enrichment_service import (
    EnrichmentError,
    PerplexityEnrichmentService,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_MAX_NAME_LENGTH = 500
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(value: str, max_length: int = _MAX_NAME_LENGTH) -> str:
    """Strip control characters and limit length."""
    cleaned = _CONTROL_CHAR_RE.sub("", value)
    return " ".join(cleaned.split())[:max_length]


# ── Create investigation ───────────────────────────────────────────────────────


@router.post(
    "/investigations",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create investigation",
    description=(
        "Submit a project name to start a new single-project investigation. "
        "Returns an investigation_id for all subsequent calls."
    ),
)
@limiter.limit("20/hour")
async def create_investigation(
    request: Request,
    body: CreateInvestigationRequest,
    db: Session = Depends(get_db),
) -> InvestigationResponse:
    """Create a new investigation record from a user-submitted project name."""
    project_name = _sanitize(body.project_name)
    user_notes = _sanitize(body.user_notes, max_length=2000) if body.user_notes else None

    investigation = Investigation(
        raw_project_name=project_name,
        user_notes=user_notes,
        status=InvestigationStatus.CREATED.value,
        stage_statuses={},
    )
    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    logger.info(
        "Investigation created: %s — '%s'",
        investigation.investigation_id,
        project_name,
    )
    return InvestigationResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        raw_project_name=investigation.raw_project_name,
        created_at=investigation.created_at,
    )


# ── Enrich with Perplexity ─────────────────────────────────────────────────────


@router.post(
    "/investigations/{investigation_id}/enrich",
    response_model=EnrichedContextResponse,
    summary="Enrich investigation context",
    description=(
        "Query Perplexity to populate the ProjectContext for this investigation. "
        "Returns the enriched context for user review. "
        "Confirm or correct it via PATCH /investigations/{id}/context before scraping."
    ),
)
async def enrich_investigation(
    investigation_id: UUID,
    db: Session = Depends(get_db),
) -> EnrichedContextResponse:
    """Call Perplexity to enrich the investigation's project context."""
    investigation = _get_investigation_or_404(investigation_id, db)

    if investigation.status not in (
        InvestigationStatus.CREATED.value,
        InvestigationStatus.ENRICHED.value,  # allow re-enrichment
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Investigation is in status '{investigation.status}'. "
                "Enrichment can only run from 'created' or 'enriched' status."
            ),
        )

    # Update status to enriching
    investigation.status = InvestigationStatus.ENRICHING.value
    db.commit()

    service = PerplexityEnrichmentService()
    try:
        ctx, warnings = service.enrich(
            project_name=investigation.raw_project_name,
            user_notes=investigation.user_notes,
        )
    except EnrichmentError as exc:
        investigation.status = InvestigationStatus.CREATED.value  # roll back
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    # Persist the enriched context as JSONB
    investigation.project_context = ctx.model_dump(mode="json")
    investigation.status = InvestigationStatus.ENRICHED.value
    db.commit()
    db.refresh(investigation)

    logger.info(
        "Investigation %s enriched — county=%s confidence=%.2f warnings=%d",
        investigation_id,
        ctx.county,
        ctx.enrichment_confidence,
        len(warnings),
    )
    return EnrichedContextResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        context=ctx,
        enrichment_warnings=warnings,
    )


# ── Patch context (user corrections) ──────────────────────────────────────────


@router.patch(
    "/investigations/{investigation_id}/context",
    response_model=EnrichedContextResponse,
    summary="Correct investigation context",
    description=(
        "Apply user corrections to the Perplexity-enriched ProjectContext. "
        "All fields are optional — only provided fields are updated. "
        "Set context_confirmed=true to mark the context as ready for scraping."
    ),
)
async def patch_investigation_context(
    investigation_id: UUID,
    body: PatchContextRequest,
    db: Session = Depends(get_db),
) -> EnrichedContextResponse:
    """Apply user corrections to the enriched context."""
    investigation = _get_investigation_or_404(investigation_id, db)

    if investigation.status not in (
        InvestigationStatus.ENRICHED.value,
        InvestigationStatus.CREATED.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Context can only be edited in 'created' or 'enriched' status, "
                f"not '{investigation.status}'."
            ),
        )

    # Merge user corrections into the stored context
    existing_ctx = _load_context(investigation)
    updated_dict = existing_ctx.model_dump(mode="json")

    corrections = body.model_dump(exclude_none=True, exclude={"context_confirmed"})
    for field, value in corrections.items():
        updated_dict[field] = value

    updated_ctx = ProjectContext(**updated_dict)

    investigation.project_context = updated_ctx.model_dump(mode="json")

    if body.context_confirmed:
        investigation.context_confirmed = True
        investigation.context_confirmed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(investigation)

    logger.info(
        "Investigation %s context patched — confirmed=%s",
        investigation_id,
        investigation.context_confirmed,
    )
    return EnrichedContextResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        context=updated_ctx,
        enrichment_warnings=[],
    )


# ── Status polling ─────────────────────────────────────────────────────────────


@router.get(
    "/investigations/{investigation_id}/status",
    response_model=InvestigationStatusResponse,
    summary="Poll investigation status",
    description="Return the current top-level status and per-stage progress map.",
)
async def get_investigation_status(
    investigation_id: UUID,
    db: Session = Depends(get_db),
) -> InvestigationStatusResponse:
    """Return current investigation status and stage breakdown."""
    investigation = _get_investigation_or_404(investigation_id, db)
    return InvestigationStatusResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        stage_statuses=investigation.stage_statuses or {},
        updated_at=investigation.updated_at,
    )


# ── Trigger pipeline ───────────────────────────────────────────────────────────


@router.post(
    "/investigations/{investigation_id}/scrape",
    response_model=InvestigationScrapeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger investigation pipeline",
    description=(
        "Enqueue the full investigation pipeline: targeted scraping → concordance "
        "→ geolocation → satellite analysis → risk scoring. "
        "Requires the investigation to be in 'enriched' or 'created' status. "
        "Poll GET /status for progress."
    ),
)
@limiter.limit("10/hour")
async def trigger_investigation_scrape(
    request: Request,
    investigation_id: UUID,
    db: Session = Depends(get_db),
) -> InvestigationScrapeResponse:
    """Enqueue investigate_project_task for this investigation."""
    investigation = _get_investigation_or_404(investigation_id, db)

    _RUNNABLE = (
        InvestigationStatus.CREATED.value,
        InvestigationStatus.ENRICHED.value,
    )
    if investigation.status not in _RUNNABLE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Pipeline can only be triggered from 'created' or 'enriched' status, "
                f"not '{investigation.status}'."
            ),
        )

    from src.tasks.ingestion_tasks import investigate_project_task

    result = investigate_project_task.delay(str(investigation_id))

    logger.info(
        "Investigation %s pipeline enqueued — task_id=%s",
        investigation_id,
        result.id,
    )
    return InvestigationScrapeResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        task_id=result.id,
    )


# ── Report ─────────────────────────────────────────────────────────────────────


@router.get(
    "/investigations/{investigation_id}/report",
    response_model=InvestigationReportResponse,
    summary="Fetch investigation report",
    description=(
        "Return the full investigation report: project card (from concordance), "
        "procurement records, financial records, and current risk assessment. "
        "Available at any pipeline stage — partial data is returned for in-progress "
        "investigations."
    ),
)
async def get_investigation_report(
    investigation_id: UUID,
    db: Session = Depends(get_db),
) -> InvestigationReportResponse:
    """Return the full investigation report."""
    investigation = _get_investigation_or_404(investigation_id, db)

    ctx = _load_context(investigation) if investigation.project_context else None

    # Retrieve concordance-resolved project card if available
    project_card: dict | None = None
    if investigation.project_uuid:
        project_card = ConcordanceService(db).get_project_truth_record(
            investigation.project_uuid
        )

    # Count evidence records linked to this investigation
    proc_count = (
        db.query(ProcurementRecord)
        .filter(ProcurementRecord.investigation_id == investigation_id)
        .count()
    )
    fin_count = (
        db.query(FinancialRecord)
        .filter(FinancialRecord.investigation_id == investigation_id)
        .count()
    )

    return InvestigationReportResponse(
        investigation_id=investigation.investigation_id,
        status=investigation.status,
        raw_project_name=investigation.raw_project_name,
        project_uuid=investigation.project_uuid,
        context=ctx,
        stage_statuses=investigation.stage_statuses or {},
        project=project_card,
        procurement_count=proc_count,
        financial_count=fin_count,
        created_at=investigation.created_at,
        updated_at=investigation.updated_at,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_investigation_or_404(
    investigation_id: UUID, db: Session
) -> Investigation:
    """Fetch investigation or raise 404."""
    investigation = (
        db.query(Investigation)
        .filter(Investigation.investigation_id == investigation_id)
        .first()
    )
    if not investigation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation {investigation_id} not found",
        )
    return investigation


def _load_context(investigation: Investigation) -> ProjectContext:
    """
    Return a ProjectContext from the stored JSONB, or a minimal seed from
    the raw_project_name if no enrichment has been run yet.
    """
    if investigation.project_context:
        return ProjectContext(**investigation.project_context)
    return ProjectContext(
        project_name=investigation.raw_project_name,
        user_notes=investigation.user_notes,
    )
