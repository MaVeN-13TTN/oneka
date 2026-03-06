"""
ML risk scoring service — wraps the trained RandomForest and writes
``ghost_probability`` + ``risk_level`` back to the Project row.

Design notes:
  - Synchronous SQLAlchemy sessions only (matches existing service pattern).
  - Model is lazy-loaded on first ``score_project`` call.
  - If the model pkl is missing *or* ML dependencies are unavailable, the
    service degrades gracefully to a fallback score derived from the existing
    ``risk_level`` set by ``DivergenceService``.
  - FeatureEngineer lives in satellite/src/ and is imported via sys.path
    injection (same pattern as satellite_tasks.py).

Prerequisites (backend venv):
  uv pip install scikit-learn==1.4.0 joblib==1.3.2 pandas==2.1.4
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import settings
from src.models.financial import FinancialRecord
from src.models.geolocation import GeolocationRecord
from src.models.procurement import ProcurementRecord
from src.models.project import Project, RiskLevel
from src.models.satellite import SatelliteAnalysis

# ── Cross-module path wiring for FeatureEngineer (satellite/src/) ─────────────
_REPO_ROOT = Path(__file__).resolve().parents[3]  # …/oneka/
_SAT_SRC = _REPO_ROOT / "satellite" / "src"

for _p in (_SAT_SRC,):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from feature_engineering import FeatureEngineer  # type: ignore[import]

    _FEATURE_ENGINEER_AVAILABLE = True
except ImportError:
    _FEATURE_ENGINEER_AVAILABLE = False

try:
    import joblib
    import numpy as np
    import pandas as pd

    _ML_AVAILABLE = True
except ImportError:
    _ML_AVAILABLE = False


# ── Risk level thresholds ─────────────────────────────────────────────────────

_LOW_MAX = 0.30       # 0.00 – 0.30 → LOW
_MEDIUM_MAX = 0.60    # 0.31 – 0.60 → MEDIUM
_HIGH_MAX = 0.80      # 0.61 – 0.80 → HIGH
                      # 0.81 – 1.00 → CRITICAL


# ── Data class returned by score_project ─────────────────────────────────────


@dataclass
class RiskScore:
    project_uuid: UUID
    ghost_probability: float
    risk_level: str
    model_version: str
    features_used: dict = field(default_factory=dict)
    model_available: bool = True


# ── Mapping helpers ───────────────────────────────────────────────────────────


def _probability_to_risk_level(p: float) -> RiskLevel:
    """Map ghost_probability (0.0 – 1.0) to RiskLevel enum."""
    if p <= _LOW_MAX:
        return RiskLevel.LOW
    if p <= _MEDIUM_MAX:
        return RiskLevel.MEDIUM
    if p <= _HIGH_MAX:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


# ── Service ───────────────────────────────────────────────────────────────────


class RiskScoringService:
    """
    Load the trained ghost-project RandomForest and score individual projects.

    Example::

        svc = RiskScoringService()
        result: RiskScore = svc.score_project(project_uuid, db)
        # -> result.ghost_probability, result.risk_level
    """

    def __init__(self) -> None:
        self._model = None
        self._model_version = "v1"
        self._fe: Optional[FeatureEngineer] = (
            FeatureEngineer() if _FEATURE_ENGINEER_AVAILABLE else None
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def score_project(self, project_uuid: UUID, db: Session) -> RiskScore:
        """
        Score a single project using the ML model.

        Steps:
          1. Fetch project + related DB rows.
          2. Extract feature vector (FeatureEngineer).
          3. ``model.predict_proba(X)`` → ``ghost_probability``.
          4. Map probability → RiskLevel.
          5. Persist ``ghost_probability`` and ``risk_level`` to DB.

        Raises:
            LookupError: Project UUID not found.
            FileNotFoundError: Model pkl missing (not yet trained).
            RuntimeError: ML dependencies not installed.
        """
        project = (
            db.query(Project).filter(Project.project_uuid == project_uuid).first()
        )
        if not project:
            raise LookupError(f"Project {project_uuid} not found")

        # Graceful degradation when ML stack unavailable
        if not _ML_AVAILABLE or not _FEATURE_ENGINEER_AVAILABLE:
            return self._fallback_score(project)

        self._load_model()

        project_data = self._fetch_project_data(project, db)
        feature_series = self._fe.extract_features(project_data)
        X = pd.DataFrame([feature_series], columns=self._fe.FEATURES)

        ghost_probability = float(self._model.predict_proba(X)[0, 1])
        risk_level = _probability_to_risk_level(ghost_probability)

        # Persist to DB
        project.ghost_probability = round(ghost_probability, 4)
        project.risk_level = risk_level
        db.commit()

        return RiskScore(
            project_uuid=project_uuid,
            ghost_probability=ghost_probability,
            risk_level=risk_level.value,
            model_version=self._model_version,
            features_used=feature_series.to_dict(),
            model_available=True,
        )

    def score_all_active_projects(self, db: Session) -> list[RiskScore]:
        """
        Batch score all ONGOING projects.

        Projects that fail individually are returned as fallback scores so the
        batch continues rather than aborting on the first error.
        """
        from src.models.project import ProjectStatus

        projects = (
            db.query(Project)
            .filter(Project.status == ProjectStatus.ONGOING)
            .all()
        )
        results: list[RiskScore] = []
        for project in projects:
            try:
                results.append(self.score_project(project.project_uuid, db))
            except Exception:
                results.append(self._fallback_score(project))
        return results

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Lazy-load the trained model pipeline from disk on first call."""
        if self._model is not None:
            return
        if not _ML_AVAILABLE:
            raise RuntimeError(
                "scikit-learn / joblib not installed. "
                "Run: uv pip install scikit-learn joblib pandas"
            )
        model_path = Path(settings.ml_model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"ML model not found at {model_path}. "
                "Train it first:  cd satellite && python scripts/run_training.py"
            )
        self._model = joblib.load(model_path)

    def _fetch_project_data(self, project: Project, db: Session) -> dict:
        """
        Assemble the ``project_data`` dict expected by
        ``FeatureEngineer.extract_features()``.
        """
        # Latest NDVI analysis with ndvi_slope populated
        latest_ndvi = (
            db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project.project_uuid,
                SatelliteAnalysis.analysis_type == "NDVI_change",
                SatelliteAnalysis.ndvi_slope.isnot(None),
            )
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        # Latest SAR analysis with sar_backscatter_delta populated
        latest_sar = (
            db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project.project_uuid,
                SatelliteAnalysis.analysis_type == "SAR_backscatter",
                SatelliteAnalysis.sar_backscatter_delta.isnot(None),
            )
            .order_by(SatelliteAnalysis.acquisition_date.desc())
            .first()
        )

        # Earliest scene with ndvi_mean < 0.3 (vegetation clearing signal)
        clearing_scene = (
            db.query(SatelliteAnalysis)
            .filter(
                SatelliteAnalysis.project_uuid == project.project_uuid,
                SatelliteAnalysis.ndvi_mean < 0.3,
            )
            .order_by(SatelliteAnalysis.acquisition_date.asc())
            .first()
        )

        # Latest financial record (by period end date)
        latest_fin = (
            db.query(FinancialRecord)
            .filter(FinancialRecord.project_uuid == project.project_uuid)
            .order_by(FinancialRecord.period_end_date.desc())
            .first()
        )

        # Procurement record (first linked record)
        procurement = (
            db.query(ProcurementRecord)
            .filter(ProcurementRecord.project_uuid == project.project_uuid)
            .first()
        )

        # Approximate divergence_score from stored risk_score
        # DivergenceService writes: risk_score = int(min(100, max(0, divergence + 50)))
        # Invert: divergence ≈ risk_score − 50
        divergence_score: Optional[float] = (
            float(project.risk_score) - 50.0
            if project.risk_score is not None
            else None
        )

        return {
            "project_name": project.project_name,
            "project_type": (
                project.project_type.value if project.project_type else None
            ),
            "county": project.county,
            "contract_sum_kes": (
                float(procurement.contract_sum_kes)
                if procurement and procurement.contract_sum_kes
                else project.estimated_value_kes
                if project.estimated_value_kes
                else None
            ),
            "contractor_nca_license": (
                procurement.contractor_nca_license if procurement else None
            ),
            "ndvi_slope": (
                float(latest_ndvi.ndvi_slope)
                if latest_ndvi and latest_ndvi.ndvi_slope is not None
                else None
            ),
            "sar_backscatter_delta": (
                float(latest_sar.sar_backscatter_delta)
                if latest_sar and latest_sar.sar_backscatter_delta is not None
                else None
            ),
            "divergence_score": divergence_score,
            "award_date": (
                procurement.award_date.isoformat()
                if procurement and procurement.award_date
                else None
            ),
            "first_ndvi_drop_date": (
                clearing_scene.acquisition_date.isoformat()
                if clearing_scene and clearing_scene.acquisition_date
                else None
            ),
            "completion_date": (
                procurement.expected_completion_date.isoformat()
                if procurement and procurement.expected_completion_date
                else None
            ),
            "absorption_rate": (
                float(latest_fin.absorption_rate)
                if latest_fin and latest_fin.absorption_rate is not None
                else None
            ),
        }

    @staticmethod
    def _fallback_score(project: Project) -> RiskScore:
        """
        Return a probability estimate derived from the existing risk_level when
        the model is unavailable (not trained yet or dependencies missing).
        """
        level_prob: dict[str, float] = {
            "LOW": 0.15,
            "MEDIUM": 0.45,
            "HIGH": 0.70,
            "CRITICAL": 0.90,
        }
        current = project.risk_level.value if project.risk_level else "MEDIUM"
        return RiskScore(
            project_uuid=project.project_uuid,
            ghost_probability=level_prob.get(current, 0.45),
            risk_level=current,
            model_version="fallback",
            model_available=False,
        )
