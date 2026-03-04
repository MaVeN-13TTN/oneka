"""
Celery ingestion tasks — data acquisition pipeline.

These tasks are enqueued by the Celery beat scheduler or triggered manually
via POST /api/v1/admin/trigger-scrape.

All scrapers live in data/scrapers/; the repo root is added to sys.path at
import time so the data layer is reachable from the backend worker process.
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Make data/ scrapers importable from within the backend worker
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.celery_app import celery_app
from src.database import SessionLocal
from src.services.financial_service import FinancialService


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async scraper coroutine from a synchronous Celery task."""
    return asyncio.run(coro)


# ── tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="src.tasks.ingestion_tasks.scrape_egp_task",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
)
def scrape_egp_task(self):
    """
    Runs the eGP (IFMIS) scraper — fetches closed Works tenders and saves
    procurement records + GPS coordinates to the database.

    Scheduled: daily at 02:00 EAT via Celery beat.
    """
    try:
        from data.scrapers.egp import EGPScraper
        scraper = EGPScraper()
        count = _run(scraper.run())
        logger.info(f"scrape_egp_task: saved {count} records")
        return {"status": "ok", "saved": count}
    except Exception as exc:
        logger.error(f"scrape_egp_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.tasks.ingestion_tasks.import_ppip_historical_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def import_ppip_historical_task(self):
    """
    One-time import of historical PPIP tender data (pre-2025 records).
    Should only be triggered manually — not on a schedule.
    """
    try:
        from data.scrapers.ppip import PPIPScraper
        scraper = PPIPScraper()
        count = _run(scraper.run())
        logger.info(f"import_ppip_historical_task: saved {count} records")
        return {"status": "ok", "saved": count}
    except Exception as exc:
        logger.error(f"import_ppip_historical_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.tasks.ingestion_tasks.ingest_cob_report_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def ingest_cob_report_task(self, pdf_path: str, fiscal_year: str):
    """
    Parses a downloaded COB BIRR PDF and inserts FinancialRecord rows.

    Args:
        pdf_path:    Local filesystem path to the downloaded PDF.
        fiscal_year: Fiscal year string e.g. "2023/2024".
    """
    try:
        db = SessionLocal()
        try:
            service = FinancialService(db)
            count = service.ingest_cob_report(pdf_path, fiscal_year)
            logger.info(f"ingest_cob_report_task: inserted {count} records from {pdf_path}")
            return {"status": "ok", "inserted": count, "pdf": pdf_path}
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"ingest_cob_report_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.tasks.ingestion_tasks.refresh_kmhfl_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def refresh_kmhfl_task(self):
    """
    Refreshes the local KMHFL facility cache (data/cache/kmhfl_facilities.json).
    Used by Phase 2 geolocation service for Tier 2 fuzzy matching.

    Scheduled: first Sunday of every month at 03:00 EAT via Celery beat.
    """
    try:
        from data.scrapers.kmhfl import KMHFLScraper
        scraper = KMHFLScraper()
        count = _run(scraper.run())
        logger.info(f"refresh_kmhfl_task: cached {count} facilities")
        return {"status": "ok", "cached": count}
    except Exception as exc:
        logger.error(f"refresh_kmhfl_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
