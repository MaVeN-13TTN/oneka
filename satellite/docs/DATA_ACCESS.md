# Satellite Data Access Guide

## Copernicus Data Space Ecosystem

### Account Setup

1. **Register Account**
   - URL: https://dataspace.copernicus.eu/
   - Click "Register" in top-right corner
   - Fill in registration form (email, username, password)
   - Verify email address
   - Login to access services

2. **Generate OAuth2 Credentials** (Optional, for API access)
   - Navigate to: https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings
   - Go to "User Settings" → "OAuth Clients"
   - Click "Create New"
   - Save `client_id` and `client_secret`

### Authentication Methods

#### Method 1: Basic Authentication (Username + Password)

```python
from sentinelsat import SentinelAPI

api = SentinelAPI(
    'your_username',
    'your_password',
    'https://catalogue.dataspace.copernicus.eu/resto'
)
```

#### Method 2: OAuth2 (Recommended for Production)

```python
import requests

# Get access token
token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
data = {
    "client_id": "your_client_id",
    "client_secret": "your_client_secret",
    "grant_type": "client_credentials"
}

response = requests.post(token_url, data=data)
access_token = response.json()["access_token"]

# Use token in API requests
headers = {"Authorization": f"Bearer {access_token}"}
```

## Scene Search

### Sentinel-2 (Optical Imagery)

**Product Types:**

- `S2MSI1C`: Level-1C (Top-of-Atmosphere Reflectance)
- `S2MSI2A`: Level-2A (Bottom-of-Atmosphere Reflectance) - **Recommended**

**Search Parameters:**

```python
from sentinelsat import SentinelAPI
from datetime import datetime

api = SentinelAPI('username', 'password', 'https://catalogue.dataspace.copernicus.eu/resto')

# Define search area (bounding box or WKT polygon)
footprint = "POLYGON((36.70 -1.50, 37.10 -1.50, 37.10 -1.10, 36.70 -1.10, 36.70 -1.50))"

# Search
products = api.query(
    area=footprint,
    date=('20240101', '20241231'),
    platformname='Sentinel-2',
    producttype='S2MSI2A',
    cloudcoverpercentage=(0, 20)  # Max 20% cloud cover
)

print(f"Found {len(products)} scenes")
```

**Cloud Cover Recommendations:**

- Urban areas: < 10% (buildings sensitive to shadows)
- Rural areas: < 20% (vegetation less sensitive)
- Rainy season (March-May, Oct-Dec): < 30% (harder to find clear scenes)

### Sentinel-1 (SAR Imagery)

**Product Types:**

- `GRD`: Ground Range Detected (multi-looked, **Recommended for ONEKA**)
- `SLC`: Single Look Complex (interferometry, advanced users)

**Search Parameters:**

```python
products = api.query(
    area=footprint,
    date=('20240101', '20241231'),
    platformname='Sentinel-1',
    producttype='GRD',
    sensoroperationalmode='IW',  # Interferometric Wide Swath
    polarisationmode='VV VH'  # Dual polarization
)
```

**Polarization Modes:**

- `VV VH`: Vertical transmit, Vertical + Horizontal receive (most common)
- `HH HV`: Horizontal transmit, Horizontal + Vertical receive (rare)
- `VV`: Single polarization (older scenes)

## Download Scenes

### Using sentinelsat Library

```python
# Download single scene
api.download(product_uuid, directory_path='/path/to/output')

# Download all search results
api.download_all(products, directory_path='/path/to/output')
```

### Using ONEKA Download Module

```bash
python src/download.py \
    --lat -1.2921 \
    --lon 36.8219 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --sensor sentinel-2 \
    --max-cloud 20 \
    --max-scenes 5 \
    --output ./data/raw/
```

### Download Speed Optimization

**Tips:**

1. **Parallel Downloads**: Download multiple scenes concurrently (max 2-3 connections)
2. **Off-Peak Hours**: EU daytime hours are slower (Kenya is 1-2 hours ahead)
3. **Smaller ROI**: Download specific tiles instead of full scenes
4. **AWS Mirror**: Use `s3://sentinel-s2-l2a` for faster downloads (requester-pays)

**Typical Download Sizes:**

- Sentinel-2 L2A: 500 MB - 1 GB per scene (compressed)
- Sentinel-1 GRD: 800 MB - 1.5 GB per scene

## Alternative Data Sources

### AWS Open Data Registry

**Sentinel-2:**

```bash
# List available tiles
aws s3 ls s3://sentinel-s2-l2a/tiles/37/M/CS/2024/ --no-sign-request

# Download specific tile
aws s3 cp s3://sentinel-s2-l2a/tiles/37/M/CS/2024/6/15/0/ ./data/raw/ --recursive --no-sign-request
```

**Cost:** Free downloads within AWS (cross-region egress: $0.09/GB)

### Google Cloud Public Datasets

```python
from google.cloud import storage

client = storage.Client.create_anonymous_client()
bucket = client.bucket("gcp-public-data-sentinel-2")

blobs = bucket.list_blobs(prefix="tiles/37/M/CS/S2A_MSIL2A_20240615")
for blob in blobs:
    blob.download_to_filename(f"./data/raw/{blob.name}")
```

**Cost:** Egress charges apply ($0.12/GB outside Google Cloud)

## Data Organization

### Recommended Directory Structure

```
data/raw/
├── sentinel-2/
│   ├── S2A_MSIL2A_20240615T073611_N0510_R092_T37MCS_20240615T112233.SAFE/
│   └── S2B_MSIL2A_20240620T073609_N0510_R092_T37MCS_20240620T111534.SAFE/
└── sentinel-1/
    ├── S1A_IW_GRDH_1SDV_20240615T032030_20240615T032055_054123_069ABC_1234.SAFE/
    └── S1B_IW_GRDH_1SDV_20240620T032030_20240620T032055_031234_05CDEF_5678.SAFE/
```

### File Naming Convention

**Sentinel-2:**

```
S2A_MSIL2A_20240615T073611_N0510_R092_T37MCS_20240615T112233
│   │       │               │     │    │       └─ Product Discriminator
│   │       │               │     │    └───────── Tile ID (MGRS)
│   │       │               │     └────────────── Relative Orbit
│   │       │               └──────────────────── Processing Baseline
│   │       └──────────────────────────────────── Sensing Date/Time
│   └──────────────────────────────────────────── Product Level
└──────────────────────────────────────────────── Satellite (A or B)
```

**Sentinel-1:**

```
S1A_IW_GRDH_1SDV_20240615T032030_20240615T032055_054123_069ABC_1234
│   │  │    │    │               │               │      │      └─ Product ID
│   │  │    │    │               │               │      └──────── Data Take ID
│   │  │    │    │               │               └─────────────── Absolute Orbit
│   │  │    │    │               └─────────────────────────────── Stop Time
│   │  │    │    └─────────────────────────────────────────────── Start Time
│   │  │    └──────────────────────────────────────────────────── Polarization
│   │  └───────────────────────────────────────────────────────── Product Type
│   └──────────────────────────────────────────────────────────── Mode (IW)
└──────────────────────────────────────────────────────────────── Satellite
```

## API Rate Limits

**Copernicus Data Space:**

- No hard rate limits
- Fair use policy: max 2 concurrent downloads per user
- Recommended: 1-2 requests/second for search API

**AWS/Google:**

- No rate limits for public buckets
- Throttling may occur with sustained high request rates

## Troubleshooting

### Issue: "Authentication failed"

**Solution:**

1. Verify credentials in `.env` file
2. Check account is activated (email verification)
3. Try resetting password

### Issue: "No scenes found"

**Possible Causes:**

1. Cloud cover too restrictive (increase `max_cloud_cover`)
2. Date range too narrow (expand date range)
3. AOI too small (verify coordinates)
4. Scene already archived (check archive status)

### Issue: "Download timeout"

**Solutions:**

1. Retry download (resume supported)
2. Use smaller ROI
3. Download during off-peak hours
4. Use AWS/Google mirror

### Issue: "Disk space full"

**Prevention:**

- Sentinel-2 scene: ~1 GB
- 30 projects × 24 months = 720 scenes = ~720 GB
- Recommended: 1 TB available space
- Delete raw data after processing to processed GeoTIFFs

## Support Resources

- **Copernicus Help**: https://documentation.dataspace.copernicus.eu/
- **Sentinel-2 User Guide**: https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi
- **Sentinel-1 User Guide**: https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar
- **sentinelsat Documentation**: https://sentinelsat.readthedocs.io/
- **ONEKA Support**: Contact ML/Satellite Engineer

---

**Last Updated:** February 9, 2026  
**Version:** 1.0  
**Author:** ONEKA AI Team
