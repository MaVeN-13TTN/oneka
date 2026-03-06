"""
DivergenceService — financial vs. physical progress divergence scoring.

The divergence score is the primary ghost-project detection signal:
  divergence = financial_progress - physical_progress

High financial absorption + low physical activity ⟹ potential ghost project.

Alert levels (written to Project.risk_level):
  RED    → divergence > 50  (CRITICAL risk)
  YELLOW → 20 ≤ divergence ≤ 50  (HIGH risk)
  GREEN  → divergence < 20  (LOW/MEDIUM risk based on absolute physical score)

Physical progress is inferred from:
  1. ndvi_slope (NDVI/month)  —  negative ≡ land clearing ≡ construction activity
  2. sar_backscatter_delta (dB) — positive ≡ new structures appearing
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.financial import FinancialRecord
from src.models.project import Project, RiskLevel
from src.models.satellite import SatelliteAnalysis

logger = logging.getLogger(__name__)

# ── Physical progress mapping ─────────────────────────────────────────────────
# NDVI slope thresholds (NDVI units/month)
_NDVI_RAPID_CLEARING = -0.05   # strong clearing activity → high physical progress
_NDVI_MODERATE = -0.02         # moderate change
_NDVI_MINIMAL = 0.01           # near-zero → little construction

# SAR VV backscatter delta thresholds (dB)
_SAR_STRONG_SIGNAL = 3.0       # > 3 dB increase → new structures
_SAR_MODERATE_SIGNAL = 1.0
_SAR_WEAK_SIGNAL = -1.0

# Divergence alert thresholds
_RED_THRESHOLD = 50.0
_YELLOW_THRESHOLD = 20.0


class DivergenceService:
    """
    Computes the divergence between financial absorption (% of budget spent)
    and physical site activity (derived from NDVI slope and SAR backscatter).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_divergence(self, project_uuid: UUID) -> dict:
        """
        Compute and persist divergence metrics for *project_uuid*.

        Side-effects:
          - Updates Project.risk_level based on the computed alert level.
          - Updates Project.risk_score (0-100, higher = more suspicious).

        Returns:
            Dict with keys:
              financial_progress  (float or None)
              physical_progress   (float or None)
              divergence_score    (float or None)
              alert_level         ('RED' | 'YELLOW' | 'GREEN' | 'UNKNOWN')
        """
        financial_progress = self._get_financial_progress(project_uuid)
        physical_progress = self._compute_physical_progress(project_uuid)

        divergence_score: Optional[float] = None
        alert_level = "UNKNOWN"
        risk_score: Optional[int] = None

        if financial_progress is not None and physical_progress is not None:
            divergence_score = round(financial_progress - physical_progress, 2)
            alert_level, risk_level_enum = self._classify_alert(
                divergence_score, physical_progress
            )
            risk_score = int(min(100, max(0, divergence_score + 50)))

            # Persist risk level on the project row
            project = (
                self.db.query(Project)
                .filter(Project.project_uuid == project_uuid)
                .first()
            )
            if project:
                project.risk_level = risk_level_enum
                project.risk_score = risk_score
                self.db.commit()

        logger.info(
            "Divergence for project %s: fin=%.1f%% phys=%.1f%% "
            "divergence=%.1f alert=%s",
            project_uuid,
            financial_progress or 0,
            physical_progress or 0,
            divergence_score or 0,
            alert_level,
        )

        return {
            "project_uuid": str(project_uuid),
            "financial_progress": financial_progress,
            "physical_progress": physical_progress,
            "divergence_score": divergence_score,
            "alert_level": alert_level,
        }

    def get_divergence_timeline(self, project_uuid: UUID) -> list[dict]:
        """
        Build a per-scene timeline of divergence estimates.

        Returns a list of dicts ordered by acquisition_date, each containing:
          acquisition_date, ndvi_mean, sar_vv_mean, financial_progress,
          divergence_estimate (or None if insufficient data).
        """
        analyses = (
            self.db.query(SatelliteAnalysis)
            .filter(SatelliteAnalysis.project_uuid == project_uuid)
            .order_by(SatelliteAnalysis.acquisition_date.asc())
            .all()
        )

        financial_progress = self._get_financial_progress(project_uuid)
        timeline = []

        for a in analyses:
            ndvi_mean = float(a.ndvi_mean) if a.ndvi_mean is not None else None
            sar_vv = float(a.sar_vv_mean) if a.sar_vv_mean is not None else None
            ndvi_slope = float(a.ndvi_slope) if a.ndvi_slope is not None else None
            sar_delta = (
                float(a.sar_backscatter_delta)
                if a.sar_backscatter_delta is not None
                else None
            )

            physical_est: Optional[float] = None
            if ndvi_slope is not None or sar_delta is not None:
                ndvi_score = self._ndvi_score(ndvi_slope) if ndvi_slope is not None else None
                sar_score = self._sar_score(sar_delta) if sar_delta is not None else None
                scores = [s for s in [ndvi_score, sar_score] if s is not None]
                physical_est = sum(scores) / len(scores) if scores else None

            divergence_est: Optional[float] = None
            if financial_progress is not None and physical_est is not None:
                divergence_est = round(financial_progress - physical_est, 2)

            timeline.append(
                {
                    "acquisition_date": str(a.acquisition_date),
                    "analysis_type": a.analysis_type,
                    "ndvi_mean": ndvi_mean,
                    "sar_vv_mean": sar_vv,
                    "ndvi_slope": ndvi_slope,
                    "financial_progress": financial_progress,
                    "divergence_estimate": divergence_est,
                }
            )

        return timeline

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_financial_progress(self, project_uuid: UUID) -> Optional[float]:
        """
        Return the latest absorption_rate (%) from FinancialRecord.

        Returns None if no financial records exist.
        """
        record = (
            self.db.query(FinancialRecord)
            .filter(FinancialRecord.project_uuid == project_uuid)
            .order_by(FinancialRecord.created_at.desc())
            .first()
        )
        if record is None or record.absorption_rate is None:
            return None
        return float(record.absorption_rate)

    def _compute_physical_progress(self, project_uuid: UUID) -> Optional[float]:
        """
        Estimate physical site activity as a 0-100 score.

        Sources (in priority order):
          1. Latest ndvi_slope if available on a NDVI_change row.
          2. Latest sar_backscatter_delta if available on a SAR_backscatter row.
          3. None if neither source has data.
        """
        # Latest NDVI slope
        ndvi_analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project_uuid,
                SatelliteAnalysis.analysis_type == "NDVI_change",
                SatelliteAnalysis.ndvi_slope.isnot(None),
            )
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        # Latest SAR delta
        sar_analysis = (
            self.db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project_uuid,
                SatelliteAnalysis.analysis_type == "SAR_backscatter",
                SatelliteAnalysis.sar_backscatter_delta.isnot(None),
            )
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        ndvi_score: Optional[float] = None
        sar_score: Optional[float] = None

        if ndvi_analysis:
            ndvi_score = self._ndvi_score(float(ndvi_analysis.ndvi_slope))

        if sar_analysis:
            sar_score = self._sar_score(float(sar_analysis.sar_backscatter_delta))

        scores = [s for s in [ndvi_score, sar_score] if s is not None]
        if not scores:
            return None

        return round(sum(scores) / len(scores), 2)

    @staticmethod
    def _ndvi_score(slope: float) -> float:
        """Map NDVI slope to a 0–100 physical activity score."""
        if slope < _NDVI_RAPID_CLEARING:
            return 90.0
        if slope < _NDVI_MODERATE:
            return 65.0
        if slope < _NDVI_MINIMAL:
            return 40.0
        return 15.0  # positive slope = vegetation recovery, no construction

    @staticmethod
    def _sar_score(delta: float) -> float:
        """Map SAR backscatter delta (dB) to a 0–100 physical activity score."""
        if delta > _SAR_STRONG_SIGNAL:
            return 85.0
        if delta > _SAR_MODERATE_SIGNAL:
            return 60.0
        if delta > _SAR_WEAK_SIGNAL:
            return 35.0
        return 15.0  # negative delta = no new structures

    @staticmethod
    def _classify_alert(
        divergence_score: float, physical_progress: float
    ) -> tuple[str, RiskLevel]:
        """Return (alert_level_str, RiskLevel enum) based on divergence."""
        if divergence_score > _RED_THRESHOLD:
            return "RED", RiskLevel.CRITICAL
        if divergence_score > _YELLOW_THRESHOLD:
            return "YELLOW", RiskLevel.HIGH
        # Green: project is on-track; use physical progress to set LOW vs MEDIUM
        if physical_progress >= 50.0:
            return "GREEN", RiskLevel.LOW
        return "GREEN", RiskLevel.MEDIUM
