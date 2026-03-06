"""
Projects API endpoints.

GET  /api/v1/projects              — paginated list with filters
GET  /api/v1/projects/geojson      — GeoJSON FeatureCollection (for CesiumJS)
POST /api/v1/projects/reconcile    — batch-link all unlinked procurement records
GET  /api/v1/projects/{uuid}       — single project
GET  /api/v1/projects/{uuid}/truth-record — unified project card
"""

import logging
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.project import Project, RiskLevel
from src.rate_limit import limiter
from src.schemas.projects import (
    ProjectListResponse,
    ProjectResponse,
    ProjectTruthRecord,
    ReconcileResponse,
)
from src.services.concordance_service import ConcordanceService

router = APIRouter()
logger = logging.getLogger(__name__)


def _sanitize_input(value: str, max_length: int = 200) -> str:
    """Strip control chars, collapse whitespace, limit length."""
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', value)
    cleaned = ' '.join(cleaned.split())
    return cleaned[:max_length]


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="List projects",
    description="Paginated project list with optional filters.",
)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(
        None, description="Filter by risk level: LOW, MEDIUM, HIGH, CRITICAL"
    ),
    county: Optional[str] = Query(None, description="Filter by county name"),
    project_type: Optional[str] = Query(
        None, description="Filter by type: health, education, roads, water, markets, other"
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by project status"
    ),
    db: Session = Depends(get_db),
):
    """Return a paginated list of infrastructure projects."""
    query = db.query(Project)

    if risk_level:
        try:
            query = query.filter(Project.risk_level == RiskLevel(risk_level.upper()))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid risk_level '{risk_level}'. "
                       f"Valid: LOW, MEDIUM, HIGH, CRITICAL",
            )
    if county:
        county = _sanitize_input(county, max_length=100)
        query = query.filter(
            Project.county.ilike(f"%{county}%")
        )
    if project_type:
        project_type = _sanitize_input(project_type, max_length=100)
        query = query.filter(
            Project.project_type.cast(str).ilike(f"%{project_type}%")
        )
    if status_filter:
        status_filter = _sanitize_input(status_filter, max_length=50)
        query = query.filter(
            Project.status.cast(str).ilike(f"%{status_filter}%")
        )

    total = query.count()
    skip = (page - 1) * page_size
    projects = query.order_by(Project.created_at.desc()).offset(skip).limit(page_size).all()

    return ProjectListResponse(
        total=total,
        page=page,
        page_size=page_size,
        projects=[ProjectResponse.model_validate(p) for p in projects],
    )


@router.get(
    "/projects/geojson",
    summary="Projects as GeoJSON",
    description="GeoJSON FeatureCollection of all geolocated projects with optional risk_level filter.",
)
async def projects_geojson(
    risk_level: Optional[str] = Query(
        None,
        description="Comma-separated: LOW,MEDIUM,HIGH,CRITICAL (e.g. ?risk_level=HIGH,CRITICAL)"
    ),
    db: Session = Depends(get_db)
):
    """Return a GeoJSON FeatureCollection of all geolocated projects."""
    from src.models.geolocation import GeolocationRecord

    query = (
        db.query(Project, GeolocationRecord)
        .join(
            GeolocationRecord,
            GeolocationRecord.project_uuid == Project.project_uuid,
        )
        .filter(Project.geolocation_status == "geolocated")
    )

    # Apply risk_level filter if provided
    if risk_level:
        requested = {r.strip().upper() for r in risk_level.split(",")}
        valid_levels = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        filtered = requested & valid_levels
        if filtered:
            enums = [RiskLevel[lv] for lv in filtered]
            query = query.filter(Project.risk_level.in_(enums))

    rows = query.all()

    features = []
    seen: set = set()
    for proj, geo in rows:
        if proj.project_uuid in seen:
            continue
        seen.add(proj.project_uuid)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(geo.longitude), float(geo.latitude)],
                },
                "properties": {
                    "project_uuid": str(proj.project_uuid),
                    "project_name": proj.project_name,
                    "project_type": proj.project_type.value if proj.project_type else None,
                    "county": proj.county,
                    "status": proj.status.value,
                    "risk_level": proj.risk_level.value if proj.risk_level else None,
                    "ghost_probability": (
                        float(proj.ghost_probability)
                        if proj.ghost_probability is not None
                        else None
                    ),
                    "estimated_value_kes": (
                        float(proj.estimated_value_kes)
                        if proj.estimated_value_kes
                        else None
                    ),
                    "gps_method": geo.match_method,
                    "gps_confidence": geo.match_confidence,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


@router.post(
    "/projects/reconcile",
    response_model=ReconcileResponse,
    summary="Reconcile unlinked procurement records",
    description=(
        "Batch-runs ConcordanceService on all procurement records that have no "
        "project_uuid.  Creates new Project rows where no fuzzy match exists."
    ),
)
@limiter.limit("3/minute")
async def reconcile_projects(request: Request, db: Session = Depends(get_db)):
    """Trigger concordance for all unlinked procurement records."""
    try:
        service = ConcordanceService(db)
        stats = service.reconcile_all_unlinked()
        return ReconcileResponse(**stats)
    except Exception as exc:
        logger.error("reconcile failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reconciliation failed",
        )


@router.get(
    "/projects/{project_uuid}",
    response_model=ProjectResponse,
    summary="Get project",
    description="Retrieve a single project by UUID.",
)
async def get_project(project_uuid: UUID, db: Session = Depends(get_db)):
    """Get project by UUID."""
    project = (
        db.query(Project)
        .filter(Project.project_uuid == project_uuid)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_uuid} not found",
        )
    return ProjectResponse.model_validate(project)


@router.get(
    "/projects/{project_uuid}/truth-record",
    response_model=ProjectTruthRecord,
    summary="Get unified project card",
    description=(
        "Returns the complete 'truth record' for a project: canonical fields plus "
        "all linked procurement, financial, and geolocation data."
    ),
)
async def get_project_truth_record(project_uuid: UUID, db: Session = Depends(get_db)):
    """Return unified project card with all linked data sources."""
    service = ConcordanceService(db)
    record = service.get_project_truth_record(project_uuid)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_uuid} not found",
        )
    return record
