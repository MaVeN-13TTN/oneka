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
                with pytest.raises(RuntimeError, match="network error"):
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
                with pytest.raises(RuntimeError, match="timeout"):
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
                with pytest.raises(RuntimeError, match="parse error"):
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
                with pytest.raises(RuntimeError, match="API down"):
                    refresh_kmhfl_task.apply()
