# scripts/

Two setup scripts for the ONEKA AI development environment. **Run them in order** when setting up a fresh clone.

```bash
# 1. Configure .env files (interactive — prompts for credentials)
bash scripts/setup_env_local.sh

# 2. Install dependencies, run migrations, seed the database
bash scripts/setup_dev.sh
```

---

## setup_env_local.sh

**Purpose:** One-time `.env` file configuration for a developer's machine.

Copies the committed `.env.example` templates to actual `.env` files, then interactively prompts you to fill in credentials. Always starts from the example files, so it's safe to re-run — existing `.env` files are backed up before being overwritten.

**What it does:**

| Step | Action                                                                           |
| ---- | -------------------------------------------------------------------------------- |
| 1    | Verifies `backend/.env.example` and `satellite/.env.example` exist               |
| 2    | Copies them to `backend/.env` and `satellite/.env` (backs up existing files)     |
| 3    | Prompts for PostgreSQL password — updates `DATABASE_URL` and `DATABASE_TEST_URL` |
| 4    | Generates a secure random `SECRET_KEY` automatically                             |
| 5    | Prompts for Copernicus Data Space credentials (optional — skip with Enter)       |
| 6    | Prompts for AWS S3 credentials — three options (see below)                       |
| 7    | Prompts for Google Maps API key (optional — skip with Enter)                     |
| 8    | Tests the database connection                                                    |

**AWS credential options (Step 6):**

- **Option 1 — Paste keys:** Keys and region are written directly into both `.env` files. boto3 reads them from environment variables at runtime.
- **Option 2 — `aws configure`:** Runs the AWS CLI wizard. Keys are stored in `~/.aws/credentials` and region in `~/.aws/config`. The script **blanks** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_REGION` in both `.env` files — this is intentional. boto3's credential chain resolves in order: env vars → `~/.aws/credentials` → IAM role. Passing empty strings to `boto3.client()` would satisfy rule 1 with bad values, so the code converts them to `None` (`or None`), causing boto3 to skip to rule 2 and correctly read `~/.aws/credentials`. Region is resolved the same way from `~/.aws/config`.
- **Option 3 — Skip:** All three AWS variables remain blank. S3-dependent features (satellite downloads, tile storage) will fail until configured.

**Why `AWS_REGION` is also blanked under option 2:**

`os.getenv("AWS_REGION", "us-east-1")` only uses the default when the variable is _absent_. When `AWS_REGION=` is present but blank it returns `""`, which would silently override the region in `~/.aws/config`. The satellite config uses `os.getenv("AWS_REGION") or None` to treat both absent and blank as `None`, letting boto3 read the correct region from `~/.aws/config` (e.g. `eu-north-1`).

**Requires:** `python3`, `psql`

---

## setup_dev.sh

**Purpose:** Full environment bootstrap — run after `setup_env_local.sh`.

Reads `backend/.env` for database credentials (never hardcodes them). Fails fast with a clear message if `backend/.env` is missing.

**What it does:**

| Step | Action                                                                                   |
| ---- | ---------------------------------------------------------------------------------------- |
| 1    | Checks prerequisites: `uv`, `psql`, `python3`                                            |
| 2    | Reads `DATABASE_URL` from `backend/.env` and parses credentials                          |
| 3    | Verifies PostgreSQL connection                                                           |
| 4    | Creates `backend/venv-backend`, `data/venv-data`, `satellite/venv-satellite` (if absent) |
| 5    | Installs all requirements via `uv pip install`                                           |
| 6    | Installs Playwright Chromium for scrapers                                                |
| 7    | Runs Alembic migrations to `head` (or stamps initial revision on a fresh schema)         |
| 8    | Downloads spaCy `en_core_web_sm` language model (Phase 2 geolocation)                    |
| 9    | Seeds 30 labelled training projects (if `projects` table is empty)                       |
| 10   | Loads Kenya Level-2 admin boundaries for Tier 3 geolocation fallback                     |

**Requires:** `backend/.env` written by `setup_env_local.sh`, `uv`, PostgreSQL running, Redis running.

---

## Prerequisites

| Tool                 | Install                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| `uv`                 | `curl -LsSf https://astral.sh/uv/install.sh \| sh`                                             |
| `psql` + PostgreSQL  | `sudo apt install postgresql postgresql-client postgis postgresql-15-postgis-3`                |
| `python3`            | `sudo apt install python3`                                                                     |
| Redis                | `sudo apt install redis-server && sudo systemctl enable --now redis-server`                    |
| `aws` CLI (optional) | [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |

After installing PostgreSQL, create the databases and user:

```bash
sudo -u postgres psql -f backend/setup_database.sql
```

For detailed credential setup instructions, see [docs/08-setup-and-running/ENV_SETUP.md](../docs/08-setup-and-running/ENV_SETUP.md).
