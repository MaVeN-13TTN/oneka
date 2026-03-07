"""
Health check and system status endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
import time
from datetime import datetime

from src.database import get_db
from src.config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Basic health check endpoint.

    Returns:
        dict: Service status and timestamp
    """
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/db")
async def database_health(db: Session = Depends(get_db)):
    """
    Check database connectivity and PostGIS extension.

    Args:
        db: Database session

    Returns:
        dict: Database status and PostGIS version

    Raises:
        HTTPException: If database is unreachable
    """
    try:
        # Test basic connection
        db.execute(text("SELECT 1"))

        # Test PostGIS extension
        result = db.execute(text("SELECT PostGIS_version()")).scalar()

        # Count tables
        table_count_result = db.execute(
            text(
                """
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
            )
        ).scalar()

        return {
            "status": "healthy",
            "database": "connected",
            "postgis_version": result,
            "table_count": table_count_result,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {str(e)}",
        )


@router.get("/status")
async def system_status(db: Session = Depends(get_db)):
    """
    Comprehensive system status with record counts.

    Args:
        db: Database session

    Returns:
        dict: System status, database stats, and record counts
    """
    try:
        # Import models here to avoid circular imports
        from src.models.project import Project
        from src.models.procurement import ProcurementRecord
        from src.models.geolocation import GeolocationRecord
        from src.models.satellite import SatelliteAnalysis

        # Count records
        project_count = db.query(Project).count()
        tender_count = db.query(ProcurementRecord).count()

        # Count geolocated projects
        geolocated_count = (
            db.query(GeolocationRecord)
            .filter(GeolocationRecord.verified == True)
            .count()
        )

        # Count all geolocation records
        geolocation_total = db.query(GeolocationRecord).count()

        # Count satellite analyses
        satellite_count = db.query(SatelliteAnalysis).count()

        # Count high-risk projects
        from src.models.project import RiskLevel

        high_risk_count = (
            db.query(Project)
            .filter(Project.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL]))
            .count()
        )

        return {
            "status": "operational",
            "service": settings.app_name,
            "version": settings.api_version,
            "environment": settings.environment,
            "database": {
                "connected": True,
                "records": {
                    "projects": project_count,
                    "tenders": tender_count,
                    "geolocation_records": geolocation_total,
                    "geolocated_verified": geolocated_count,
                    "satellite_analyses": satellite_count,
                    "high_risk_projects": high_risk_count,
                },
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        # If models aren't created yet, return basic status
        return {
            "status": "operational",
            "service": settings.app_name,
            "version": settings.api_version,
            "environment": settings.environment,
            "database": {
                "connected": True,
                "note": "Tables not yet created or error querying: " + str(e),
            },
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/ping")
async def ping():
    """
    Simple ping endpoint for load balancer health checks.

    Returns:
        dict: Minimal response with timestamp
    """
    return {"ping": "pong", "timestamp": time.time()}
