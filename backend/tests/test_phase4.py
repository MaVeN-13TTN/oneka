"""
Phase 4 test suite — ML Feature Engineering, Training Pipeline, and Risk Scoring.

Coverage targets:
  feature_engineering.py  (satellite/src)
  train_model.py           (satellite/src)
  risk_scoring_service.py  (backend/src/services)
  ml_tasks.py              (backend/src/tasks)
  risk.py                  (backend/src/routers)

Tests that require scikit-learn are conditionally skipped via
``pytest.importorskip`` when the backend venv has not yet installed it.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest

# ── Ensure satellite/src is importable ───────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/tests/… → oneka/
_SAT_SRC = _REPO_ROOT / "satellite" / "src"
if str(_SAT_SRC) not in sys.path:
    sys.path.insert(0, str(_SAT_SRC))

from feature_engineering import FeatureEngineer, FEATURES  # satellite module

_TRAINING_CSV = _REPO_ROOT / "satellite" / "data" / "training" / "training_projects.csv"

# ── Backend model imports ─────────────────────────────────────────────────────
from src.models.project import Project, ProjectStatus, RiskLevel

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_project(test_db, *, project_uuid=None, name="Test Road", status=None,
                  risk_level=None, county="Nairobi"):
    p = Project(
        project_uuid=project_uuid or uuid4(),
        project_name=name,
        county=county,
        status=status or ProjectStatus.ONGOING,
        risk_level=risk_level,
    )
    test_db.add(p)
    test_db.commit()
    test_db.refresh(p)
    return p


# =============================================================================
# Group 1 — FeatureEngineer (CSV training mode)
# =============================================================================

class TestFeatureEngineer:
    """Tests for satellite/src/feature_engineering.py — CSV training dataframe."""

    def test_build_training_dataframe_shape(self):
        """30 projects × 10 features."""
        fe = FeatureEngineer()
        X, y = fe.build_training_dataframe(_TRAINING_CSV)
        assert X.shape == (30, len(FEATURES))
        assert len(y) == 30

    def test_feature_names(self):
        """Returned columns match canonical FEATURES list."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        assert list(X.columns) == FEATURES

    def test_label_distribution(self):
        """Training CSV has exactly 10 ghost (1) and 20 success (0) labels."""
        fe = FeatureEngineer()
        _, y = fe.build_training_dataframe(_TRAINING_CSV)
        assert y.sum() == 10
        assert (y == 0).sum() == 20

    def test_contract_value_log_kiambu_hospital(self):
        """Row 0: Kiambu Level 4 Hospital, budget_kes=350_000_000 → log10≈8.544."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        expected = math.log10(350_000_000)
        assert abs(X.iloc[0]["contract_value_log"] - expected) < 0.001

    def test_project_type_health_encoded(self):
        """'Hospital' keyword → project_type_encoded = 0 (HEALTH)."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        # Row 0: Kiambu Level 4 Hospital Construction
        assert X.iloc[0]["project_type_encoded"] == 0.0

    def test_project_type_roads_encoded(self):
        """'Road' keyword → project_type_encoded = 2 (ROADS)."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        # Row 1: Mombasa Mtongwe Link Road
        assert X.iloc[1]["project_type_encoded"] == 2.0

    def test_county_cloud_risk_known_county(self):
        """Kisumu maps to a cloud-risk value in the MODIS lookup table."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        # Row 4: Kisumu Kondele Footbridge
        risk = X.iloc[4]["county_cloud_risk"]
        assert 0.0 < risk <= 1.0

    def test_satellite_features_are_nan_in_csv_mode(self):
        """ndvi_slope and sar_backscatter_delta are NaN for CSV-only training."""
        fe = FeatureEngineer()
        X, _ = fe.build_training_dataframe(_TRAINING_CSV)
        assert np.isnan(X.iloc[0]["ndvi_slope"])
        assert np.isnan(X.iloc[0]["sar_backscatter_delta"])
        assert np.isnan(X.iloc[0]["divergence_score"])


# =============================================================================
# Group 2 — Model Training (requires scikit-learn)
# =============================================================================

# Sets a flag without killing the module import when sklearn is absent.
# Only TestTrainModel is gated; Groups 3-5 fall back gracefully via
# RiskScoringService._fallback_score() when sklearn is not available.
try:
    import sklearn as _sklearn  # noqa: F401

    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


@pytest.mark.skipif(not _SKLEARN_AVAILABLE, reason="scikit-learn not installed in backend venv")
class TestTrainModel:
    """Tests for satellite/src/train_model.py — RandomForest training pipeline."""

    @pytest.fixture(scope="class")
    def trained_artifacts(self, tmp_path_factory):
        """Train once, share across tests in this class."""
        out = tmp_path_factory.mktemp("models")
        from train_model import train_ghost_project_classifier, MODEL_FILENAME

        fe = FeatureEngineer()
        X, y = fe.build_training_dataframe(_TRAINING_CSV)
        pipeline, metrics = train_ghost_project_classifier(X, y, out)
        return {"pipeline": pipeline, "metrics": metrics, "out": out,
                "MODEL_FILENAME": MODEL_FILENAME, "X": X, "y": y}

    def test_train_returns_pipeline_and_metrics(self, trained_artifacts):
        assert trained_artifacts["pipeline"] is not None
        assert isinstance(trained_artifacts["metrics"], dict)

    def test_metrics_has_required_keys(self, trained_artifacts):
        required = {"cv_auc", "cv_precision_ghost", "cv_recall_ghost", "cv_f1_ghost",
                    "n_samples", "n_ghost", "n_success", "smote_applied"}
        assert required.issubset(trained_artifacts["metrics"].keys())

    def test_metrics_n_samples(self, trained_artifacts):
        m = trained_artifacts["metrics"]
        assert m["n_samples"] == 30
        assert m["n_ghost"] == 10
        assert m["n_success"] == 20

    def test_pkl_file_created(self, trained_artifacts):
        assert (trained_artifacts["out"] / trained_artifacts["MODEL_FILENAME"]).exists()

    def test_model_metrics_json_created(self, trained_artifacts):
        assert (trained_artifacts["out"] / "model_metrics.json").exists()

    def test_feature_importance_csv_created(self, trained_artifacts):
        assert (trained_artifacts["out"] / "feature_importance.csv").exists()

    def test_pipeline_predict_proba_shape(self, trained_artifacts):
        """Trained pipeline returns (30, 2) probability array on training data."""
        proba = trained_artifacts["pipeline"].predict_proba(trained_artifacts["X"])
        assert proba.shape == (30, 2)
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_all_row_probabilities_sum_to_one(self, trained_artifacts):
        """Each row of predict_proba sums to 1.0."""
        proba = trained_artifacts["pipeline"].predict_proba(trained_artifacts["X"])
        row_sums = proba.sum(axis=1)
        assert np.allclose(row_sums, 1.0, atol=1e-6)


# =============================================================================
# Group 3 — RiskScoringService
# =============================================================================

class TestRiskScoringService:
    """Tests for backend/src/services/risk_scoring_service.py."""

    def test_score_project_raises_lookup_error_for_missing_project(self, test_db):
        from src.services.risk_scoring_service import RiskScoringService

        svc = RiskScoringService()
        with pytest.raises(LookupError, match="not found"):
            svc.score_project(uuid4(), test_db)

    def test_probability_to_risk_level_low(self):
        from src.services.risk_scoring_service import _probability_to_risk_level

        assert _probability_to_risk_level(0.00) == RiskLevel.LOW
        assert _probability_to_risk_level(0.30) == RiskLevel.LOW

    def test_probability_to_risk_level_medium(self):
        from src.services.risk_scoring_service import _probability_to_risk_level

        assert _probability_to_risk_level(0.31) == RiskLevel.MEDIUM
        assert _probability_to_risk_level(0.60) == RiskLevel.MEDIUM

    def test_probability_to_risk_level_high(self):
        from src.services.risk_scoring_service import _probability_to_risk_level

        assert _probability_to_risk_level(0.61) == RiskLevel.HIGH
        assert _probability_to_risk_level(0.80) == RiskLevel.HIGH

    def test_probability_to_risk_level_critical(self):
        from src.services.risk_scoring_service import _probability_to_risk_level

        assert _probability_to_risk_level(0.81) == RiskLevel.CRITICAL
        assert _probability_to_risk_level(1.00) == RiskLevel.CRITICAL

    def test_fallback_score_maps_critical_risk_level(self):
        """CRITICAL fallback → ghost_probability ≥ 0.80."""
        from src.services.risk_scoring_service import RiskScoringService

        p = Project(
            project_uuid=uuid4(),
            project_name="Ghost Building",
            status=ProjectStatus.ONGOING,
            risk_level=RiskLevel.CRITICAL,
        )
        result = RiskScoringService._fallback_score(p)
        assert result.ghost_probability >= 0.80
        assert result.risk_level == "CRITICAL"
        assert result.model_available is False
        assert result.model_version == "fallback"

    def test_fallback_score_for_low_risk(self):
        from src.services.risk_scoring_service import RiskScoringService

        p = Project(
            project_uuid=uuid4(),
            project_name="Good Project",
            status=ProjectStatus.COMPLETED,
            risk_level=RiskLevel.LOW,
        )
        result = RiskScoringService._fallback_score(p)
        assert result.ghost_probability <= 0.30

    def test_score_project_with_mocked_model_persists_to_db(self, test_db):
        """Mock ML model returning p=0.9 → CRITICAL written to Project row."""
        import pandas as pd
        from src.services.risk_scoring_service import RiskScoringService

        project = _make_project(test_db, name="Ghost Road")

        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.10, 0.90]])

        mock_fe = MagicMock(spec=FeatureEngineer)
        mock_fe.FEATURES = FEATURES
        mock_fe.extract_features.return_value = pd.Series(
            {f: 0.0 for f in FEATURES}
        )

        svc = RiskScoringService()
        svc._model = mock_model   # bypass _load_model
        svc._fe = mock_fe

        with patch("src.services.risk_scoring_service._ML_AVAILABLE", True), \
             patch("src.services.risk_scoring_service._FEATURE_ENGINEER_AVAILABLE", True):
            result = svc.score_project(project.project_uuid, test_db)

        assert abs(result.ghost_probability - 0.90) < 0.001
        assert result.risk_level == "CRITICAL"

        # Verify persisted to DB
        test_db.refresh(project)
        assert project.ghost_probability is not None
        assert project.risk_level == RiskLevel.CRITICAL

    def test_score_all_active_projects_returns_list(self, test_db):
        """batch scoring returns a list with one entry per ONGOING project."""
        from src.services.risk_scoring_service import RiskScoringService

        _make_project(test_db, name="Project Alpha")
        _make_project(test_db, name="Project Beta")
        _make_project(test_db, name="Completed Bridge",
                      status=ProjectStatus.COMPLETED)  # should be excluded

        svc = RiskScoringService()
        # All will use fallback score since model not trained
        results = svc.score_all_active_projects(test_db)
        assert len(results) >= 2  # at least the 2 ONGOING projects
        for r in results:
            assert 0.0 <= r.ghost_probability <= 1.0


# =============================================================================
# Group 4 — ML Celery Tasks
# =============================================================================

class TestMLTasks:
    """Tests for backend/src/tasks/ml_tasks.py."""

    def test_score_project_risk_task_success(self, test_db, test_engine, monkeypatch):
        """Task returns dict with required keys when project exists."""
        from sqlalchemy.orm import sessionmaker
        from src.tasks.ml_tasks import score_project_risk_task

        # Redirect the task's SessionLocal to the test DB so it can see the project
        TestSession = sessionmaker(bind=test_engine)
        monkeypatch.setattr("src.tasks.ml_tasks.SessionLocal", TestSession)

        project = _make_project(test_db, name="Task Test Project",
                                risk_level=RiskLevel.MEDIUM)
        # Call eagerly (not via Celery broker)
        result = score_project_risk_task.apply(args=[str(project.project_uuid)])
        assert result.successful()
        output = result.get()
        assert "project_uuid" in output
        assert "ghost_probability" in output
        assert "risk_level" in output
        assert "model_version" in output

    def test_score_project_risk_task_unknown_uuid(self):
        """Task returns error dict (not exception) for unknown project."""
        from src.tasks.ml_tasks import score_project_risk_task

        result = score_project_risk_task.apply(args=[str(uuid4())])
        assert result.successful()
        output = result.get()
        assert "error" in output

    def test_batch_score_task_returns_summary(self, test_db):
        """batch_score_task returns total_projects, scored, fallback keys."""
        from src.tasks.ml_tasks import batch_score_task

        _make_project(test_db, name="Ongoing School 1")
        result = batch_score_task.apply()
        assert result.successful()
        output = result.get()
        assert "total_projects" in output
        assert "scored" in output
        assert "fallback" in output


# =============================================================================
# Group 5 — Risk Router
# =============================================================================

class TestRiskRouter:
    """Integration tests for GET /api/v1/risk/score and GET /api/v1/risk/heat-map."""

    def test_risk_score_404_unknown_project(self, client):
        """Non-existent project UUID → 404."""
        resp = client.get(f"/api/v1/risk/score/{uuid4()}")
        assert resp.status_code == 404

    def test_risk_score_model_not_trained_returns_200(self, client, test_db):
        """Existing project with no model → 200 with model_available=False or result."""
        project = _make_project(test_db, name="Road No Model",
                                risk_level=RiskLevel.HIGH)
        resp = client.get(f"/api/v1/risk/score/{project.project_uuid}")
        assert resp.status_code == 200
        body = resp.json()
        assert "ghost_probability" in body
        assert "risk_level" in body

    def test_risk_heat_map_returns_geojson(self, client):
        """GET /risk/heat-map returns a GeoJSON FeatureCollection."""
        resp = client.get("/api/v1/risk/heat-map")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert "features" in body
        assert isinstance(body["features"], list)

    def test_risk_heat_map_empty_when_no_geolocated_projects(self, client, test_db):
        """No geolocated projects → features list is empty."""
        _make_project(test_db, name="Ungeolocated Project")
        resp = client.get("/api/v1/risk/heat-map")
        assert resp.status_code == 200
        body = resp.json()
        # No GeolocationRecord created → no features
        assert body["features"] == []

    def test_risk_heat_map_risk_level_filter(self, client, test_db):
        """?risk_level=LOW filter — returns only LOW projects (may be empty)."""
        _make_project(test_db, name="Critical Project", risk_level=RiskLevel.CRITICAL)
        resp = client.get("/api/v1/risk/heat-map?risk_level=LOW")
        assert resp.status_code == 200
        body = resp.json()
        # Each returned project must have risk_level == LOW
        for feat in body["features"]:
            assert feat["properties"]["risk_level"] == "LOW"
