# ONEKA AI — Backend API

**Kenya's First Autonomous Infrastructure Auditing Platform**

FastAPI backend that combines procurement data, financial records, satellite imagery, and ML risk scoring to detect ghost infrastructure projects.

## Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.12 |
| FastAPI | 0.109.0 |
| PostgreSQL + PostGIS | 15+ |
| SQLAlchemy | 2.0.25 |
| Alembic | 1.13.1 |
| Celery + Redis | 5.3.6 |
| scikit-learn | 1.4.0 |
| WeasyPrint | 61.0+ |

## Project Structure

```
backend/
├── alembic/                  # Database migrations
│   └── versions/             # 4 migration files (initial → satellite divergence)
├── ken_adm_geojson/          # Kenya admin boundary GeoJSON (L0–L2 + centroids)
├── scripts/
│   ├── seed_training_projects.py   # Seed 30 training projects into DB
│   └── load_ward_boundaries.py     # Load admin boundaries from GeoJSON
├── src/
│   ├── middleware/
│   │   └── security_headers.py     # CSP, HSTS, X-Frame-Options
│   ├── models/               # 6 SQLAlchemy ORM models
│   │   ├── project.py        # projects — master registry (UUID PK)
│   │   ├── procurement.py    # procurement_records — tender data
│   │   ├── financial.py      # financial_records — budget/absorption
│   │   ├── geolocation.py    # geolocation_records — GPS + PostGIS POINT
│   │   ├── satellite.py      # satellite_analyses — NDVI/SAR metrics
│   │   └── admin_boundary.py # admin_boundaries — ward/county polygons
│   ├── routers/              # 9 API routers (34 endpoints)
│   │   ├── health.py         # Health checks & system status
│   │   ├── procurement.py    # CRUD + scraping triggers
│   │   ├── projects.py       # Project listing, GeoJSON, reconciliation
│   │   ├── financial.py      # Budget records & absorption analysis
│   │   ├── geolocation.py    # 3-tier GPS resolution
│   │   ├── satellite.py      # Satellite analysis & tiles
│   │   ├── risk.py           # ML ghost probability scoring
│   │   ├── maps.py           # Google Maps tile proxy
│   │   └── certificates.py   # Section 106B legal PDF generation
│   ├── schemas/              # Pydantic request/response models
│   ├── services/             # Business logic layer (11 services)
│   ├── tasks/                # Celery background tasks (4 modules)
│   ├── main.py               # FastAPI application entry point
│   ├── celery_app.py         # Celery configuration + beat schedule
│   ├── config.py             # Pydantic settings (reads .env)
│   ├── database.py           # SQLAlchemy engine + session factory
│   └── rate_limit.py         # Shared slowapi limiter instance
├── templates/
│   └── certificate_106b.html # Jinja2 template for legal PDFs
├── tests/                    # 281 tests, 80% coverage
├── Dockerfile                # Production image (python:3.12-slim)
├── alembic.ini               # Migration configuration
├── requirements.txt          # Python dependencies
└── setup_database.sql        # PostgreSQL/PostGIS initialization
```

## Quick Start

```bash
# 1. Database setup (as postgres superuser)
sudo -u postgres psql -f setup_database.sql

# 2. Create virtual environment
uv venv venv-backend --python 3.12

# 3. Install dependencies
uv pip install -r requirements.txt --python venv-backend/bin/python

# 4. Download spaCy model (for geolocation NER)
venv-backend/bin/python -m spacy download en_core_web_sm

# 5. Configure environment
cp .env.example .env   # then edit with your credentials

# 6. Run migrations
venv-backend/bin/alembic upgrade head

# 7. Seed training data (optional)
PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev \
  venv-backend/bin/python scripts/seed_training_projects.py

# 8. Start API server
venv-backend/bin/uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs | http://localhost:8000/redoc

## API Endpoints

### Health & Status

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Basic health check |
| `GET` | `/api/v1/health/db` | Database + PostGIS check |
| `GET` | `/api/v1/status` | System status with record counts |
| `GET` | `/api/v1/ping` | Minimal ping for load balancers |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/projects` | Paginated list (filter: county, risk_level, status, project_type) |
| `GET` | `/api/v1/projects/geojson` | GeoJSON FeatureCollection (optional `?risk_level=HIGH,CRITICAL`) |
| `POST` | `/api/v1/projects/reconcile` | Batch-link procurement records via fuzzy matching |
| `GET` | `/api/v1/projects/{uuid}` | Single project by UUID |
| `GET` | `/api/v1/projects/{uuid}/truth-record` | Unified project card with all linked data |

### Procurement

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/procurement` | Create procurement record |
| `GET` | `/api/v1/procurement` | List records (paginated, filterable, sortable) |
| `GET` | `/api/v1/procurement/search` | Search by tender number |
| `POST` | `/api/v1/procurement/scrape` | Trigger PPIP scraper |
| `GET` | `/api/v1/procurement/stats/summary` | Statistics summary |
| `GET` | `/api/v1/procurement/{id}` | Get single record |
| `PUT` | `/api/v1/procurement/{id}` | Update record |
| `DELETE` | `/api/v1/procurement/{id}` | Delete record |

### Financial

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/financial/{uuid}` | All financial records for a project |
| `GET` | `/api/v1/financial/{uuid}/absorption` | Absorption gap analysis |

### Geolocation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/geolocation/resolve` | Run 3-tier GPS resolution |
| `GET` | `/api/v1/geolocation/coverage` | Tier breakdown statistics |

### Satellite & Divergence

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/satellite/analyse/{uuid}` | Queue satellite analysis (Celery) |
| `GET` | `/api/v1/satellite/status/{task_id}` | Poll task status |
| `GET` | `/api/v1/satellite/tiles/{uuid}/ndvi/{z}/{x}/{y}` | NDVI tile (redirect or 202) |
| `GET` | `/api/v1/satellite/tiles-status/{uuid}` | Tile generation status + URLs |
| `GET` | `/api/v1/projects/{uuid}/divergence` | Financial vs physical divergence |
| `GET` | `/api/v1/dashboard/heat-map` | All projects for heat-map |

### Risk Scoring

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/risk/score/{uuid}` | ML ghost probability + feature breakdown |
| `GET` | `/api/v1/risk/heat-map` | GeoJSON with risk levels |

### Maps

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/maps/tiles/session` | Google Maps session token |
| `GET` | `/api/v1/maps/tiles/{token}/{z}/{x}/{y}` | Tile proxy (streaming) |

### Certificates

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/certificates/{uuid}` | Generate Section 106B(4) PDF |
| `GET` | `/api/v1/certificates/{uuid}/status` | Check certificate readiness |

## Database Schema

Six tables with PostGIS geometry columns:

| Table | Description |
|-------|-------------|
| `projects` | Master registry — UUID PK, risk level, ghost probability |
| `procurement_records` | Tender data from eGP/PPIP/NCA — contract values, GPS, contractor info |
| `financial_records` | Budget allocation/absorption from COB BIRR reports |
| `geolocation_records` | 3-tier GPS coordinates with PostGIS POINT geometry |
| `satellite_analyses` | NDVI/SAR metrics, temporal slopes, divergence scores |
| `admin_boundaries` | Kenya admin polygons with PostGIS MULTIPOLYGON geometry |

Migrations are in `alembic/versions/`. Run `alembic upgrade head` to initialize.

## Services

| Service | Purpose |
|---------|---------|
| `ProcurementService` | CRUD, scraping, deduplication, S3 document management |
| `FinancialService` | COB PDF ingestion, absorption gap calculation |
| `ConcordanceService` | Entity resolution via RapidFuzz fuzzy matching (threshold >= 85) |
| `GeolocationService` | 3-tier GPS: eGP embedded → KMHFL fuzzy match → ward centroid fallback |
| `SatelliteService` | Queue Celery analysis, persist NDVI/SAR results, compute temporal slopes |
| `DivergenceService` | Financial vs physical progress divergence scoring |
| `RiskScoringService` | RandomForest ghost probability inference (10-feature vector) |
| `TileService` | XYZ tile generation orchestration, S3 upload, presigned URLs |
| `CertificateService` | Section 106B(4) legal PDF via Jinja2 + WeasyPrint |
| `S3StorageService` | AWS S3 upload/download, presigned URLs (capped at 3600s), SHA-256 |

## Celery Background Tasks

**Broker:** Redis | **Timezone:** Africa/Nairobi

### Beat Schedule (automatic)

| Task | Schedule | Description |
|------|----------|-------------|
| `scrape_egp_task` | Daily 02:00 EAT | eGP Works tenders + GPS extraction |
| `refresh_kmhfl_task` | 1st Sunday/month 03:00 | KMHFL facility cache refresh |
| `scrape_nca_task` | 15th of month 03:30 | NCA approved projects |
| `batch_score_task` | Sunday 04:00 | Weekly ML re-scoring of all ONGOING projects |

### On-demand Tasks

| Task | Trigger | Description |
|------|---------|-------------|
| `import_ppip_historical_task` | Manual | One-time historical PPIP import |
| `ingest_cob_report_task` | Manual | Parse COB BIRR PDF → financial records |
| `analyse_project_task` | POST /satellite/analyse | Full satellite pipeline + ML scoring |
| `generate_project_tiles_task` | GET /satellite/tiles | XYZ tile pyramid → S3 |

### Start Workers

```bash
# Worker (4 concurrent tasks)
celery -A src.celery_app worker --loglevel=info --concurrency=4

# Beat scheduler (periodic tasks)
celery -A src.celery_app beat --loglevel=info
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | **(required)** | PostgreSQL connection string |
| `DATABASE_TEST_URL` | — | Test database URL |
| `DEBUG` | `False` | Enable debug mode |
| `ENVIRONMENT` | `development` | Environment name |
| `SECRET_KEY` | — | JWT secret key |
| `AWS_ACCESS_KEY_ID` | — | AWS credentials for S3 |
| `AWS_SECRET_ACCESS_KEY` | — | AWS credentials for S3 |
| `AWS_S3_BUCKET` | — | S3 bucket name |
| `COPERNICUS_USERNAME` | — | ESA Copernicus credentials |
| `COPERNICUS_PASSWORD` | — | ESA Copernicus credentials |
| `GOOGLE_MAPS_API_KEY` | — | Google Maps API key (server-side) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for Celery |
| `ML_MODEL_PATH` | `satellite/models/ghost_detector_v1.pkl` | Trained model path |

## Security

- **CSP headers** on all responses (relaxed for /docs and /redoc)
- **HSTS**, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- **Rate limiting** via slowapi (maps 5/min session, satellite 10/min, reconcile 3/min)
- **Input sanitization** — control char stripping, whitespace collapse, length truncation
- **CORS** restricted to localhost:3000 (dev) and oneka.ai (prod)
- **Presigned URLs** capped at 3600s
- **Google API key** never exposed to frontend (server-side proxy only)

## Testing

```bash
cd backend

# Run all tests (281 pass, 80% coverage)
./venv-backend/bin/pytest tests/ -v --tb=short

# Run a specific test file
./venv-backend/bin/pytest tests/test_phase4.py -v

# Coverage report
./venv-backend/bin/pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

Test database: `oneka_test` — created by `setup_database.sql`, tables auto-created/dropped per session.

## Docker

```bash
# Build image
docker build -t oneka-backend .

# Full stack via docker-compose (from repo root)
docker-compose up -d    # starts postgres, redis, api, worker
docker-compose ps       # verify all healthy
```

## Documentation

- [Database Setup](docs/database-setup-and-configuration.md)

---

**ONEKA AI** — *Making the Invisible, Actionable*
