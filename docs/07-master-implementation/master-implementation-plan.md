# Oneka AI: Master Backend Implementation Plan

**Document Type:** Technical Project Management — Master Implementation Plan  
**Role:** Technical Project Manager  
**Reference Date:** March 1, 2026  
**Scope:** `backend/`, `data/`, `satellite/` — all three engineering workstreams  
**Team:** Backend Engineer (Dev 1), Geospatial/Satellite Engineer (Dev 2), ML Engineer (Dev 2), DevOps (Dev 4)  
**Target:** Fully operational backend, data pipelines, satellite processing, and ML model — ready for frontend integration

---

## Codebase State Assessment

Before planning forward, every implementation decision is grounded in what **already exists** vs. what **must be built**.

### What Is Already Built ✅

| Component                                              | Location                                      | Status                                                                      |
| ------------------------------------------------------ | --------------------------------------------- | --------------------------------------------------------------------------- |
| FastAPI app skeleton + CORS                            | `backend/src/main.py`                         | ✅ Done                                                                     |
| Settings / env config                                  | `backend/src/config.py`                       | ✅ Done                                                                     |
| SQLAlchemy + PostGIS engine                            | `backend/src/database.py`                     | ✅ Done                                                                     |
| All 5 SQLAlchemy models                                | `backend/src/models/`                         | ✅ Done (`project`, `procurement`, `financial`, `geolocation`, `satellite`) |
| Alembic migration scaffold                             | `backend/alembic/`                            | ✅ Done                                                                     |
| Procurement CRUD router + service                      | `backend/src/routers/procurement.py`          | ✅ Done                                                                     |
| Pydantic schemas for procurement                       | `backend/src/schemas/procurement.py`          | ✅ Done                                                                     |
| PPIP scraper (synchronous, rate-limited)               | `backend/src/services/ppip_scraper.py`        | ✅ Done                                                                     |
| S3 PDF storage service                                 | `backend/src/services/s3_storage.py`          | ✅ Done                                                                     |
| Health check router                                    | `backend/src/routers/health.py`               | ✅ Done                                                                     |
| Async PPIP scraper (Playwright)                        | `data/scrapers/ppip.py`                       | ✅ Done                                                                     |
| Async e-GP scraper (Playwright, response interception) | `data/scrapers/egp.py`                        | ✅ Done                                                                     |
| Async NCA scraper (Playwright)                         | `data/scrapers/nca.py`                        | ✅ Done                                                                     |
| Async KMHFL scraper (Playwright)                       | `data/scrapers/kmhfl.py`                      | ✅ Done                                                                     |
| CoB PDF downloader (Playwright)                        | `data/scrapers/cob.py`                        | ✅ Done                                                                     |
| CoB PDF table parser (pdfplumber)                      | `data/parsers/cob.py`                         | ✅ Done                                                                     |
| Base scraper abstract class                            | `data/scrapers/base.py`                       | ✅ Done                                                                     |
| Copernicus/Sentinelsat downloader                      | `satellite/src/download.py`                   | ✅ Done                                                                     |
| Sentinel-2 NDVI processor (Satpy + Rasterio fallback)  | `satellite/src/process_ndvi.py`               | ✅ Done                                                                     |
| Sentinel-1 SAR processor (PyroSAR + SNAP)              | `satellite/src/process_sar.py`                | ✅ Done                                                                     |
| Satellite utils (coords, bbox, statistics)             | `satellite/src/utils.py`                      | ✅ Done                                                                     |
| Satellite config                                       | `satellite/src/config.py`                     | ✅ Done                                                                     |
| Training projects loader/visualiser                    | `satellite/scripts/load_training_projects.py` | ✅ Done                                                                     |
| 30-project training dataset (CSV)                      | `satellite/data/training/`                    | ✅ Done                                                                     |

### Critical Gaps (Must Build) 🔴

| Gap                                                                                                                                                                                                                      | Where It Belongs                                  | Why It Blocks                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **No Alembic migration has been generated/run** — tables don't exist in PostgreSQL yet                                                                                                                                   | `backend/alembic/versions/`                       | Everything else depends on the DB existing                                                                  |
| **Two disconnected scraper codebases** — `data/scrapers/` (async Playwright) vs `backend/src/services/ppip_scraper.py` (sync requests) — need unification                                                                | `backend/src/services/`                           | Duplicated effort, conflicting approaches                                                                   |
| **e-GP GPS pipeline not wired** — `data/scrapers/egp.py` already intercepts e-GP `tenderDetails` JSON which includes mandatory GPS coordinates (July 2025 rule); these coords are not yet saved to `geolocation_records` | `data/scrapers/egp.py`, new migration             | Without this, the highest-quality GPS source is unused; 70–85% coverage vs 25–40% from fuzzy matching alone |
| **No GPS quality scoring** — e-GP pins have varying accuracy (manually pinned vs auto-geocoded); score not stored                                                                                                        | new migration (`gps_quality_score` column)        | Geospatial engineer cannot prioritise GPS validation work                                                   |
| **No entity resolution service** — spaCy NER + RapidFuzz fuzzy matching as fallback for records with no e-GP GPS                                                                                                         | `backend/src/services/geolocation_service.py`     | Without this, records from PPIP/NCA/COB (no embedded GPS) have no coordinates                               |
| **No financial data pipeline** — no service to ingest or parse COB BIRR reports into `financial_records` table                                                                                                           | `backend/src/services/financial_service.py`       | Cannot calculate financial vs physical divergence                                                           |
| **No concordance/interoperability service** — no logic assigns project_uuid, links procurement → financial → geolocation                                                                                                 | `backend/src/services/concordance_service.py`     | Projects exist in isolation; no unified project card                                                        |
| **No satellite pipeline orchestrator** — no code that takes a project_uuid → looks up GPS → tasks Copernicus API → runs NDVI/SAR → stores result                                                                         | `backend/src/services/satellite_service.py`       | The satellite module is standalone scripts, disconnected from the backend DB                                |
| **No Celery task queue** — redis + celery configured but no task definitions                                                                                                                                             | `backend/src/tasks/`                              | Satellite processing and scraping must run asynchronously, not in request lifecycles                        |
| **No ML model training pipeline** — Random Forest not yet trained; only training data and feature plan exist                                                                                                             | `satellite/src/train_model.py`                    | Without the model, there is no risk score                                                                   |
| **No ML inference integration** — no service that calls the trained model and writes results to `satellite_analyses` table                                                                                               | `backend/src/services/risk_scoring_service.py`    | Risk scores never make it to the API                                                                        |
| **No Google Maps / 3D Tiles integration** — no tile proxy or metadata endpoint for CesiumJS                                                                                                                              | `backend/src/routers/maps.py`                     | Frontend dashboard cannot render                                                                            |
| **No financial vs physical divergence calculator** — the "Truth Timeline" green vs blue line logic                                                                                                                       | `backend/src/services/divergence_service.py`      | Core ghost-project detection signal never computed                                                          |
| **No Section 106B certificate generator**                                                                                                                                                                                | `backend/src/services/certificate_service.py`     | Legal export feature entirely absent                                                                        |
| **Missing routers** for projects, financial, geolocation, satellite, ML risk, maps                                                                                                                                       | `backend/src/routers/`                            | API has only procurement and health endpoints                                                               |
| **KMHFL API URL outdated** — config points to `api.kmhfl.health.go.ke`; needs `api.kmhfr.health.go.ke`                                                                                                                   | `backend/src/config.py`, `data/scrapers/kmhfl.py` | Health facility geolocation will fail                                                                       |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  INGESTION LAYER (data/scrapers/)                                    │
│  [PPIP] [e-GP] [NCA] [KMHFL] [CoB BIRR]                              │
│  Async Playwright + httpx → raw data → PostgreSQL staging            │
└────────────────────────┬─────────────────────────────────────────────┘
                         │ Celery tasks (backend/src/tasks/)
┌────────────────────────▼─────────────────────────────────────────────┐
│  INTEROPERABILITY ENGINE (backend/src/services/)                     │
│  ConcordanceService → assigns project_uuid                           │
│  GeolocationService → e-GP GPS (primary) → spaCy NER + RapidFuzz     │
│                       (fallback for non-e-GP sources) → ward polygon │
│  FinancialService   → COB BIRR parser → financial_records            │
└────────────────────────┬─────────────────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────────────────┐
│  DATABASE (PostgreSQL 15 + PostGIS 3.4)                              │
│  projects | procurement_records | financial_records                  │
│  geolocation_records | satellite_analyses                            │
└──────────┬──────────────────────────────┬────────────────────────────┘
           │                              │
┌──────────▼──────────┐       ┌───────────▼────────────────────────────┐
│ SATELLITE PIPELINE  │       │  ML RISK ENGINE                        │
│ SatelliteService    │       │  RiskScoringService                    │
│ → Copernicus query  │       │  → RandomForest inference              │
│ → NDVI + SAR calc   │       │  → 0-100 risk score per project        │
│ → change detection  │       │  → writes to satellite_analyses        │
│ → divergence score  │       └────────────────────────────────────────┘
└─────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────────-──┐
│  FASTAPI LAYER (backend/src/routers/)                                │
│  /projects /procurement /financial /geolocation /satellite /risk     │
│  /maps (Google Tiles proxy) /certificates (Section 106B)             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Environment & Database Bootstrap

**Owner:** Backend Engineer + DevOps  
**Duration:** 1 day  
**Prerequisite for all other phases**

### 0.1 Environment Setup

All three modules (`backend/`, `data/`, `satellite/`) need clean, reproducible environments.

**Tasks:**

- [ ] Create a root-level `docker-compose.yml` (PostgreSQL 15 + PostGIS, Redis, the FastAPI app, Celery worker)
- [ ] Consolidate the three separate `.env` / `.env.example` files into a single root `.env.example` used by all modules
- [ ] Fix `backend/src/config.py` — update `kmhfl_api_url` from `http://kmhfl.health.go.ke/api` to `https://api.kmhfr.health.go.ke/api/v2`
- [ ] Fix `data/scrapers/kmhfl.py` — update `API_URL` from `api.kmhfl.health.go.ke` to `api.kmhfr.health.go.ke`
- [ ] Verify `satellite/requirements.txt` installs cleanly; GDAL/SNAP system dependencies need a documented install script

**Deliverables:**

- `docker-compose.yml` at repo root
- `scripts/setup_dev.sh` — one-command dev environment setup

### 0.2 Database Migration

The models are defined but the tables don't exist yet.

**Tasks:**

- [ ] Run `alembic revision --autogenerate -m "initial_schema"` inside `backend/`
- [ ] Review the generated migration — ensure PostGIS `Geometry` column types are correctly emitted by GeoAlchemy2
- [ ] Add a manual step to the migration to create the PostGIS extension: `CREATE EXTENSION IF NOT EXISTS postgis;`
- [ ] Run `alembic upgrade head`
- [ ] Seed the database with the 30 training projects from `satellite/data/training/training_projects.csv` via a `backend/scripts/seed_training_projects.py` script

**Deliverables:**

- `backend/alembic/versions/001_initial_schema.py` — first migration file
- `backend/scripts/seed_training_projects.py`
- Confirmed: all 5 tables exist in a running PostgreSQL instance

---

## Phase 1 — Data Ingestion Pipelines

**Owner:** Backend Engineer  
**Duration:** 3–4 days  
**Depends on:** Phase 0

The `data/scrapers/` directory contains async Playwright-based scrapers that reference a non-existent `backend.db` AsyncSessionLocal and `backend.models.tenders` module. These must be refactored to use the canonical SQLAlchemy models in `backend/src/models/`.

### 1.1 Unify the Scraper Architecture

**Problem:** Two competing scraper implementations exist:

- `data/scrapers/ppip.py` — async, references `backend.db`, `backend.models.tenders` (does not exist)
- `backend/src/services/ppip_scraper.py` — sync, uses requests, correct model imports

**Resolution:** The async Playwright scrapers in `data/scrapers/` are the canonical implementation. Fix their import paths to use `backend.src.database` and `backend.src.models`.

**Revised source priority (from sprint-roles-and-responsibilities.md, Feb 19 2026):**

- **e-GP is the primary data source** — mandatory GPS coordinates have been embedded in all e-GP tenders since July 2025 (National Treasury ruling). Expected GPS coverage: 70–85%.
- **PPIP is a one-time historical import** — PPIP is a read-only archive. Run the importer once to backfill pre-2025 records; do not set up a continuous scraping job for PPIP.
- **NCA / COB / KMHFR** are supplementary sources.

**Tasks:**

- [ ] Refactor `data/scrapers/ppip.py`:
  - Replace `from backend.db import AsyncSessionLocal` with `from backend.src.database import SessionLocal`
  - Replace `from backend.models.tenders import Tender` with `from backend.src.models.procurement import ProcurementRecord`
  - Map PPIP API response fields to `ProcurementRecord` columns
  - Set `source_system = "PPIP"`, `is_historical = True`
  - **Run once** to backfill pre-2025 records; do not schedule for continuous execution

- [ ] Refactor `data/scrapers/egp.py` **(P0 — primary geolocation source)**:
  - Fix import paths: `from backend.src.database import SessionLocal`, `from backend.src.models.procurement import ProcurementRecord`
  - Map e-GP `tenderDetails` JSON structure to `ProcurementRecord`
  - Set `source_system = "eGP"` and `extraction_method = "playwright_intercept"`
  - **Extract and persist GPS coordinates** from `tenderDetails.deliveryLocation.geometry.coordinates` into `GeolocationRecord` at scrape time — do not defer to the geolocation service
  - Compute `gps_quality_score` (0–100) based on source type: `EGP_MANUAL_PIN = 90`, `EGP_AUTO_GEOCODED = 70`, `EGP_MISSING = 0`
  - Add a new Alembic migration (`002_add_egp_gps_fields.py`) adding columns to `procurement_records`:
    - `egp_tender_id TEXT`
    - `delivery_latitude NUMERIC(10,7)`
    - `delivery_longitude NUMERIC(10,7)`
    - `gps_source TEXT` — one of `EGP_MANUAL_PIN`, `KMHFL_MATCHED`, `NEMIS_MATCHED`, `WARD_CENTROID`
    - `gps_quality_score INTEGER` — 0–100

- [ ] Refactor `data/scrapers/kmhfl.py`:
  - Update API URL to `https://api.kmhfr.health.go.ke/api/v2/facilities/`
  - Replace `from backend.models.core import Facility` with `from backend.src.models.geolocation import GeolocationRecord`
  - Store facilities as `GeolocationRecord` rows with `source_system = "KMHFR"`, `match_method = "registry"`

- [ ] Refactor `data/scrapers/nca.py`:
  - Map NCA project fields to `ProcurementRecord` with `source_system = "NCA"`
  - Cross-reference NCA license number for `contractor_nca_license` field

- [ ] Refactor `data/scrapers/cob.py`:
  - Wire `CoBParser` from `data/parsers/cob.py` into the save logic
  - Map extracted expenditure tables to `FinancialRecord` model
  - Set `source_system = "COB"`, extract `vote_head`, `ministry`, `absorption_rate`, `budget_absorbed_kes`

**Deliverables:**

- All 5 scrapers import from `backend.src.models` correctly
- Each scraper has a tested `run()` method that successfully saves records to the database
- `data/scrapers/__init__.py` exports all scraper classes

### 1.2 Build the COB Financial Parser

The `data/parsers/cob.py` `CoBParser` exists but only extracts tables. It needs a bridge to the financial model.

**Tasks:**

- [ ] Extend `CoBParser.find_expenditure_table()` to return structured dicts, not raw DataFrames
- [ ] Add `CoBParser.extract_financial_records(project_name: str) -> List[dict]` that:
  - Calls `find_expenditure_table()`
  - Fuzzy-matches `project_name` against the "Vote" column using `rapidfuzz.process.extractOne`
  - Returns a list of dicts matching the `FinancialRecord` schema
- [ ] Create `backend/src/services/financial_service.py` with:
  - `ingest_cob_report(pdf_path: str, fiscal_year: str)` — calls `CoBParser`, saves `FinancialRecord` rows
  - `get_financial_records_for_project(project_uuid: UUID)` — CRUD query
  - `calculate_absorption_gap(project_uuid: UUID) -> dict` — computes `budget_absorbed / contract_sum` divergence

**Deliverables:**

- `backend/src/services/financial_service.py`
- 10+ `FinancialRecord` rows seeded from at least one real COB BIRR PDF

### 1.3 Celery Task Wiring

Long-running scraping jobs must not block the FastAPI request loop.

**Tasks:**

- [ ] Create `backend/src/tasks/__init__.py`
- [ ] Create `backend/src/tasks/ingestion_tasks.py`:

  ```python
  @celery_app.task(name="tasks.import_ppip_historical")
  def import_ppip_historical_task(max_pages: int = 500): ...
  # NOTE: Run once only. PPIP is a historical archive — not a live feed.

  @celery_app.task(name="tasks.scrape_egp")
  def scrape_egp_task(): ...
  # Primary continuous source. Schedule daily via Celery Beat.

  @celery_app.task(name="tasks.ingest_cob_report")
  def ingest_cob_report_task(pdf_url: str, fiscal_year: str): ...

  @celery_app.task(name="tasks.refresh_kmhfl")
  def refresh_kmhfl_task(): ...
  # Schedule monthly — KMHFR facility list does not change frequently.
  ```

- [ ] Create `backend/src/celery_app.py` — Celery app factory connected to Redis
- [ ] Configure Celery Beat schedule: `scrape_egp_task` daily at 02:00 EAT; `refresh_kmhfl_task` first Sunday of each month
- [ ] Add a `/api/v1/admin/trigger-scrape` endpoint (POST, admin-only) that accepts `source: str` and enqueues the appropriate task

**Deliverables:**

- `backend/src/tasks/` package with `ingestion_tasks.py`
- `backend/src/celery_app.py`
- Celery worker startable via `celery -A backend.src.celery_app worker`

---

## Phase 2 — Interoperability Engine

**Owner:** Backend Engineer  
**Duration:** 3–4 days  
**Depends on:** Phase 1 (data in procurement_records and geolocation_records tables)

This is the core intellectual contribution of Oneka AI — linking siloed data sources into a unified project record.

### 2.1 Geolocation Service (Proxy Geolocation Engine)

**File:** `backend/src/services/geolocation_service.py`

**Purpose:** Given a tender title (e.g., "Construction of Gituamba Dispensary"), resolve it to GPS coordinates. e-GP records already carry GPS from scraping — this service handles all other sources as a fallback pipeline.

**Geolocation strategy (three-tier):**

1. **Tier 1 — e-GP embedded GPS** (`gps_source = EGP_MANUAL_PIN` or `EGP_AUTO_GEOCODED`): Already saved by the e-GP scraper. Skip NER/fuzzy matching entirely for these records. Expected coverage: 70–85% of records.
2. **Tier 2 — spaCy NER + RapidFuzz** (`gps_source = KMHFL_MATCHED` or `NEMIS_MATCHED`): For records without e-GP GPS, extract the candidate entity name and fuzzy-match against the KMHFR/NEMIS registry. Expected coverage: 10–15% of remaining records.
3. **Tier 3 — Ward centroid fallback** (`gps_source = WARD_CENTROID`): For records that fail both tiers, assign the geographic centre of the project's ward from UNOCHA admin boundaries. Lowest precision; always produces a coordinate.

**Tasks:**

- [ ] Add `spacy` to `backend/requirements.txt`; download `en_core_web_sm` model in `scripts/setup_dev.sh`

- [ ] Create `GeolocationService` class with:

  ```python
  class GeolocationService:
      def __init__(self, db: Session):
          self.db = db
          self._nlp = spacy.load("en_core_web_sm")
          self._kmhfr_cache = self._build_facility_cache("KMHFR")
          self._nemis_cache = self._build_facility_cache("NEMIS")

      def resolve(self, procurement_id: int) -> GeolocationResult:
          """
          Steps:
          1. Load ProcurementRecord — check if delivery_latitude is already set
             (e-GP embedded GPS). If yes, return immediately (Tier 1).
          2. Run spaCy NER on tender_title:
             doc = self._nlp(tender_title)
             candidates = [ent.text for ent in doc.ents if ent.label_ in ("FAC", "GPE", "LOC", "ORG")]
             Also strip common construction prefixes with regex:
             ("Construction of", "Proposed", "Rehabilitation of", "Upgrading of")
          3. For each candidate: rapidfuzz.process.extractOne(
               candidate, {**self._kmhfr_cache, **self._nemis_cache},
               scorer=fuzz.token_set_ratio, score_cutoff=70)
          4. If best_score >= 90: auto-accept → gps_source=KMHFL_MATCHED, gps_quality_score=80
          5. If 70 <= best_score < 90: flag needs_review → gps_source=KMHFL_MATCHED, gps_quality_score=60
          6. If no match: ward centroid fallback → gps_source=WARD_CENTROID, gps_quality_score=20
          7. Save GeolocationRecord; update ProcurementRecord.gps_source + gps_quality_score
          8. Return GeolocationResult(lat, lon, confidence, method)
          """

      def batch_resolve(self, project_uuids: List[UUID]) -> dict:
          """Resolve geolocation for a list of projects — skip Tier 1 records."""

      def _build_facility_cache(self, source_system: str) -> dict:
          """Load all records with given source_system from DB into a name→coords dict."""
  ```

- [ ] Implement ward-centroid fallback by loading UNOCHA Kenya admin boundary GeoJSON (Level 3 = Wards) into PostGIS at startup
- [ ] Add `POST /api/v1/geolocation/resolve` endpoint — accepts `procurement_id`, returns GPS + `gps_quality_score` + method
- [ ] Add `GET /api/v1/geolocation/coverage` endpoint — returns breakdown: `{tier1_egp: N, tier2_fuzzy: N, tier3_ward: N, unresolved: N}`

**Deliverables:**

- `backend/src/services/geolocation_service.py`
- `backend/src/routers/geolocation.py`
- Ward boundary GeoJSON loaded into a `admin_boundaries` PostGIS table (new migration)

### 2.2 Concordance Service (Universal Project UUID Assignment)

**File:** `backend/src/services/concordance_service.py`

**Purpose:** Create and maintain the master `Project` record that links procurement → financial → geolocation → satellite rows.

**Tasks:**

- [ ] Create `ConcordanceService` class with:

  ```python
  class ConcordanceService:
      def link_procurement_to_project(self, procurement_id: int) -> Project:
          """
          1. Load ProcurementRecord
          2. Check if project_name fuzzy-matches any existing Project (score > 85)
             → If yes: link procurement.project_uuid = existing.project_uuid
             → If no: Create new Project row, assign fresh UUID
          3. Call GeolocationService.resolve(tender_title, county)
             → Save GeolocationRecord linked to project_uuid
          4. Set Project.county, project_type (inferred from title keywords)
          5. Set Project.risk_level = RiskLevel.LOW (default until ML scores it)
          6. Return updated Project
          """

      def link_financial_to_project(self, financial_id: int) -> Project:
          """
          Fuzzy-match FinancialRecord.ministry + programme
          against Project.project_name to assign project_uuid.
          """

      def get_project_truth_record(self, project_uuid: UUID) -> dict:
          """
          The "5-second unified project card":
          Returns: Project + all ProcurementRecords + all FinancialRecords
          + GeolocationRecord + latest SatelliteAnalysis + risk_score
          """
  ```

- [ ] Add `POST /api/v1/projects/reconcile` endpoint that triggers concordance for all unlinked records
- [ ] Add `GET /api/v1/projects/{project_uuid}/truth-record` — returns the full unified project card

**Deliverables:**

- `backend/src/services/concordance_service.py`
- `backend/src/routers/projects.py` (full CRUD + truth-record endpoint)
- At minimum 25 projects with linked procurement + geolocation records

---

## Phase 3 — Satellite Processing Pipeline Integration

**Owner:** Geospatial / Satellite Engineer  
**Duration:** 4–5 days  
**Depends on:** Phase 2 (projects with GPS coordinates in DB)

The satellite module (`satellite/src/`) has working standalone scripts. Phase 3 wires them into the backend database and Celery task queue.

### 3.1 Satellite Service (Backend Integration Layer)

**File:** `backend/src/services/satellite_service.py`

**Purpose:** Acts as the bridge between the backend DB and the standalone satellite processing module.

**Tasks:**

- [ ] Create `SatelliteService` class:

  ```python
  class SatelliteService:
      def queue_analysis(self, project_uuid: UUID) -> str:
          """
          1. Load GeolocationRecord for project → get lat, lon
          2. Load ProcurementRecord → get award_date, expected_completion_date
          3. Enqueue Celery task: analyse_project_task(project_uuid, lat, lon, start_date, end_date)
          4. Return task_id for status polling
          """

      def save_ndvi_result(self, project_uuid: UUID, result: dict) -> SatelliteAnalysis:
          """Write NDVIProcessor output to satellite_analyses table."""

      def save_sar_result(self, project_uuid: UUID, result: dict) -> SatelliteAnalysis:
          """Write SARProcessor output to satellite_analyses table."""

      def get_time_series(self, project_uuid: UUID) -> List[SatelliteAnalysis]:
          """Return all satellite_analyses for a project ordered by acquisition_date."""
  ```

### 3.2 Satellite Celery Tasks

**File:** `backend/src/tasks/satellite_tasks.py`

**Tasks:**

- [ ] Create `analyse_project_task(project_uuid, lat, lon, start_date, end_date)`:
  ```
  1. Call CopernicusDownloader.search_sentinel2(lat, lon, start_date, end_date, max_cloud_cover=20)
  2. Download top 3 scenes with lowest cloud cover
  3. For each scene: run NDVIProcessor → extract statistics → save via SatelliteService.save_ndvi_result()
  4. Call CopernicusDownloader.search_sentinel1(lat, lon, start_date, end_date)
  5. Download and run SARProcessor → save via SatelliteService.save_sar_result()
  6. After all scenes processed: call divergence_service.calculate_divergence(project_uuid)
  7. Enqueue score_project_risk_task(project_uuid) — triggers ML scoring
  ```
- [ ] Create `batch_analyse_flagged_projects_task()` — runs `analyse_project_task` for all projects with `risk_level = None`
- [ ] Add `POST /api/v1/satellite/analyse/{project_uuid}` endpoint that enqueues the analysis task
- [ ] Add `GET /api/v1/satellite/status/{task_id}` endpoint that polls Celery task status

### 3.3 NDWI Water Filter

**File:** `satellite/src/process_ndwi.py` (new file)

**Purpose:** Calculate NDWI to filter false positives — a wetland or seasonal flood mimics NDVI change but is not a ghost project.

**Tasks:**

- [ ] Create `NDWIProcessor` class mirroring `NDVIProcessor`:
  - Bands: B03 (Green) and B08 (NIR) → NDWI = (Green - NIR) / (Green + NIR)
  - Values > 0.3 indicate standing water → flag as `water_present = True`
  - Expose `process(lat, lon, date) -> NDWIResult`
- [ ] Integrate NDWI result into `analyse_project_task` as a pre-check:
  - If `water_present = True` during baseline period → set `analysis_type = "NDWI_water"`, skip NDVI ghost-project logic
  - Log as `change_detected = False, notes = "seasonal water body — not a construction site"`

### 3.4 Change Detection & Divergence Score

**File:** `backend/src/services/divergence_service.py`

**Purpose:** Compute the "Truth Timeline" — the financial vs physical progress gap.

**Tasks:**

- [ ] Create `DivergenceService`:

  ```python
  class DivergenceService:
      def calculate_divergence(self, project_uuid: UUID) -> DivergenceResult:
          """
          1. Get latest FinancialRecord for project → financial_progress = absorption_rate
          2. Get SatelliteAnalysis time-series → compute physical_progress from NDVI change
             Physical progress = map ndvi_change to 0-100 score:
               - ndvi_drop > 0.5 AND sar_increase > 3dB → physical_progress = 60-80%
               - ndvi_drop > 0.3 AND sar_increase > 1dB → physical_progress = 30-60%
               - ndvi_drop < 0.1 AND no sar change       → physical_progress ≈ 0%
          3. divergence_score = financial_progress - physical_progress
          4. If divergence_score > 50: alert_level = "RED"
             If 20 < divergence_score <= 50: alert_level = "YELLOW"
             Else: alert_level = "GREEN"
          5. Save to Project.risk_level based on alert_level
          6. Return DivergenceResult(financial_progress, physical_progress,
                                     divergence_score, alert_level)
          """
  ```

- [ ] Add `GET /api/v1/projects/{project_uuid}/divergence` endpoint returning the divergence timeline
- [ ] Add `GET /api/v1/dashboard/heat-map` endpoint returning all projects with risk levels and coordinates (for CesiumJS)

**Deliverables:**

- `backend/src/services/satellite_service.py`
- `backend/src/services/divergence_service.py`
- `backend/src/tasks/satellite_tasks.py`
- `satellite/src/process_ndwi.py`
- `backend/src/routers/satellite.py`
- At least 10 projects with satellite analyses and computed divergence scores

---

## Phase 4 — Machine Learning Training & Inference

**Owner:** ML Engineer  
**Duration:** 4–5 days  
**Depends on:** Phase 3 (satellite_analyses table populated with time-series data)

### 4.1 Feature Engineering Pipeline

**File:** `satellite/src/feature_engineering.py` (new file)

**Tasks:**

- [ ] Create `FeatureEngineer` class that reads from the database (or CSV for training):

  ```python
  class FeatureEngineer:
      FEATURES = [
          "ndvi_slope",           # Rate of NDVI change per month
          "sar_backscatter_delta", # Max SAR VV change from baseline
          "divergence_score",     # financial_progress - physical_progress
          "months_to_clearing",   # Months from award_date to first NDVI drop > 0.3
          "absorption_anomaly",   # Deviation from linear spend baseline at month M
                              # NOTE: Full S-curve time-series regression is OUT OF SCOPE for MVP
                              # (see 8-week-cto-plan.md). Use linear interpolation only.
          "contract_value_log",   # log10(contract_sum_kes) — normalise scale
          "project_type_encoded", # One-hot: health=0, education=1, roads=2, water=3
          "county_cloud_risk",    # pre-computed: annual cloud fraction for county
          "contractor_tier",      # NCA: 1=NCA1, 2=NCA2, etc. (from NCA scraper data)
          "phase_on_schedule",    # binary: is spending rate within S-curve tolerance?
      ]

      def extract_features(self, project_uuid: UUID) -> pd.Series:
          """Pull all satellite_analyses + financial_records for a project,
          compute the FEATURES list, return as a row for model input."""

      def build_training_dataframe(self, projects_csv: Path) -> pd.DataFrame:
          """Build full feature matrix from the 30 training projects CSV."""
  ```

### 4.2 Model Training

**File:** `satellite/src/train_model.py` (new file)

**Tasks:**

- [ ] Implement training pipeline:

  ```python
  def train_ghost_project_classifier(features_df: pd.DataFrame, labels: pd.Series):
      """
      1. Preprocess: impute missing values (median), scale numeric features
      2. Handle class imbalance: SMOTE oversample the ghost=1 class
         (training set has 10 ghost : 20 successful → 33% : 67% imbalance)
      3. Train RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced")
      4. 5-fold StratifiedKFold cross-validation → log mean AUC, precision, recall, F1
      5. If CV AUC >= 0.80: save model to satellite/models/ghost_detector_v1.pkl
      6. Also save: feature_importance.csv, confusion_matrix.png, roc_curve.png
      7. Target metrics:
         - AUC >= 0.80
         - Precision (ghost class) >= 0.75
         - Recall (ghost class) >= 0.70
      """
  ```

- [ ] Create `satellite/scripts/run_training.py` — CLI wrapper:
  ```
  python scripts/run_training.py --data data/training/training_projects.csv --output models/
  ```
- [ ] Export model metrics to `satellite/docs/model_performance_report.md` automatically

### 4.3 ML Inference Service

**File:** `backend/src/services/risk_scoring_service.py`

**Tasks:**

- [ ] Create `RiskScoringService`:

  ```python
  class RiskScoringService:
      def __init__(self):
          self.model = joblib.load(settings.ml_model_path)
          self.feature_engineer = FeatureEngineer()

      def score_project(self, project_uuid: UUID) -> RiskScore:
          """
          1. Call FeatureEngineer.extract_features(project_uuid)
          2. model.predict_proba(features) → ghost_probability (0.0 - 1.0)
          3. Map to risk categories:
             0-30%:   LOW     (green)
             31-60%:  MEDIUM  (yellow)
             61-80%:  HIGH    (orange)
             81-100%: CRITICAL (red)
          4. Update Project.risk_level in DB
          5. Write SatelliteAnalysis row with analysis_type="ML_RISK_SCORE"
          6. Return RiskScore(project_uuid, score, level, features_used, model_version)
          """

      def score_all_active_projects(self) -> List[RiskScore]:
          """Batch score all projects with status=ONGOING."""
  ```

- [ ] Create Celery task in `backend/src/tasks/ml_tasks.py`:
  - `score_project_risk_task(project_uuid)` — called automatically after satellite analysis completes
  - `batch_score_task()` — weekly batch re-scoring of all active projects
- [ ] Add setting `ml_model_path` to `backend/src/config.py`
- [ ] Add `GET /api/v1/risk/score/{project_uuid}` endpoint
- [ ] Add `GET /api/v1/risk/heat-map` endpoint — returns all projects as GeoJSON with risk level and ghost_probability

**Deliverables:**

- `satellite/src/feature_engineering.py`
- `satellite/src/train_model.py`
- `satellite/scripts/run_training.py`
- `satellite/models/ghost_detector_v1.pkl`
- `satellite/docs/model_performance_report.md`
- `backend/src/services/risk_scoring_service.py`
- `backend/src/tasks/ml_tasks.py`
- `backend/src/routers/risk.py`

---

## Phase 5 — Google Maps / 3D Tiles Integration

**Owner:** Backend Engineer + Satellite Engineer  
**Duration:** 2–3 days  
**Depends on:** Phase 4 (projects have risk scores and GPS coordinates)

### 5.1 Maps Router (Google Tiles Proxy)

**File:** `backend/src/routers/maps.py`

The Google Maps API key must not be exposed to the browser. The backend proxies requests to the Maps Tiles API.

**Tasks:**

- [ ] Create `/api/v1/maps/tiles/session` endpoint (POST):
  - Calls `https://tile.googleapis.com/v1/createSession` with server-side API key
  - Returns session token to the frontend
  - Session tokens expire after 3 hours; cache in Redis

- [ ] Create `/api/v1/maps/tiles/{session_token}/{z}/{x}/{y}` endpoint (GET):
  - Proxies tile requests to Google Maps Tiles API
  - Adds `key=GOOGLE_MAPS_API_KEY` server-side
  - Forwards tile bytes to frontend
  - This pattern prevents API key leakage in browser network traffic

- [ ] Add API key to `backend/src/config.py` (already has `google_maps_api_key` field)

**Security Note:** The API key must only ever appear in server-side requests. The frontend passes the session token; the backend adds the API key. Never expose `google_maps_api_key` in any response body or frontend bundle.

### 5.2 Satellite Tile Generation

**File:** `satellite/src/generate_tiles.py` (new file)

CesiumJS needs satellite imagery served as XYZ map tiles, not raw GeoTIFF files.

**Tasks:**

- [ ] Create `TileGenerator` class:
  - Input: processed NDVI GeoTIFF or SAR GeoTIFF from `satellite/data/processed/`
  - Convert to Web Mercator (EPSG:3857) using `rasterio.warp.reproject`
  - Apply colormap (NDVI: green-brown diverging; SAR: grayscale)
  - Generate XYZ tile pyramid using `gdal2tiles` or `cogeo-mosaic`
  - Upload tile pyramid to AWS S3 bucket as `tiles/{project_uuid}/{layer}/{z}/{x}/{y}.png`
  - Return base tile URL for database storage

- [ ] Store tile base URL in `SatelliteAnalysis.tile_url` (add column via new migration)
- [ ] Add `GET /api/v1/satellite/tiles/{project_uuid}/ndvi/{z}/{x}/{y}` endpoint — proxies or redirects to S3 tiles

### 5.3 Project GeoJSON Endpoint

**Tasks:**

- [ ] Add `GET /api/v1/projects/geojson` endpoint:
  - Returns all projects as a GeoJSON FeatureCollection
  - Each Feature has: `project_uuid`, `project_name`, `risk_level`, `ghost_probability`, `alert_level`, `county`, coordinates
  - This is the data source for CesiumJS `GeoJsonDataSource` rendering
  - Supports `?risk_level=HIGH,CRITICAL` filter parameter

**Deliverables:**

- `backend/src/routers/maps.py`
- `satellite/src/generate_tiles.py`
- `SatelliteAnalysis.tile_url` column migration
- `GET /api/v1/projects/geojson` endpoint documented in OpenAPI

---

## Phase 6 — Section 106B Legal Certificate Generator

**Owner:** Backend Engineer  
**Duration:** 2 days  
**Depends on:** Phase 3 (satellite analyses with immutable metadata)

### 6.1 Certificate Service

**File:** `backend/src/services/certificate_service.py`

**Tasks:**

- [ ] Create `CertificateService`:

  ```python
  class CertificateService:
      def generate_106b_certificate(self, project_uuid: UUID,
                                     analyst_name: str,
                                     analyst_title: str) -> bytes:
          """
          Generate a Section 106B Evidence Act certificate as PDF.

          Certificate must contain (per Section 106B(4) requirements):
          1. Source of the electronic record (ESA Copernicus Data Space)
          2. Scene acquisition timestamp (ISO 8601)
          3. Processing algorithm description (NDVI formula, SAR calibration steps)
          4. Data integrity proof: SHA-256 hash of the original downloaded scene file
          5. Chain of custody: download timestamp, processing timestamp, analyst name
          6. Statement: "The computer system was operating properly at the time the
             data described herein was produced."
          7. Signature block for signing official (OAG/EACC representative)

          Implementation:
          1. Query SatelliteAnalysis and Project from DB
          2. Retrieve scene file hash from S3 object metadata
          3. Render Jinja2 HTML template → WeasyPrint PDF
          4. Return PDF bytes (caller saves to S3 or serves as download)
          """
  ```

- [ ] Create `backend/templates/certificate_106b.html` — Jinja2 HTML template styled as an official legal document
- [ ] Add certificate generation to `backend/requirements.txt`: `weasyprint`, `jinja2`
- [ ] Add `GET /api/v1/certificates/{project_uuid}` endpoint:
  - Query param: `?analyst_name=...&analyst_title=...`
  - Returns PDF as `application/pdf` download
  - Also stores certificate in S3 at `certificates/{project_uuid}/{timestamp}.pdf`

**Deliverables:**

- `backend/src/services/certificate_service.py`
- `backend/templates/certificate_106b.html`
- `backend/src/routers/certificates.py`
- End-to-end test: generate a certificate for one of the 30 training projects

---

## Phase 7 — API Hardening & Test Coverage

**Owner:** All Engineers  
**Duration:** 2–3 days  
**Depends on:** Phases 1–6

### 7.1 Complete Router Registration

Update `backend/src/main.py` to register all new routers:

```python
# Add to main.py
from src.routers import (
    health, procurement, projects, financial,
    geolocation, satellite, risk, maps, certificates
)

app.include_router(projects.router,      prefix="/api/v1", tags=["Projects"])
app.include_router(financial.router,     prefix="/api/v1", tags=["Financial"])
app.include_router(geolocation.router,   prefix="/api/v1", tags=["Geolocation"])
app.include_router(satellite.router,     prefix="/api/v1", tags=["Satellite"])
app.include_router(risk.router,          prefix="/api/v1", tags=["Risk Scoring"])
app.include_router(maps.router,          prefix="/api/v1", tags=["Maps"])
app.include_router(certificates.router,  prefix="/api/v1", tags=["Certificates"])
```

### 7.2 Test Coverage Requirements

Existing tests: `backend/tests/` has `test_health.py`, `test_models.py`, `test_procurement.py` (29 tests passing at Sprint 2).

**New tests required:**

| Test File                     | What to Cover                                                                                                                                                         |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_geolocation_service.py` | Tier 1: e-GP GPS passthrough; Tier 2: spaCy NER + RapidFuzz with known KMHFR records; Tier 3: ward centroid fallback; `gps_quality_score` correctly set for each tier |
| `test_concordance_service.py` | project_uuid assignment; duplicate detection                                                                                                                          |
| `test_financial_service.py`   | COB PDF parsing; absorption gap calculation                                                                                                                           |
| `test_divergence_service.py`  | known result: 90% financial + 0% physical = RED                                                                                                                       |
| `test_satellite_tasks.py`     | mock Copernicus API; ensure NDVI result saved to DB                                                                                                                   |
| `test_risk_scoring.py`        | known training project scores correctly as ghost/successful                                                                                                           |
| `test_certificate.py`         | PDF generated with all required Section 106B fields                                                                                                                   |
| `test_maps.py`                | Google Tiles session creation; GeoJSON endpoint                                                                                                                       |

**Target:** ≥ 70% code coverage across `backend/src/`

### 7.3 Security Hardening

- [ ] Ensure `google_maps_api_key` is never returned in any API response body
- [ ] Add rate limiting to all public endpoints (use `slowapi` library with Redis backend)
- [ ] Validate all input coordinates (lat/lon range checks before Copernicus query)
- [ ] Sanitise all `tender_title` inputs before fuzzy matching (strip SQL injection patterns)
- [ ] Ensure S3 bucket policies block public access; all presigned URLs expire in 60 minutes
- [ ] Add `Content-Security-Policy` and `X-Content-Type-Options` headers in CORS middleware

---

## Complete File Delivery Checklist

### New Files to Create

```
backend/
├── src/
│   ├── celery_app.py                          # Phase 1
│   ├── routers/
│   │   ├── projects.py                        # Phase 2
│   │   ├── financial.py                       # Phase 2
│   │   ├── geolocation.py                     # Phase 2
│   │   ├── satellite.py                       # Phase 3
│   │   ├── risk.py                            # Phase 4
│   │   ├── maps.py                            # Phase 5
│   │   └── certificates.py                   # Phase 6
│   ├── services/
│   │   ├── geolocation_service.py             # Phase 2
│   │   ├── concordance_service.py             # Phase 2
│   │   ├── financial_service.py               # Phase 1.2
│   │   ├── satellite_service.py               # Phase 3
│   │   ├── divergence_service.py              # Phase 3.4
│   │   ├── risk_scoring_service.py            # Phase 4
│   │   └── certificate_service.py             # Phase 6
│   └── tasks/
│       ├── __init__.py                        # Phase 1.3
│       ├── ingestion_tasks.py                 # Phase 1.3
│       ├── satellite_tasks.py                 # Phase 3.2
│       └── ml_tasks.py                        # Phase 4
├── templates/
│   └── certificate_106b.html                  # Phase 6
├── scripts/
│   └── seed_training_projects.py              # Phase 0
└── alembic/versions/
    ├── 001_initial_schema.py                  # Phase 0
    ├── 002_add_egp_gps_fields.py              # Phase 1.1
    └── 003_add_tile_url_column.py             # Phase 5

satellite/
├── src/
│   ├── process_ndwi.py                        # Phase 3.3
│   ├── feature_engineering.py                 # Phase 4.1
│   ├── train_model.py                         # Phase 4.2
│   └── generate_tiles.py                      # Phase 5.2
├── scripts/
│   └── run_training.py                        # Phase 4.2
└── models/
    └── ghost_detector_v1.pkl                  # Phase 4 output

data/
├── scrapers/
│   ├── ppip.py          (refactor)            # Phase 1.1
│   ├── egp.py           (refactor)            # Phase 1.1
│   ├── nca.py           (refactor)            # Phase 1.1
│   ├── kmhfl.py         (refactor)            # Phase 1.1
│   └── cob.py           (refactor)            # Phase 1.1
└── parsers/
    └── cob.py           (extend)              # Phase 1.2

docker-compose.yml                             # Phase 0
scripts/setup_dev.sh                           # Phase 0
```

### Files to Modify

| File                         | Change                                                                     |
| ---------------------------- | -------------------------------------------------------------------------- |
| `backend/src/config.py`      | Fix KMHFL URL; add `ml_model_path`; add rate limiting config               |
| `backend/src/main.py`        | Register all new routers                                                   |
| `backend/requirements.txt`   | Add `weasyprint`, `jinja2`, `slowapi`, `imbalanced-learn`, `spacy`         |
| `satellite/requirements.txt` | Add `scikit-learn`, `imbalanced-learn`, `joblib`, `pandas`, `cogeo-mosaic` |
| `scripts/setup_dev.sh`       | Add `python -m spacy download en_core_web_sm`                              |

---

## Execution Timeline (8 Weeks)

| Week       | Phase                       | Engineer         | Output                                                                                            |
| ---------- | --------------------------- | ---------------- | ------------------------------------------------------------------------------------------------- |
| **Week 1** | Phase 0 + Phase 1.1         | Backend + DevOps | Docker, DB tables, scrapers refactored; e-GP GPS columns migrated; e-GP scraper saving GPS coords |
| **Week 2** | Phase 1.2 + Phase 1.3       | Backend          | COB parser, Celery Beat schedule, financial records in DB; PPIP one-time historical import run    |
| **Week 3** | Phase 2.1                   | Backend          | Three-tier geolocation live; e-GP GPS coverage ≥ 70%; spaCy NER fallback for non-e-GP records     |
| **Week 4** | Phase 2.2                   | Backend          | Concordance service, unified project truth-record endpoint live                                   |
| **Week 5** | Phase 3.1 + 3.2 + 3.3       | Satellite        | Satellite pipeline wired to DB, NDVI/SAR/NDWI runs end-to-end                                     |
| **Week 6** | Phase 3.4 + Phase 4.1 + 4.2 | Satellite + ML   | Divergence scores computed; ML model trained (AUC ≥ 0.80)                                         |
| **Week 7** | Phase 4.3 + Phase 5         | ML + Backend     | Risk scores in DB; Google Tiles proxy live; GeoJSON endpoint ready                                |
| **Week 8** | Phase 6 + Phase 7           | All              | 106B certificate generator; all tests green; OpenAPI docs complete                                |

---

## Definition of Done (Backend Complete)

The backend is considered complete when all of the following are satisfied:

- [ ] `docker-compose up` brings up the full stack (PostgreSQL, Redis, FastAPI, Celery)
- [ ] `alembic upgrade head` runs clean with no errors
- [ ] All 5 `data/scrapers/` import from `backend.src.models` without errors
- [ ] e-GP scraper has populated at least 100 `procurement_records` with `gps_source` set
- [ ] PPIP historical importer has run once and backfilled pre-2025 records
- [ ] KMHFR scraper has populated at least 5,000 `geolocation_records`
- [ ] COB parser has ingested at least 1 BIRR report → `financial_records` populated
- [ ] e-GP GPS coverage ≥ 70% of all procurement records (`/api/v1/geolocation/coverage` confirms)
- [ ] Concordance service links 25+ procurement records to project UUIDs with GPS coordinates
- [ ] Satellite pipeline runs end-to-end for at least 5 projects (NDVI + SAR analyses in DB)
- [ ] NDWI water filter is applied before NDVI analysis for all projects
- [ ] Divergence scores are computed for all analysed projects (GREEN / YELLOW / RED)
- [ ] ML model trained, AUC ≥ 0.80 on 5-fold CV, saved as `ghost_detector_v1.pkl`
- [ ] Risk scores returned for all analysed projects via `/api/v1/risk/score/{uuid}`
- [ ] Google Tiles session endpoint returns valid session token
- [ ] `/api/v1/projects/geojson` returns all projects as valid GeoJSON
- [ ] Section 106B certificate generated as downloadable PDF with all required fields
- [ ] Test coverage ≥ 70% across `backend/src/`
- [ ] All security hardening items completed (API key never exposed, rate limiting active)
- [ ] `GET /docs` (OpenAPI UI) documents all endpoints with request/response schemas
