"""
Phase 7 — Satellite Celery task tests.

Covers src/tasks/satellite_tasks.py with mocked Copernicus + processors.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest

from src.celery_app import celery_app
from src.models.geolocation import GeolocationRecord
from src.models.project import Project, ProjectStatus, RiskLevel

celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_project(db, project_uuid=None, risk_level=None):
    p = Project(
        project_uuid=project_uuid or uuid4(),
        project_name="Test Satellite Project",
        county="Nairobi",
        status=ProjectStatus.ONGOING,
        risk_level=risk_level,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_geo(db, project_uuid, lat=-1.29, lon=36.82):
    g = GeolocationRecord(
        project_uuid=project_uuid,
        latitude=lat,
        longitude=lon,
        match_method="egp_manual",
        match_confidence=95,
        source_system="EGP",
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# =============================================================================
# analyse_project_task — ImportError fallback
# =============================================================================


class TestAnalyseProjectTask:
    """Tests for analyse_project_task with satellite libs unavailable."""

    def test_analyse_import_error_fallback(self, test_db, test_engine):
        """When CopernicusDownloader unavailable, task falls back gracefully."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        project = _make_project(test_db)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch(
                "src.tasks.satellite_tasks._require_copernicus_downloader",
                side_effect=ImportError("sentinelsat not installed"),
            ):
                with patch("src.tasks.satellite_tasks.celery_app") as mock_celery:
                    from src.tasks.satellite_tasks import analyse_project_task
                    result = analyse_project_task.apply(
                        args=[str(project.project_uuid), -1.29, 36.82, "2024-01-01", "2024-06-01"]
                    )

        data = result.result
        assert data["ndvi_scenes_saved"] == 0
        assert data["sar_scenes_saved"] == 0

    def test_analyse_returns_summary_dict(self, test_db, test_engine):
        """Returns dict with required keys."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        project = _make_project(test_db)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch(
                "src.tasks.satellite_tasks._require_copernicus_downloader",
                side_effect=ImportError("unavailable"),
            ):
                with patch("src.tasks.satellite_tasks.celery_app"):
                    from src.tasks.satellite_tasks import analyse_project_task
                    result = analyse_project_task.apply(
                        args=[str(project.project_uuid), -1.29, 36.82, "2024-01-01", "2024-06-01"]
                    )

        data = result.result
        assert "project_uuid" in data
        assert "ndvi_scenes_saved" in data
        assert "sar_scenes_saved" in data
        assert "ndvi_slope" in data
        assert "alert_level" in data

    def test_analyse_enqueues_risk_scoring(self, test_db, test_engine):
        """Verifies celery_app.send_task called for ML scoring."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        project = _make_project(test_db)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch(
                "src.tasks.satellite_tasks._require_copernicus_downloader",
                side_effect=ImportError("unavailable"),
            ):
                mock_celery = MagicMock()
                with patch("src.tasks.satellite_tasks.celery_app", mock_celery):
                    from src.tasks.satellite_tasks import analyse_project_task
                    analyse_project_task.apply(
                        args=[str(project.project_uuid), -1.29, 36.82, "2024-01-01", "2024-06-01"]
                    )

        mock_celery.send_task.assert_called_once_with(
            "src.tasks.ml_tasks.score_project_risk_task",
            args=[str(project.project_uuid)],
        )


# =============================================================================
# batch_analyse_flagged_projects_task
# =============================================================================


class TestBatchAnalyse:
    """Tests for batch_analyse_flagged_projects_task."""

    def test_batch_queues_geolocated_projects(self, test_db, test_engine):
        """Projects with GeolocationRecord get queued."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        p1 = _make_project(test_db)
        _make_geo(test_db, p1.project_uuid)

        p2 = _make_project(test_db)
        # p2 has no geolocation

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch("src.tasks.satellite_tasks.analyse_project_task") as mock_task:
                from src.tasks.satellite_tasks import batch_analyse_flagged_projects_task
                result = batch_analyse_flagged_projects_task.apply()

        data = result.result
        assert data["queued"] == 1
        assert data["skipped_no_geo"] == 1
        mock_task.delay.assert_called_once()

    def test_batch_skips_projects_without_geo(self, test_db, test_engine):
        """Project without GeolocationRecord is skipped."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        _make_project(test_db)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch("src.tasks.satellite_tasks.analyse_project_task"):
                from src.tasks.satellite_tasks import batch_analyse_flagged_projects_task
                result = batch_analyse_flagged_projects_task.apply()

        assert result.result["queued"] == 0
        assert result.result["skipped_no_geo"] == 1

    def test_batch_returns_summary(self, test_db, test_engine):
        """Returns dict with queued, skipped_no_geo, total_projects keys."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch("src.tasks.satellite_tasks.analyse_project_task"):
                from src.tasks.satellite_tasks import batch_analyse_flagged_projects_task
                result = batch_analyse_flagged_projects_task.apply()

        data = result.result
        assert "queued" in data
        assert "skipped_no_geo" in data
        assert "total_projects" in data


# =============================================================================
# score_project_risk_task (satellite_tasks version)
# =============================================================================


class TestScoreProjectRiskTask:
    """Tests for score_project_risk_task in satellite_tasks."""

    def test_score_project_not_found(self, test_db, test_engine):
        """Unknown UUID returns error dict."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            from src.tasks.satellite_tasks import score_project_risk_task
            result = score_project_risk_task.apply(args=[str(uuid4())])

        assert result.result.get("error") == "not found"

    def test_score_model_not_trained_fallback(self, test_db, test_engine):
        """FileNotFoundError falls back to divergence-based risk."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        project = _make_project(test_db, risk_level=RiskLevel.MEDIUM)

        mock_svc_cls = MagicMock()
        mock_svc_cls.return_value.score_project.side_effect = FileNotFoundError("model missing")

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch.dict("sys.modules", {}):
                with patch(
                    "src.services.risk_scoring_service.RiskScoringService",
                    mock_svc_cls,
                ):
                    from src.tasks.satellite_tasks import score_project_risk_task
                    result = score_project_risk_task.apply(args=[str(project.project_uuid)])

        data = result.result
        assert data["model_available"] is False
        assert data["model_version"] == "not_trained"

    def test_score_success_with_model(self, test_db, test_engine):
        """Successful risk scoring via model."""
        from sqlalchemy.orm import sessionmaker
        TestSession = sessionmaker(bind=test_engine)

        project = _make_project(test_db)

        mock_score = MagicMock()
        mock_score.ghost_probability = 0.85
        mock_score.risk_level = "CRITICAL"
        mock_score.model_version = "ghost_detector_v1"
        mock_score.model_available = True

        mock_svc_cls = MagicMock()
        mock_svc_cls.return_value.score_project.return_value = mock_score

        with patch("src.tasks.satellite_tasks.SessionLocal", TestSession):
            with patch(
                "src.services.risk_scoring_service.RiskScoringService",
                mock_svc_cls,
            ):
                from src.tasks.satellite_tasks import score_project_risk_task
                result = score_project_risk_task.apply(args=[str(project.project_uuid)])

        data = result.result
        assert data["ghost_probability"] == 0.85
        assert data["risk_level"] == "CRITICAL"
