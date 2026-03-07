# Single-Project Investigation Pipeline — Execution Report

**Date:** March 8, 2026  
**Status:** All 5 sprints complete. 334 backend tests, 116 data tests, 82% coverage.

---

## 1. Overview

The single-project investigation feature lets a user nominate any Kenya government infrastructure project by name. The system then:

1. Enriches the project name with structured context (Perplexity AI or manual input)
2. Runs all five data scrapers in **targeted mode** against that specific project
3. Links scraped records to a canonical `Project` row via fuzzy concordance
4. Resolves GPS coordinates through the three-tier geolocation engine
5. Queues satellite analysis and ML risk scoring

This is distinct from the bulk ingestion pipeline (Celery beat) which scrapes all active tenders on a schedule. The investigation pipeline operates on a single project in near-real-time (~2–5 minutes end-to-end).

---

## 2. Status State Machine

```
POST /investigations
        │
        ▼
    CREATED ──────────────────────────────────────────┐
        │                                             │ Perplexity unavailable
        │ POST /investigations/{id}/enrich            │ (502 returned, status
        ▼                                             │  rolled back to CREATED)
    ENRICHING                                         │
        │                                             │
        ▼                                             │
    ENRICHED ◄────────────────────────────────────────┘
        │         PATCH /investigations/{id}/context
        │         (manual context — bypasses Perplexity)
        │ POST /investigations/{id}/scrape
        ▼
    SCRAPING      Stage 1: all 5 scrapers (targeted mode)
        │
        ▼
    CONCORDANCE   Stage 2: RapidFuzz entity resolution → Project row
        │
        ▼
    GEOLOCATING   Stage 3: read resolved GeolocationRecord
        │
        ▼
    SATELLITE     Stage 4: analyse_project_task enqueued (if coords resolved)
        │
        ▼
    SCORING       Stage 5: score_project_risk_task enqueued by satellite chain
        │
        ▼
    COMPLETE ─────────── or ────── FAILED (unrecoverable error)
```

Both `CREATED` and `ENRICHED` are valid launch states for `POST /scrape`. This allows investigations to proceed even when Perplexity is unavailable (see §4 Fallback Path).

---

## 3. API Endpoints

All endpoints are under `/api/v1/investigations`.

| Method  | Path                           | Description                     | Status    |
| ------- | ------------------------------ | ------------------------------- | --------- |
| `POST`  | `/investigations`              | Create a new investigation      | 201       |
| `POST`  | `/investigations/{id}/enrich`  | Perplexity AI enrichment        | 200 / 502 |
| `PATCH` | `/investigations/{id}/context` | Manual context correction       | 200       |
| `POST`  | `/investigations/{id}/scrape`  | Trigger full pipeline           | 202       |
| `GET`   | `/investigations/{id}/status`  | Poll stage progress             | 200       |
| `GET`   | `/investigations/{id}/report`  | Fetch full investigation report | 200       |

### Rate Limits

| Endpoint                           | Limit                                           |
| ---------------------------------- | ----------------------------------------------- |
| `POST /investigations`             | 20/hour                                         |
| `POST /investigations/{id}/scrape` | 10/hour                                         |
| `POST /investigations/{id}/enrich` | (no explicit limit — relies on default 200/min) |

---

## 4. Pre-Pipeline: Context Enrichment

Before the scraping pipeline can run, the investigation needs a `ProjectContext` — a structured JSON payload that scoped all five scrapers' targeted queries.

### Path A: Perplexity AI (automatic)

`POST /investigations/{id}/enrich` calls `PerplexityEnrichmentService.enrich()`:

1. Builds a structured query from `raw_project_name`
2. Calls the Perplexity Sonar-Pro API (`sonar-pro` model by default)
3. Parses the JSON response into a `ProjectContext`:
   - `canonical_name` — normalised project title
   - `county` — Kenya county
   - `aliases` — known alternate names
   - `fiscal_years` — relevant financial years (e.g. `["2022/2023"]`)
   - `search_terms` — derived keyword list for scraper targeting
   - `coordinates` — [lat, lon] if Perplexity can resolve location
   - `procuring_entity`, `ministry`, `vote_head` — for COB matching
4. Persists `project_context` (JSONB) to the `investigations` table
5. Advances status to `ENRICHED`

**On failure:** If the Perplexity API is unavailable or returns an error, `EnrichmentError` is raised. The router catches this, rolls status back to `CREATED`, and returns `502 Bad Gateway`. The investigation remains eligible for the manual path.

**Required env var:**

```
PERPLEXITY_API_KEY=pplx-...
PERPLEXITY_MODEL=sonar-pro
```

### Path B: Manual Context (Perplexity fallback)

`PATCH /investigations/{id}/context` accepts any subset of `ProjectContext` fields:

```json
{
  "canonical_name": "Proposed Turkana Water Supply Project",
  "county": "Turkana",
  "fiscal_years": ["2023/2024"],
  "procuring_entity": "Ministry of Water & Sanitation"
}
```

The endpoint merges the supplied fields into the existing `project_context` (seeding from `raw_project_name` if no prior context exists). Status is **not advanced** — `CREATED` stays `CREATED`, `ENRICHED` stays `ENRICHED`. The investigation can then be scraped from `CREATED` status.

This path requires **no API keys** and is fully operational even when Perplexity is down.

---

## 5. Pipeline Stages (`investigate_project_task`)

The `investigate_project_task` Celery task executes the 7-stage pipeline synchronously within a single worker.

### Stage 1 — Load Context

Reads the `Investigation` row and deserialises `project_context` into a `DataProjectContext` object. If no context exists, returns `{"status": "error", "reason": "no context"}` immediately — the pipeline does not proceed.

Advances status to `SCRAPING`.

### Stage 2 — Targeted Scraping

Runs all five scrapers in **targeted mode** — each scraper's `fetch(ctx=ctx)` method uses the `ProjectContext` to build specific queries (project name, county, fiscal year, procuring entity) rather than bulk-fetching all records.

| Scraper        | Source                 | Targeted Query Strategy                                 |
| -------------- | ---------------------- | ------------------------------------------------------- |
| `EGPScraper`   | egpkenya.go.ke         | Filter by `search_terms` + `procuring_entity`           |
| `NCAScraper`   | nca.go.ke              | Filter by `canonical_name` + `aliases`                  |
| `PPIPScraper`  | tenders.go.ke          | Filter by `search_terms` + `county`                     |
| `KMHFLScraper` | api.kmhfr.health.go.ke | Filter by facility name + county (health projects only) |
| `CoBPoller`    | cob.go.ke              | Download relevant BIRR PDFs for target fiscal years     |

Each scraper's `save()` is called only if `fetch()` returns records. Scraper failures are non-fatal — the pipeline continues with a warning log and `stage_counts[label] = 0`.

**COB PDF parsing** (if a relevant BIRR PDF is downloaded): The `IntelligentCoBParser` runs a two-stage extraction:

- Stage 1: pdfplumber keyword scan — narrows a 300-page PDF to 5–15 candidate pages
- Stage 2: GPT-4o Vision — renders each candidate page, sends to OpenAI Vision API with a structured prompt, extracts budget figures (`approved_budget_kes`, `absorbed_kes`, `absorption_rate_pct`)

**Vision cost guardrail:** `VISION_COST_LIMIT_USD` (default `$5.00`) caps OpenAI spend per investigation. The parser tracks `total_cost_usd` and stops before issuing the next Vision request if the cap is reached.

**Required env vars (for COB Vision):**

```
OPENAI_API_KEY=sk-...
OPENAI_VISION_MODEL=gpt-4o
VISION_MAX_PAGES=20
VISION_COST_LIMIT_USD=5.0
```

### Stage 3 — Row Tagging

All `ProcurementRecord` and `FinancialRecord` rows created during the scrape window are tagged with `investigation_id = inv_uuid`. This links raw scraped data to the investigation for the report endpoint.

If `ctx.coordinates` was provided by Perplexity, all unlocated procurement records for this investigation are seeded with those coordinates (`gps_source = "PERPLEXITY_CONTEXT"`, quality score 85), giving Tier 1 geolocation a head start.

Advances status to `CONCORDANCE`.

### Stage 4 — Concordance

`ConcordanceService.link_procurement_to_project()` is called for each tagged `ProcurementRecord` that has no `project_uuid` yet.

The concordance algorithm:

1. Attempts exact tender-number lookup
2. If no match, runs RapidFuzz `token_set_ratio` against all existing `Project` rows (threshold ≥ 85)
3. If matched, links the record to the existing project
4. If no match, creates a new `Project` row and links to it

The first resolved `project_uuid` is stored on the `Investigation` row. Advances status to `GEOLOCATING`.

### Stage 5 — Geolocation

Reads back the `GeolocationRecord` for `project_uuid` (ordered by `match_confidence DESC`). The record was already created by `ConcordanceService` internally (which calls `GeolocationService.resolve()` as part of linking).

Three-tier resolution:

- **Tier 1:** e-GP embedded GPS coordinates (`gps_source = "EGP_DELIVERY"` / `"PERPLEXITY_CONTEXT"`)
- **Tier 2:** spaCy NER + RapidFuzz fuzzy match against KMHFL/NEMIS facility registry
- **Tier 3:** Ward centroid fallback from Kenya admin boundary GeoJSON

Resolved lat/lon is stored in `stage_statuses.geolocation`. Advances status to `SATELLITE`.

### Stage 6 — Satellite Analysis (Enqueue)

If coordinates were resolved, `analyse_project_task.delay()` is enqueued with:

- `project_uuid`
- `lat`, `lon`
- `start_date`, `end_date` — derived from `ctx.fiscal_years` (or a 2-year rolling window)

The satellite task runs asynchronously: it downloads Sentinel-2 imagery, computes NDVI temporal slope, SAR backscatter change, and NDWI, then writes a `SatelliteAnalysis` row. On completion it chains into `score_project_risk_task`.

If no coordinates were resolved, `stage_statuses.satellite = {"status": "skipped_no_coords"}`.

Advances status to `SCORING` (satellite chain will transition to `COMPLETE` or `FAILED`).

### Stage 7 — Final Status Update

Sets `stage_statuses.satellite` and updates top-level status to `SCORING`. Control is handed off to the satellite Celery chain. The `GET /status` endpoint can be polled to track progress from `SCORING → COMPLETE`.

**On unrecoverable error:** Any uncaught exception triggers the `except` block, which sets `investigation.status = "failed"` and calls `self.retry(exc=exc)` (up to 2 retries with 120-second delay).

---

## 6. Report Endpoint

`GET /investigations/{id}/report` returns a unified view once the pipeline reaches `COMPLETE`:

```json
{
  "investigation_id": "...",
  "status": "complete",
  "project": { ... },           // Project card
  "context": { ... },           // ProjectContext (enriched)
  "procurement_records": [...],  // All records tagged to this investigation
  "financial_records": [...],    // All FinancialRecord rows
  "satellite_analysis": { ... }, // Latest NDVI/SAR metrics
  "risk_score": { ... },         // ML ghost probability
  "divergence": { ... }          // Financial vs physical gap
}
```

---

## 7. Data Layer: Targeted Scraper Context API

All five scrapers accept an optional `ctx: ProjectContext` argument in `fetch()`. When provided:

```python
# data/context.py
@dataclass
class ProjectContext:
    canonical_name: Optional[str] = None
    search_terms: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    coordinates: Optional[tuple[float, float]] = None
    fiscal_years: list[str] = field(default_factory=list)
    procuring_entity: Optional[str] = None
    ministry: Optional[str] = None
    county: Optional[str] = None
    vote_head: Optional[str] = None
```

Without `ctx`, scrapers fall back to bulk-fetch mode (used by the Celery beat schedule).

---

## 8. Sprint Delivery Summary

| Sprint   | Feature                                                                               | Backend Tests | Data Tests  |
| -------- | ------------------------------------------------------------------------------------- | ------------- | ----------- |
| Sprint 1 | `Investigation` model, `PerplexityEnrichmentService`, 6 API endpoints                 | +26 (→ 307)   | —           |
| Sprint 2 | Targeted scrapers (`ctx` param), `investigate_project_task` v1, `DataProjectContext`  | +5 (→ 312)    | +29 (→ 74)  |
| Sprint 3 | `IntelligentCoBParser` (pdf2image + GPT-4o Vision), `ingest_cob_report_intelligent()` | —             | +34 (→ 108) |
| Sprint 4 | Full 7-stage pipeline, E2E tests, `/scrape` + `/report` endpoints, migration 010      | +19 (→ 331)   | —           |
| Sprint 5 | Vision cost guardrails (`VISION_COST_LIMIT_USD`), Perplexity fallback tests           | +3 (→ 334)    | +8 (→ 116)  |

---

## 9. Test Coverage

### Backend (334 tests, 82% coverage)

| Test Class                        | Tests                        | Covers                                                                         |
| --------------------------------- | ---------------------------- | ------------------------------------------------------------------------------ |
| `TestPerplexityEnrichmentService` | 10                           | County extraction, canonical name, aliases, warnings, API keys, error handling |
| `TestInvestigationModel`          | 7                            | ORM round-trip, status transitions, JSONB context, cascade                     |
| `TestInvestigationsRouter`        | 17                           | All 6 endpoints, error cases, rate limits, context patching                    |
| `TestPerplexityFallback`          | 3                            | 502 on failure, manual PATCH, full enrich→fail→patch→scrape path               |
| `TestIngestCoBReportIntelligent`  | (in test_phase4.py)          | Two-stage parser integration, fiscal year routing                              |
| `TestInvestigationPipeline`       | (in test_ingestion_tasks.py) | Full 7-stage Celery task, stage status updates, error recovery                 |

### Data Layer (116 tests, isolated)

| Test Class                 | Tests | Covers                                                                        |
| -------------------------- | ----- | ----------------------------------------------------------------------------- |
| `TestEGPTargeted`          | 7     | GPS extraction, targeted keyword fetch, quality scoring                       |
| `TestNCATargeted`          | 6     | Targeted HTML search, row validation, ID namespacing                          |
| `TestPPIPTargeted`         | 5     | County + fiscal year filtering, date parsing                                  |
| `TestKMHFLTargeted`        | 5     | Targeted facility cache query, JSON persistence                               |
| `TestCoBTargeted`          | 6     | Targeted report discovery, metadata deduplication                             |
| `TestIntelligentCoBParser` | 16    | Stage 1 candidate selection, Stage 2 Vision API, JSON parsing, error recovery |
| `TestVisionCostGuardrails` | 8     | Cost accumulation, limit enforcement, zero-limit block, uncapped mode         |

---

## 10. Known Limitations & Future Work

| Item                      | Notes                                                                                                                                                       |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Concurrent investigations | Row-tagging by `created_at` timestamp assumes low concurrency. High-volume deployment needs scraper-level investigation ID propagation.                     |
| Satellite chain timing    | `SCORING → COMPLETE` transition depends on the satellite Celery worker processing the analysis. Chain latency varies with S3 + Copernicus API availability. |
| COB Vision cost           | Fixed at $5/investigation. Projects with large BIRR PDFs may benefit from a higher limit set via `VISION_COST_LIMIT_USD`.                                   |
| Perplexity confidence     | `enrichment_confidence < 0.7` triggers a user-facing warning but does not block the pipeline.                                                               |
| PPIP status               | PPIP is historical backfill only — `is_historical=True`. Never configure a continuous PPIP scraping schedule.                                               |
