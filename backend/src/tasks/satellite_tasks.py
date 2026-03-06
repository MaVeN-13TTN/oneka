"""
Satellite Celery tasks — processing pipeline for Sentinel-1 and Sentinel-2 imagery.

Task graph per project:
  analyse_project_task
    ├─ Download S2 scenes (cloud ≤ 20 %, top 3)
    │    ├─ NDWIProcessor  →  skip if water_present
    │    └─ NDVIProcessor  →  save_ndvi_result()
    ├─ Download S1 GRD scene
    │    └─ SARProcessor   →  save_sar_result()
    ├─ SatelliteService.compute_ndvi_slope()
    ├─ DivergenceService.calculate_divergence()
    └─ score_project_risk_task.delay()

batch_analyse_flagged_projects_task enqueues analyse_project_task for every
project that has a GeolocationRecord but risk_level IS NULL.
"""

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# ─── repo path wiring ────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # oneka/
_SATELLITE_SRC = _REPO_ROOT / "satellite"
for _p in [str(_REPO_ROOT), str(_SATELLITE_SRC)]:
    if _p not in sys.path:
        sys.path.insert(0, str(_p))

from src.celery_app import celery_app
from src.database import SessionLocal
from src.models.geolocation import GeolocationRecord
from src.models.project import Project, RiskLevel
from src.services.satellite_service import SatelliteService
from src.services.divergence_service import DivergenceService


# ─── helpers ─────────────────────────────────────────────────────────────────

def _require_copernicus_downloader():
    """Lazy import — raises ImportError with clear message if unavailable."""
    try:
        from src.download import CopernicusDownloader  # satellite venv path
        return CopernicusDownloader
    except ImportError as exc:
        raise ImportError(
            "CopernicusDownloader not available.  "
            "Ensure the satellite venv is active and sentinelsat is installed."
        ) from exc


# ─── tasks ───────────────────────────────────────────────────────────────────

@celery_app.task(
    name="src.tasks.satellite_tasks.analyse_project_task",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def analyse_project_task(
    self,
    project_uuid: str,
    lat: float,
    lon: float,
    start_date: str,
    end_date: str,
) -> dict:
    """
    Full satellite analysis pipeline for a single project.

    Steps:
      1. Search and download up to 3 Sentinel-2 L2A scenes (cloud ≤ 20 %).
      2. For each scene: run NDWIProcessor; skip if water_present=True.
      3. For non-water scenes: run NDVIProcessor; persist via SatelliteService.
      4. Search and download 1 Sentinel-1 GRD scene.
      5. Run SARProcessor; persist via SatelliteService.
      6. Compute NDVI temporal slope (requires ≥ 2 scenes).
      7. Run DivergenceService.calculate_divergence().
      8. Enqueue score_project_risk_task.

    Args:
        project_uuid:  String UUID of the project.
        lat:           Site latitude.
        lon:           Site longitude.
        start_date:    Scene search window start (YYYY-MM-DD).
        end_date:      Scene search window end (YYYY-MM-DD).

    Returns:
        Summary dict: {ndvi_scenes_saved, sar_scenes_saved, ndvi_slope, alert_level}.
    """
    try:
        db = SessionLocal()
        sat_service = SatelliteService(db)
        uuid_obj = UUID(project_uuid)

        ndvi_saved = 0
        sar_saved = 0
        ndvi_slope: Optional[float] = None
        divergence_result: dict = {}

        try:
            CopernicusDownloader = _require_copernicus_downloader()
            downloader = CopernicusDownloader()

            import tempfile
            from pathlib import Path as _Path

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = _Path(tmp_dir)

                # ── Sentinel-2 NDVI / NDWI ──────────────────────────────
                s2_scenes = downloader.search_sentinel2(
                    lat, lon, start_date, end_date, max_cloud_cover=20
                )[:3]

                for scene_meta in s2_scenes:
                    scene_dir = downloader.download_scene(
                        scene_meta["uuid"], tmp_path / "s2", unzip=True
                    )
                    if scene_dir is None:
                        continue

                    acq_date = date.fromisoformat(scene_meta["sensing_date"])

                    # NDWI water check
                    try:
                        from src.process_ndwi import NDWIProcessor
                        ndwi_result = NDWIProcessor(scene_dir).process()
                        if ndwi_result.water_present:
                            logger.info(
                                "Skipping scene %s (water detected, NDWI=%.3f)",
                                scene_meta["title"],
                                ndwi_result.ndwi_mean,
                            )
                            continue
                    except Exception as ndwi_exc:
                        logger.warning("NDWI check failed: %s", ndwi_exc)

                    # NDVI processing
                    try:
                        from src.process_ndvi import NDVIProcessor
                        ndvi_result = NDVIProcessor(scene_dir).process(
                            lat, lon, tmp_path / "ndvi_out"
                        )
                        sat_service.save_ndvi_result(uuid_obj, ndvi_result, acq_date)
                        ndvi_saved += 1
                    except Exception as ndvi_exc:
                        logger.warning(
                            "NDVI processing failed for scene %s: %s",
                            scene_meta["title"],
                            ndvi_exc,
                        )

                # ── Sentinel-1 SAR ───────────────────────────────────────
                s1_scenes = downloader.search_sentinel1(
                    lat, lon, start_date, end_date
                )[:1]

                for scene_meta in s1_scenes:
                    scene_dir = downloader.download_scene(
                        scene_meta["uuid"], tmp_path / "s1", unzip=True
                    )
                    if scene_dir is None:
                        continue

                    try:
                        from src.process_sar import SARProcessor
                        sar_result = SARProcessor(scene_dir).process(
                            lat, lon, tmp_path / "sar_out"
                        )
                        acq_date = date.fromisoformat(scene_meta["sensing_date"])
                        sat_service.save_sar_result(uuid_obj, sar_result, acq_date)
                        sar_saved += 1
                    except Exception as sar_exc:
                        logger.warning(
                            "SAR processing failed for scene %s: %s",
                            scene_meta["title"],
                            sar_exc,
                        )

        except ImportError as ie:
            logger.warning(
                "Satellite libraries not available (%s) — skipping scene downloads", ie
            )

        # ── Temporal slope + divergence ──────────────────────────────────
        if ndvi_saved >= 2:
            ndvi_slope = sat_service.compute_ndvi_slope(uuid_obj)

        div_service = DivergenceService(db)
        divergence_result = div_service.calculate_divergence(uuid_obj)

        # ── Risk scoring (Phase 4 placeholder) ──────────────────────────
        score_project_risk_task.delay(project_uuid)

        summary = {
            "project_uuid": project_uuid,
            "ndvi_scenes_saved": ndvi_saved,
            "sar_scenes_saved": sar_saved,
            "ndvi_slope": ndvi_slope,
            "alert_level": divergence_result.get("alert_level", "UNKNOWN"),
        }
        logger.info("analyse_project_task complete: %s", summary)
        return summary

    except Exception as exc:
        logger.error(
            "analyse_project_task failed for %s: %s", project_uuid, exc, exc_info=True
        )
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    name="src.tasks.satellite_tasks.batch_analyse_flagged_projects_task",
    bind=True,
)
def batch_analyse_flagged_projects_task(self) -> dict:
    """
    Enqueue analyse_project_task for all geolocated projects with no risk_level.

    Run this manually or via Celery beat to bootstrap a full site survey.

    Returns:
        Dict: {queued: int, skipped_no_geo: int, total_projects: int}
    """
    db = SessionLocal()
    try:
        projects = (
            db.query(Project)
            .filter(Project.risk_level.is_(None))
            .all()
        )
        queued = 0
        skipped = 0

        for project in projects:
            geo = (
                db.query(GeolocationRecord)
                .filter(GeolocationRecord.project_uuid == project.project_uuid)
                .first()
            )
            if not geo:
                skipped += 1
                continue

            from datetime import datetime, timedelta
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=540)).strftime("%Y-%m-%d")

            analyse_project_task.delay(
                str(project.project_uuid),
                float(geo.latitude),
                float(geo.longitude),
                start_date,
                end_date,
            )
            queued += 1

        result = {
            "queued": queued,
            "skipped_no_geo": skipped,
            "total_projects": len(projects),
        }
        logger.info("batch_analyse_flagged_projects_task: %s", result)
        return result
    finally:
        db.close()


@celery_app.task(
    name="src.tasks.satellite_tasks.score_project_risk_task",
    bind=True,
    max_retries=1,
)
def score_project_risk_task(self, project_uuid: str) -> dict:
    """
    Phase 4 placeholder — ML risk scoring.

    For Phase 3, maps the divergence alert level directly to RiskLevel.
    Phase 4 will replace this with an actual RandomForest/XGBoost inference call.

    Args:
        project_uuid: String UUID of the project to score.

    Returns:
        Dict: {project_uuid, risk_level, risk_score}.
    """
    db = SessionLocal()
    try:
        uuid_obj = UUID(project_uuid)
        project = db.query(Project).filter(Project.project_uuid == uuid_obj).first()
        if not project:
            return {"project_uuid": project_uuid, "error": "not found"}

        # Risk level set by DivergenceService — return current state
        result = {
            "project_uuid": project_uuid,
            "risk_level": project.risk_level.value if project.risk_level else None,
            "risk_score": project.risk_score,
        }
        logger.info("score_project_risk_task complete: %s", result)
        return result
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        db.close()
