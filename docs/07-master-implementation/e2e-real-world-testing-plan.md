# ONEKA AI — End-to-End Real-World Testing Plan

**Document Type:** Verification & Validation Plan
**Scope:** Full backend stack — FastAPI, Celery, PostgreSQL/PostGIS, Redis, S3, Perplexity AI, Copernicus satellite
**Environment:** Local (`docker-compose up`) or staging server
**Base URL:** `http://localhost:8000`

---

## Purpose

This plan verifies that every layer of the ONEKA backend works correctly against
**live, real-world Kenyan government data** — not mocks. Unit tests (335 passing,
80% coverage) confirm individual components. This plan confirms the full
pipeline produces correct outputs when connected to real external systems.

Run this plan:

- After any change to scraper logic, service logic, or Alembic migrations
- Before tagging a release candidate
- After rotating any external API key
- Whenever new real-world data must be verified end-to-end

---

## Pre-flight Checklist

Before making any API call, confirm all of the following.

### 1. Services

```bash
docker-compose ps
```

All four containers must show `Up`:

| Container      | Port | Purpose                                          |
| -------------- | ---- | ------------------------------------------------ |
| `oneka-db`     | 5432 | PostgreSQL 16 + PostGIS 3.4                      |
| `oneka-redis`  | 6379 | Celery broker + result backend                   |
| `oneka-api`    | 8000 | FastAPI application                              |
| `oneka-worker` | —    | Celery worker (ingestion + satellite + ML tasks) |

### 2. Required Environment Variables (`backend/.env`)

| Variable                | Required for          | Notes                        |
| ----------------------- | --------------------- | ---------------------------- |
| `DATABASE_URL`          | All                   | PostgreSQL connection string |
| `REDIS_URL`             | All                   | Redis connection string      |
| `PERPLEXITY_API_KEY`    | Step 2.2 enrichment   | sonar-pro model              |
| `AWS_ACCESS_KEY_ID`     | Certificates, tiles   | IAM user with S3 access      |
| `AWS_SECRET_ACCESS_KEY` | Certificates, tiles   |                              |
| `AWS_S3_BUCKET`         | Certificates, tiles   | e.g. `oneka-data`            |
| `AWS_REGION`            | Certificates, tiles   | e.g. `af-south-1`            |
| `GOOGLE_MAPS_API_KEY`   | Section 7 only        | Maps Tiles API enabled       |
| `COPERNICUS_USERNAME`   | Section 6 only        | Copernicus Open Access Hub   |
| `COPERNICUS_PASSWORD`   | Section 6 only        |                              |
| `OPENAI_API_KEY`        | COB IntelligentParser | Vision mode for BIRR PDFs    |

### 3. Baseline DB State

Record these counts before the test run so you can confirm new rows are written:

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

Expected: `{"status": "ok", "database": "connected", "redis": "connected", ...}`

---

## Section 1 — Health & Security Headers

### Test 1.1 — API Health

```bash
curl -i http://localhost:8000/api/v1/health
```

**Pass:** `200 OK`, body contains `"status": "ok"`, `"database": "connected"`, `"redis": "connected"`.

### Test 1.2 — Security Headers

Inspect the response headers from any endpoint. All six must be present:

| Header                      | Expected Value                    |
| --------------------------- | --------------------------------- |
| `X-Content-Type-Options`    | `nosniff`                         |
| `X-Frame-Options`           | `DENY`                            |
| `X-XSS-Protection`          | `1; mode=block`                   |
| `Referrer-Policy`           | `strict-origin-when-cross-origin` |
| `Content-Security-Policy`   | non-empty                         |
| `Strict-Transport-Security` | non-empty                         |

**Pass:** All 6 headers present on every response.

---

## Section 2 — Single-Project Investigation Pipeline

This is the primary end-to-end flow. Use these real-world projects (pick at least two):

| Project Name                                     | County   | Type   | Notes                                       |
| ------------------------------------------------ | -------- | ------ | ------------------------------------------- |
| `Construction of Garissa County Headquarters`    | Garissa  | OTHER  | High-profile, known stall risk              |
| `Raila Odinga International Airport Kisumu`      | Kisumu   | OTHER  | Major transport, long timeline              |
| `Talanta Sports City`                            | Nairobi  | OTHER  | Large value, contractor disputes documented |
| `Construction of Narok County Referral Hospital` | Narok    | HEALTH | eGP records likely available                |
| `Upgrading of Moyale Border Road`                | Marsabit | ROADS  | KeNHA/eGP records exist                     |

---

### Step 2.1 — Create Investigation

```bash
curl -s -X POST http://localhost:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Construction of Garissa County Headquarters",
    "user_notes": "County government headquarters in Garissa County, funded through NG-CDF and county government allocation, contractor unknown"
  }' | python3 -m json.tool
```

**Pass criteria:**

- HTTP `201 Created`
- Response contains `investigation_id` (UUID format)
- `status` = `"created"`
- `raw_project_name` matches input exactly

**Action:** Save `investigation_id` — used in every subsequent step.

---

### Step 2.2 — Perplexity Enrichment

```bash
curl -s -X POST http://localhost:8000/api/v1/investigations/{investigation_id}/enrich \
  | python3 -m json.tool
```

**Pass criteria:**

- HTTP `200 OK`
- `status` = `"enriched"`
- `context.county` = `"Garissa"` (or recognisable variant)
- `context.coordinates` = `[lat, lon]` within Kenya bounds (lat −4.7 to 4.6, lon 33.9 to 41.9)
- `context.enrichment_confidence` ≥ 0.60
- `context.search_terms` is a non-empty list
- `context.fiscal_years` is a non-empty list

**Document any `enrichment_warnings`:**

- `"Low enrichment confidence"` → patch context manually in Step 2.3
- `"County could not be determined"` → geolocation uses lower-accuracy fallback
- `"No fiscal years found"` → COB poller downloads all BIRR reports

---

### Step 2.3 — Patch Context (if needed)

If confidence < 0.70, county is wrong, or coordinates are missing:

```bash
curl -s -X PATCH http://localhost:8000/api/v1/investigations/{investigation_id}/context \
  -H "Content-Type: application/json" \
  -d '{
    "county": "Garissa",
    "coordinates": [0.4536, 42.0122],
    "fiscal_years": ["2021/2022", "2022/2023", "2023/2024"],
    "context_confirmed": true
  }' | python3 -m json.tool
```

If enrichment was accurate, confirm with minimal patch:

```bash
curl -s -X PATCH http://localhost:8000/api/v1/investigations/{investigation_id}/context \
  -H "Content-Type: application/json" \
  -d '{"context_confirmed": true}' | python3 -m json.tool
```

**Pass criteria:** `200 OK`, updated context returned with `context_confirmed: true`.

---

### Step 2.4 — Trigger Investigation Pipeline

```bash
curl -s -X POST http://localhost:8000/api/v1/investigations/{investigation_id}/scrape \
  | python3 -m json.tool
```

**Pass criteria:** `202 Accepted`. Save `task_id`.

The Celery worker now executes 5 stages:

| Stage | Status value  | What happens                                              |
| ----- | ------------- | --------------------------------------------------------- |
| 1     | `scraping`    | eGP → PPIP fallback → NCA → KMHFL → COB                   |
| 2     | `concordance` | Procurement records linked to a Project row               |
| 3     | `geolocating` | 3-tier GPS resolution                                     |
| 4     | `satellite`   | Copernicus download + NDVI/SAR analysis (if coords found) |
| 5     | `scoring`     | ML ghost probability written to Project                   |

---

### Step 2.5 — Poll for Completion

Poll every 10–15 seconds:

```bash
watch -n 10 "curl -s http://localhost:8000/api/v1/investigations/{investigation_id}/status | python3 -m json.tool"
```

**Expected progression:**

```
created → enriching → enriched → scraping → concordance → geolocating → satellite → scoring → complete
```

**At each stage, verify `stage_statuses`:**

| Key                           | Expected after scraping                            |
| ----------------------------- | -------------------------------------------------- |
| `scraping.counts.egp`         | ≥ 0 integer                                        |
| `scraping.tagged_procurement` | ≥ 1 if eGP or PPIP found records                   |
| `concordance.project_uuid`    | non-null UUID                                      |
| `geolocation.lat` / `.lon`    | non-null floats                                    |
| `geolocation.resolved`        | `true`                                             |
| `satellite.status`            | `"queued"` (coords found) or `"skipped_no_coords"` |

**If status = `"failed"`:** Check Celery worker logs:

```bash
docker-compose logs oneka-worker --tail=100
```

Document which stage failed and the exception message.

---

### Step 2.6 — Fetch Full Investigation Report

```bash
curl -s http://localhost:8000/api/v1/investigations/{investigation_id}/report \
  | python3 -m json.tool
```

**Pass criteria:**

- `project_uuid` is non-null
- `procurement_count` ≥ 1
- `project.risk_level` is one of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `project.location.latitude` is non-null
- `project.location.method` shows GPS tier used
- `project.procurement[0].source_system` is one of `eGP`, `PPIP`, `NCA`
- `project.procurement[0].contract_sum_kes` is a non-null number

**Action:** Save `project_uuid` — used in Sections 3, 4, 5, and 6.

---

## Section 3 — Project Data Endpoints

### Test 3.1 — Get Single Project

```bash
curl -s http://localhost:8000/api/v1/projects/{project_uuid} | python3 -m json.tool
```

**Pass:** `200 OK`, `geolocation_status: "geolocated"`, all core fields present.

### Test 3.2 — Unified Truth Record

```bash
curl -s http://localhost:8000/api/v1/projects/{project_uuid}/truth-record \
  | python3 -m json.tool
```

**Pass:**

- `procurement` array non-empty with `tender_number`, `contract_sum_kes`, `contractor_name`
- `location.method` documents the GPS tier: `egp_embedded_gps` | `kmhfl_fuzzy` | `ward_fallback` | `perplexity_tier0`
- `financial` array (may be empty — acceptable for new projects)

### Test 3.3 — Paginated Project List with County Filter

```bash
curl -s "http://localhost:8000/api/v1/projects?page=1&page_size=10&county=Garissa" \
  | python3 -m json.tool
```

**Pass:** New project appears in results, `total` has increased since baseline.

### Test 3.4 — GeoJSON FeatureCollection

```bash
curl -s http://localhost:8000/api/v1/projects/geojson | python3 -m json.tool
```

**Pass:**

- Valid GeoJSON `FeatureCollection`
- New project feature has `geometry.coordinates` = `[longitude, latitude]` (lon first — GeoJSON spec)
- `properties.risk_level` is populated

### Test 3.5 — GeoJSON with Risk Level Filter

```bash
curl -s "http://localhost:8000/api/v1/projects/geojson?risk_level=HIGH,CRITICAL" \
  | python3 -m json.tool
```

**Pass:** Only features with `risk_level: "HIGH"` or `"CRITICAL"` returned.

---

## Section 4 — ML Risk Scoring

### Test 4.1 — Score a Project

```bash
curl -s http://localhost:8000/api/v1/risk/score/{project_uuid} | python3 -m json.tool
```

**Pass:**

- `ghost_probability` is float between 0.0 and 1.0
- `risk_level` is one of `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `model_available: true`
- `features_used` contains 10 keys (some may be `null` without satellite data)

**If `model_available: false`**, retrain the model:

```bash
cd satellite
python scripts/run_training.py --data data/training/training_projects.csv --output models/
```

Then re-run this test.

### Test 4.2 — Risk Heat Map

```bash
curl -s http://localhost:8000/api/v1/risk/heat-map | python3 -m json.tool
```

**Pass:** GeoJSON `FeatureCollection`, `count` ≥ 1, new project appears.

### Test 4.3 — Heat Map Filtered

```bash
curl -s "http://localhost:8000/api/v1/risk/heat-map?risk_level=CRITICAL" \
  | python3 -m json.tool
```

**Pass:** Only CRITICAL-risk projects returned. If none exist, `features: []` and `count: 0` is acceptable.

---

## Section 5 — Section 106B Legal Certificate

### Test 5.1 — Check Readiness

```bash
curl -s http://localhost:8000/api/v1/certificates/{project_uuid}/status \
  | python3 -m json.tool
```

**Pass:** `200 OK`, `ready` field is present (may be `false` if no satellite data yet — proceed anyway).

### Test 5.2 — Generate and Download Certificate PDF

```bash
curl -s -o /tmp/certificate_106b.pdf \
  "http://localhost:8000/api/v1/certificates/{project_uuid}?analyst_name=John%20Kamau&analyst_title=Senior%20Infrastructure%20Analyst"
echo "Exit code: $?"
file /tmp/certificate_106b.pdf
```

**Pass:**

- Exit code 0
- `file` command reports `PDF document`
- PDF opens in a viewer
- PDF contains all 7 Section 106B(4) statutory fields:
  1. Project name and location
  2. Contracting authority (procuring entity)
  3. Contract value (KES)
  4. Physical progress assessment
  5. Financial absorption rate
  6. Satellite scene integrity hash (SHA-256, 64 characters)
  7. Analyst name, title, and generation timestamp

**If `400`:** `analyst_name` query param is missing.
**If `502`:** AWS S3 credentials not configured in `.env`.

---

## Section 6 — Satellite Tile Endpoints

> Run only if `COPERNICUS_USERNAME` / `COPERNICUS_PASSWORD` are set and the satellite
> stage in Step 2.5 showed `"status": "queued"`.

### Test 6.1 — Tile Generation Status

```bash
curl -s http://localhost:8000/api/v1/satellite/tiles-status/{project_uuid} \
  | python3 -m json.tool
```

**Pass:**

- `status: "generating"` while Celery tile task runs
- `status: "ready"` when complete, with populated `ndvi_url` and `sar_url` (presigned S3 URLs)

### Test 6.2 — Fetch a Tile

Compute z/x/y tile coordinates for the project's location using:

```
https://www.maptiler.com/google-maps-coordinates-tile-bounds-projection/
```

```bash
curl -s -o /tmp/tile.png \
  "http://localhost:8000/api/v1/satellite/tiles/{project_uuid}/ndvi/12/2456/1591"
file /tmp/tile.png
```

**Pass:** PNG image or `202 Accepted` if tiles still generating.

### Test 6.3 — Divergence Analysis

```bash
curl -s http://localhost:8000/api/v1/satellite/{project_uuid}/divergence \
  | python3 -m json.tool
```

**Pass:** Divergence status is `RED`, `YELLOW`, or `GREEN`. `absorption_gap` and `ndvi_slope` are present.

---

## Section 7 — Google Maps Proxy

> Run only if `GOOGLE_MAPS_API_KEY` is set with the Maps Tiles API enabled.

### Test 7.1 — Request Session Token

```bash
curl -s -X POST http://localhost:8000/api/v1/maps/tiles/session \
  -H "Content-Type: application/json" \
  -d '{"map_type": "roadmap", "language": "en-GB", "region": "KE"}' \
  | python3 -m json.tool
```

**Pass:** `200 OK`, `session_token` is a long string, `expiry` timestamp present.
**Rate limit:** 5 requests/minute. Wait 12 seconds between attempts.

### Test 7.2 — Proxy a Map Tile (Nairobi)

```bash
curl -s -o /tmp/map_tile.png \
  "http://localhost:8000/api/v1/maps/tiles/{session_token}/10/609/463"
file /tmp/map_tile.png
```

**Pass:** PNG image, Google logo visible. `Content-Type: image/png` or `image/jpg`.

---

## Section 8 — Bulk Ingestion Tasks

### Test 8.1 — KMHFL Cache

```bash
# Check cache exists
ls -lah data/cache/kmhfl_facilities.json 2>/dev/null || echo "MISSING"

# Trigger refresh via Python if missing
cd backend && ./venv-backend/bin/python -c "
from src.tasks.ingestion_tasks import refresh_kmhfl_task
result = refresh_kmhfl_task.delay()
print('Task ID:', result.id)
"
```

**Pass:** JSON file exists with ≥ 100 health facility entries.

### Test 8.2 — Reconcile Orphaned Procurement Records

```bash
curl -s -X POST http://localhost:8000/api/v1/projects/reconcile | python3 -m json.tool
```

**Pass:** `200 OK`, response includes `total_processed`, `linked`, `created_new`, `failed`.
Document the `failed` count and reason if > 0.

---

## Section 9 — Input Validation & Security Guards

### Test 9.1 — Project name too short (< 3 chars)

```bash
curl -s -X POST http://localhost:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -d '{"project_name": "AB"}' | python3 -m json.tool
```

**Pass:** `422 Unprocessable Entity`.

### Test 9.2 — Control character stripping

```bash
curl -s -X POST http://localhost:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -d '{"project_name": "Test\u0000Project\u001fName"}' | python3 -m json.tool
```

**Pass:** `201 Created`. Verify `raw_project_name` has control characters stripped (no `\x00` or `\x1f`).

### Test 9.3 — Invalid satellite tile coordinates

```bash
curl -s "http://localhost:8000/api/v1/satellite/tiles/00000000-0000-0000-0000-000000000000/ndvi/99/999999/999999"
```

**Pass:** `400 Bad Request` — not `500 Internal Server Error`.

### Test 9.4 — Rate limit enforcement (Maps proxy)

Send 6 POST requests to `/api/v1/maps/tiles/session` within 60 seconds.

```bash
for i in {1..6}; do
  echo "Request $i:"
  curl -s -o /dev/null -w "%{http_code}\n" -X POST \
    http://localhost:8000/api/v1/maps/tiles/session \
    -H "Content-Type: application/json" \
    -d '{"map_type": "roadmap"}'
  sleep 1
done
```

**Pass:** First 5 return `200`. The 6th returns `429 Too Many Requests`.

---

## Section 10 — Database Verification

After all tests, connect to the database directly and verify rows landed correctly.

```bash
docker-compose exec oneka-db psql -U oneka_user -d oneka_dev
```

```sql
-- 1. Investigation record
SELECT investigation_id, status, project_uuid,
       stage_statuses->>'scraping' AS scraping,
       stage_statuses->>'concordance' AS concordance,
       stage_statuses->>'geolocation' AS geolocation
FROM investigations
ORDER BY created_at DESC LIMIT 5;

-- 2. Procurement records linked to the investigation
SELECT procurement_id, source_system, tender_number,
       contract_sum_kes, contractor_name,
       delivery_latitude, delivery_longitude, gps_source
FROM procurement_records
WHERE investigation_id = '<your_investigation_id>';

-- 3. Geolocation was resolved
SELECT geolocation_id, source_system, match_method,
       match_confidence, latitude, longitude
FROM geolocation_records
WHERE project_uuid = '<your_project_uuid>'
ORDER BY match_confidence DESC;

-- 4. Satellite analyses (if Copernicus ran)
SELECT analysis_id, sensor, acquisition_date, analysis_type,
       ndvi_mean, ndvi_slope, sar_backscatter_delta
FROM satellite_analyses
WHERE project_uuid = '<your_project_uuid>';

-- 5. Risk score written back to project
SELECT project_name, county, status, risk_level,
       ghost_probability, risk_score, geolocation_status
FROM projects
WHERE project_uuid = '<your_project_uuid>';

-- 6. Financial records (may be 0 for new projects)
SELECT financial_id, fiscal_year, ministry, programme,
       budget_allocated_kes, budget_absorbed_kes, absorption_rate
FROM financial_records
WHERE project_uuid = '<your_project_uuid>';
```

---

## Pass / Fail Summary Table

| Section | Test                 | Pass Condition                                     |
| ------- | -------------------- | -------------------------------------------------- |
| 1       | Health               | `status: ok`, DB + Redis connected                 |
| 1       | Security Headers     | All 6 headers present                              |
| 2.1     | Create investigation | `201`, UUID returned                               |
| 2.2     | Enrichment           | Confidence ≥ 0.60, county + coords populated       |
| 2.4     | Trigger pipeline     | `202 Accepted`                                     |
| 2.5     | Completion           | Status reaches `scoring` or `complete`             |
| 2.6     | Report               | `procurement_count` ≥ 1, `project_uuid` non-null   |
| 3       | Truth record         | GPS tier documented, procurement records present   |
| 3       | GeoJSON              | New project in FeatureCollection, correct geometry |
| 4       | Risk score           | `ghost_probability` float, `risk_level` non-null   |
| 5       | Certificate          | PDF downloads, all 7 statutory fields present      |
| 6       | Tiles                | PNG returned or `202` if still generating          |
| 7       | Maps proxy           | Session token returned, tile PNG streams           |
| 8       | Reconcile            | No unhandled errors, `failed` count is 0           |
| 9       | Validation           | 422/400/429 on bad inputs, no 500s                 |
| 10      | DB rows              | All expected rows present in correct tables        |

---

## Known Acceptable Gaps

These are expected limitations — do not fail the test for these:

| Gap                                     | Expected Behaviour           | Notes                                              |
| --------------------------------------- | ---------------------------- | -------------------------------------------------- |
| `satellite.status: "skipped_no_coords"` | No Copernicus download       | Fires when geolocation returned ward centroid only |
| `model_available: false`                | Fallback risk score returned | Retrain model; AUC 0.56 with CSV-only data         |
| `financial_count: 0`                    | No COB BIRR match            | Normal for projects not yet in Treasury reporting  |
| `ghost_probability` low-confidence      | Score still returns          | 7 of 10 ML features are NaN without satellite data |
| Session token cached in-memory          | Single-worker only           | Redis cache needed for multi-worker production     |

---

## Celery Worker Log Reference

```bash
# Stream worker logs live
docker-compose logs -f oneka-worker

# Check a specific task result
cd backend && ./venv-backend/bin/python -c "
from src.celery_app import celery_app
result = celery_app.AsyncResult('<task_id>')
print('State:', result.state)
print('Result:', result.result)
"
```

---

_Last updated: 2026-03-10 | Relates to: `docs/07-master-implementation/completion-report.md`_
