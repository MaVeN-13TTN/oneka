"""
Risk scoring router — Phase 4 endpoints.

Endpoints:
  GET /api/v1/risk/score/{project_uuid}
      Returns ghost probability, risk level, and feature breakdown.
      Falls back gracefully when model is not yet trained.

  GET /api/v1/risk/heat-map
      Returns all geolocated projects as a GeoJSON FeatureCollection
      with ghost_probability and risk_level for dashboard pins.
      Supports optional ?risk_level=HIGH,CRITICAL filter.
"""

from __future__ import annotations

import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.geolocation import GeolocationRecord
from src.models.project import Project

router = APIRouter()


# ── GET /risk/score/{project_uuid} ────────────────────────────────────────────


@router.get("/risk/score/{project_uuid}", tags=["Risk Scoring"])
def get_risk_score(project_uuid: UUID, db: Session = Depends(get_db)):
    """
    Return the ML ghost probability and feature breakdown for a project.

    - When the model pkl exists → runs full ML inference and updates DB.
    - When the model is not yet trained (FileNotFoundError) → returns a
      fallback score derived from the existing divergence-based risk_level.
    - Returns 404 if the project does not exist.
    """
    project = db.query(Project).filter(Project.project_uuid == project_uuid).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        from src.services.risk_scoring_service import RiskScoringService

        svc = RiskScoringService()
        score = svc.score_project(project_uuid, db)
    except FileNotFoundError as exc:
        # Model not yet trained — return placeholder with current risk state
        return {
            "project_uuid": str(project_uuid),
            "ghost_probability": (
                float(project.ghost_probability)
                if project.ghost_probability is not None
                else None
            ),
            "risk_level": (
                project.risk_level.value if project.risk_level else None
            ),
            "model_version": "not_trained",
            "model_available": False,
            "message": (
                "Model not yet trained. "
                "Run: cd satellite && python scripts/run_training.py"
            ),
        }

    return {
        "project_uuid": str(score.project_uuid),
        "ghost_probability": round(score.ghost_probability, 4),
        "risk_level": score.risk_level,
        "model_version": score.model_version,
        "model_available": score.model_available,
        "features_used": {
            k: None if isinstance(v, float) and math.isnan(v) else v
            for k, v in score.features_used.items()
        },
    }


# ── GET /risk/heat-map ────────────────────────────────────────────────────────


@router.get("/risk/heat-map", tags=["Risk Scoring"])
def get_risk_heat_map(
    risk_level: Optional[str] = Query(
        default=None,
        description="Comma-separated filter, e.g. HIGH,CRITICAL",
    ),
    db: Session = Depends(get_db),
):
    """
    Return all geolocated projects as a GeoJSON FeatureCollection.

    Each Feature contains:
      - ``geometry``: Point [longitude, latitude]
      - ``properties``: project_uuid, project_name, risk_level,
                        ghost_probability, alert_level, county, status.

    Use ``?risk_level=HIGH,CRITICAL`` to filter by one or more risk levels.
    """
    query = (
        db.query(Project, GeolocationRecord)
        .join(
            GeolocationRecord,
            GeolocationRecord.project_uuid == Project.project_uuid,
        )
    )

    # Optional risk_level filter
    if risk_level:
        requested = {r.strip().upper() for r in risk_level.split(",")}
        from src.models.project import RiskLevel

        valid_levels = {rl.value for rl in RiskLevel}
        filtered = requested & valid_levels
        if filtered:
            query = query.filter(
                Project.risk_level.in_(
                    [RiskLevel[lv] for lv in filtered]
                )
            )

    rows = query.all()

    features = []
    for project, geo in rows:
        if geo.latitude is None or geo.longitude is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(geo.longitude), float(geo.latitude)],
                },
                "properties": {
                    "project_uuid": str(project.project_uuid),
                    "project_name": project.project_name,
                    "risk_level": (
                        project.risk_level.value if project.risk_level else None
                    ),
                    "ghost_probability": (
                        float(project.ghost_probability)
                        if project.ghost_probability is not None
                        else None
                    ),
                    "alert_level": (
                        project.risk_level.value
                        if project.risk_level
                        else "UNKNOWN"
                    ),
                    "county": project.county,
                    "status": (
                        project.status.value if project.status else None
                    ),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
    }
