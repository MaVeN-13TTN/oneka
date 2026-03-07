# ONEKA AI — Data Acquisition Layer

**Web scrapers and parsers that feed Kenya infrastructure procurement, financial, and geolocation data into the ONEKA AI platform.**

This module runs independently from the backend — it has its own virtual environment, async database driver, and lightweight SQLAlchemy Core table definitions.

## Architecture

```
data/
├── scrapers/              # 5 async web scrapers (bulk + targeted mode)
│   ├── base.py            # Abstract BaseScraper (fetch → save → run)
│   ├── egp.py             # e-GP Kenya — Playwright, XHR intercept
│   ├── ppip.py            # PPIP tenders.go.ke — httpx REST API
│   ├── kmhfl.py           # KMHFL health facilities — httpx paginated API
│   ├── nca.py             # NCA approved projects — Playwright HTML scrape
│   └── cob.py             # COB BIRR reports — Playwright + httpx PDF download
├── parsers/
│   ├── cob.py             # CoBParser — pdfplumber table extraction + RapidFuzz matching
│   └── intelligent_cob.py # IntelligentCoBParser — two-stage: pdfplumber + GPT-4o Vision
├── context.py             # ProjectContext dataclass — targeted scraper query scope
├── tests/                 # 116 isolated unit tests
│   ├── test_base_scraper.py     # BaseScraper run() orchestration
│   ├── test_cob_parser.py       # CoBParser table extraction + matching
│   ├── test_models.py           # SQLAlchemy Core table definitions
│   ├── test_scrapers.py         # Scraper data transformations (bulk mode)
│   ├── test_targeted_scrapers.py# Targeted mode — ctx-driven fetch for all 5 scrapers
│   └── test_intelligent_cob.py  # IntelligentCoBParser + VisionCostGuardrails
├── cache/                 # JSON caches (KMHFL facilities, COB report metadata)
├── db.py                  # Async SQLAlchemy engine (asyncpg driver)
├── models.py              # Lightweight SQLAlchemy Core table definitions
└── requirements.txt       # Python dependencies
```

## Scrapers

### e-GP Kenya (`scrapers/egp.py`)

|                   |                                                                                                             |
| ----------------- | ----------------------------------------------------------------------------------------------------------- |
| **Source**        | https://egpkenya.go.ke/tender                                                                               |
| **Method**        | Playwright headless Chromium — intercepts XHR JSON responses from `/api/xcommon/get-ten-tab-tender-details` |
| **Data**          | Closed Works tenders: tender number, title, procuring entity, contract details                              |
| **GPS**           | Extracts delivery location coordinates from GeoJSON `geometry.coordinates`                                  |
| **Quality**       | Manual pin = 90, auto-geocoded = 70                                                                         |
| **Output**        | Upserts to `procurement_records` + `geolocation_records`                                                    |
| **Schedule**      | Daily at 02:00 EAT via Celery beat                                                                          |
| **Targeted mode** | `fetch(ctx=ctx)` filters by `ctx.search_terms` + `ctx.procuring_entity`                                     |

### PPIP (`scrapers/ppip.py`)

|                   |                                                                                  |
| ----------------- | -------------------------------------------------------------------------------- |
| **Source**        | https://tenders.go.ke/api/active-tenders                                         |
| **Method**        | Direct HTTP GET via httpx (JSON API)                                             |
| **Data**          | Active tenders: tender number, title, procuring entity, contract sum, award date |
| **Output**        | Upserts to `procurement_records`                                                 |
| **Schedule**      | Manual trigger only (historical one-time import)                                 |
| **Targeted mode** | `fetch(ctx=ctx)` filters by `ctx.search_terms` + `ctx.county`                    |

### KMHFL (`scrapers/kmhfl.py`)

|                   |                                                                                                           |
| ----------------- | --------------------------------------------------------------------------------------------------------- |
| **Source**        | https://api.kmhfr.health.go.ke/api/facilities/facilities/                                                 |
| **Method**        | Paginated HTTP GET via httpx (page_size=100, follows `next` URLs)                                         |
| **Data**          | All Kenya health facilities with names, codes, GPS coordinates                                            |
| **Output**        | JSON cache at `cache/kmhfl_facilities.json` (consumed by backend GeolocationService Tier 2 fuzzy matcher) |
| **Schedule**      | 1st Sunday of month at 03:00 EAT via Celery beat                                                          |
| **Targeted mode** | `fetch(ctx=ctx)` queries facilities by `ctx.county` + facility name keywords                              |

### NCA (`scrapers/nca.py`)

|                   |                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------- |
| **Source**        | https://www.nca.go.ke/approved-projects                                               |
| **Method**        | Playwright headless Chromium — HTML table scraping with 15 heuristic search terms     |
| **Data**          | Approved projects: project ID, name, developer, contractor, architect, engineer, type |
| **Output**        | Upserts to `procurement_records` (tender_number namespaced as `NCA-{id}`)             |
| **Schedule**      | 15th of month at 03:30 EAT via Celery beat                                            |
| **Targeted mode** | `fetch(ctx=ctx)` uses `ctx.canonical_name + ctx.aliases` as search terms              |

### COB BIRR Reports (`scrapers/cob.py`)

|                   |                                                                                     |
| ----------------- | ----------------------------------------------------------------------------------- |
| **Source**        | https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/ |
| **Method**        | Playwright for link discovery + httpx for PDF download                              |
| **Data**          | County budget implementation review PDFs (quarterly/consolidated)                   |
| **Output**        | Raw PDFs to `data/raw/cob/` + metadata cache to `cache/cob_reports.json`            |
| **Schedule**      | Manual trigger — PDF parsing handled by backend `FinancialService`                  |
| **Targeted mode** | `process(ctx=ctx)` downloads PDFs matching `ctx.fiscal_years`                       |

## Parsers

### Standard COB PDF Parser (`parsers/cob.py`)

Extracts financial records from Controller of Budget BIRR PDF reports:

1. Opens PDF with `pdfplumber`, extracts tables from first 50 pages
2. Identifies the expenditure table by matching column headers (Vote, Approved Budget, Expenditure, Absorption)
3. Uses RapidFuzz `token_set_ratio` (cutoff: 60) to fuzzy-match project names against Vote column values
4. Extracts: allocated budget, absorbed budget, absorption rate per matched row
5. Returns dicts keyed to `FinancialRecord` column names for backend ingestion

Used by the bulk `ingest_cob_report_task` Celery task.

### IntelligentCoBParser (`parsers/intelligent_cob.py`)

Two-stage COB BIRR PDF extraction using GPT-4o Vision, designed for the single-project investigation pipeline:

**Stage 1 — Candidate page selection (pdfplumber, no API cost)**

- Scans every page for keywords derived from the `ProjectContext` (canonical name, aliases, procuring entity, vote head)
- Narrows a 300-page PDF to 5–15 candidate pages

**Stage 2 — GPT-4o Vision extraction (OpenAI API)**

- Renders each candidate page to PNG at configurable DPI (default 200)
- Sends rendered image + structured prompt to GPT-4o Vision
- Extracts: `approved_budget_kes`, `released_kes`, `absorbed_kes`, `absorption_rate_pct`, `reporting_period`, `page_label`
- Returns JSON only — no hallucination of non-project data

**Vision cost guardrail:**

- Tracks `total_cost_usd` per extraction run (at $5/1M input + $15/1M output tokens, GPT-4o pricing)
- Stops before issuing the next Vision request when `total_cost_usd >= cost_limit_usd`
- Default cap: `$5.00` per investigation (configurable via `VISION_COST_LIMIT_USD`)
- `pages_processed` and `total_cost_usd` are accessible after `extract()` completes

Used by `FinancialService.ingest_cob_report_intelligent()` (backend), which is called from `investigate_project_task` Stage 2.

## Database Layer

### `db.py` — Async Engine

- Reads `DATABASE_URL` from `backend/.env` via python-dotenv
- Converts `postgresql://` to `postgresql+asyncpg://` for the asyncpg driver
- Default: `postgresql://oneka_user:password@localhost:5432/oneka_dev`
- Exports `AsyncSessionLocal` (async sessionmaker)

### `models.py` — Core Tables

Lightweight `sqlalchemy.Table` objects (not full ORM classes) used for INSERT/UPSERT only:

- **`procurement_records`** — 22 columns: tender_number (unique), tender_title, procuring_entity, contract_sum_kes, award_date, GPS coordinates, contractor details
- **`geolocation_records`** — 12 columns: latitude, longitude, facility_code, match_confidence, match_method

Column names and types stay in sync with the canonical backend Alembic migrations.

## Data Flow

```
e-GP Kenya ──────┐
PPIP tenders.go.ke ──┤──→ procurement_records (PostgreSQL)
NCA nca.go.ke ───┘         │
                           ├──→ geolocation_records (PostgreSQL)
e-GP GPS extraction ───────┘

KMHFL MoH API ──────────→ cache/kmhfl_facilities.json
                              └──→ Backend GeolocationService Tier 2 fuzzy match

COB cob.go.ke ──→ raw/cob/*.pdf ──→ CoBParser ──→ Backend FinancialService
                  cache/cob_reports.json    │          └──→ financial_records
                                            └──→ IntelligentCoBParser + GPT-4o Vision
                                                    └──→ investigation financial_records

── Single-project investigation pipeline ──────────────────────────────────────
investigate_project_task (backend Celery)
  │
  └─→ EGPScraper.fetch(ctx=ctx)   ─→ procurement_records (tagged investigation_id)
  └─→ NCAScraper.fetch(ctx=ctx)   ─→ procurement_records
  └─→ PPIPScraper.fetch(ctx=ctx)  ─→ procurement_records
  └─→ KMHFLScraper.fetch(ctx=ctx) ─→ cache/kmhfl_facilities.json
  └─→ CoBPoller.process(ctx=ctx)  ─→ IntelligentCoBParser ─→ financial_records
```

## Setup

```bash
cd data/

# Create virtual environment
uv venv venv-data --python 3.12

# Install dependencies
uv pip install -r requirements.txt --python venv-data/bin/python

# Install Playwright Chromium (required for eGP, NCA, COB scrapers)
venv-data/bin/python -m playwright install chromium

# Install system dependencies for IntelligentCoBParser (pdf2image)
sudo apt install poppler-utils   # provides pdftoppm used by pdf2image
```

The data module reads `DATABASE_URL` from `backend/.env` — no separate data `.env` is required unless you need to override it. See [data/.env.example](data/.env.example).

## Running Scrapers

Each scraper can be run standalone or via Celery tasks from the backend:

```bash
cd /path/to/oneka

# Run individual scrapers
data/venv-data/bin/python -m data.scrapers.egp
data/venv-data/bin/python -m data.scrapers.ppip
data/venv-data/bin/python -m data.scrapers.kmhfl
data/venv-data/bin/python -m data.scrapers.nca
data/venv-data/bin/python -m data.scrapers.cob
```

Via Celery (from backend):

```bash
cd backend
celery -A src.celery_app worker --loglevel=info
# Tasks: scrape_egp_task, import_ppip_historical_task, refresh_kmhfl_task, scrape_nca_task
```

## Testing

```bash
cd data/

# Run full test suite (116 tests, isolated — no database or network required)
../data/venv-data/bin/python -m pytest tests/ -v --tb=short

# Run only targeted scraper tests
../data/venv-data/bin/python -m pytest tests/test_targeted_scrapers.py -v

# Run only IntelligentCoBParser tests
../data/venv-data/bin/python -m pytest tests/test_intelligent_cob.py -v
```

**Test status:** 116 passed

### Test Files

| File                              | Tests | Covers                                                                                                                                                                                     |
| --------------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `tests/test_base_scraper.py`      | 5     | `BaseScraper.run()` orchestration — success, empty fetch, None fetch, exception handling, results attribute                                                                                |
| `tests/test_cob_parser.py`        | 12    | `CoBParser`: table extraction (mocked pdfplumber), expenditure table detection, financial record extraction with RapidFuzz matching, `_to_decimal` formatting, absorption rate computation |
| `tests/test_models.py`            | 12    | SQLAlchemy Core table definitions — table names, primary keys, unique constraints, nullable flags, column presence, type lengths, metadata contents                                        |
| `tests/test_scrapers.py`          | 16    | Scraper data transformations — EGP GPS quality/GeoJSON extraction, PPIP date parsing/field fallbacks, NCA ID namespacing/row validation, KMHFL JSON cache, COB poller URL deduplication    |
| `tests/test_targeted_scrapers.py` | 29    | Targeted mode — `ctx`-driven `fetch()` for all 5 scrapers: keyword injection, county/fiscal-year filtering, context-aware COB PDF discovery, KMHFL targeted cache                          |
| `tests/test_intelligent_cob.py`   | 16    | `IntelligentCoBParser`: Stage 1 keyword selection, Stage 2 Vision API (mock), JSON extraction, match=false handling, multi-page aggregation                                                |
| `tests/test_intelligent_cob.py`   | 8     | `TestVisionCostGuardrails`: cost accumulation per token type, limit enforcement, zero-limit block, `None`-limit uncapped operation, missing usage graceful handling                        |

All tests run in isolation using mocks and stubs — no PostgreSQL, Redis, Playwright, or network access required.

## Dependencies

| Category        | Packages                                                           |
| --------------- | ------------------------------------------------------------------ |
| HTTP & Scraping | httpx 0.26.0, beautifulsoup4 4.12.3, lxml 5.1.0, playwright 1.41.2 |
| PDF Parsing     | pdfplumber 0.10.3, pdf2image 1.17.0 (+ poppler-utils system dep)   |
| AI / Vision     | openai 1.12.0 (GPT-4o Vision for IntelligentCoBParser)             |
| Database        | sqlalchemy 2.0.25, asyncpg 0.29.0, alembic 1.13.1                  |
| Data Processing | pandas 2.1.4                                                       |
| NLP & Matching  | spacy 3.7.2, rapidfuzz 3.6.1                                       |
| Utilities       | python-dotenv 1.0.0                                                |
| Dev             | pytest 7.4.4, pytest-cov, pytest-asyncio, black, flake8, mypy      |

## Design Decisions

- **Separate venv** — Keeps Playwright/pdfplumber/asyncpg out of the backend's FastAPI dependency tree
- **SQLAlchemy Core (not ORM)** — Minimal insert/upsert capability without importing the full backend Pydantic stack
- **Upsert deduplication** — All scrapers use `ON CONFLICT DO NOTHING` or `DO UPDATE` on `tender_number`, making re-runs idempotent
- **Two scraping strategies** — REST APIs (PPIP, KMHFL) use httpx; JavaScript-heavy portals (eGP, NCA, COB) use Playwright
- **Cache-first for non-DB data** — KMHFL facilities and COB metadata stored as JSON, consumed downstream by backend services

---

**ONEKA AI** — _Making the Invisible, Actionable_
