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


@celery_app.task(
    name="src.tasks.ingestion_tasks.scrape_nca_task",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def scrape_nca_task(self):
    """
    Scrapes NCA (National Construction Authority) approved projects.

    NCA data changes infrequently — scheduled monthly via Celery beat.
    """
    try:
        from data.scrapers.nca import NCAScraper
        scraper = NCAScraper()
        count = _run(scraper.run())
        logger.info(f"scrape_nca_task: saved {count} records")
        return {"status": "ok", "saved": count}
    except Exception as exc:
        logger.error(f"scrape_nca_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="src.tasks.ingestion_tasks.investigate_project_task",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def investigate_project_task(self, investigation_id: str):
    """
    Full investigation pipeline: scrape → concordance → geolocation → satellite.

    Stage 1  SCRAPING   — targeted mode on all five scrapers
    Stage 2  CONCORDANCE — link procurement records to a canonical Project row
    Stage 3  GEOLOCATING — resolve GPS (Tier 0 from ctx.coordinates takes
                           precedence; Tiers 1-3 run inside concordance)
    Stage 4  SATELLITE   — enqueue analyse_project_task if lat/lon resolved
    Stage 5  SCORING     — satellite chain runs score_project_risk_task

    Args:
        investigation_id: UUID string of the Investigation row.
    """
    import uuid as _uuid_mod
    from datetime import datetime, timezone

    from src.models.financial import FinancialRecord
    from src.models.geolocation import GeolocationRecord
    from src.models.investigation import Investigation, InvestigationStatus
    from src.models.procurement import ProcurementRecord
    from src.services.concordance_service import ConcordanceService

    inv_uuid: _uuid_mod.UUID | None = None

    def _db():
        """Return a fresh SessionLocal; caller must close it."""
        return SessionLocal()

    def _update_inv(db_session, **kwargs):
        """Fetch and update the Investigation row; commit."""
        inv = db_session.query(Investigation).filter(
            Investigation.investigation_id == inv_uuid
        ).first()
        if inv:
            for k, v in kwargs.items():
                setattr(inv, k, v)
            db_session.commit()
        return inv

    try:
        inv_uuid = _uuid_mod.UUID(investigation_id)

        # ── 1. Load investigation + build data-layer context ─────────────────
        db = _db()
        try:
            inv = db.query(Investigation).filter(
                Investigation.investigation_id == inv_uuid
            ).first()

            if not inv:
                logger.error(
                    f"investigate_project_task: {investigation_id} not found"
                )
                return {"status": "error", "reason": "not found"}

            if not inv.project_context:
                logger.error(
                    f"investigate_project_task: no context for {investigation_id}"
                )
                return {"status": "error", "reason": "no context"}

            ctx_dict = inv.project_context

            from data.context import ProjectContext as DataProjectContext

            coords = ctx_dict.get("coordinates")
            ctx = DataProjectContext(
                canonical_name=ctx_dict.get("canonical_name"),
                search_terms=ctx_dict.get("search_terms", []),
                aliases=ctx_dict.get("aliases", []),
                coordinates=tuple(coords) if coords and len(coords) == 2 else None,
                fiscal_years=ctx_dict.get("fiscal_years", []),
                procuring_entity=ctx_dict.get("procuring_entity"),
                ministry=ctx_dict.get("ministry"),
                county=ctx_dict.get("county"),
                vote_head=(
                    str(ctx_dict["vote_head"])
                    if ctx_dict.get("vote_head") is not None
                    else None
                ),
            )

            _update_inv(db, status=InvestigationStatus.SCRAPING.value)
        finally:
            db.close()

        # ── 2. SCRAPING: run all five scrapers ────────────────────────────────
        from data.scrapers.cob import CoBPoller
        from data.scrapers.egp import EGPScraper
        from data.scrapers.kmhfl import KMHFLScraper
        from data.scrapers.nca import NCAScraper
        from data.scrapers.ppip import PPIPScraper

        scrape_start = datetime.now(timezone.utc)
        stage_counts: dict[str, int] = {}

        for label, cls in [
            ("egp", EGPScraper),
            ("nca", NCAScraper),
            ("ppip", PPIPScraper),
            ("kmhfl", KMHFLScraper),
        ]:
            try:
                scraper = cls()
                data = _run(scraper.fetch(ctx=ctx))
                count = _run(scraper.save(data)) if data else 0
                stage_counts[label] = count
                logger.info(f"investigate_project_task: {label} → {count}")
            except Exception as exc:
                logger.warning(f"investigate_project_task: {label} failed: {exc}")
                stage_counts[label] = 0

        try:
            poller = CoBPoller()
            _run(poller.process(ctx=ctx))
            stage_counts["cob"] = 1
        except Exception as exc:
            logger.warning(f"investigate_project_task: cob failed: {exc}")
            stage_counts["cob"] = 0

        # ── 3. Tag rows created during this scrape window ─────────────────────
        # Rows are tagged by created_at timestamp.  Low-concurrency MVP assumption:
        # two investigations are unlikely to scrape simultaneously.
        db = _db()
        try:
            tagged_proc = db.query(ProcurementRecord).filter(
                ProcurementRecord.created_at >= scrape_start,
                ProcurementRecord.investigation_id.is_(None),
            ).update(
                {"investigation_id": inv_uuid},
                synchronize_session=False,
            )

            tagged_fin = db.query(FinancialRecord).filter(
                FinancialRecord.created_at >= scrape_start,
                FinancialRecord.investigation_id.is_(None),
            ).update(
                {"investigation_id": inv_uuid},
                synchronize_session=False,
            )

            # Tier 0 geolocation: if Perplexity supplied coordinates, seed them
            # on investigation procurement records so Tier 1 picks them up.
            if ctx.coordinates:
                lat0, lon0 = ctx.coordinates
                db.query(ProcurementRecord).filter(
                    ProcurementRecord.investigation_id == inv_uuid,
                    ProcurementRecord.delivery_latitude.is_(None),
                ).update(
                    {
                        "delivery_latitude": lat0,
                        "delivery_longitude": lon0,
                        "gps_source": "PERPLEXITY_CONTEXT",
                        "gps_quality_score": 85,
                    },
                    synchronize_session=False,
                )

            db.commit()

            _update_inv(
                db,
                status=InvestigationStatus.CONCORDANCE.value,
                stage_statuses={
                    **(db.query(Investigation).filter(
                        Investigation.investigation_id == inv_uuid
                    ).first().stage_statuses or {}),
                    "scraping": {
                        "status": "done",
                        "counts": stage_counts,
                        "tagged_procurement": tagged_proc,
                        "tagged_financial": tagged_fin,
                    },
                },
            )
        finally:
            db.close()

        # ── 4. CONCORDANCE: link procurement records to a Project ─────────────
        db = _db()
        project_uuid: _uuid_mod.UUID | None = None
        concordance_stats: dict = {"linked": 0, "failed": 0}
        try:
            proc_records = (
                db.query(ProcurementRecord)
                .filter(
                    ProcurementRecord.investigation_id == inv_uuid,
                    ProcurementRecord.project_uuid.is_(None),
                )
                .all()
            )

            concordance = ConcordanceService(db)
            for rec in proc_records:
                try:
                    result_uuid = concordance.link_procurement_to_project(
                        rec.procurement_id
                    )
                    if result_uuid:
                        project_uuid = result_uuid
                        concordance_stats["linked"] += 1
                    else:
                        concordance_stats["failed"] += 1
                except Exception as exc:
                    logger.warning(
                        f"concordance link failed for {rec.procurement_id}: {exc}"
                    )
                    concordance_stats["failed"] += 1

            # Persist the resolved project_uuid on the Investigation row
            inv = db.query(Investigation).filter(
                Investigation.investigation_id == inv_uuid
            ).first()
            if inv:
                if project_uuid:
                    inv.project_uuid = project_uuid
                inv.status = InvestigationStatus.GEOLOCATING.value
                current = inv.stage_statuses or {}
                inv.stage_statuses = {
                    **current,
                    "concordance": {
                        "status": "done",
                        **concordance_stats,
                        "project_uuid": str(project_uuid) if project_uuid else None,
                    },
                }
                db.commit()
        finally:
            db.close()

        # ── 5. GEOLOCATING: read back resolved coordinates from GeolocationRecord
        #    (ConcordanceService.link_procurement_to_project already called
        #    GeolocationService.resolve() internally — we just read the result.)
        geo_lat: float | None = None
        geo_lon: float | None = None
        db = _db()
        try:
            if project_uuid:
                geo_rec = (
                    db.query(GeolocationRecord)
                    .filter(GeolocationRecord.project_uuid == project_uuid)
                    .order_by(GeolocationRecord.match_confidence.desc())
                    .first()
                )
                if geo_rec:
                    geo_lat = float(geo_rec.latitude)
                    geo_lon = float(geo_rec.longitude)

            inv = db.query(Investigation).filter(
                Investigation.investigation_id == inv_uuid
            ).first()
            if inv:
                inv.status = InvestigationStatus.SATELLITE.value
                current = inv.stage_statuses or {}
                inv.stage_statuses = {
                    **current,
                    "geolocation": {
                        "status": "done",
                        "lat": geo_lat,
                        "lon": geo_lon,
                        "resolved": geo_lat is not None,
                    },
                }
                db.commit()
        finally:
            db.close()

        # ── 6. SATELLITE: enqueue analyse_project_task if coordinates resolved ─
        satellite_status = "skipped_no_coords"
        if geo_lat is not None and geo_lon is not None and project_uuid:
            from src.tasks.satellite_tasks import analyse_project_task as _sat_task

            # Derive date range from fiscal years; default to a rolling 2-year window.
            if ctx.fiscal_years:
                start_year = ctx.fiscal_years[0].split("/")[0]
                start_date = f"{start_year}-07-01"
                end_date = f"{int(start_year) + 1}-06-30"
            else:
                from datetime import date

                today = date.today()
                start_date = f"{today.year - 2}-01-01"
                end_date = today.isoformat()

            _sat_task.delay(
                project_uuid=str(project_uuid),
                lat=geo_lat,
                lon=geo_lon,
                start_date=start_date,
                end_date=end_date,
            )
            satellite_status = "queued"
            logger.info(
                f"investigate_project_task: satellite queued for {project_uuid} "
                f"at ({geo_lat}, {geo_lon}) window {start_date}→{end_date}"
            )

        # ── 7. Final status update ────────────────────────────────────────────
        db = _db()
        try:
            inv = db.query(Investigation).filter(
                Investigation.investigation_id == inv_uuid
            ).first()
            if inv:
                # SCORING — satellite chain will transition to COMPLETE when done.
                inv.status = InvestigationStatus.SCORING.value
                current = inv.stage_statuses or {}
                inv.stage_statuses = {
                    **current,
                    "satellite": {"status": satellite_status},
                }
                db.commit()
        finally:
            db.close()

        logger.info(
            f"investigate_project_task: pipeline complete for {investigation_id} "
            f"— project={project_uuid}, satellite={satellite_status}"
        )
        return {
            "status": "ok",
            "investigation_id": investigation_id,
            "project_uuid": str(project_uuid) if project_uuid else None,
            "stage_counts": stage_counts,
        }

    except Exception as exc:
        # Mark investigation FAILED on unrecoverable error so the frontend
        # can surface a clear error state rather than staying in a limbo status.
        if inv_uuid is not None:
            try:
                db = _db()
                try:
                    inv = db.query(Investigation).filter(
                        Investigation.investigation_id == inv_uuid
                    ).first()
                    if inv:
                        inv.status = InvestigationStatus.FAILED.value
                        db.commit()
                finally:
                    db.close()
            except Exception:
                pass

        logger.error(f"investigate_project_task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
