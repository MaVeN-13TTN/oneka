# ONEKA AI — Environment Variables Setup Guide

This guide walks you through obtaining every credential and configuring both `.env` files for local development.

ONEKA uses two separate `.env` files:

| File | Module | Config Loader |
|------|--------|---------------|
| `backend/.env` | FastAPI web API, Celery workers | Pydantic `BaseSettings` (automatic) |
| `satellite/.env` | Satellite processing pipeline | `python-dotenv` + `os.getenv()` (manual) |

Both files are git-ignored. Copy the `.env.example` templates to get started:

```bash
cp backend/.env.example backend/.env
cp satellite/.env.example satellite/.env
```

---

## Table of Contents

1. [PostgreSQL + PostGIS](#1-postgresql--postgis)
2. [Redis](#2-redis)
3. [Copernicus Data Space](#3-copernicus-data-space)
4. [AWS S3](#4-aws-s3)
5. [Google Maps API](#5-google-maps-api)
6. [Application Settings](#6-application-settings)
7. [Complete .env Reference](#7-complete-env-reference)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. PostgreSQL + PostGIS

**Used by:** `backend/.env` only

ONEKA requires PostgreSQL 15+ with the PostGIS extension for geospatial queries.

### Install

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-client postgis postgresql-15-postgis-3 libpq-dev
```

### Create databases and user

**Option A — Use the provided setup script:**

```bash
sudo -u postgres psql -f backend/setup_database.sql
```

**Option B — Manual setup:**

```bash
sudo -u postgres psql
```

```sql
CREATE USER oneka_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE oneka_dev OWNER oneka_user;
CREATE DATABASE oneka_test OWNER oneka_user;

-- Enable PostGIS on both databases
\c oneka_dev
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
GRANT ALL ON SCHEMA public TO oneka_user;

\c oneka_test
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
GRANT ALL ON SCHEMA public TO oneka_user;

\q
```

### Configure in `backend/.env`

```env
DATABASE_URL=postgresql://oneka_user:your_secure_password@localhost:5432/oneka_dev
DATABASE_TEST_URL=postgresql://oneka_user:your_secure_password@localhost:5432/oneka_test
```

| Variable | Format | Description |
|----------|--------|-------------|
| `DATABASE_URL` | `postgresql://user:password@host:port/dbname` | Main development database connection |
| `DATABASE_TEST_URL` | Same format | Test database (used by pytest, destroyed/rebuilt each run) |

> Replace `your_secure_password` with the password you set during `CREATE USER`. The default in `setup_database.sql` is `password` — change it for anything beyond local development.

---

## 2. Redis

**Used by:** `backend/.env` only

Redis serves as the Celery message broker (task queue) and tile cache.

### Install

```bash
# Ubuntu/Debian
sudo apt install redis-server

# Start and enable on boot
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify
redis-cli ping
# Expected: PONG
```

### Configure in `backend/.env`

```env
REDIS_URL=redis://localhost:6379/0
```

| Variable | Format | Description |
|----------|--------|-------------|
| `REDIS_URL` | `redis://host:port/db_number` | Celery broker + tile cache. Default port is 6379, default db is 0 |

The default value `redis://localhost:6379/0` works out of the box for a fresh Redis install with no password set.

If you configure Redis with a password (recommended for production), the format becomes:

```env
REDIS_URL=redis://:your_redis_password@localhost:6379/0
```

---

## 3. Copernicus Data Space

**Used by:** Both `backend/.env` and `satellite/.env`

Copernicus Data Space Ecosystem provides free access to Sentinel-1 and Sentinel-2 satellite imagery.

### 3a. Create an account (username + password)

1. Go to [https://dataspace.copernicus.eu](https://dataspace.copernicus.eu)
2. Click the avatar icon in the top right corner
3. Click **REGISTER** on the right side of the landing page
4. Fill in the registration form, accept terms and conditions
5. Click **REGISTER**
6. Check your email and click **Verify email address**
7. You can now log in with your email and password

**Support:** help-login@dataspace.copernicus.eu

### 3b. Get OAuth2 client credentials (optional)

The `COPERNICUS_CLIENT_ID` and `COPERNICUS_CLIENT_SECRET` are only needed if you use the openEO or Sentinel Hub APIs directly. For basic satellite downloading via OData, username/password is sufficient.

To get OAuth2 credentials:

1. Go to the [Sentinel Hub Dashboard](https://shapps.dataspace.copernicus.eu/dashboard)
2. Log in with your Copernicus Data Space credentials
3. Navigate to **User Settings** or **OAuth Clients**
4. Create a new OAuth client — this generates a `client_id` and `client_secret`
5. Copy both values immediately (the secret is shown only once)

### Configure in both `.env` files

**`backend/.env`:**
```env
COPERNICUS_USERNAME=your_email@example.com
COPERNICUS_PASSWORD=your_copernicus_password
```

**`satellite/.env`:**
```env
COPERNICUS_USERNAME=your_email@example.com
COPERNICUS_PASSWORD=your_copernicus_password
COPERNICUS_CLIENT_ID=your_client_id_here
COPERNICUS_CLIENT_SECRET=your_client_secret_here
```

| Variable | Required | Where | Description |
|----------|----------|-------|-------------|
| `COPERNICUS_USERNAME` | Yes (for satellite downloads) | Both | Your registered email address |
| `COPERNICUS_PASSWORD` | Yes (for satellite downloads) | Both | Your account password |
| `COPERNICUS_CLIENT_ID` | No | satellite only | OAuth2 client ID (Sentinel Hub Dashboard) |
| `COPERNICUS_CLIENT_SECRET` | No | satellite only | OAuth2 client secret (shown once at creation) |

> These credentials are the same across both files — use the same email/password for both.

---

## 4. AWS S3

**Used by:** Both `backend/.env` and `satellite/.env`

S3 stores satellite GeoTIFFs, generated map tiles, and PDF certificates.

### 4a. Create an IAM user

1. Sign in to the [AWS IAM Console](https://console.aws.amazon.com/iam/)
2. Navigate to **Users** > **Create user**
3. Enter a username (e.g. `oneka-dev`)
4. Do NOT enable console access (not needed for programmatic use)
5. On **Set permissions**, choose **Attach policies directly**
6. Attach `AmazonS3FullAccess` (for development) or create a custom policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:GetObjectAttributes"
      ],
      "Resource": [
        "arn:aws:s3:::oneka-satellite-data",
        "arn:aws:s3:::oneka-satellite-data/*"
      ]
    }
  ]
}
```

7. Click **Create user**

### 4b. Generate access keys

1. Go to **Users** > select your user > **Security credentials** tab
2. Under **Access keys**, click **Create access key**
3. Select use case: **Application running outside AWS**
4. Click **Create access key**
5. **Download the .csv immediately** — the secret key is shown only once

### 4c. Create the S3 bucket

1. Go to the [S3 Console](https://console.aws.amazon.com/s3/)
2. Click **Create bucket**
3. Bucket name: `oneka-satellite-data`
4. Region: `us-east-1` (or your preferred region)
5. **Block all public access**: keep enabled (presigned URLs handle access)
6. Click **Create bucket**

### Configure in both `.env` files

**`backend/.env`:**
```env
AWS_ACCESS_KEY_ID=AKIA...your_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_REGION=us-east-1
AWS_S3_BUCKET=oneka-satellite-data
```

**`satellite/.env`:**
```env
AWS_ACCESS_KEY_ID=AKIA...your_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_REGION=us-east-1
S3_BUCKET=oneka-satellite-data
```

| Variable | Where | Description |
|----------|-------|-------------|
| `AWS_ACCESS_KEY_ID` | Both | Starts with `AKIA` (20 characters) |
| `AWS_SECRET_ACCESS_KEY` | Both | 40-character secret (shown once at creation) |
| `AWS_REGION` | Both | AWS region where your bucket lives (e.g. `us-east-1`) |
| `AWS_S3_BUCKET` | backend | Bucket name as read by Pydantic Settings |
| `S3_BUCKET` | satellite | Same bucket, different env var name (read by `os.getenv`) |

> **Important:** `AWS_S3_BUCKET` (backend) and `S3_BUCKET` (satellite) must point to the same bucket. Use identical values.

> AWS credentials are optional for local development if you only run tests (tests mock S3). You need real credentials only when running satellite downloads or tile generation.

---

## 5. Google Maps API

**Used by:** `backend/.env` only

The Google Maps API proxies map tiles to the frontend. The API key is never exposed to the client.

### 5a. Create a Google Cloud project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top > **New Project**
3. Name it (e.g. `oneka-dev`) and click **Create**
4. Select the new project from the dropdown

### 5b. Enable the Map Tiles API

1. Go to **APIs & Services** > **Library**
2. Search for and enable these APIs:
   - **Map Tiles API** (`tile.googleapis.com`) — required for 2D/3D tiles
   - **Maps JavaScript API** (`maps-backend.googleapis.com`) — required for base map
3. Click **Enable** for each

### 5c. Create an API key

1. Go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** > **API key**
3. Copy the generated key
4. Click **Restrict Key** (recommended):
   - Under **API restrictions**, select **Restrict key**
   - Select only **Map Tiles API** and **Maps JavaScript API**
   - Under **Application restrictions**, select **IP addresses** and add your server IP (or leave unrestricted for local dev)
5. Click **Save**

### 5d. Enable billing

Google Maps requires a billing account. New accounts get $200/month free credit which covers most development usage.

1. Go to **Billing** in the Cloud Console
2. Link a billing account to your project

### Configure in `backend/.env`

```env
GOOGLE_MAPS_API_KEY=AIza...your_api_key
```

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_MAPS_API_KEY` | No (maps proxy returns 503 without it) | Starts with `AIza`, ~39 characters |

> Optional for local development. The maps proxy endpoints will return errors without it, but all other functionality works normally.

---

## 6. Application Settings

These variables control application behavior and don't require external credentials.

### Backend-only settings (`backend/.env`)

| Variable | Default | Valid values | Description |
|----------|---------|-------------|-------------|
| `APP_NAME` | `ONEKA AI API` | Any string | Application name shown in API docs |
| `DEBUG` | `False` | `True` / `False` | Enables debug logging and stack traces |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` | Current environment |
| `API_VERSION` | `1.0.0` | Semver string | API version displayed in docs |
| `API_HOST` | `0.0.0.0` | IP address | Uvicorn bind address |
| `API_PORT` | `8000` | 1024–65535 | Uvicorn bind port |
| `SECRET_KEY` | (insecure default) | Random 32+ char string | JWT token signing key |
| `ALGORITHM` | `HS256` | `HS256` / `HS384` / `HS512` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Positive integer | JWT token expiry in minutes |
| `PPIP_BASE_URL` | `https://tenders.go.ke` | URL | Kenya PPIP tender portal base URL |
| `KMHFL_API_URL` | `https://api.kmhfr.health.go.ke/api` | URL | Kenya Master Health Facility List API |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` | Logging verbosity |

**Generating a secure SECRET_KEY:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Satellite-only settings (`satellite/.env`)

| Variable | Default | Valid values | Description |
|----------|---------|-------------|-------------|
| `RAW_DATA_DIR` | `./data/raw` | Directory path | Where downloaded .SAFE scenes are stored |
| `PROCESSED_DATA_DIR` | `./data/processed` | Directory path | Where processed GeoTIFFs are stored |
| `TRAINING_DATA_DIR` | `./data/training` | Directory path | Where training CSVs live |
| `SNAP_INSTALL_DIR` | `/usr/local/snap` | Directory path | ESA SNAP Toolbox install location |
| `NUM_WORKERS` | `4` | 1–16 | Parallel processing workers |
| `MAX_CLOUD_COVER` | `20` | 0–100 | Max cloud cover % for Sentinel-2 scene selection |
| `BACKEND_API_URL` | `http://localhost:8000` | URL | Backend API for callbacks after processing |
| `BACKEND_API_KEY` | — | String | API key for authenticating with the backend |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` | Logging verbosity |
| `LOG_FILE` | `./logs/satellite_processing.log` | File path | Log file location |
| `DEBUG` | `False` | `True` / `False` | Enables debug mode |
| `TEST_MODE` | `False` | `True` / `False` | Uses small data subsets for testing |

---

## 7. Complete .env Reference

### Minimum viable `backend/.env` (local development)

```env
DATABASE_URL=postgresql://oneka_user:password@localhost:5432/oneka_dev
DATABASE_TEST_URL=postgresql://oneka_user:password@localhost:5432/oneka_test
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change_me_to_something_random_in_production
DEBUG=False
```

Everything else has sensible defaults. Add AWS, Copernicus, and Google Maps credentials as needed.

### Minimum viable `satellite/.env` (local development)

```env
DEBUG=False
TEST_MODE=False
```

All other variables have defaults. Add Copernicus credentials when you need to download satellite imagery, and AWS credentials when you need S3 uploads.

---

## 8. Troubleshooting

### PostgreSQL

**`FATAL: role "oneka_user" does not exist`**

The database user hasn't been created. Run:
```bash
sudo -u postgres psql -c "CREATE USER oneka_user WITH PASSWORD 'password';"
```

**`FATAL: database "oneka_dev" does not exist`**

Run the setup script or create manually:
```bash
sudo -u postgres psql -f backend/setup_database.sql
```

**`FATAL: Peer authentication failed for user "oneka_user"`**

PostgreSQL is using peer auth instead of password auth. Edit `pg_hba.conf`:
```bash
# Find the file
sudo -u postgres psql -c "SHOW hba_file;"

# Edit it — change "peer" to "md5" for local connections
sudo nano /etc/postgresql/15/main/pg_hba.conf
```

Change the line:
```
local   all   all   peer
```
to:
```
local   all   all   md5
```

Then restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

**`ERROR: could not open extension control file "/usr/share/postgresql/15/extension/postgis.control": No such file or directory`**

PostGIS extension is not installed:
```bash
sudo apt install postgresql-15-postgis-3
```

Replace `15` with your PostgreSQL version (`psql --version`).

### Redis

**`Error: Could not connect to Redis at localhost:6379: Connection refused`**

Redis is not running:
```bash
sudo systemctl start redis-server
sudo systemctl status redis-server
```

**Redis returns `NOAUTH Authentication required`**

Redis has a password set. Update your connection URL:
```env
REDIS_URL=redis://:your_redis_password@localhost:6379/0
```

### Copernicus Data Space

**`401 Unauthorized` when downloading scenes**

- Verify your username (email) and password are correct
- Try logging in at [https://dataspace.copernicus.eu](https://dataspace.copernicus.eu) to confirm your account works
- Check for typos — the password is case-sensitive
- If you have 2FA enabled, you may need to use OAuth2 client credentials instead

**`HTTP 429 Too Many Requests`**

Copernicus rate-limits API calls. Wait a few minutes and retry, or reduce `NUM_WORKERS`.

**`No scenes found` for your area of interest**

- Increase `MAX_CLOUD_COVER` (e.g. from 20 to 50)
- Verify your coordinates are in Kenya (lat: -4.7 to 4.6, lon: 33.9 to 41.9)
- Sentinel-2 has a 5-day revisit — try a wider date range

### AWS S3

**`botocore.exceptions.NoCredentialsError: Unable to locate credentials`**

AWS credentials are not configured. Set them in your `.env`:
```env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

Or configure via the AWS CLI:
```bash
aws configure
```

**`botocore.exceptions.ClientError: An error occurred (AccessDenied)`**

Your IAM user lacks the required S3 permissions. Attach `AmazonS3FullAccess` or the custom policy from section 4a.

**`botocore.exceptions.ClientError: An error occurred (NoSuchBucket)`**

The bucket doesn't exist. Create it in the AWS Console (section 4c) or via CLI:
```bash
aws s3 mb s3://oneka-satellite-data --region us-east-1
```

### Google Maps API

**`403 Forbidden` or `REQUEST_DENIED` from maps proxy**

- Verify the API key is correct and not restricted to a different IP
- Ensure **Map Tiles API** is enabled in the Google Cloud Console
- Check that billing is enabled on the project

**`Maps proxy returns 503`**

`GOOGLE_MAPS_API_KEY` is not set in `backend/.env`. The maps endpoints require this key to function.

### General

**Tests pass but the app fails to start**

Check that all required variables are set. The minimum required variable is `DATABASE_URL`:
```bash
cd backend
source venv-backend/bin/activate
python -c "from src.config import settings; print(settings.database_url)"
```

**`pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings`**

A required setting is missing from `backend/.env`. The error message tells you which field. Most commonly `database_url` — Pydantic requires it because it has no default value.

**Environment variable not taking effect**

- Check for typos in the variable name
- Ensure there are no spaces around the `=` sign: `KEY=value` (not `KEY = value`)
- Ensure there are no trailing spaces or invisible characters
- If you changed `.env`, restart the application — `.env` is only read at startup
- Shell-exported variables (`export KEY=value`) take precedence over `.env` file values

---

**ONEKA AI** — *Making the Invisible, Actionable*
