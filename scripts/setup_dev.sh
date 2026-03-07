#!/usr/bin/env bash
# Oneka AI — One-command development environment setup
# Usage: bash scripts/setup_dev.sh
# Run from the repository root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "=== Oneka AI — Dev Environment Setup ==="
echo "Repo root: $REPO_ROOT"
echo ""

# ── Prerequisite checks ───────────────────────────────────────────────────
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "ERROR: '$1' is required but not installed." >&2
    echo "       Install it and re-run this script." >&2
    exit 1
  fi
}

check_cmd uv
check_cmd psql
check_cmd python3

echo "✓ Prerequisites satisfied (uv, psql, python3)"

# ── PostgreSQL check ──────────────────────────────────────────────────────
echo ""
echo "--- Checking PostgreSQL ---"
if ! PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -c "SELECT 1;" &>/dev/null; then
  echo "WARNING: Cannot connect to oneka_dev as oneka_user."
  echo "         Run backend/setup_database.sql as a PostgreSQL superuser:"
  echo "         sudo -u postgres psql -f backend/setup_database.sql"
  echo "         Then re-run this script."
else
  echo "✓ PostgreSQL connection OK (oneka_dev)"
fi

# ── Backend venv ──────────────────────────────────────────────────────────
echo ""
echo "--- Backend venv (backend/venv-backend) ---"
if [ ! -d "backend/venv-backend" ]; then
  echo "Creating backend venv..."
  uv venv backend/venv-backend --python 3.12
fi
echo "Installing backend requirements..."
uv pip install -r backend/requirements.txt --python backend/venv-backend/bin/python
echo "✓ Backend dependencies installed"

# ── Data venv ─────────────────────────────────────────────────────────────
echo ""
echo "--- Data venv (data/venv-data) ---"
if [ ! -d "data/venv-data" ]; then
  echo "Creating data venv..."
  uv venv data/venv-data --python 3.12
fi
echo "Installing data requirements..."
uv pip install -r data/requirements.txt --python data/venv-data/bin/python
echo "✓ Data dependencies installed"

# Install Playwright browsers (required for scrapers)
echo "Installing Playwright Chromium browser..."
data/venv-data/bin/python -m playwright install chromium 2>/dev/null || \
  echo "WARNING: Playwright browser install failed — run manually: python -m playwright install chromium"
echo "✓ Playwright ready"

# ── Satellite venv ────────────────────────────────────────────────────────
echo ""
echo "--- Satellite venv (satellite/venv-satellite) ---"
if [ ! -d "satellite/venv-satellite" ]; then
  echo "Creating satellite venv..."
  uv venv satellite/venv-satellite --python 3.12
fi
echo "Installing satellite requirements..."
uv pip install -r satellite/requirements.txt --python satellite/venv-satellite/bin/python
echo "✓ Satellite dependencies installed"

# ── Alembic migration ─────────────────────────────────────────────────────
echo ""
echo "--- Alembic migrations ---"
ALEMBIC_ENV="PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev"
if PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -c "SELECT 1 FROM alembic_version LIMIT 1;" &>/dev/null 2>&1; then
  echo "✓ Alembic version table exists — running upgrade head..."
  (cd backend && PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev \
    venv-backend/bin/python -m alembic upgrade head)
else
  echo "No alembic_version found — stamping at initial revision..."
  (cd backend && PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev \
    venv-backend/bin/python -m alembic stamp bcf9c05b9fb7)
fi
echo "✓ Alembic at head"

# ── spaCy model ───────────────────────────────────────────────────────────
echo ""
echo "--- spaCy language model (required for Phase 2 geolocation) ---"
# spaCy is not in requirements.txt yet; skip if not installed
if backend/venv-backend/bin/python -c "import spacy" &>/dev/null 2>&1; then
  backend/venv-backend/bin/python -m spacy download en_core_web_sm
  echo "✓ spaCy en_core_web_sm downloaded"
else
  echo "NOTE: spacy not yet installed. It will be added in Phase 2."
  echo "      After adding it to backend/requirements.txt, run:"
  echo "      python -m spacy download en_core_web_sm"
fi

# ── SNAP / GDAL note ──────────────────────────────────────────────────────
echo ""
echo "--- System dependencies note ---"
echo "GDAL:  $(gdal-config --version 2>/dev/null || echo 'not found — install: sudo apt-get install gdal-bin libgdal-dev')"
if command -v snap &>/dev/null; then
  echo "SNAP:  $(snap --version 2>/dev/null | head -1)"
else
  echo "SNAP:  not found — required for SAR processing (PyroSAR)."
  echo "       Download from: https://step.esa.int/main/download/snap-download/"
fi

# ── Seed training data ────────────────────────────────────────────────────
echo ""
echo "--- Seeding training projects ---"
if PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -c "SELECT COUNT(*) FROM projects;" &>/dev/null 2>&1; then
  PROJ_COUNT=$(PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -t -c "SELECT COUNT(*) FROM projects;" | tr -d ' \n')
  if [ "$PROJ_COUNT" -eq "0" ]; then
    echo "Seeding 30 training projects..."
    (cd backend && PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev \
      venv-backend/bin/python scripts/seed_training_projects.py)
  else
    echo "✓ $PROJ_COUNT project(s) already in DB — skipping seed"
  fi
fi

# ── Load admin boundaries (Phase 2 Tier 3 geolocation) ───────────────
echo ""
echo "--- Loading admin boundaries ---"
if PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -c "SELECT COUNT(*) FROM admin_boundaries;" &>/dev/null 2>&1; then
  BOUNDARY_COUNT=$(PGPASSWORD=password psql -U oneka_user -d oneka_dev -h localhost -t -c "SELECT COUNT(*) FROM admin_boundaries;" | tr -d ' \n')
  if [ "$BOUNDARY_COUNT" -eq "0" ]; then
    GEOJSON_FILE="$REPO_ROOT/backend/ken_adm_geojson/ken_admin2.geojson"
    if [ -f "$GEOJSON_FILE" ]; then
      echo "Loading Level 2 (sub-county) boundaries from ken_admin2.geojson..."
      (cd backend && PGPASSWORD=password DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev \
        venv-backend/bin/python scripts/load_ward_boundaries.py --geojson "$GEOJSON_FILE")
    else
      echo "NOTE: ken_admin2.geojson not found at $GEOJSON_FILE"
      echo "      Download from: https://data.humdata.org/dataset/cod-ab-ken"
    fi
  else
    echo "✓ $BOUNDARY_COUNT boundary record(s) already loaded — skipping"
  fi
else
  echo "NOTE: admin_boundaries table not found — run Alembic migrations first"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the API:"
echo "  cd backend && source venv-backend/bin/activate"
echo "  uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "To start the full stack with Docker:"
echo "  docker-compose up -d"
echo ""
echo "API docs: http://localhost:8000/docs"
