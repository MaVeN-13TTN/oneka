"""
Phase 7 — Celery ingestion task tests.

Covers src/tasks/ingestion_tasks.py with mocked scrapers and services.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.celery_app import celery_app


# Force Celery eager mode for tests
celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)


# =============================================================================
# scrape_egp_task
# =============================================================================


class TestScrapeEgpTask:
    """Tests for scrape_egp_task."""

    def test_scrape_egp_success(self):
        mock_scraper_cls = MagicMock()
        mock_scraper_cls.return_value.run = MagicMock(return_value=42)
        mock_module = MagicMock()
        mock_module.EGPScraper = mock_scraper_cls

        with patch("src.tasks.ingestion_tasks._run", return_value=42):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.egp": mock_module}):
                from src.tasks.ingestion_tasks import scrape_egp_task
                result = scrape_egp_task.apply()

        assert result.result["status"] == "ok"
        assert result.result["saved"] == 42

    def test_scrape_egp_retry_on_error(self):
        with patch("src.tasks.ingestion_tasks._run", side_effect=RuntimeError("network error")):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.egp": MagicMock()}):
                from src.tasks.ingestion_tasks import scrape_egp_task
                # Celery 5 wraps the original exception in celery.exceptions.Retry
                # in eager+propagate mode, so catch the base Exception.
                with pytest.raises(Exception):
                    scrape_egp_task.apply()


# =============================================================================
# import_ppip_historical_task
# =============================================================================


class TestImportPpipTask:
    """Tests for import_ppip_historical_task."""

    def test_ppip_import_success(self):
        with patch("src.tasks.ingestion_tasks._run", return_value=15):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.ppip": MagicMock()}):
                from src.tasks.ingestion_tasks import import_ppip_historical_task
                result = import_ppip_historical_task.apply()

        assert result.result["status"] == "ok"
        assert result.result["saved"] == 15

    def test_ppip_import_retry_on_error(self):
        with patch("src.tasks.ingestion_tasks._run", side_effect=RuntimeError("timeout")):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.ppip": MagicMock()}):
                from src.tasks.ingestion_tasks import import_ppip_historical_task
                with pytest.raises(Exception):
                    import_ppip_historical_task.apply()


# =============================================================================
# ingest_cob_report_task
# =============================================================================


class TestIngestCobTask:
    """Tests for ingest_cob_report_task."""

    def test_ingest_cob_success(self):
        mock_db = MagicMock()
        mock_session_local = MagicMock(return_value=mock_db)
        mock_service = MagicMock()
        mock_service.ingest_cob_report.return_value = 5

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_session_local):
            with patch("src.tasks.ingestion_tasks.FinancialService", return_value=mock_service):
                from src.tasks.ingestion_tasks import ingest_cob_report_task
                result = ingest_cob_report_task.apply(args=["/tmp/cob.pdf", "2023/2024"])

        assert result.result["status"] == "ok"
        assert result.result["inserted"] == 5
        mock_db.close.assert_called_once()

    def test_ingest_cob_retry_on_error(self):
        mock_db = MagicMock()
        mock_session_local = MagicMock(return_value=mock_db)
        mock_service = MagicMock()
        mock_service.ingest_cob_report.side_effect = RuntimeError("parse error")

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_session_local):
            with patch("src.tasks.ingestion_tasks.FinancialService", return_value=mock_service):
                from src.tasks.ingestion_tasks import ingest_cob_report_task
                with pytest.raises(Exception):
                    ingest_cob_report_task.apply(args=["/tmp/cob.pdf", "2023/2024"])

    def test_ingest_cob_closes_db_on_success(self):
        mock_db = MagicMock()
        mock_session_local = MagicMock(return_value=mock_db)
        mock_service = MagicMock()
        mock_service.ingest_cob_report.return_value = 0

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_session_local):
            with patch("src.tasks.ingestion_tasks.FinancialService", return_value=mock_service):
                from src.tasks.ingestion_tasks import ingest_cob_report_task
                ingest_cob_report_task.apply(args=["/tmp/cob.pdf", "2023/2024"])

        mock_db.close.assert_called_once()


# =============================================================================
# refresh_kmhfl_task
# =============================================================================


class TestRefreshKmhflTask:
    """Tests for refresh_kmhfl_task."""

    def test_kmhfl_refresh_success(self):
        with patch("src.tasks.ingestion_tasks._run", return_value=200):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.kmhfl": MagicMock()}):
                from src.tasks.ingestion_tasks import refresh_kmhfl_task
                result = refresh_kmhfl_task.apply()

        assert result.result["status"] == "ok"
        assert result.result["cached"] == 200

    def test_kmhfl_refresh_retry_on_error(self):
        with patch("src.tasks.ingestion_tasks._run", side_effect=RuntimeError("API down")):
            with patch.dict("sys.modules", {"data": MagicMock(), "data.scrapers": MagicMock(), "data.scrapers.kmhfl": MagicMock()}):
                from src.tasks.ingestion_tasks import refresh_kmhfl_task
                with pytest.raises(Exception):
                    refresh_kmhfl_task.apply()


# =============================================================================
# investigate_project_task
# =============================================================================


class TestInvestigateProjectTask:
    """Tests for investigate_project_task — targeted single-project pipeline."""

    _INV_ID = "550e8400-e29b-41d4-a716-446655440000"

    def _make_mock_inv(self):
        """Return a populated mock investigation with project_context JSONB."""
        from src.models.investigation import InvestigationStatus

        mock_inv = MagicMock()
        mock_inv.investigation_id = self._INV_ID
        mock_inv.project_context = {
            "canonical_name": "Bungoma District Hospital",
            "search_terms": ["Bungoma Hospital"],
            "aliases": ["District Hospital Bungoma"],
            "coordinates": None,
            "fiscal_years": ["2023/2024"],
            "procuring_entity": "Ministry of Health",
        }
        mock_inv.status = InvestigationStatus.ENRICHED.value
        mock_inv.stage_statuses = {}
        return mock_inv

    def _make_data_mocks(self):
        """Build sys.modules entries to mock all data-layer imports."""
        mock_context_module = MagicMock()
        # Set coordinates=None so the Tier-0 ``lat0, lon0 = ctx.coordinates``
        # unpack is skipped (ctx.coordinates is falsy rather than a bare MagicMock).
        mock_ctx = MagicMock()
        mock_ctx.coordinates = None
        mock_ctx.fiscal_years = ["2023/2024"]
        mock_context_module.ProjectContext = MagicMock(return_value=mock_ctx)

        mock_egp    = MagicMock(); mock_egp.EGPScraper    = MagicMock()
        mock_nca    = MagicMock(); mock_nca.NCAScraper    = MagicMock()
        mock_ppip   = MagicMock(); mock_ppip.PPIPScraper  = MagicMock()
        mock_kmhfl  = MagicMock(); mock_kmhfl.KMHFLScraper = MagicMock()
        mock_cob    = MagicMock()
        mock_cob_poller = MagicMock()
        mock_cob.CoBPoller = MagicMock(return_value=mock_cob_poller)

        return {
            "data":              MagicMock(),
            "data.context":      mock_context_module,
            "data.scrapers":     MagicMock(),
            "data.scrapers.egp":   mock_egp,
            "data.scrapers.nca":   mock_nca,
            "data.scrapers.ppip":  mock_ppip,
            "data.scrapers.kmhfl": mock_kmhfl,
            "data.scrapers.cob":   mock_cob,
        }

    def test_success_runs_all_scrapers_and_updates_status(self):
        """Happy path — all scrapers succeed, status transitions to SCORING."""
        mock_inv   = self._make_mock_inv()
        mock_db    = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_inv
        # Ordered queries (GeolocationRecord) return None → satellite skipped
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_sess  = MagicMock(return_value=mock_db)

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_sess), \
             patch("src.tasks.ingestion_tasks._run", return_value=None), \
             patch("src.services.concordance_service.ConcordanceService"), \
             patch("src.tasks.satellite_tasks.analyse_project_task"), \
             patch.dict("sys.modules", self._make_data_mocks()):
            from src.tasks.ingestion_tasks import investigate_project_task
            result = investigate_project_task.apply(args=[self._INV_ID])

        assert result.result["status"] == "ok"
        assert result.result["investigation_id"] == self._INV_ID
        assert "stage_counts" in result.result
        # DB committed at least once per stage
        assert mock_db.commit.call_count >= 2

    def test_investigation_not_found_returns_error(self):
        """Task returns error dict when investigation_id doesn't exist."""
        mock_db   = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_sess = MagicMock(return_value=mock_db)

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_sess), \
             patch.dict("sys.modules", self._make_data_mocks()):
            from src.tasks.ingestion_tasks import investigate_project_task
            result = investigate_project_task.apply(args=[self._INV_ID])

        assert result.result["status"] == "error"
        assert result.result["reason"] == "not found"

    def test_missing_project_context_returns_error(self):
        """Task returns error dict when project_context is NULL."""
        mock_inv  = self._make_mock_inv()
        mock_inv.project_context = None
        mock_db   = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_inv
        mock_sess = MagicMock(return_value=mock_db)

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_sess), \
             patch.dict("sys.modules", self._make_data_mocks()):
            from src.tasks.ingestion_tasks import investigate_project_task
            result = investigate_project_task.apply(args=[self._INV_ID])

        assert result.result["status"] == "error"
        assert result.result["reason"] == "no context"

    def test_scraper_failure_is_tolerated(self):
        """A scraper exception should not abort the whole task — other scrapers
        still run and counts include the failed scraper as 0."""
        mock_inv  = self._make_mock_inv()
        mock_db   = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_inv
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_sess = MagicMock(return_value=mock_db)

        def _run_side_effect(coro):
            # Raise on the very first call (EGP fetch) to simulate failure
            if _run_side_effect.calls == 0:
                _run_side_effect.calls += 1
                raise RuntimeError("EGP down")
            _run_side_effect.calls += 1
            return None

        _run_side_effect.calls = 0

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_sess), \
             patch("src.tasks.ingestion_tasks._run", side_effect=_run_side_effect), \
             patch("src.services.concordance_service.ConcordanceService"), \
             patch("src.tasks.satellite_tasks.analyse_project_task"), \
             patch.dict("sys.modules", self._make_data_mocks()):
            from src.tasks.ingestion_tasks import investigate_project_task
            result = investigate_project_task.apply(args=[self._INV_ID])

        assert result.result["status"] == "ok"
        assert result.result["stage_counts"]["egp"] == 0  # failed scraper reported as 0

    def test_db_session_closed_on_success(self):
        """DB session is always closed regardless of outcome."""
        mock_inv  = self._make_mock_inv()
        mock_db   = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_inv
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_sess = MagicMock(return_value=mock_db)

        with patch("src.tasks.ingestion_tasks.SessionLocal", mock_sess), \
             patch("src.tasks.ingestion_tasks._run", return_value=None), \
             patch("src.services.concordance_service.ConcordanceService"), \
             patch("src.tasks.satellite_tasks.analyse_project_task"), \
             patch.dict("sys.modules", self._make_data_mocks()):
            from src.tasks.ingestion_tasks import investigate_project_task
            investigate_project_task.apply(args=[self._INV_ID])

        # close() called once per stage (at least 4 stages × 1 DB)
        assert mock_db.close.call_count >= 4
