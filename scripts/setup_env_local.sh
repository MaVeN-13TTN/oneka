#!/usr/bin/env bash
# ONEKA AI — Local Development .env Setup
# Usage: bash scripts/setup_env_local.sh  (run from repo root)
#
# Assumes backend/.env.example and satellite/.env.example already exist.
# Copies them to .env, then interactively fills in credentials.
# Run this BEFORE setup_dev.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Colour helpers ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}${1}${NC}"; }
success() { echo -e "${GREEN}✓ ${1}${NC}"; }
warn()    { echo -e "${YELLOW}⚠  ${1}${NC}"; }
error()   { echo -e "${RED}✗ ${1}${NC}" >&2; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║             ONEKA AI — Local Development .env Setup                     ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
info "Repo root: $REPO_ROOT"
echo ""

BACKEND_EXAMPLE="$REPO_ROOT/backend/.env.example"
SATELLITE_EXAMPLE="$REPO_ROOT/satellite/.env.example"
BACKEND_ENV="$REPO_ROOT/backend/.env"
SATELLITE_ENV="$REPO_ROOT/satellite/.env"

# ── Step 1: Verify .env.example templates exist ───────────────────────────
echo -e "${BOLD}━━ Step 1: Checking .env.example templates ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
MISSING=0
[[ ! -f "$BACKEND_EXAMPLE" ]]   && { error "backend/.env.example not found.";   MISSING=1; }
[[ ! -f "$SATELLITE_EXAMPLE" ]] && { error "satellite/.env.example not found."; MISSING=1; }
if [[ $MISSING -eq 1 ]]; then
    error "Example files are required. Restore them from git: git checkout backend/.env.example satellite/.env.example"
    exit 1
fi
success "Found backend/.env.example"
success "Found satellite/.env.example"
echo ""

# ── Step 2: Copy .env.example → .env ─────────────────────────────────────
echo -e "${BOLD}━━ Step 2: Copying templates to .env files ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
for ENV_FILE in "$BACKEND_ENV" "$SATELLITE_ENV"; do
    if [[ -f "$ENV_FILE" ]]; then
        BACKUP="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP"
        warn "Backed up existing $(basename "$(dirname "$ENV_FILE")")/.env → $(basename "$BACKUP")"
    fi
done
cp "$BACKEND_EXAMPLE"   "$BACKEND_ENV"
cp "$SATELLITE_EXAMPLE" "$SATELLITE_ENV"
success "Copied backend/.env.example  → backend/.env"
success "Copied satellite/.env.example → satellite/.env"
echo ""

# ── set_env: replace a KEY=value line in a .env file ─────────────────────
# Uses Python to handle passwords that contain shell-special characters.
set_env() {
    local file="$1" key="$2" value="$3"
    python3 - "$value" <<PYEOF
import sys, re
value = sys.argv[1]
path  = "$file"
key   = "$key"
text  = open(path).read()
text  = re.sub(r'^' + re.escape(key) + r'=.*', key + '=' + value, text, flags=re.MULTILINE)
open(path, 'w').write(text)
PYEOF
}

# ── Step 3: Database password ─────────────────────────────────────────────
echo -e "${BOLD}━━ Step 3: Database Configuration ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "If you haven't set up PostgreSQL yet, run first:"
echo -e "  ${GREEN}sudo -u postgres psql -f backend/setup_database.sql${NC}"
echo ""
read -rp "PostgreSQL password for 'oneka_user' [default: password]: " DB_PASSWORD
DB_PASSWORD="${DB_PASSWORD:-password}"
set_env "$BACKEND_ENV" "DATABASE_URL"      "postgresql://oneka_user:${DB_PASSWORD}@localhost:5432/oneka_dev"
set_env "$BACKEND_ENV" "DATABASE_TEST_URL" "postgresql://oneka_user:${DB_PASSWORD}@localhost:5432/oneka_test"
success "DATABASE_URL and DATABASE_TEST_URL updated"
echo ""

# ── Step 4: Generate SECRET_KEY ───────────────────────────────────────────
echo -e "${BOLD}━━ Step 4: Security Key ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
set_env "$BACKEND_ENV" "SECRET_KEY" "$SECRET_KEY"
success "Generated and set SECRET_KEY"
echo ""

# ── Step 5: Copernicus Data Space credentials ─────────────────────────────
echo -e "${BOLD}━━ Step 5: Copernicus Data Space Credentials ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Required for downloading Sentinel-1/2 satellite imagery."
echo "Register free at: https://dataspace.copernicus.eu/"
echo "Press Enter on each prompt to skip and keep the placeholder values."
echo ""
read -rp  "Copernicus email/username [skip]: " COPERNICUS_USER
read -rsp "Copernicus password        [skip]: " COPERNICUS_PASS
echo ""

if [[ -n "$COPERNICUS_USER" ]]; then
    set_env "$BACKEND_ENV"   "COPERNICUS_USERNAME" "$COPERNICUS_USER"
    set_env "$BACKEND_ENV"   "COPERNICUS_PASSWORD" "$COPERNICUS_PASS"
    set_env "$SATELLITE_ENV" "COPERNICUS_USERNAME" "$COPERNICUS_USER"
    set_env "$SATELLITE_ENV" "COPERNICUS_PASSWORD" "$COPERNICUS_PASS"
    success "Copernicus credentials written to both .env files"

    echo ""
    echo "OAuth2 client credentials (optional — only needed for Sentinel Hub / openEO API):"
    echo "Find them in the Sentinel Hub Dashboard → User Settings → OAuth Clients."
    read -rp  "Copernicus Client ID     [skip]: " COPERNICUS_CLIENT_ID
    read -rsp "Copernicus Client Secret [skip]: " COPERNICUS_CLIENT_SECRET
    echo ""
    if [[ -n "$COPERNICUS_CLIENT_ID" ]]; then
        set_env "$SATELLITE_ENV" "COPERNICUS_CLIENT_ID"     "$COPERNICUS_CLIENT_ID"
        set_env "$SATELLITE_ENV" "COPERNICUS_CLIENT_SECRET" "$COPERNICUS_CLIENT_SECRET"
        success "Copernicus OAuth2 credentials written to satellite/.env"
    else
        warn "OAuth2 credentials skipped — placeholders remain in satellite/.env"
    fi
else
    warn "Copernicus credentials skipped — placeholder values remain"
fi
echo ""

# ── Step 6: AWS S3 credentials ────────────────────────────────────────────
echo -e "${BOLD}━━ Step 6: AWS S3 Credentials ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Required for storing satellite GeoTIFFs and map tiles in S3."
echo "See: docs/08-setup-and-running/ENV_SETUP.md § 4 for IAM + bucket setup."
echo ""
echo "How would you like to configure AWS?"
echo "  1) Paste access keys  — written directly into both .env files"
echo "  2) aws configure      — keys stored in ~/.aws/credentials"
echo "                          (boto3 reads them automatically at runtime;"
echo "                           no keys needed in .env)"
echo "  3) Skip for now       — placeholder values remain; S3 features won't work"
echo ""
read -rp "Choice [1/2/3, default: 3]: " AWS_CHOICE
AWS_CHOICE="${AWS_CHOICE:-3}"

case "$AWS_CHOICE" in
    1)
        read -rp  "AWS Access Key ID (starts with AKIA): " AWS_KEY
        read -rsp "AWS Secret Access Key:                 " AWS_SECRET
        echo ""
        read -rp  "AWS Region [us-east-1]:                " AWS_REGION
        AWS_REGION="${AWS_REGION:-us-east-1}"
        if [[ -n "$AWS_KEY" ]]; then
            set_env "$BACKEND_ENV"   "AWS_ACCESS_KEY_ID"     "$AWS_KEY"
            set_env "$BACKEND_ENV"   "AWS_SECRET_ACCESS_KEY" "$AWS_SECRET"
            set_env "$BACKEND_ENV"   "AWS_REGION"            "$AWS_REGION"
            set_env "$SATELLITE_ENV" "AWS_ACCESS_KEY_ID"     "$AWS_KEY"
            set_env "$SATELLITE_ENV" "AWS_SECRET_ACCESS_KEY" "$AWS_SECRET"
            set_env "$SATELLITE_ENV" "AWS_REGION"            "$AWS_REGION"
            success "AWS credentials written to both .env files"
        else
            warn "No key entered — placeholder values remain"
        fi
        ;;
    2)
        if command -v aws &>/dev/null; then
            echo ""
            info "Running 'aws configure'. Credentials will be stored in ~/.aws/credentials."
            info "boto3 credential precedence: env vars → ~/.aws/credentials → IAM role."
            info "Because the .env files will still contain placeholder values,"
            info "boto3 will correctly fall through to ~/.aws/credentials at runtime."
            echo ""
            aws configure
            echo ""
            # Blank keys and region so Pydantic/os.getenv load empty strings → None,
            # causing boto3 to fall through to ~/.aws/credentials + ~/.aws/config.
            # Leaving placeholder strings would have boto3 use them as explicit
            # credentials, bypassing the chain entirely.
            set_env "$BACKEND_ENV"   "AWS_ACCESS_KEY_ID"     ""
            set_env "$BACKEND_ENV"   "AWS_SECRET_ACCESS_KEY" ""
            set_env "$BACKEND_ENV"   "AWS_REGION"            ""
            set_env "$SATELLITE_ENV" "AWS_ACCESS_KEY_ID"     ""
            set_env "$SATELLITE_ENV" "AWS_SECRET_ACCESS_KEY" ""
            set_env "$SATELLITE_ENV" "AWS_REGION"            ""
            success "AWS configured via 'aws configure'"
            success "AWS keys and region blanked in .env — boto3 will use ~/.aws/credentials + ~/.aws/config at runtime"
        else
            error "'aws' CLI not found — install it first:"
            error "  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
            warn "Falling back to placeholder values in .env"
        fi
        ;;
    *)
        warn "AWS credentials skipped — placeholder values remain"
        warn "S3-dependent features (tile storage, satellite downloads) will fail until configured."
        ;;
esac
echo ""

# ── Step 7: Google Maps API key ───────────────────────────────────────────
echo -e "${BOLD}━━ Step 7: Google Maps API Key ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Required for the server-side map tiles proxy (backend only)."
echo "Get one at: https://console.cloud.google.com/ (see ENV_SETUP.md § 5)."
echo "Press Enter to skip."
echo ""
read -rp "Google Maps API Key (starts with AIza) [skip]: " GOOGLE_MAPS_KEY
if [[ -n "$GOOGLE_MAPS_KEY" ]]; then
    set_env "$BACKEND_ENV" "GOOGLE_MAPS_API_KEY" "$GOOGLE_MAPS_KEY"
    success "Google Maps API key written to backend/.env"
else
    warn "Google Maps key skipped — maps proxy endpoints will return errors until configured"
fi
echo ""

# ── Step 8: Perplexity AI API key ───────────────────────────────────────────
echo -e "${BOLD}━━ Step 8: Perplexity AI API Key ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Required for the single-project investigation pipeline enrichment stage."
echo "Register and get a key at: https://www.perplexity.ai/settings/api"
echo "See: docs/08-setup-and-running/ENV_SETUP.md § 6 for setup details."
echo "Press Enter to skip."
echo ""
read -rp "Perplexity API Key (starts with pplx-) [skip]: " PERPLEXITY_KEY
if [[ -n "$PERPLEXITY_KEY" ]]; then
    set_env "$BACKEND_ENV" "PERPLEXITY_API_KEY" "$PERPLEXITY_KEY"
    success "Perplexity API key written to backend/.env"
else
    warn "Perplexity key skipped — investigation enrichment will use manual context fallback"
fi
echo ""

# ── Step 9: OpenAI API key ────────────────────────────────────────────────
echo -e "${BOLD}━━ Step 9: OpenAI API Key ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Required for the IntelligentCoBParser (GPT-4o Vision) — parsing CoB BIRR PDFs."
echo "Get a key at: https://platform.openai.com/api-keys"
echo "See: docs/08-setup-and-running/ENV_SETUP.md § 7 for cost details (~\$0.10–\$1.50/investigation)."
echo "Press Enter to skip."
echo ""
read -rp "OpenAI API Key (starts with sk-) [skip]: " OPENAI_KEY
if [[ -n "$OPENAI_KEY" ]]; then
    set_env "$BACKEND_ENV" "OPENAI_API_KEY" "$OPENAI_KEY"
    success "OpenAI API key written to backend/.env"
else
    warn "OpenAI key skipped — IntelligentCoBParser will be unavailable; standard CoBParser will be used"
fi
echo ""

# ── Step 10: Quick database connectivity check ────────────────────────────
echo -e "${BOLD}━━ Step 10: Database Connection Check ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
if PGPASSWORD="$DB_PASSWORD" psql -U oneka_user -d oneka_dev -h localhost -c "SELECT 1;" &>/dev/null 2>&1; then
    success "Connected to oneka_dev — database is ready"
else
    warn "Cannot connect to oneka_dev as oneka_user."
    echo "       If the database doesn't exist yet, run:"
    echo -e "         ${GREEN}sudo -u postgres psql -f backend/setup_database.sql${NC}"
    echo "       Then re-run this script, or proceed and run setup_dev.sh which will warn again."
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}✓ .env files configured${NC}"
echo ""
echo "Files written:"
echo "  • backend/.env"
echo "  • satellite/.env"
echo ""

# Report remaining placeholders
NEEDS_CREDS=()
grep -qE "your_copernicus_(username|password)" "$BACKEND_ENV" && \
    NEEDS_CREDS+=("Copernicus credentials  — satellite imagery downloads")
grep -qE "your_aws_(access_key|secret_key)" "$BACKEND_ENV" && \
    NEEDS_CREDS+=("AWS credentials         — S3 tile/GeoTIFF storage")
grep -q "your_google_maps_api_key" "$BACKEND_ENV" && \
    NEEDS_CREDS+=("Google Maps API key     — map tiles proxy")
grep -q "your_perplexity_api_key" "$BACKEND_ENV" && \
    NEEDS_CREDS+=("Perplexity API key      — investigation enrichment (§ 6)")
grep -q "your_openai_api_key" "$BACKEND_ENV" && \
    NEEDS_CREDS+=("OpenAI API key          — IntelligentCoBParser Vision (§ 7)")

if [[ ${#NEEDS_CREDS[@]} -gt 0 ]]; then
    warn "Still using placeholders for:"
    for item in "${NEEDS_CREDS[@]}"; do
        echo "    • $item"
    done
    echo ""
    echo "Add them later when you need those features."
    echo "Reference: docs/08-setup-and-running/ENV_SETUP.md"
fi

echo ""
echo "Next: install dependencies, run migrations, and seed the database:"
echo -e "  ${GREEN}bash scripts/setup_dev.sh${NC}"
echo ""
