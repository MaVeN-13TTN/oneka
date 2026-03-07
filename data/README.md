# ONEKA AI — Data Acquisition Layer

**Web scrapers and parsers that feed Kenya infrastructure procurement, financial, and geolocation data into the ONEKA AI platform.**

This module runs independently from the backend — it has its own virtual environment, async database driver, and lightweight SQLAlchemy Core table definitions.

## Architecture

```
data/
├── scrapers/              # 5 async web scrapers
│   ├── base.py            # Abstract BaseScraper (fetch → save → run)
│   ├── egp.py             # e-GP Kenya — Playwright, XHR intercept
│   ├── ppip.py            # PPIP tenders.go.ke — httpx REST API
│   ├── kmhfl.py           # KMHFL health facilities — httpx paginated API
│   ├── nca.py             # NCA approved projects — Playwright HTML scrape
│   └── cob.py             # COB BIRR reports — Playwright + httpx PDF download
├── parsers/
│   └── cob.py             # CoBParser — pdfplumber table extraction + RapidFuzz matching
├── tests/                 # 45 isolated unit tests
│   ├── test_base_scraper.py   # BaseScraper run() orchestration
│   ├── test_cob_parser.py     # CoBParser table extraction + matching
│   ├── test_models.py         # SQLAlchemy Core table definitions
│   └── test_scrapers.py       # Scraper data transformations (EGP, PPIP, NCA, KMHFL, COB)
├── cache/                 # JSON caches (KMHFL facilities, COB report metadata)
├── db.py                  # Async SQLAlchemy engine (asyncpg driver)
├── models.py              # Lightweight SQLAlchemy Core table definitions
└── requirements.txt       # Python dependencies
```

## Scrapers

### e-GP Kenya (`scrapers/egp.py`)

| | |
|---|---|
| **Source** | https://egpkenya.go.ke/tender |
| **Method** | Playwright headless Chromium — intercepts XHR JSON responses from `/api/xcommon/get-ten-tab-tender-details` |
| **Data** | Closed Works tenders: tender number, title, procuring entity, contract details |
| **GPS** | Extracts delivery location coordinates from GeoJSON `geometry.coordinates` |
| **Quality** | Manual pin = 90, auto-geocoded = 70 |
| **Output** | Upserts to `procurement_records` + `geolocation_records` |
| **Schedule** | Daily at 02:00 EAT via Celery beat |

### PPIP (`scrapers/ppip.py`)

| | |
|---|---|
| **Source** | https://tenders.go.ke/api/active-tenders |
| **Method** | Direct HTTP GET via httpx (JSON API) |
| **Data** | Active tenders: tender number, title, procuring entity, contract sum, award date |
| **Output** | Upserts to `procurement_records` |
| **Schedule** | Manual trigger only (historical one-time import) |

### KMHFL (`scrapers/kmhfl.py`)

| | |
|---|---|
| **Source** | https://api.kmhfr.health.go.ke/api/facilities/facilities/ |
| **Method** | Paginated HTTP GET via httpx (page_size=100, follows `next` URLs) |
| **Data** | All Kenya health facilities with names, codes, GPS coordinates |
| **Output** | JSON cache at `cache/kmhfl_facilities.json` (consumed by backend GeolocationService Tier 2 fuzzy matcher) |
| **Schedule** | 1st Sunday of month at 03:00 EAT via Celery beat |

### NCA (`scrapers/nca.py`)

| | |
|---|---|
| **Source** | https://www.nca.go.ke/approved-projects |
| **Method** | Playwright headless Chromium — HTML table scraping with 15 heuristic search terms |
| **Data** | Approved projects: project ID, name, developer, contractor, architect, engineer, type |
| **Output** | Upserts to `procurement_records` (tender_number namespaced as `NCA-{id}`) |
| **Schedule** | 15th of month at 03:30 EAT via Celery beat |

### COB BIRR Reports (`scrapers/cob.py`)

| | |
|---|---|
| **Source** | https://cob.go.ke/reports/consolidated-county-budget-implementation-review-reports/ |
| **Method** | Playwright for link discovery + httpx for PDF download |
| **Data** | County budget implementation review PDFs (quarterly/consolidated) |
| **Output** | Raw PDFs to `data/raw/cob/` + metadata cache to `cache/cob_reports.json` |
| **Schedule** | Manual trigger — PDF parsing handled by backend `FinancialService` |

## Parser

### COB PDF Parser (`parsers/cob.py`)

Extracts financial records from Controller of Budget BIRR PDF reports:

1. Opens PDF with `pdfplumber`, extracts tables from first 50 pages
2. Identifies the expenditure table by matching column headers (Vote, Approved Budget, Expenditure, Absorption)
3. Uses RapidFuzz `token_set_ratio` (cutoff: 60) to fuzzy-match project names against Vote column values
4. Extracts: allocated budget, absorbed budget, absorption rate per matched row
5. Returns dicts keyed to `FinancialRecord` column names for backend ingestion

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
                  cache/cob_reports.json              └──→ financial_records
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
```

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

# Run full test suite (45 tests, isolated — no database or network required)
../data/venv-data/bin/python -m pytest tests/ -v --tb=short
```

**Test status:** 45 passed

### Test Files

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_base_scraper.py` | 5 | `BaseScraper.run()` orchestration — success, empty fetch, None fetch, exception handling, results attribute |
| `tests/test_cob_parser.py` | 12 | `CoBParser`: table extraction (mocked pdfplumber), expenditure table detection, financial record extraction with RapidFuzz matching, `_to_decimal` formatting, absorption rate computation |
| `tests/test_models.py` | 12 | SQLAlchemy Core table definitions — table names, primary keys, unique constraints, nullable flags, column presence, type lengths, metadata contents |
| `tests/test_scrapers.py` | 16 | Scraper data transformations — EGP GPS quality/GeoJSON extraction, PPIP date parsing/field fallbacks, NCA ID namespacing/row validation, KMHFL JSON cache, COB poller URL deduplication |

All tests run in isolation using mocks and stubs — no PostgreSQL, Redis, Playwright, or network access required.

## Dependencies

| Category | Packages |
|----------|----------|
| HTTP & Scraping | httpx 0.26.0, beautifulsoup4 4.12.3, lxml 5.1.0, playwright 1.41.2 |
| PDF Parsing | pdfplumber 0.10.3 |
| Database | sqlalchemy 2.0.25, asyncpg 0.29.0, alembic 1.13.1 |
| Data Processing | pandas 2.1.4 |
| NLP & Matching | spacy 3.7.2, rapidfuzz 3.6.1 |
| Utilities | python-dotenv 1.0.0 |
| Dev | pytest 7.4.4, pytest-cov, pytest-asyncio, black, flake8, mypy |

## Design Decisions

- **Separate venv** — Keeps Playwright/pdfplumber/asyncpg out of the backend's FastAPI dependency tree
- **SQLAlchemy Core (not ORM)** — Minimal insert/upsert capability without importing the full backend Pydantic stack
- **Upsert deduplication** — All scrapers use `ON CONFLICT DO NOTHING` or `DO UPDATE` on `tender_number`, making re-runs idempotent
- **Two scraping strategies** — REST APIs (PPIP, KMHFL) use httpx; JavaScript-heavy portals (eGP, NCA, COB) use Playwright
- **Cache-first for non-DB data** — KMHFL facilities and COB metadata stored as JSON, consumed downstream by backend services

---

**ONEKA AI** — *Making the Invisible, Actionable*
