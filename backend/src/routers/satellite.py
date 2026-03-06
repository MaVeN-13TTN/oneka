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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.project import Project
from src.rate_limit import limiter
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
@limiter.limit("10/minute")
async def queue_satellite_analysis(
    request: Request, project_uuid: UUID, db: Session = Depends(get_db)
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
        "Returns a 256×256 PNG map tile for the given XYZ coordinates, "
        "or triggers tile generation if not yet available.  "
        "Returns 307 redirect to presigned S3 URL if tiles are ready, "
        "or 202 Accepted if tile generation is in progress."
    ),
)
async def get_ndvi_tile(
    project_uuid: UUID, z: int, x: int, y: int, db: Session = Depends(get_db)
):
    """
    Return NDVI XYZ tile for project.

    If tiles already generated: 307 redirect to presigned S3 URL
    If tiles missing: 202 Accepted + trigger generation + return task_id
    """
    from src.services.tile_service import TileService
    from src.models.geolocation import GeolocationRecord
    from fastapi.responses import RedirectResponse, JSONResponse

    # Validate zoom and coordinates
    if not (0 <= z <= 28):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid zoom level: {z} (must be 0-28)",
        )
    if not (0 <= x < (2 ** z) and 0 <= y < (2 ** z)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tile out of bounds at z{z}/x{x}/y{y}",
        )

    try:
        service = TileService(db)
        tile_status = service.get_tile_status(project_uuid)

        if tile_status["status"] == "complete" and tile_status["tile_url_template"]:
            # Tiles already generated; redirect to presigned S3 URL
            s3_prefix = tile_status["tile_url_template"].split("?")[0]  # Remove query params
            tile_url = (
                s3_prefix.replace("{z}", str(z))
                .replace("{x}", str(x))
                .replace("{y}", str(y))
            )

            # Generate presigned URL
            urls = service.get_tile_presigned_urls(project_uuid, "ndvi", z_range=(z, z))
            if urls:
                return RedirectResponse(url=urls[0], status_code=307)

            # Fallback: return tile_url as-is
            return RedirectResponse(url=tile_url, status_code=307)

        # Tiles not yet generated; trigger generation
        try:
            task_id = service.queue_tile_generation(project_uuid, "ndvi")
            return JSONResponse(
                status_code=202,
                content={
                    "status": "queued",
                    "task_id": task_id,
                    "message": f"Tile generation queued; task_id={task_id}",
                },
                headers={"X-Task-ID": task_id},
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_ndvi_tile failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch tile",
        )


@router.get(
    "/satellite/tiles-status/{project_uuid}",
    summary="Tile generation status",
    description=(
        "Get tile generation status for a project. "
        "Returns status and presigned URLs if tiles are complete."
    ),
)
async def get_tiles_status(
    project_uuid: UUID, db: Session = Depends(get_db)
):
    """
    Return tile generation status and presigned URLs.

    Returns:
        {
            'status': 'complete'|'pending'|'generating'|'failed',
            'tile_url_template': '...' or null,
            'presigned_urls': [...] or null,
            'error': null or message
        }
    """
    from src.services.tile_service import TileService

    try:
        service = TileService(db)
        status_dict = service.get_tile_status(project_uuid)

        if status_dict["status"] == "complete":
            try:
                urls = service.get_tile_presigned_urls(
                    project_uuid, "ndvi", z_range=(8, 14)
                )
                status_dict["presigned_urls"] = urls
            except ValueError:
                logger.warning(
                    f"Could not generate presigned URLs for {project_uuid}"
                )

        return status_dict

    except Exception as exc:
        logger.error("get_tiles_status failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tile status",
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
