# ONEKA AI — Setup & Running Guide

**Platform:** Kenya Autonomous Infrastructure Auditing System
**Stack:** FastAPI + Celery + PostgreSQL/PostGIS + Redis + Sentinel satellite processing + scikit-learn ML

---

## Prerequisites

| Requirement       | Version | Notes                                      |
| ----------------- | ------- | ------------------------------------------ |
| Python            | 3.12+   | All three modules use 3.12                 |
| PostgreSQL        | 15+     | With PostGIS 3.4 extension                 |
| Redis             | 7+      | Celery broker + result backend             |
| uv                | latest  | Python package manager (`pip install uv`)  |
| Docker (optional) | 24+     | Alternative to manual Postgres/Redis setup |
| GDAL              | 3.8+    | Required for satellite raster processing   |
| SNAP              | 9+      | Only needed for SAR processing (optional)  |

---

## 1. Infrastructure Setup

### Option A: Docker (recommended for Postgres + Redis)

```bash
# Start only the infrastructure services
docker-compose up -d postgres redis

# Verify they are healthy
docker-compose ps
# Both should show "healthy"
```

This starts:

- **PostgreSQL 16 + PostGIS 3.4** on `localhost:5432` (user: `oneka_user`, password: `password`)
- **Redis 7** on `localhost:6379`

The `setup_database.sql` script runs automatically on first start, creating `oneka_dev`, `oneka_test` databases with PostGIS enabled.

### Option B: Manual (native Postgres + Redis)

```bash
# Install PostgreSQL + PostGIS (Ubuntu/Debian)
sudo apt install postgresql-16 postgresql-16-postgis-3 redis-server

# Create databases and user
sudo -u postgres psql -f backend/setup_database.sql

# Start Redis
sudo systemctl start redis-server
```

---

## 2. Backend Setup

```bash
cd backend

# Create virtual environment
uv venv venv-backend --python 3.12

# Activate
source venv-backend/bin/activate

# Install all dependencies
uv pip install -r requirements.txt

# Download spaCy NLP model (required for Tier 2 geolocation)
python -m spacy download en_core_web_sm
```

### Environment Configuration

```bash
# Copy the example env file
cp .env.example .env

# Edit with your actual credentials
nano .env
```

Key settings to configure:

| Variable                | Description                                | Required              |
| ----------------------- | ------------------------------------------ | --------------------- |
| `DATABASE_URL`          | PostgreSQL connection string               | Yes                   |
| `DATABASE_TEST_URL`     | Test database connection string            | For testing           |
| `REDIS_URL`             | Redis connection string                    | Yes (for Celery)      |
| `AWS_ACCESS_KEY_ID`     | AWS credentials for S3                     | For PDF/tile storage  |
| `AWS_SECRET_ACCESS_KEY` | AWS secret                                 | For PDF/tile storage  |
| `AWS_S3_BUCKET`         | S3 bucket name                             | For PDF/tile storage  |
| `COPERNICUS_USERNAME`   | Copernicus Data Space login                | For satellite imagery |
| `COPERNICUS_PASSWORD`   | Copernicus password                        | For satellite imagery |
| `GOOGLE_MAPS_API_KEY`   | Google Maps Tiles API key                  | For map tile proxy    |
| `SECRET_KEY`            | Application secret (change in production!) | Yes                   |

---

## 3. Database Initialization

If not using Docker's auto-initialization:

```bash
cd backend

# The app creates tables via SQLAlchemy on first connection.
# Alternatively, if you have Alembic migrations:
# source venv-backend/bin/activate
# alembic upgrade head

# Or let the app create tables on startup — SQLAlchemy Base.metadata.create_all
# is called by the test fixtures and can be triggered manually:
python -c "from src.database import init_db; init_db()"
```

---

## 4. Running the Backend

### API Server (development)

```bash
cd backend
source venv-backend/bin/activate

# Start FastAPI with hot-reload
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:

- **API root:** http://localhost:8000
- **Interactive docs (Swagger):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/api/v1/health
- **System status:** http://localhost:8000/api/v1/status

### Celery Worker

In a separate terminal:

```bash
cd backend
source venv-backend/bin/activate

# Start the Celery worker
celery -A src.celery_app worker --loglevel=info --concurrency=4
```

### Celery Beat (periodic task scheduler)

In a third terminal (optional — for scheduled scraping/scoring):

```bash
cd backend
source venv-backend/bin/activate

# Start the beat scheduler
celery -A src.celery_app beat --loglevel=info
```

**Scheduled tasks:**
| Task | Schedule | Description |
|---|---|---|
| `scrape-egp-daily` | Daily at 02:00 EAT | Scrape Kenya e-GP procurement portal |
| `refresh-kmhfl-monthly` | 1st Sunday monthly at 03:00 EAT | Refresh health facility registry cache |
| `batch-score-weekly` | Sundays at 04:00 EAT | Re-score all active projects with ML model |

---

## 5. Running Tests

### Backend Tests (281 tests — requires PostgreSQL)

```bash
cd backend
source venv-backend/bin/activate

# Ensure the test database exists (see step 1)
# Tests use: postgresql://oneka_user:password@localhost:5432/oneka_test

# Run full test suite with coverage
./venv-backend/bin/pytest tests/ -v --tb=short

# Run specific test file
./venv-backend/bin/pytest tests/test_phase4.py -v

# Run tests by marker
./venv-backend/bin/pytest tests/ -m "unit" -v

# Run with coverage report only
./venv-backend/bin/pytest tests/ --cov=src --cov-report=term-missing
```

**Current test status:** 281 passed, 1 skipped, 80% coverage

### Data Acquisition Tests (45 tests — fully isolated)

```bash
cd data

# Run full test suite (no database, network, or Playwright required)
venv-data/bin/python -m pytest tests/ -v --tb=short
```

**Current test status:** 45 passed

Tests cover: BaseScraper orchestration, CoBParser PDF table extraction, SQLAlchemy Core table definitions, scraper data transformations (EGP GPS, PPIP dates, NCA IDs, KMHFL cache, COB poller).

### Satellite Tests (122 tests — fully isolated)

```bash
cd satellite

# Run full test suite (no Copernicus API, S3, or SNAP required)
venv-satellite/bin/python -m pytest tests/ -v --tb=short
```

**Current test status:** 122 passed

Tests cover: FeatureEngineer (48 tests), Config class (15 tests), utility functions (26 tests), TileGenerator (10 tests), NDVI slope regression (7 tests), NDWI computation (6 tests), plus 8 core util tests.

### Run All Tests

```bash
# From the project root — run all 448 tests across all modules
cd backend  && ./venv-backend/bin/pytest tests/ -v --tb=short && cd ..
cd data     && venv-data/bin/python -m pytest tests/ -v --tb=short && cd ..
cd satellite && venv-satellite/bin/python -m pytest tests/ -v --tb=short && cd ..
```

| Module | Tests | Isolation | Requirements |
|--------|-------|-----------|--------------|
| `backend/tests/` | 281 | Integration | PostgreSQL + Redis |
| `data/tests/` | 45 | Fully isolated | None (mocks only) |
| `satellite/tests/` | 122 | Fully isolated | None (pure computation) |
| **Total** | **448** | | |

---

## 6. Satellite Module Setup

```bash
cd satellite

# Create virtual environment
uv venv venv-satellite --python 3.12
source venv-satellite/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Validate the environment
python scripts/validate_environment.py
```

### Configure satellite credentials

```bash
cp .env.example .env
nano .env
# Set COPERNICUS_USERNAME, COPERNICUS_PASSWORD, AWS credentials
```

### Re-train the ML model (optional)

```bash
cd satellite
source venv-satellite/bin/activate

python scripts/run_training.py \
  --data data/training/training_projects.csv \
  --output models/
```

Output: `models/ghost_detector_v1.pkl` + metrics + plots

---

## 7. Full Stack with Docker Compose

To run everything containerized:

```bash
# From project root
docker-compose up -d

# This starts:
#   postgres  — PostGIS database on :5432
#   redis     — Task broker on :6379
#   api       — FastAPI on :8000
#   worker    — Celery worker

# View logs
docker-compose logs -f api
docker-compose logs -f worker

# Stop everything
docker-compose down
```

**Note:** The Docker setup requires a `backend/Dockerfile` to be created. For local development, running services natively (steps 2-5) is recommended.

---

## 8. API Endpoints Reference

### Core Endpoints

| Method | Path                | Description                      |
| ------ | ------------------- | -------------------------------- |
| GET    | `/api/v1/health`    | Health check                     |
| GET    | `/api/v1/health/db` | Database + PostGIS check         |
| GET    | `/api/v1/status`    | System status with record counts |
| GET    | `/api/v1/ping`      | Load balancer ping               |

### Projects

| Method | Path                                   | Description                                                     |
| ------ | -------------------------------------- | --------------------------------------------------------------- |
| GET    | `/api/v1/projects`                     | Paginated list (filters: risk_level, county, type, status)      |
| GET    | `/api/v1/projects/geojson`             | GeoJSON FeatureCollection (filter: `?risk_level=HIGH,CRITICAL`) |
| GET    | `/api/v1/projects/{uuid}`              | Single project                                                  |
| GET    | `/api/v1/projects/{uuid}/truth-record` | Unified project card with all linked data                       |
| POST   | `/api/v1/projects/reconcile`           | Batch concordance for unlinked records (3/min)                  |

### Procurement

| Method | Path                                | Description                 |
| ------ | ----------------------------------- | --------------------------- |
| POST   | `/api/v1/procurement`               | Create procurement record   |
| GET    | `/api/v1/procurement`               | Paginated list with filters |
| GET    | `/api/v1/procurement/search`        | Search by tender number     |
| POST   | `/api/v1/procurement/scrape`        | Trigger PPIP scraper        |
| GET    | `/api/v1/procurement/stats/summary` | Statistics                  |
| GET    | `/api/v1/procurement/{id}`          | Get by ID                   |
| PUT    | `/api/v1/procurement/{id}`          | Update                      |
| DELETE | `/api/v1/procurement/{id}`          | Delete                      |

### Financial

| Method | Path                                  | Description                   |
| ------ | ------------------------------------- | ----------------------------- |
| GET    | `/api/v1/financial/{uuid}`            | Financial records for project |
| GET    | `/api/v1/financial/{uuid}/absorption` | Absorption gap analysis       |

### Geolocation

| Method | Path                           | Description               |
| ------ | ------------------------------ | ------------------------- |
| POST   | `/api/v1/geolocation/resolve`  | 3-tier GPS resolution     |
| GET    | `/api/v1/geolocation/coverage` | Tier breakdown statistics |

### Satellite & Divergence

| Method | Path                                              | Description                         |
| ------ | ------------------------------------------------- | ----------------------------------- |
| POST   | `/api/v1/satellite/analyse/{uuid}`                | Queue satellite analysis (10/min)   |
| GET    | `/api/v1/satellite/status/{task_id}`              | Celery task status                  |
| GET    | `/api/v1/satellite/tiles/{uuid}/ndvi/{z}/{x}/{y}` | NDVI tile (redirect or 202)         |
| GET    | `/api/v1/satellite/tiles-status/{uuid}`           | Tile generation status + URLs       |
| GET    | `/api/v1/projects/{uuid}/divergence`              | Divergence score + timeline         |
| GET    | `/api/v1/dashboard/heat-map`                      | GeoJSON for all geolocated projects |

### Risk Scoring (ML)

| Method | Path                        | Description                                     |
| ------ | --------------------------- | ----------------------------------------------- |
| GET    | `/api/v1/risk/score/{uuid}` | ML ghost probability + features                 |
| GET    | `/api/v1/risk/heat-map`     | GeoJSON with risk data (filter: `?risk_level=`) |

### Google Maps Proxy

| Method | Path                                     | Description                  |
| ------ | ---------------------------------------- | ---------------------------- |
| POST   | `/api/v1/maps/tiles/session`             | Create session token (5/min) |
| GET    | `/api/v1/maps/tiles/{token}/{z}/{x}/{y}` | Tile proxy (60/min)          |

### Certificates

| Method | Path                                 | Description                        |
| ------ | ------------------------------------ | ---------------------------------- |
| GET    | `/api/v1/certificates/{uuid}`        | Generate Section 106B PDF (10/min) |
| GET    | `/api/v1/certificates/{uuid}/status` | Check certificate readiness        |

---

## 9. Rate Limits

All rate limits use `slowapi` with per-IP tracking:

| Endpoint                              | Limit      |
| ------------------------------------- | ---------- |
| Default (all endpoints)               | 200/minute |
| `POST /maps/tiles/session`            | 5/minute   |
| `GET /maps/tiles/{token}/{z}/{x}/{y}` | 60/minute  |
| `POST /satellite/analyse/{uuid}`      | 10/minute  |
| `POST /projects/reconcile`            | 3/minute   |
| `GET /certificates/{uuid}`            | 10/minute  |

Exceeding the limit returns `429 Too Many Requests`.

---

## 10. Security Headers

All responses include:

| Header                      | Value                                                                                          |
| --------------------------- | ---------------------------------------------------------------------------------------------- |
| `X-Content-Type-Options`    | `nosniff`                                                                                      |
| `X-Frame-Options`           | `DENY`                                                                                         |
| `X-XSS-Protection`          | `1; mode=block`                                                                                |
| `Referrer-Policy`           | `strict-origin-when-cross-origin`                                                              |
| `Content-Security-Policy`   | `default-src 'self'; img-src 'self' https://*.amazonaws.com; style-src 'self' 'unsafe-inline'` |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains`                                                          |

---

## Troubleshooting

### "Database connection failed"

```bash
# Verify PostgreSQL is running
pg_isready -U oneka_user -d oneka_dev

# Verify PostGIS extension
psql -U oneka_user -d oneka_dev -c "SELECT PostGIS_version();"
```

### "ModuleNotFoundError: No module named 'src'"

Make sure you are running from the `backend/` directory:

```bash
cd backend
uvicorn src.main:app --reload
```

### Test database errors

```bash
# Ensure the test database exists
psql -U oneka_user -c "CREATE DATABASE oneka_test;" 2>/dev/null || true
psql -U oneka_user -d oneka_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

### Celery worker not picking up tasks

```bash
# Verify Redis is running
redis-cli ping  # Should return PONG

# Check Celery is registered
celery -A src.celery_app inspect registered
```

### spaCy model not found

```bash
source venv-backend/bin/activate
python -m spacy download en_core_web_sm
```
