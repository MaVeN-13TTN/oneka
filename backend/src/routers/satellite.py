"""
Satellite API endpoints.

POST /api/v1/satellite/analyse/{project_uuid}    — queue satellite analysis
GET  /api/v1/satellite/status/{task_id}          — Celery task status
GET  /api/v1/satellite/tiles/{project_uuid}/ndvi/{z}/{x}/{y}  — tile (Phase 5)
GET  /api/v1/projects/{project_uuid}/divergence  — divergence scores
GET  /api/v1/dashboard/heat-map                  — all projects for heat-map
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.project import Project
from src.services.satellite_service import SatelliteService
from src.services.divergence_service import DivergenceService

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── satellite analysis ───────────────────────────────────────────────────────

@router.post(
    "/satellite/analyse/{project_uuid}",
    summary="Queue satellite analysis",
    description=(
        "Enqueue a Celery task to download and process Sentinel-1 and Sentinel-2 "
        "scenes for the project.  The project must already have a GeolocationRecord."
    ),
)
async def queue_satellite_analysis(
    project_uuid: UUID, db: Session = Depends(get_db)
):
    """Queue analyse_project_task for a single project."""
    service = SatelliteService(db)
    try:
        task_id = service.queue_analysis(project_uuid)
        return {
            "project_uuid": str(project_uuid),
            "task_id": task_id,
            "status": "queued",
        }
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    except Exception as exc:
        logger.error("queue_satellite_analysis failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue satellite analysis",
        )


@router.get(
    "/satellite/status/{task_id}",
    summary="Get Celery task status",
    description="Poll the status of a queued satellite analysis task.",
)
async def get_task_status(task_id: str):
    """Return Celery AsyncResult state for *task_id*."""
    try:
        from src.celery_app import celery_app
        from celery.result import AsyncResult

        result = AsyncResult(task_id, app=celery_app)
        payload: dict = {"task_id": task_id, "status": result.state}

        if result.successful():
            payload["result"] = result.result
        elif result.failed():
            payload["error"] = str(result.result)

        return payload
    except Exception as exc:
        logger.error("get_task_status failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve task status",
        )


@router.get(
    "/satellite/tiles/{project_uuid}/ndvi/{z}/{x}/{y}",
    summary="NDVI tile (Phase 5)",
    description=(
        "Returns a 256×256 PNG map tile for the given XYZ coordinates.  "
        "Full COG tile generation is deferred to Phase 5.  "
        "This endpoint returns 501 for now."
    ),
)
async def get_ndvi_tile(
    project_uuid: UUID, z: int, x: int, y: int, db: Session = Depends(get_db)
):
    """Tile endpoint placeholder — Phase 5 COG tile generation not yet implemented."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "NDVI tile generation (COG/cogeo-mosaic) is a Phase 5 feature.  "
            "Use the image_url field from /satellite/time-series for direct "
            "GeoTIFF access."
        ),
    )


# ─── divergence ───────────────────────────────────────────────────────────────

@router.get(
    "/projects/{project_uuid}/divergence",
    summary="Get project divergence score",
    description=(
        "Computes financial-vs-physical divergence for the project and returns "
        "the current alert level (RED/YELLOW/GREEN) and supporting metrics."
    ),
)
async def get_project_divergence(
    project_uuid: UUID, db: Session = Depends(get_db)
):
    """Return divergence metrics for a project."""
    project = (
        db.query(Project).filter(Project.project_uuid == project_uuid).first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_uuid} not found",
        )

    service = DivergenceService(db)
    result = service.calculate_divergence(project_uuid)
    timeline = service.get_divergence_timeline(project_uuid)
    result["timeline"] = timeline
    return result


# ─── dashboard ───────────────────────────────────────────────────────────────

@router.get(
    "/dashboard/heat-map",
    summary="Risk heat-map data",
    description=(
        "Returns all geolocated projects with risk level and divergence data "
        "for rendering a Leaflet/CesiumJS heat-map."
    ),
)
async def get_heat_map(db: Session = Depends(get_db)):
    """Return risk data for all geolocated projects."""
    from src.models.geolocation import GeolocationRecord
    from src.models.satellite import SatelliteAnalysis

    rows = (
        db.query(Project, GeolocationRecord)
        .join(
            GeolocationRecord,
            GeolocationRecord.project_uuid == Project.project_uuid,
        )
        .all()
    )

    features = []
    seen: set = set()

    for proj, geo in rows:
        if proj.project_uuid in seen:
            continue
        seen.add(proj.project_uuid)

        analyses_count = (
            db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == proj.project_uuid)
            .count()
        )

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
                    "risk_score": proj.risk_score,
                    "ghost_probability": (
                        float(proj.ghost_probability)
                        if proj.ghost_probability is not None
                        else None
                    ),
                    "satellite_analyses_count": analyses_count,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features, "total": len(features)}
