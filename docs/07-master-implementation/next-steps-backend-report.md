# Oneka AI — Backend Next Steps Report

**Generated:** 2026-03-04
**Scope:** `backend/`, `data/`, `satellite/`
**Reference:** `docs/07-master-implementation/master-implementation-plan.md`, `docs/03-technical/system-flowchart.md`
**Branch:** `develop`

---

## Executive Summary

The project has a solid Sprint 1–2 foundation: all 5 SQLAlchemy models, the Alembic migration, the procurement CRUD router, S3 storage, and the standalone satellite processing scripts (`download.py`, `process_ndvi.py`, `process_sar.py`) are production-quality and tested. However, **none of the system's core intelligence has been built yet** — no data flows end-to-end, no projects have GPS coordinates, no satellite analyses have been run, and no risk scores exist. The implementation plan's Phases 0–7 are approximately 15% complete.

The single most urgent problem is a **broken import chain** in `data/scrapers/`: all five scrapers import from `backend.db` and `backend.models.tenders`, which do not exist. No data can be ingested until this is fixed.

---

## Current State vs. Plan

### What Is Complete

| Component                        | Location                                        | Quality                    |
| -------------------------------- | ----------------------------------------------- | -------------------------- |
| FastAPI app + CORS               | `backend/src/main.py`                           | Production                 |
| Pydantic settings                | `backend/src/config.py`                         | Production                 |
| SQLAlchemy engine + PostGIS      | `backend/src/database.py`                       | Production                 |
| All 5 ORM models                 | `backend/src/models/`                           | Production                 |
| Alembic initial migration        | `backend/alembic/versions/bcf9c05b...`          | Production                 |
| Health router (4 endpoints)      | `backend/src/routers/health.py`                 | Production                 |
| Procurement router (8 endpoints) | `backend/src/routers/procurement.py`            | Production                 |
| Procurement service + S3         | `backend/src/services/`                         | Production                 |
| Satellite config + utils         | `satellite/src/config.py`, `utils.py`           | Production                 |
| Copernicus downloader            | `satellite/src/download.py`                     | Production                 |
| NDVI processor                   | `satellite/src/process_ndvi.py`                 | Production (minor AOI gap) |
| SAR processor (PyroSAR)          | `satellite/src/process_sar.py`                  | Production (requires SNAP) |
| Training dataset                 | `satellite/data/training/training_projects.csv` | 30 labelled projects       |
| EGP scraper (structure)          | `data/scrapers/egp.py`                          | Broken imports             |
| PPIP scraper (structure)         | `data/scrapers/ppip.py`                         | Broken imports             |
| COB poller (structure)           | `data/scrapers/cob.py`                          | Broken imports             |
| KMHFL scraper (structure)        | `data/scrapers/kmhfl.py`                        | Broken imports             |
| NCA scraper (structure)          | `data/scrapers/nca.py`                          | Broken imports             |
| 29 backend tests                 | `backend/tests/`                                | Passing                    |
| 8 satellite utils tests          | `satellite/tests/test_utils.py`                 | Passing                    |

### What Is Missing (Complete List)

| Component                 | File(s) to Create                                     | Blocking Phase |
| ------------------------- | ----------------------------------------------------- | -------------- |
| Docker dev stack          | `docker-compose.yml` + `scripts/setup_dev.sh`         | Phase 0        |
| DB seed script            | `backend/scripts/seed_training_projects.py`           | Phase 0        |
| Scraper import fix        | `data/scrapers/*.py` (refactor)                       | Phase 1        |
| EGP GPS columns migration | `backend/alembic/versions/002_add_egp_gps_fields.py`  | Phase 1        |
| COB field extraction      | `data/parsers/cob.py` (extend)                        | Phase 1        |
| `FinancialService`        | `backend/src/services/financial_service.py`           | Phase 1        |
| Celery app                | `backend/src/celery_app.py`                           | Phase 1        |
| Ingestion tasks           | `backend/src/tasks/ingestion_tasks.py`                | Phase 1        |
| `GeolocationService`      | `backend/src/services/geolocation_service.py`         | Phase 2        |
| Geolocation router        | `backend/src/routers/geolocation.py`                  | Phase 2        |
| `ConcordanceService`      | `backend/src/services/concordance_service.py`         | Phase 2        |
| Projects router           | `backend/src/routers/projects.py`                     | Phase 2        |
| Financial router          | `backend/src/routers/financial.py`                    | Phase 2        |
| Ward boundary data        | PostGIS `admin_boundaries` table + GeoJSON            | Phase 2        |
| `SatelliteService`        | `backend/src/services/satellite_service.py`           | Phase 3        |
| Satellite Celery tasks    | `backend/src/tasks/satellite_tasks.py`                | Phase 3        |
| `NDWIProcessor`           | `satellite/src/process_ndwi.py`                       | Phase 3        |
| NDVI AOI spatial mask     | `satellite/src/process_ndvi.py` (fix)                 | Phase 3        |
| `ndvi_slope` computation  | `satellite/src/process_ndvi.py` (extend)              | Phase 3        |
| `DivergenceService`       | `backend/src/services/divergence_service.py`          | Phase 3        |
| Satellite router          | `backend/src/routers/satellite.py`                    | Phase 3        |
| `FeatureEngineer`         | `satellite/src/feature_engineering.py`                | Phase 4        |
| Model training pipeline   | `satellite/src/train_model.py`                        | Phase 4        |
| Training CLI              | `satellite/scripts/run_training.py`                   | Phase 4        |
| Trained model artifact    | `satellite/models/ghost_detector_v1.pkl`              | Phase 4        |
| `RiskScoringService`      | `backend/src/services/risk_scoring_service.py`        | Phase 4        |
| ML Celery tasks           | `backend/src/tasks/ml_tasks.py`                       | Phase 4        |
| Risk router               | `backend/src/routers/risk.py`                         | Phase 4        |
| Google Tiles proxy router | `backend/src/routers/maps.py`                         | Phase 5        |
| `TileGenerator`           | `satellite/src/generate_tiles.py`                     | Phase 5        |
| Tile URL migration        | `backend/alembic/versions/003_add_tile_url_column.py` | Phase 5        |
| `CertificateService`      | `backend/src/services/certificate_service.py`         | Phase 6        |
| 106B Jinja2 template      | `backend/templates/certificate_106b.html`             | Phase 6        |
| Certificates router       | `backend/src/routers/certificates.py`                 | Phase 6        |
| Rate limiting             | `slowapi` wired in `main.py`                          | Phase 7        |
| Full router registration  | `backend/src/main.py` (update)                        | Phase 7        |
| 8 new test files          | `backend/tests/test_*.py`                             | Phase 7        |

---

## Phase-by-Phase Next Steps

---

### Phase 0 — Environment & Database Bootstrap

**Status:** Partially done. The Alembic migration exists. Docker and seed scripts do not.

**Tasks:**

1. **Create `docker-compose.yml`** at repo root:
   - Services: `postgres` (PostgreSQL 15 + PostGIS 3.4), `redis` (Redis 7), `api` (FastAPI), `worker` (Celery)
   - Volume for Postgres data persistence
   - Health checks on Postgres before API starts

2. **Create `scripts/setup_dev.sh`**:
   - Creates Python virtual environments for all three modules
   - Installs `backend/requirements.txt`, `data/requirements.txt`, `satellite/requirements.txt`
   - Runs `python -m spacy download en_core_web_sm`
   - Runs `alembic upgrade head` inside `backend/`
   - Documents SNAP and GDAL system dependency installation

3. **Fix config URL** in `backend/src/config.py`:
   - Change `kmhfl_api_url` from `http://kmhfl.health.go.ke/api` → `https://api.kmhfr.health.go.ke/api/v2`
   - Also fix `data/scrapers/kmhfl.py` `API_URL` constant to match

4. **Create `backend/scripts/seed_training_projects.py`**:
   - Reads `satellite/data/training/training_projects.csv`
   - Creates `Project` rows for all 30 training projects with `risk_level = None` (pending ML scoring)
   - Creates stub `ProcurementRecord` rows from the CSV `budget_kes` and `award_date` fields for testing

**Deliverables:** `docker-compose.yml`, `scripts/setup_dev.sh`, seed script, config URL fix

---

### Phase 1 — Data Ingestion Pipelines

**Status:** Not started. All five scrapers have broken imports. COB parser is incomplete.

**Critical blocker:** `data/scrapers/*.py` all import from `backend.db.AsyncSessionLocal` and `backend.models.tenders.Tender` — these modules do not exist. No data can be ingested until imports are corrected to point at `backend.src.database` and `backend.src.models`.

#### 1.1 Scraper Import Refactor (all 5 scrapers)

For each scraper in `data/scrapers/`, replace the broken imports:

```
# Before (broken)
from backend.db import AsyncSessionLocal
from backend.models.tenders import Tender

# After (correct)
from backend.src.database import SessionLocal
from backend.src.models.procurement import ProcurementRecord
```

Field mapping per scraper:

- **`egp.py`** (highest priority — primary GPS source):
  - Map `tenderDetails.tenderrefno` → `tender_number`
  - Map `tenderDetails.tendertitle` → `tender_title`
  - Map `tenderDetails.procuringEntity` → `procuring_entity`
  - **Extract `deliveryLocation.geometry.coordinates` → save to `GeolocationRecord` immediately at scrape time**
  - Set `gps_quality_score`: `EGP_MANUAL_PIN = 90`, `EGP_AUTO_GEOCODED = 70`, `EGP_MISSING = 0`
  - Set `source_system = "eGP"`, `extraction_method = "playwright_intercept"`

- **`ppip.py`** (one-time historical import only):
  - Map `tender_ref`/`tender_no` → `tender_number`
  - Set `source_system = "PPIP"`, mark as historical

- **`kmhfl.py`**:
  - Change target table from `Facility` → `GeolocationRecord`
  - Set `source_system = "KMHFR"`, `match_method = "registry"`
  - Store facility lat/lon as PostGIS Point via `GeolocationRecord.set_geom_from_coordinates()`

- **`nca.py`**:
  - Map `ProjectName` → `tender_title`, `MainContractor` → `contractor_name`
  - Set `source_system = "NCA"`

- **`cob.py`**:
  - Wire `CoBParser` into the `save()` logic for COB PDFs
  - Map parsed expenditure table fields to `FinancialRecord`

#### 1.2 New Alembic Migration: EGP GPS Columns

Create `backend/alembic/versions/002_add_egp_gps_fields.py` to add to `procurement_records`:

```sql
ALTER TABLE procurement_records ADD COLUMN egp_tender_id TEXT;
ALTER TABLE procurement_records ADD COLUMN delivery_latitude NUMERIC(10,7);
ALTER TABLE procurement_records ADD COLUMN delivery_longitude NUMERIC(10,7);
ALTER TABLE procurement_records ADD COLUMN gps_source TEXT;  -- EGP_MANUAL_PIN | KMHFL_MATCHED | NEMIS_MATCHED | WARD_CENTROID
ALTER TABLE procurement_records ADD COLUMN gps_quality_score INTEGER;  -- 0-100
```

#### 1.3 Complete the COB Financial Parser

Extend `data/parsers/cob.py`:

- `find_expenditure_table()` currently returns a raw `pd.DataFrame`. It needs to return structured dicts instead.
- Add `extract_financial_records(project_name: str) -> List[dict]` that:
  - Calls `find_expenditure_table()`
  - Uses `rapidfuzz.process.extractOne` to match `project_name` against the "Vote" column
  - Returns rows mapped to `FinancialRecord` schema keys: `vote_head`, `budget_allocated_kes`, `budget_absorbed_kes`, `absorption_rate`, `reporting_period`

#### 1.4 Create `FinancialService`

New file: `backend/src/services/financial_service.py`

- `ingest_cob_report(pdf_path: str, fiscal_year: str)`: calls `CoBParser`, saves `FinancialRecord` rows
- `get_financial_records_for_project(project_uuid: UUID)`: DB query
- `calculate_absorption_gap(project_uuid: UUID) -> dict`: `budget_absorbed / contract_sum`

#### 1.5 Celery App and Ingestion Tasks

New files:

- `backend/src/celery_app.py`: Celery factory connected to Redis
- `backend/src/tasks/__init__.py`
- `backend/src/tasks/ingestion_tasks.py`:
  - `scrape_egp_task()` — daily schedule (02:00 EAT)
  - `import_ppip_historical_task(max_pages=500)` — run once only
  - `ingest_cob_report_task(pdf_url, fiscal_year)` — triggered on new COB PDF
  - `refresh_kmhfl_task()` — monthly schedule

Also add `POST /api/v1/admin/trigger-scrape` endpoint to `main.py` for manual task triggering.

**Phase 1 Definition of Done:**

- All 5 scrapers import from `backend.src.models` without errors
- EGP scraper saves GPS coordinates to `GeolocationRecord` at scrape time
- PPIP one-time import populates `procurement_records`
- KMHFL scraper populates `geolocation_records` with ≥100 facility records in test run
- COB parser maps PDF tables to `FinancialRecord` rows
- Celery worker starts with `celery -A backend.src.celery_app worker`

---

### Phase 2 — Interoperability Engine

**Status:** Not started. No services or routers exist for geolocation, concordance, or projects.

**Depends on:** Phase 1 (data in `procurement_records` and `geolocation_records` tables)

#### 2.1 Geolocation Service (Three-Tier)

New file: `backend/src/services/geolocation_service.py`

Three-tier resolution pipeline:

| Tier | Trigger                                       | Method                                                           | `gps_quality_score` |
| ---- | --------------------------------------------- | ---------------------------------------------------------------- | ------------------- |
| 1    | `delivery_latitude` already set (e-GP)        | Pass-through, skip NER                                           | 70–90               |
| 2    | No e-GP GPS; spaCy NER extracts facility name | Fuzzy match against KMHFR registry (RapidFuzz `token_set_ratio`) | 60–80               |
| 3    | Fuzzy match score < 70                        | Ward centroid from UNOCHA admin boundaries                       | 20                  |

Steps:

- Add `spacy` to `backend/requirements.txt`
- Load UNOCHA Kenya Level 3 (Ward) admin boundary GeoJSON into a new PostGIS `admin_boundaries` table via a migration
- Implement `GeolocationService.resolve(procurement_id)` — returns `GeolocationResult(lat, lon, confidence, method)`
- Implement `GeolocationService.batch_resolve(project_uuids)` — skip Tier 1 records already geolocated

New router: `backend/src/routers/geolocation.py`

- `POST /api/v1/geolocation/resolve` — resolve a single procurement record
- `GET /api/v1/geolocation/coverage` — returns `{tier1_egp: N, tier2_fuzzy: N, tier3_ward: N, unresolved: N}`

#### 2.2 Concordance Service

New file: `backend/src/services/concordance_service.py`

- `link_procurement_to_project(procurement_id)`:
  - RapidFuzz fuzzy match of `tender_title` against existing `Project.project_name` (score > 85 = same project)
  - If no match: create new `Project` row with fresh UUID
  - Infers `project_type` from title keywords (health/education/roads/water)
  - Calls `GeolocationService.resolve()` to assign GPS
- `link_financial_to_project(financial_id)`: fuzzy-matches `ministry + programme` to `project_name`
- `get_project_truth_record(project_uuid)`: unified "5-second project card" — all linked records

New router: `backend/src/routers/projects.py`

- `GET /api/v1/projects` — list with pagination and risk-level filter
- `GET /api/v1/projects/{uuid}` — single project
- `GET /api/v1/projects/{uuid}/truth-record` — full unified project card
- `POST /api/v1/projects/reconcile` — trigger concordance for all unlinked records
- `GET /api/v1/projects/geojson` — all projects as GeoJSON FeatureCollection (for CesiumJS)

New router: `backend/src/routers/financial.py`

- `GET /api/v1/financial/{project_uuid}` — all financial records for a project
- `GET /api/v1/financial/{project_uuid}/absorption` — absorption gap calculation

**Phase 2 Definition of Done:**

- ≥ 25 projects exist with linked procurement + geolocation records
- `/api/v1/geolocation/coverage` shows tier breakdown
- e-GP GPS coverage ≥ 70% of all procurement records
- Truth-record endpoint returns complete unified project card

---

### Phase 3 — Satellite Processing Pipeline Integration

**Status:** The standalone scripts exist but are not wired to the database or Celery.

**Depends on:** Phase 2 (projects with GPS coordinates in DB)

#### 3.1 `SatelliteService` (Backend Bridge)

New file: `backend/src/services/satellite_service.py`

- `queue_analysis(project_uuid)`: loads GPS from `GeolocationRecord`, enqueues Celery task, returns `task_id`
- `save_ndvi_result(project_uuid, result)`: writes `NDVIProcessor` output dict to `satellite_analyses` table
- `save_sar_result(project_uuid, result)`: writes `SARProcessor` output dict to `satellite_analyses` table
- `get_time_series(project_uuid)`: all `SatelliteAnalysis` rows ordered by `acquisition_date`

#### 3.2 Satellite Celery Tasks

New file: `backend/src/tasks/satellite_tasks.py`

- `analyse_project_task(project_uuid, lat, lon, start_date, end_date)`:
  1. Search + download Sentinel-2 scenes (top 3 by cloud cover ≤ 20%)
  2. For each scene: run `NDWIProcessor` → if `water_present = True`, skip NDVI, log and continue
  3. For each non-water scene: run `NDVIProcessor` → `save_ndvi_result()`
  4. Search + download Sentinel-1 GRD scene
  5. Run `SARProcessor` → `save_sar_result()`
  6. Call `divergence_service.calculate_divergence(project_uuid)`
  7. Enqueue `score_project_risk_task(project_uuid)`
- `batch_analyse_flagged_projects_task()`: runs analysis for all projects with `risk_level = None`

#### 3.3 `NDWIProcessor` (New File)

New file: `satellite/src/process_ndwi.py`

- Mirrors `NDVIProcessor` structure
- NDWI = (B03 Green − B08 NIR) / (B03 Green + B08 NIR)
- Returns `NDWIResult(water_present: bool, ndwi_mean: float)`
- `water_present = True` if `ndwi_mean > 0.3`
- Used as pre-check in `analyse_project_task` before running NDVI

#### 3.4 Fix NDVI AOI Spatial Masking

In `satellite/src/process_ndvi.py`, `extract_aoi_statistics()` currently uses the whole image array. A comment in the file already notes this gap. Fix it to:

- Use `rasterio.mask.mask()` with the 500m circular polygon generated by `create_bbox()`
- This ensures stats represent only the project site, not surrounding land

#### 3.5 `ndvi_slope` Computation (Multi-Scene Temporal)

Extend `NDVIProcessor` to compute `ndvi_slope`:

- Requires ≥ 2 scenes from different dates for the same AOI
- `ndvi_slope` = linear regression slope of `ndvi_mean` over time (NDVI change per month)
- A negative slope (vegetation clearing) is the primary ghost project signal

#### 3.6 `DivergenceService`

New file: `backend/src/services/divergence_service.py`

- `calculate_divergence(project_uuid)`:
  - `financial_progress` = latest `FinancialRecord.absorption_rate`
  - `physical_progress` = f(ndvi_slope, sar_backscatter_delta) mapped to 0–100 score
  - `divergence_score` = `financial_progress − physical_progress`
  - `alert_level`: RED (> 50), YELLOW (20–50), GREEN (< 20)
  - Updates `Project.risk_level` in DB

New router: `backend/src/routers/satellite.py`

- `POST /api/v1/satellite/analyse/{project_uuid}` — enqueue analysis task
- `GET /api/v1/satellite/status/{task_id}` — poll Celery status
- `GET /api/v1/satellite/tiles/{project_uuid}/ndvi/{z}/{x}/{y}` — proxy/redirect to S3 tiles
- `GET /api/v1/projects/{project_uuid}/divergence` — divergence timeline
- `GET /api/v1/dashboard/heat-map` — all projects with risk levels + coordinates (for CesiumJS)

**Phase 3 Definition of Done:**

- At least 5 projects have NDVI + SAR analyses in `satellite_analyses` table
- NDWI water filter applied before every NDVI analysis
- Divergence scores computed and stored for all analysed projects
- `alert_level` correctly set: RED / YELLOW / GREEN

---

### Phase 4 — Machine Learning Training & Inference

**Status:** Not started. Training data exists (30 labelled projects). No training code exists.

**Depends on:** Phase 3 (populated `satellite_analyses` table with time-series data)

#### 4.1 `FeatureEngineer`

New file: `satellite/src/feature_engineering.py`

10 features per project:

| Feature                 | Source                                                  | Notes                                                                     |
| ----------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------- |
| `ndvi_slope`            | `satellite_analyses`                                    | Rate of NDVI change per month                                             |
| `sar_backscatter_delta` | `satellite_analyses`                                    | Max VV change from baseline                                               |
| `divergence_score`      | Computed by `DivergenceService`                         | financial − physical                                                      |
| `months_to_clearing`    | `satellite_analyses` + `procurement_records.award_date` | Months from award to first NDVI drop > 0.3                                |
| `absorption_anomaly`    | `financial_records`                                     | Deviation from linear spend (MVP: linear interpolation only, not S-curve) |
| `contract_value_log`    | `procurement_records.contract_sum_kes`                  | `log10(contract_sum)`                                                     |
| `project_type_encoded`  | `projects.project_type`                                 | health=0, education=1, roads=2, water=3                                   |
| `county_cloud_risk`     | Pre-computed lookup table                               | Annual cloud fraction per county                                          |
| `contractor_tier`       | `procurement_records.contractor_nca_license`            | NCA1=1 through NCA8=8                                                     |
| `phase_on_schedule`     | Financial + satellite                                   | Binary: spend rate within tolerance                                       |

Methods:

- `extract_features(project_uuid) -> pd.Series`: reads live DB data
- `build_training_dataframe(projects_csv: Path) -> pd.DataFrame`: builds from CSV for training

#### 4.2 Model Training Script

New file: `satellite/src/train_model.py`

- `train_ghost_project_classifier(features_df, labels)`:
  1. Median imputation for missing values
  2. SMOTE oversampling for ghost class (10:20 imbalance)
  3. `RandomForestClassifier(n_estimators=200, max_depth=8, class_weight="balanced")`
  4. 5-fold `StratifiedKFold` cross-validation
  5. Target: AUC ≥ 0.80, Precision (ghost) ≥ 0.75, Recall (ghost) ≥ 0.70
  6. Save `satellite/models/ghost_detector_v1.pkl` + `feature_importance.csv` + plots

New file: `satellite/scripts/run_training.py`

```
python scripts/run_training.py --data data/training/training_projects.csv --output models/
```

#### 4.3 `RiskScoringService`

New file: `backend/src/services/risk_scoring_service.py`

- `score_project(project_uuid)`:
  - Calls `FeatureEngineer.extract_features(project_uuid)`
  - `model.predict_proba(features)` → `ghost_probability` (0.0–1.0)
  - Maps to `RiskLevel`: LOW (0–30%), MEDIUM (31–60%), HIGH (61–80%), CRITICAL (81–100%)
  - Updates `Project.risk_level` and `Project.ghost_probability` in DB (note: `ghost_probability` column needs to be added to the `projects` model)
- `score_all_active_projects()`: batch scoring

New file: `backend/src/tasks/ml_tasks.py`

- `score_project_risk_task(project_uuid)`: called automatically after satellite analysis
- `batch_score_task()`: weekly re-scoring of all active projects

New router: `backend/src/routers/risk.py`

- `GET /api/v1/risk/score/{project_uuid}` — risk score + features breakdown
- `GET /api/v1/risk/heat-map` — all projects as GeoJSON with `ghost_probability` (for dashboard pins)

**Note:** `ghost_probability` field is referenced in the `projects` table in the system flowchart but does not exist in the current `Project` model. Add a migration to add `ghost_probability NUMERIC(5,4)` to `projects`.

**Phase 4 Definition of Done:**

- `ghost_detector_v1.pkl` trained with 5-fold CV AUC ≥ 0.80
- Risk scores populated for all analysed projects
- `GET /api/v1/risk/score/{uuid}` returns ghost probability

---

### Phase 5 — Google Maps / 3D Tiles Integration

**Status:** Not started. `google_maps_api_key` already in `config.py`.

**Depends on:** Phase 4 (projects have risk scores and GPS coordinates)

#### 5.1 Google Maps Proxy Router

New file: `backend/src/routers/maps.py`

- `POST /api/v1/maps/tiles/session`:
  - Server-side call to `https://tile.googleapis.com/v1/createSession` using `GOOGLE_MAPS_API_KEY`
  - Session token cached in Redis (3-hour TTL)
  - **Never expose the API key in any response**
- `GET /api/v1/maps/tiles/{session_token}/{z}/{x}/{y}`:
  - Proxies tile requests to Google Maps Tiles API, appending `key=` server-side
  - Streams tile bytes to frontend

#### 5.2 Satellite Tile Generation

New file: `satellite/src/generate_tiles.py`

- `TileGenerator` class:
  - Input: processed NDVI or SAR GeoTIFF
  - Reproject to Web Mercator (EPSG:3857) using `rasterio.warp.reproject`
  - Apply colormap (NDVI: green–brown diverging; SAR: grayscale)
  - Generate XYZ tile pyramid using `gdal2tiles` (or `cogeo-mosaic`)
  - Upload to S3 at `tiles/{project_uuid}/{layer}/{z}/{x}/{y}.png`
  - Return base tile URL

Add `SatelliteAnalysis.tile_url_template` is already in the model but may need a separate `tile_base_url` migration for cleaner storage of the S3 root path.

#### 5.3 Projects GeoJSON Endpoint

Add to `backend/src/routers/projects.py`:

- `GET /api/v1/projects/geojson`: all projects as `GeoJSON FeatureCollection`
  - Properties per Feature: `project_uuid`, `project_name`, `risk_level`, `ghost_probability`, `alert_level`, `county`
  - Supports `?risk_level=HIGH,CRITICAL` filter

**Phase 5 Definition of Done:**

- `/api/v1/maps/tiles/session` returns valid session token
- `/api/v1/projects/geojson` returns valid GeoJSON with risk data
- At least 3 projects have S3 tile pyramids accessible via `/api/v1/satellite/tiles/…`

---

### Phase 6 — Section 106B Legal Certificate Generator

**Status:** Not started. Requirements fully defined.

**Depends on:** Phase 3 (satellite analyses with scene metadata + SHA-256 hashes stored in S3)

#### 6.1 `CertificateService`

New file: `backend/src/services/certificate_service.py`

Section 106B (Kenya Evidence Act) certificate must contain:

1. Source of the electronic record (ESA Copernicus Data Space)
2. Scene acquisition timestamp (ISO 8601)
3. Processing algorithm description (NDVI formula, SAR calibration steps)
4. Data integrity proof: SHA-256 hash of the downloaded scene file (from S3 object metadata)
5. Chain of custody: download timestamp, processing timestamp, analyst name/title
6. Statement: `"The computer system was operating properly at the time the data described herein was produced."`
7. Signature block for signing official (OAG/EACC)

Implementation:

- Render Jinja2 HTML template → WeasyPrint PDF
- `generate_106b_certificate(project_uuid, analyst_name, analyst_title) -> bytes`
- Store certificate in S3 at `certificates/{project_uuid}/{timestamp}.pdf`
- Retrieve SHA-256 hash from S3 object metadata (already computed by `s3_storage.py` on upload)

New file: `backend/templates/certificate_106b.html` — Jinja2 template styled as an official Kenyan legal document

Add to `backend/requirements.txt`: `weasyprint`, `jinja2` (if not already present)

New router: `backend/src/routers/certificates.py`

- `GET /api/v1/certificates/{project_uuid}?analyst_name=…&analyst_title=…` → PDF download

**Phase 6 Definition of Done:**

- Certificate generated for at least one of the 30 training projects
- PDF contains all 7 required Section 106B fields
- Certificate stored in S3 and retrievable via the endpoint

---

### Phase 7 — API Hardening & Test Coverage

**Status:** Not started. Existing test coverage is ~62% (by Sprint 2 estimate, procurement tests only).

**Depends on:** Phases 1–6

#### 7.1 Register All Routers in `main.py`

Update `backend/src/main.py` to add:

```python
from src.routers import (
    projects, financial, geolocation, satellite, risk, maps, certificates
)
app.include_router(projects.router,      prefix="/api/v1", tags=["Projects"])
app.include_router(financial.router,     prefix="/api/v1", tags=["Financial"])
app.include_router(geolocation.router,   prefix="/api/v1", tags=["Geolocation"])
app.include_router(satellite.router,     prefix="/api/v1", tags=["Satellite"])
app.include_router(risk.router,          prefix="/api/v1", tags=["Risk Scoring"])
app.include_router(maps.router,          prefix="/api/v1", tags=["Maps"])
app.include_router(certificates.router,  prefix="/api/v1", tags=["Certificates"])
```

#### 7.2 New Test Files Required

| Test File                     | Key Assertions                                                                                                                     |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `test_geolocation_service.py` | Tier 1 GPS passthrough; Tier 2 NER + RapidFuzz with known KMHFR record; Tier 3 ward centroid; `gps_quality_score` correct per tier |
| `test_concordance_service.py` | New project created on first record; duplicate title links to same UUID; truth-record returns all linked data                      |
| `test_financial_service.py`   | COB PDF parsing extracts `absorption_rate`; absorption gap calculation                                                             |
| `test_divergence_service.py`  | 90% financial + 0% physical → RED alert; known Green and Yellow cases                                                              |
| `test_satellite_tasks.py`     | Mock Copernicus API; NDWI water filter skips NDVI; NDVI result saved to DB                                                         |
| `test_risk_scoring.py`        | Known ghost training project scores > 0.61; known successful project scores < 0.30                                                 |
| `test_certificate.py`         | PDF generated; all 7 Section 106B fields present in output                                                                         |
| `test_maps.py`                | Session token returned (mocked Google API); GeoJSON endpoint returns valid FeatureCollection                                       |

**Target:** ≥ 70% code coverage across `backend/src/`

#### 7.3 Security Hardening

- Add `slowapi` rate limiting with Redis backend to all public endpoints
- Add `Content-Security-Policy` and `X-Content-Type-Options` response headers
- Validate all coordinate inputs (lat ±90, lon ±180) before forwarding to Copernicus
- Sanitise `tender_title` inputs before fuzzy matching
- Confirm `GOOGLE_MAPS_API_KEY` never appears in any API response body
- Confirm S3 bucket blocks public access; all presigned URLs expire in ≤ 60 minutes

---

## Dependency Order (Critical Path)

```
Phase 0 (Docker + DB)
  └── Phase 1 (Scraper Fix + Celery + Financial Parser)
        └── Phase 2 (Geolocation + Concordance + Project Router)
              └── Phase 3 (Satellite Pipeline + NDWI + Divergence)
                    └── Phase 4 (ML Training + Risk Scoring)
                    │
                    └── Phase 5 (Google Maps Proxy + Tile Generator)
                          └── Phase 6 (Section 106B Certificate)
                                └── Phase 7 (Hardening + Full Test Coverage)
```

Phases 5 and 6 can run in parallel after Phase 4 is complete.

---

## Known Technical Gaps Not in the Original Plan

These issues were discovered during code review and are not mentioned in the master implementation plan:

| Gap                                                                                                                                                                    | Location                                                 | Fix                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/src/services/ppip_scraper.py` CSS selectors are template guesses (`tr.tender-row`, `.tender-number`, etc.) — not validated against the live PPIP HTML         | `backend/src/services/ppip_scraper.py`                   | The canonical PPIP scraper is `data/scrapers/ppip.py` (already uses the correct JSON API endpoint). The backend service version should be removed or replaced with a call to the data/ scraper after the import fix. |
| `Project` model has no `ghost_probability` column                                                                                                                      | `backend/src/models/project.py`                          | Add `ghost_probability = Column(Numeric(5, 4), nullable=True)` and create migration `004_add_ghost_probability.py`                                                                                                   |
| `FinancialRecord` has no `fiscal_year` column — the system flowchart and master plan reference it, but the model only has `reporting_period` (a string)                | `backend/src/models/financial.py`                        | Assess whether `reporting_period` is sufficient or if a separate `fiscal_year` column (e.g. `"2023/2024"`) is needed for COB ingestion                                                                               |
| `satellite/src/process_ndvi.py` computes statistics on the full scene, not the 500m AOI. The comment acknowledges this as a known gap.                                 | `satellite/src/process_ndvi.py:extract_aoi_statistics()` | Implement rasterio mask with circular polygon in Phase 3                                                                                                                                                             |
| No `ndvi_slope` is computed anywhere — only per-scene `ndvi_mean`. The flowchart and ML feature table both require `ndvi_slope` as the primary ghost detection signal. | `satellite/src/process_ndvi.py`                          | Add multi-scene temporal regression in Phase 3                                                                                                                                                                       |

---

## Dependencies to Add

| Package                        | Module      | Required For                 |
| ------------------------------ | ----------- | ---------------------------- |
| `celery[redis]`                | `backend`   | Phase 1 task queue           |
| `spacy` + `en_core_web_sm`     | `backend`   | Phase 2 NER geolocation      |
| `rapidfuzz`                    | `backend`   | Phase 2 fuzzy matching       |
| `weasyprint`                   | `backend`   | Phase 6 PDF generation       |
| `jinja2`                       | `backend`   | Phase 6 certificate template |
| `slowapi`                      | `backend`   | Phase 7 rate limiting        |
| `imbalanced-learn` (SMOTE)     | `satellite` | Phase 4 ML training          |
| `scikit-learn`                 | `satellite` | Phase 4 ML training          |
| `joblib`                       | `satellite` | Phase 4 model serialization  |
| `cogeo-mosaic` or `gdal2tiles` | `satellite` | Phase 5 tile generation      |

---

## Definition of Done (Full Backend)

The backend is complete when all of the following pass:

- [ ] `docker-compose up` starts PostgreSQL + Redis + FastAPI + Celery cleanly
- [ ] `alembic upgrade head` runs with no errors
- [ ] All 5 `data/scrapers/` import from `backend.src.models` without errors
- [ ] e-GP scraper has populated ≥ 100 `procurement_records` with `gps_source` set
- [ ] PPIP historical importer has run once (backfilled pre-2025 records)
- [ ] KMHFR scraper has populated ≥ 5,000 `geolocation_records`
- [ ] COB parser has ingested ≥ 1 BIRR report → `financial_records` populated
- [ ] e-GP GPS coverage ≥ 70% confirmed via `/api/v1/geolocation/coverage`
- [ ] Concordance service links ≥ 25 procurement records to project UUIDs with GPS
- [ ] Satellite pipeline runs end-to-end for ≥ 5 projects (NDVI + SAR + NDWI in DB)
- [ ] NDWI water filter applied before each NDVI analysis
- [ ] Divergence scores computed (GREEN / YELLOW / RED) for all analysed projects
- [ ] ML model trained: 5-fold CV AUC ≥ 0.80, saved as `ghost_detector_v1.pkl`
- [ ] Risk scores returned for all analysed projects via `/api/v1/risk/score/{uuid}`
- [ ] Google Tiles session endpoint returns valid session token
- [ ] `/api/v1/projects/geojson` returns valid GeoJSON with all projects and risk pins
- [ ] Section 106B certificate generated as downloadable PDF with all required fields
- [ ] Test coverage ≥ 70% across `backend/src/`
- [ ] Rate limiting active on all public endpoints
- [ ] `GET /docs` (OpenAPI UI) documents all endpoints with schemas
- [ ] `GOOGLE_MAPS_API_KEY` is never returned in any API response body
