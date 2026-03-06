"""
Geolocation API endpoints.

POST /api/v1/geolocation/resolve    — resolve GPS for a single procurement record
GET  /api/v1/geolocation/coverage   — tier breakdown across all records
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas.geolocation import (
    GeolocationCoverageResponse,
    GeolocationResolveRequest,
    GeolocationResultResponse,
)
from src.services.geolocation_service import GeolocationService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/geolocation/resolve",
    response_model=GeolocationResultResponse,
    summary="Resolve GPS for a procurement record",
    description=(
        "Run the 3-tier geolocation pipeline for the given procurement record. "
        "Tier 1: eGP embedded GPS. "
        "Tier 2: spaCy NER + RapidFuzz KMHFL match. "
        "Tier 3: UNOCHA ward centroid fallback."
    ),
)
async def resolve_geolocation(
    body: GeolocationResolveRequest, db: Session = Depends(get_db)
):
    """Resolve GPS coordinates for a single procurement record."""
    try:
        service = GeolocationService(db)
        result = service.resolve(body.procurement_id)

        if result is None:
            return GeolocationResultResponse(
                procurement_id=body.procurement_id,
                resolved=False,
            )

        return GeolocationResultResponse(
            procurement_id=body.procurement_id,
            resolved=True,
            tier=result.tier,
            latitude=result.lat,
            longitude=result.lon,
            confidence=result.confidence,
            method=result.method,
            facility_name=result.facility_name,
            match_score=result.match_score,
        )
    except Exception as exc:
        logger.error("geolocation/resolve failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Geolocation resolution failed",
        )


@router.get(
    "/geolocation/coverage",
    response_model=GeolocationCoverageResponse,
    summary="GPS coverage statistics",
    description="Return tier breakdown of GPS resolution across all procurement records.",
)
async def geolocation_coverage(db: Session = Depends(get_db)):
    """Return geolocation tier coverage counts."""
    service = GeolocationService(db)
    stats = service.get_coverage_stats()
    return GeolocationCoverageResponse(**stats)
