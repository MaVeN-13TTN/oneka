"""
SatelliteService — DB bridge for satellite processing results.

Responsibilities:
  - Queue a new satellite analysis for a project via Celery
  - Persist NDVIProcessor / SARProcessor output dicts to satellite_analyses
  - Retrieve time-series analyses for a project
  - Compute and store the ndvi_slope linear regression
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

import numpy as np
from sqlalchemy.orm import Session

from src.models.satellite import SatelliteAnalysis
from src.models.geolocation import GeolocationRecord
from src.models.project import Project

logger = logging.getLogger(__name__)

# Look-back window for Sentinel searches (days)
_DEFAULT_LOOKBACK_DAYS = 540  # ~18 months


class SatelliteService:
    """
    Provides methods to queue satellite analysis and persist results to the DB.

    Designed to be used by:
      - API router  (queue_analysis, get_time_series)
      - Celery tasks (save_ndvi_result, save_sar_result, compute_ndvi_slope)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Queuing
    # ------------------------------------------------------------------

    def queue_analysis(
        self,
        project_uuid: UUID,
        lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    ) -> str:
        """
        Enqueue a satellite analysis Celery task for *project_uuid*.

        Looks up the project's GPS coordinates from GeolocationRecord, then
        calls ``analyse_project_task`` via ``celery_app.send_task`` to avoid
        circular imports between the service and the tasks module.

        Args:
            project_uuid:   UUID of the project to analyse.
            lookback_days:  How many days back to search for Sentinel scenes.

        Returns:
            Celery task ID string.

        Raises:
            ValueError: If the project has no GeolocationRecord.
            LookupError: If the project does not exist.
        """
        project = (
            self.db.query(Project)
            .filter(Project.project_uuid == project_uuid)
            .first()
        )
        if not project:
            raise LookupError(f"Project {project_uuid} not found")

        geo = (
            self.db.query(GeolocationRecord)
            .filter(GeolocationRecord.project_uuid == project_uuid)
            .first()
        )
        if not geo:
            raise ValueError(
                f"Project {project_uuid} has no geolocation — run geolocation "
                "resolution first"
            )

        lat = float(geo.latitude)
        lon = float(geo.longitude)

        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_dt = datetime.utcnow() - timedelta(days=lookback_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        from src.celery_app import celery_app

        result = celery_app.send_task(
            "src.tasks.satellite_tasks.analyse_project_task",
            args=[str(project_uuid), lat, lon, start_date, end_date],
        )
        logger.info(
            "Queued satellite analysis for project %s — task_id=%s",
            project_uuid,
            result.id,
        )
        return result.id

    # ------------------------------------------------------------------
    # Persisting processor output
    # ------------------------------------------------------------------

    def save_ndvi_result(
        self,
        project_uuid: UUID,
        result: dict,
        acquisition_date: Optional[date] = None,
    ) -> SatelliteAnalysis:
        """
        Persist the output dict from NDVIProcessor.process() to satellite_analyses.

        Args:
            project_uuid:     Parent project UUID.
            result:           Dict returned by NDVIProcessor.process().
            acquisition_date: Scene acquisition date (falls back to today).

        Returns:
            Committed SatelliteAnalysis ORM instance.
        """
        stats = result.get("statistics", {})
        ndvi_mean = stats.get("mean")
        ndvi_std = stats.get("std")
        ndvi_min = stats.get("min")
        ndvi_max = stats.get("max")

        acq_date = acquisition_date or date.today()
        scene_id = result.get("scene_id")

        analysis = SatelliteAnalysis(
            project_uuid=project_uuid,
            sensor="Sentinel-2",
            acquisition_date=acq_date,
            scene_id=scene_id,
            analysis_type="NDVI_change",
            ndvi_mean=ndvi_mean if ndvi_mean is not None and np.isfinite(ndvi_mean) else None,
            ndvi_std=ndvi_std if ndvi_std is not None and np.isfinite(ndvi_std) else None,
            ndvi_min=ndvi_min if ndvi_min is not None and np.isfinite(ndvi_min) else None,
            ndvi_max=ndvi_max if ndvi_max is not None and np.isfinite(ndvi_max) else None,
            image_url=result.get("geotiff_path"),
            thumbnail_url=result.get("visualization_path"),
            processing_algorithm="rasterio",
            processing_date=date.today(),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        logger.info(
            "Saved NDVI result for project %s — analysis_id=%s",
            project_uuid,
            analysis.analysis_id,
        )
        return analysis

    def save_sar_result(
        self,
        project_uuid: UUID,
        result: dict,
        acquisition_date: Optional[date] = None,
        baseline_vv: Optional[float] = None,
    ) -> SatelliteAnalysis:
        """
        Persist the output dict from SARProcessor.process() to satellite_analyses.

        Args:
            project_uuid:     Parent project UUID.
            result:           Dict returned by SARProcessor.process().
            acquisition_date: Scene acquisition date (falls back to today).
            baseline_vv:      Historical baseline VV backscatter (dB) for
                              computing sar_backscatter_delta.

        Returns:
            Committed SatelliteAnalysis ORM instance.
        """
        backscatter = result.get("backscatter", {})
        vv_stats = backscatter.get("VV", {})
        vh_stats = backscatter.get("VH", {})

        vv_mean = vv_stats.get("mean")
        vh_mean = vh_stats.get("mean")

        sar_delta: Optional[float] = None
        if baseline_vv is not None and vv_mean is not None and np.isfinite(vv_mean):
            sar_delta = round(vv_mean - baseline_vv, 4)

        acq_date = acquisition_date or date.today()

        analysis = SatelliteAnalysis(
            project_uuid=project_uuid,
            sensor="Sentinel-1",
            acquisition_date=acq_date,
            scene_id=result.get("scene_id"),
            analysis_type="SAR_backscatter",
            sar_vv_mean=vv_mean if vv_mean is not None and np.isfinite(vv_mean) else None,
            sar_vh_mean=vh_mean if vh_mean is not None and np.isfinite(vh_mean) else None,
            sar_backscatter_delta=sar_delta,
            processing_algorithm="pyrosar",
            processing_date=date.today(),
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        logger.info(
            "Saved SAR result for project %s — analysis_id=%s",
            project_uuid,
            analysis.analysis_id,
        )
        return analysis

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_time_series(self, project_uuid: UUID) -> list[SatelliteAnalysis]:
        """
        Return all SatelliteAnalysis rows for a project, ordered by acquisition date.
        """
        return (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.asc())
            .all()
        )

    def get_analyses_count(self, project_uuid: UUID) -> int:
        """Return the number of satellite analyses stored for *project_uuid*."""
        return (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .count()
        )

    # ------------------------------------------------------------------
    # Temporal slope
    # ------------------------------------------------------------------

    def compute_ndvi_slope(self, project_uuid: UUID) -> Optional[float]:
        """
        Compute the NDVI temporal slope for *project_uuid* and persist it.

        Queries all NDVI_change SatelliteAnalysis rows sorted by
        acquisition_date, runs a linear regression on (months, ndvi_mean),
        and writes the resulting slope back to every analysis row for the
        project.

        Returns:
            Slope in NDVI/month, or None if fewer than 2 valid scenes.
        """
        analyses = (
            self.db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project_uuid,
                SatelliteAnalysis.analysis_type == "NDVI_change",
                SatelliteAnalysis.ndvi_mean.isnot(None),
            )
            .order_by(SatelliteAnalysis.acquisition_date.asc())
            .all()
        )

        if len(analyses) < 2:
            logger.debug(
                "Not enough NDVI scenes for slope computation (project=%s, n=%d)",
                project_uuid,
                len(analyses),
            )
            return None

        dates = [str(a.acquisition_date) for a in analyses]
        ndvi_means = [float(a.ndvi_mean) for a in analyses]

        # Linear regression: months since first scene
        base = datetime.strptime(dates[0], "%Y-%m-%d")
        x = np.array(
            [(datetime.strptime(d, "%Y-%m-%d") - base).days / 30.44 for d in dates],
            dtype=float,
        )
        y = np.array(ndvi_means, dtype=float)
        valid = np.isfinite(y)

        if valid.sum() < 2:
            return None

        coeffs = np.polyfit(x[valid], y[valid], 1)
        slope = round(float(coeffs[0]), 4)

        # Persist slope on every NDVI row for the project
        for analysis in analyses:
            analysis.ndvi_slope = slope
        self.db.commit()

        logger.info(
            "NDVI slope for project %s = %.4f NDVI/month", project_uuid, slope
        )
        return slope
