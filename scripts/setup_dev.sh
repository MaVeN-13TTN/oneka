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

# ── Read credentials from backend/.env ────────────────────────────────────
echo ""
echo "--- Reading backend/.env ---"
if [[ ! -f "backend/.env" ]]; then
  echo "ERROR: backend/.env not found." >&2
  echo "       Run scripts/setup_env_local.sh first to create it." >&2
  exit 1
fi

# Parse DATABASE_URL from backend/.env and extract components
DATABASE_URL=$(grep "^DATABASE_URL=" backend/.env | cut -d'=' -f2-)
read -r DB_USER DB_PASSWORD DB_HOST DB_PORT DB_NAME < <(python3 -c "
from urllib.parse import urlparse
u = urlparse('$DATABASE_URL')
print(u.username or 'oneka_user',
      u.password or 'password',
      u.hostname or 'localhost',
      u.port or 5432,
      u.path.lstrip('/') or 'oneka_dev')
")
echo "✓ Loaded database config from backend/.env (host=$DB_HOST db=$DB_NAME user=$DB_USER)"

# ── PostgreSQL check ──────────────────────────────────────────────────────
echo ""
echo "--- Checking PostgreSQL ---"
if ! PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -c "SELECT 1;" &>/dev/null; then
  echo "WARNING: Cannot connect to $DB_NAME as $DB_USER."
  echo "         Run backend/setup_database.sql as a PostgreSQL superuser:"
  echo "         sudo -u postgres psql -f backend/setup_database.sql"
  echo "         Then re-run this script."
else
  echo "✓ PostgreSQL connection OK ($DB_NAME)"
fi

# ── Helper: check that a set of packages are importable ──────────────────
verify_imports() {
  local python_bin="$1"; shift
  local failed=()
  for pkg in "$@"; do
    if ! "$python_bin" -c "import $pkg" &>/dev/null 2>&1; then
      failed+=("$pkg")
    fi
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "  Cannot import: ${failed[*]}" >&2
    return 1
  fi
  return 0
}

# ── Helper: sync a venv — check installed state, verify, install if needed ─
#
# Usage: sync_venv <label> <venv_dir> <req_file> <pkg1> [pkg2 ...]
#
# Flow:
#   1. Create venv if it does not exist.
#   2. Compare sha256(req_file) against <venv_dir>/.req_hash:
#        a. Hash matches → deps appear installed:
#             verify key imports → OK: skip install and continue
#                               → FAIL: reinstall + re-verify (handles corruption)
#        b. No hash file (fresh venv) → install + verify + save hash
#        c. Hash differs (req_file changed) → update install + verify + save hash
#   Exits non-zero if verification fails after an install attempt.
sync_venv() {
  local label="$1"
  local venv_dir="$2"
  local req_file="$3"
  shift 3
  local verify_pkgs=("$@")
  local python_bin="${venv_dir}/bin/python"
  local hash_file="${venv_dir}/.req_hash"

  echo ""
  echo "--- ${label} venv (${venv_dir}) ---"

  if [ ! -d "$venv_dir" ]; then
    echo "Creating ${label} venv..."
    uv venv "$venv_dir" --python 3.12
  fi

  local current_hash stored_hash=""
  current_hash=$(sha256sum "$req_file" | cut -d' ' -f1)
  [[ -f "$hash_file" ]] && stored_hash=$(cat "$hash_file")

  if [[ "$stored_hash" == "$current_hash" ]]; then
    # requirements.txt unchanged since last recorded install — verify imports
    echo "Pre-existing install detected (requirements.txt unchanged since last run)."
    echo "Skipping uv pip install — verifying key imports instead..."
    if verify_imports "$python_bin" "${verify_pkgs[@]}"; then
      echo "✓ ${label} — all packages present and importable. Nothing to install."
    else
      echo "Import check failed — one or more packages are missing or broken."
      echo "Reinstalling ${label} dependencies..."
      uv pip install -r "$req_file" --python "$python_bin"
      if verify_imports "$python_bin" "${verify_pkgs[@]}"; then
        echo "$current_hash" > "$hash_file"
        echo "✓ ${label} reinstalled and verified."
      else
        echo "ERROR: ${label} verification failed after reinstall — check requirements.txt" >&2
        exit 1
      fi
    fi

  elif [[ -z "$stored_hash" ]]; then
    # Venv exists but no hash file — either a fresh clone or a manually created venv.
    # Run a quick import check first; if everything already imports, just record the
    # hash and skip the install (saves time when the venv was set up outside this script).
    echo "No install record found for ${label} venv."
    echo "Checking whether packages are already present..."
    if verify_imports "$python_bin" "${verify_pkgs[@]}"; then
      echo "All key packages already importable — recording install state and skipping uv pip install."
      echo "$current_hash" > "$hash_file"
      echo "✓ ${label} — pre-existing packages verified and recorded."
    else
      echo "Some packages missing — installing ${label} dependencies..."
      uv pip install -r "$req_file" --python "$python_bin"
      if verify_imports "$python_bin" "${verify_pkgs[@]}"; then
        echo "$current_hash" > "$hash_file"
        echo "✓ ${label} dependencies installed and verified."
      else
        echo "ERROR: ${label} verification failed after install — check requirements.txt" >&2
        exit 1
      fi
    fi

  else
    # Hash present but stale — requirements.txt has changed since the last recorded install
    echo "requirements.txt has changed since last install — updating ${label} dependencies..."
    uv pip install -r "$req_file" --python "$python_bin"
    if verify_imports "$python_bin" "${verify_pkgs[@]}"; then
      echo "$current_hash" > "$hash_file"
      echo "✓ ${label} dependencies updated and verified."
    else
      echo "ERROR: ${label} verification failed after update — check requirements.txt" >&2
      exit 1
    fi
  fi
}

# ── Backend venv ──────────────────────────────────────────────────────────
# Canary packages: core FastAPI stack + task queue + DB layer
sync_venv "Backend" backend/venv-backend backend/requirements.txt \
  fastapi sqlalchemy celery pydantic alembic

# ── Data venv ─────────────────────────────────────────────────────────────
# Canary packages: HTTP client, HTML parser, browser automation, PDF parser, data frames
sync_venv "Data" data/venv-data data/requirements.txt \
  httpx bs4 playwright pdfplumber pandas

# ── Playwright Chromium browser ───────────────────────────────────────────
# Check for the Chromium executable under ~/.cache/ms-playwright/ — the path
# playwright install places it at runtime. Avoids running the installer on
# every invocation.
echo ""
echo "--- Playwright Chromium browser ---"
CHROMIUM_OK=$(data/venv-data/bin/python - <<'PYEOF'
import pathlib
base = pathlib.Path.home() / ".cache" / "ms-playwright"
found = list(base.glob("chromium-*/chrome-linux/chrome")) + \
        list(base.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
print("yes" if any(f.exists() for f in found) else "no")
PYEOF
2>/dev/null || echo "no")
if [[ "$CHROMIUM_OK" == "yes" ]]; then
  echo "✓ Playwright Chromium already installed — skipping"
else
  echo "Installing Playwright Chromium browser..."
  data/venv-data/bin/python -m playwright install chromium && \
    echo "✓ Playwright Chromium installed" || \
    echo "WARNING: Playwright browser install failed — run manually: python -m playwright install chromium"
fi

# ── Satellite venv ────────────────────────────────────────────────────────
# Canary packages: raster I/O, vector, coordinate transforms, satellite API client, array ops
sync_venv "Satellite" satellite/venv-satellite satellite/requirements.txt \
  rasterio shapely geopandas sentinelsat xarray boto3

# ── Alembic migration ─────────────────────────────────────────────────────
echo ""
echo "--- Alembic migrations ---"
if PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -c "SELECT 1 FROM alembic_version LIMIT 1;" &>/dev/null 2>&1; then
  echo "✓ Alembic version table exists — running upgrade head..."
  (cd backend && PGPASSWORD="$DB_PASSWORD" DATABASE_URL="$DATABASE_URL" \
    venv-backend/bin/python -m alembic upgrade head)
else
  echo "No alembic_version found — stamping at initial revision..."
  # The base schema is created by setup_database.sql outside of Alembic.
  # Stamp at the initial migration revision so incremental migrations run correctly.
  INITIAL_REV=$(cd backend && PGPASSWORD="$DB_PASSWORD" DATABASE_URL="$DATABASE_URL" \
    venv-backend/bin/python -m alembic history 2>/dev/null | tail -1 | grep -oE '^[a-f0-9]+')
  INITIAL_REV="${INITIAL_REV:-bcf9c05b9fb7}"
  (cd backend && PGPASSWORD="$DB_PASSWORD" DATABASE_URL="$DATABASE_URL" \
    venv-backend/bin/python -m alembic stamp "$INITIAL_REV")
fi
echo "✓ Alembic at head"

# ── spaCy model ───────────────────────────────────────────────────────────
echo ""
echo "--- spaCy language model (required for Phase 2 geolocation) ---"
if backend/venv-backend/bin/python -c "import spacy" &>/dev/null 2>&1; then
  # spaCy is installed — check whether the model is already present
  if backend/venv-backend/bin/python -c "import spacy; spacy.load('en_core_web_sm')" &>/dev/null 2>&1; then
    echo "✓ spaCy en_core_web_sm already installed — skipping"
  else
    echo "Downloading spaCy en_core_web_sm model..."
    backend/venv-backend/bin/python -m spacy download en_core_web_sm
    echo "✓ spaCy en_core_web_sm downloaded"
  fi
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
if PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -c "SELECT COUNT(*) FROM projects;" &>/dev/null 2>&1; then
  PROJ_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -t -c "SELECT COUNT(*) FROM projects;" | tr -d ' \n')
  if [ "$PROJ_COUNT" -eq "0" ]; then
    echo "Seeding 30 training projects..."
    (cd backend && PGPASSWORD="$DB_PASSWORD" DATABASE_URL="$DATABASE_URL" \
      venv-backend/bin/python scripts/seed_training_projects.py)
  else
    echo "✓ $PROJ_COUNT project(s) already in DB — skipping seed"
  fi
fi

# ── Load admin boundaries (Phase 2 Tier 3 geolocation) ───────────────
echo ""
echo "--- Loading admin boundaries ---"
if PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -c "SELECT COUNT(*) FROM admin_boundaries;" &>/dev/null 2>&1; then
  BOUNDARY_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -U "$DB_USER" -d "$DB_NAME" -h "$DB_HOST" -t -c "SELECT COUNT(*) FROM admin_boundaries;" | tr -d ' \n')
  if [ "$BOUNDARY_COUNT" -eq "0" ]; then
    GEOJSON_FILE="$REPO_ROOT/backend/ken_adm_geojson/ken_admin2.geojson"
    if [ -f "$GEOJSON_FILE" ]; then
      echo "Loading Level 2 (sub-county) boundaries from ken_admin2.geojson..."
      (cd backend && PGPASSWORD="$DB_PASSWORD" DATABASE_URL="$DATABASE_URL" \
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
