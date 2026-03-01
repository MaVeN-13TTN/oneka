# Satellite Data Storage Structure

## Directory Organization

### Overview

```
satellite/
├── data/
│   ├── raw/                    # Downloaded satellite scenes (temporary)
│   ├── processed/              # Processed GeoTIFFs and visualizations
│   └── training/               # Training dataset for ML model
├── src/                        # Source code
├── tests/                      # Unit tests
└── docs/                       # Documentation
```

## Detailed Structure

### Raw Data Directory

**Purpose:** Store downloaded Sentinel-1 and Sentinel-2 SAFE archives

**Structure:**

```
data/raw/
├── sentinel-2/
│   ├── 2024-01-15_kiambu_hospital/
│   │   ├── S2A_MSIL2A_20240115T073611_N0510_R092_T37MCS_20240115T112233.SAFE/
│   │   │   ├── GRANULE/
│   │   │   │   └── L2A_T37MCS_A044123_20240115T074230/
│   │   │   │       ├── IMG_DATA/
│   │   │   │       │   ├── R10m/                # 10m resolution bands (B02, B03, B04, B08)
│   │   │   │       │   ├── R20m/                # 20m resolution bands
│   │   │   │       │   └── R60m/                # 60m resolution bands
│   │   │   │       ├── QI_DATA/                 # Quality indicators
│   │   │   │       │   └── MSK_CLOUDS_B00.gml   # Cloud mask
│   │   │   │       └── AUX_DATA/
│   │   │   ├── DATASTRIP/
│   │   │   ├── HTML/
│   │   │   └── manifest.safe
│   │   └── S2B_MSIL2A_20240620T073609_*.SAFE/   # Post-construction scene
│   └── 2024-02-10_mombasa_road/
│       └── ...
└── sentinel-1/
    ├── 2024-01-18_kiambu_hospital/
    │   ├── S1A_IW_GRDH_1SDV_20240118T032030_*.SAFE/
    │   │   ├── annotation/                       # Metadata XMLs
    │   │   ├── measurement/                      # GeoTIFF data files
    │   │   │   ├── s1a-iw-grd-vv-*.tiff          # VV polarization
    │   │   │   └── s1a-iw-grd-vh-*.tiff          # VH polarization
    │   │   ├── preview/                          # Quick-look images
    │   │   └── manifest.safe
    │   └── S1B_IW_GRDH_*.SAFE/                   # Post-construction scene
    └── ...
```

**Retention Policy:**

- Keep raw SAFE archives for **7 days** after processing
- Delete after processed GeoTIFFs are generated and validated
- Archive critical scenes to S3 Glacier for long-term storage

**Disk Space Estimates:**

- Sentinel-2 L2A: ~1 GB per scene (compressed)
- Sentinel-1 GRD: ~1.2 GB per scene
- 30 projects × 2 scenes (pre/post) = 60 scenes × 1 GB = **60 GB raw data**

### Processed Data Directory

**Purpose:** Store analysis outputs (GeoTIFFs, visualizations, statistics)

**Structure:**

```
data/processed/
├── ndvi/
│   ├── kiambu_hospital/
│   │   ├── baseline/
│   │   │   ├── S2A_MSIL2A_20240115_NDVI.tif              # GeoTIFF
│   │   │   ├── S2A_MSIL2A_20240115_NDVI.png              # Visualization
│   │   │   └── S2A_MSIL2A_20240115_NDVI_metadata.json    # Statistics
│   │   └── current/
│   │       ├── S2B_MSIL2A_20240620_NDVI.tif
│   │       ├── S2B_MSIL2A_20240620_NDVI.png
│   │       └── S2B_MSIL2A_20240620_NDVI_metadata.json
│   └── mombasa_road/
│       └── ...
├── sar/
│   ├── kiambu_hospital/
│   │   ├── baseline/
│   │   │   ├── S1A_20240118_VV.tif                       # VV backscatter (dB)
│   │   │   ├── S1A_20240118_VH.tif                       # VH backscatter (dB)
│   │   │   ├── S1A_20240118_SAR.png                      # RGB composite
│   │   │   └── S1A_20240118_SAR_metadata.json
│   │   └── current/
│   │       └── ...
│   └── ...
├── false_color/
│   └── {project_name}/
│       ├── {date}_FalseColor_NIR.png
│       └── ...
└── tiles/                                                # XYZ web map tiles
    ├── ndvi/
    │   └── kiambu_hospital/
    │       └── {z}/{x}/{y}.png
    └── sar/
        └── ...
```

**File Naming Convention:**

```
{sensor}_{date}_{analysis_type}.{extension}

Examples:
- S2A_20240115_NDVI.tif
- S1A_20240118_VV.tif
- S2B_20240620_FalseColor.png
```

**Retention Policy:**

- Keep **indefinitely** (used for ML training and audits)
- Compress GeoTIFFs with LZW (reduces size by 30-50%)
- Web tiles expire after **90 days** (regenerate on demand)

### Training Data Directory

**Purpose:** Store labeled training dataset for ML model

**Structure:**

```
data/training/
├── training_projects.csv                          # Master CSV with 30 projects
├── features/
│   ├── project_001_features.json                  # Extracted features
│   ├── project_002_features.json
│   └── ...
├── time_series/
│   ├── project_001_ndvi_timeseries.csv            # Monthly NDVI values
│   ├── project_001_sar_timeseries.csv
│   └── ...
└── labels/
    ├── project_001_label.json                     # Ground truth label
    └── ...
```

**training_projects.csv Format:**

```csv
project_id,project_name,county,latitude,longitude,award_date,completion_date,budget_kes,status,evidence_source
001,"Kiambu Level 4 Hospital","Kiambu",-1.0332,36.8856,2022-01-15,2023-12-31,350000000,success,"OAG Audit Report 2024"
002,"Mombasa Mtongwe Road","Mombasa",-4.0840,39.6330,2021-06-01,2023-05-30,500000000,ghost,"EACC Investigation 2023"
...
```

**Feature JSON Format:**

```json
{
  "project_id": "001",
  "features": {
    "ndvi_initial": 0.62,
    "ndvi_final": 0.18,
    "ndvi_max_drop": 0.55,
    "ndvi_slope": -0.023,
    "ndvi_recovery_ratio": 0.08,
    "clearing_detected": true,
    "months_to_clearing": 2,
    "sar_initial": -15.2,
    "sar_final": -8.4,
    "sar_increase": 6.8,
    "structure_detected": true,
    "months_active": 24,
    "progress_gap": -5,
    "contract_value_log": 19.67,
    "project_type": "health"
  },
  "label": "success"
}
```

**Time-Series CSV Format:**

```csv
date,ndvi_mean,ndvi_std,cloud_cover,valid_pixels_pct
2022-01-15,0.62,0.08,5.2,98.5
2022-02-12,0.58,0.09,12.1,95.3
2022-03-14,0.35,0.15,8.7,97.2
...
```

## File Metadata

### GeoTIFF Metadata Tags

```python
{
    "TIFFTAG_DATETIME": "2024:06:20 14:32:15",
    "TIFFTAG_SOFTWARE": "ONEKA Satellite Processing v0.1.0",
    "TIFFTAG_ARTIST": "ONEKA AI",
    "TIFFTAG_COPYRIGHT": "© 2026 ONEKA AI",
    "TIFFTAG_IMAGEDESCRIPTION": "NDVI processed from Sentinel-2 L2A",
    "project_id": "001",
    "project_name": "Kiambu Level 4 Hospital",
    "analysis_type": "NDVI_change",
    "sensor": "Sentinel-2",
    "scene_id": "S2A_MSIL2A_20240115T073611",
}
```

### JSON Metadata Schema

```json
{
  "scene_id": "S2A_MSIL2A_20240115T073611_N0510_R092_T37MCS_20240115T112233",
  "sensor": "Sentinel-2",
  "satellite": "Sentinel-2A",
  "acquisition_date": "2024-01-15",
  "processing_date": "2024-06-20T14:32:15Z",
  "analysis_type": "NDVI_change",
  "project": {
    "project_id": "001",
    "project_name": "Kiambu Level 4 Hospital",
    "county": "Kiambu",
    "coordinates": {
      "latitude": -1.0332,
      "longitude": 36.8856
    }
  },
  "aoi": {
    "center_lat": -1.0332,
    "center_lon": 36.8856,
    "radius_m": 500,
    "area_ha": 78.54
  },
  "statistics": {
    "ndvi_mean": 0.42,
    "ndvi_std": 0.12,
    "ndvi_min": -0.05,
    "ndvi_max": 0.78,
    "ndvi_median": 0.45,
    "ndvi_p25": 0.35,
    "ndvi_p75": 0.52
  },
  "quality": {
    "cloud_cover_pct": 8.5,
    "valid_pixels_pct": 95.2,
    "edge_distance_m": 2500,
    "cloud_masked": true
  },
  "processing": {
    "algorithm": "satpy",
    "version": "0.45.0",
    "parameters": {
      "mask_clouds": true,
      "resampling": "bilinear"
    }
  },
  "outputs": {
    "geotiff": "data/processed/ndvi/kiambu_hospital/baseline/S2A_MSIL2A_20240115_NDVI.tif",
    "visualization": "data/processed/ndvi/kiambu_hospital/baseline/S2A_MSIL2A_20240115_NDVI.png",
    "metadata": "data/processed/ndvi/kiambu_hospital/baseline/S2A_MSIL2A_20240115_NDVI_metadata.json"
  }
}
```

## Cloud Storage (AWS S3)

### Bucket Structure

```
s3://oneka-satellite-data/
├── raw/                        # Optional: archive critical scenes
│   └── {project_id}/
│       └── {sensor}/
│           └── {scene_id}.zip
├── processed/
│   ├── geotiffs/               # Processed GeoTIFFs
│   │   └── {project_id}/
│   │       ├── ndvi/
│   │       │   └── {scene_id}_NDVI.tif
│   │       └── sar/
│   │           ├── {scene_id}_VV.tif
│   │           └── {scene_id}_VH.tif
│   └── tiles/                  # XYZ web map tiles
│       └── {project_id}/
│           └── ndvi/{z}/{x}/{y}.png
└── training/
    ├── training_projects.csv
    ├── features/
    └── labels/
```

### S3 Lifecycle Policies

```json
{
  "Rules": [
    {
      "Id": "Archive raw data after 30 days",
      "Filter": {
        "Prefix": "raw/"
      },
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "Id": "Delete old tiles after 90 days",
      "Filter": {
        "Prefix": "processed/tiles/"
      },
      "Status": "Enabled",
      "Expiration": {
        "Days": 90
      }
    }
  ]
}
```

### Cost Optimization

**Storage Classes:**

- `S3 Standard`: Processed GeoTIFFs, training data (~$0.023/GB/month)
- `S3 Intelligent-Tiering`: Archived raw scenes (~$0.0125/GB/month after 90 days)
- `S3 Glacier`: Long-term archive (~$0.004/GB/month)

**Estimated Costs (Annual):**

- 30 projects × 24 months × 2 scenes = 1,440 scenes
- Processed GeoTIFFs: 1,440 × 50 MB = 72 GB × $0.023 = **$19.94/year**
- Tiles (90-day retention): ~20 GB × $0.023 = **$5.52/year**
- **Total S3 cost: ~$25/year**

## Backup Strategy

### Local Backup

```bash
# Daily incremental backup
rsync -avz --progress \
    ./data/processed/ \
    /mnt/backup/satellite/processed/

# Weekly full backup
tar -czf satellite_backup_$(date +%Y%m%d).tar.gz data/
```

### Cloud Backup (S3)

```bash
# Sync processed data to S3
aws s3 sync ./data/processed/ s3://oneka-satellite-data/processed/ \
    --storage-class INTELLIGENT_TIERING \
    --exclude "*.zip" \
    --exclude "*.SAFE/*"
```

### Disaster Recovery

**Recovery Time Objective (RTO):** 24 hours  
**Recovery Point Objective (RPO):** 1 day

**Procedure:**

1. Restore training data from S3: `aws s3 sync s3://... ./data/training/`
2. Restore processed GeoTIFFs: `aws s3 sync s3://... ./data/processed/`
3. Re-download critical raw scenes from Copernicus (if needed)

## Cleanup Scripts

### Automated Cleanup

```bash
#!/bin/bash
# cleanup_satellite_data.sh

# Remove raw SAFE archives older than 7 days
find ./data/raw/ -name "*.SAFE" -type d -mtime +7 -exec rm -rf {} \;

# Remove raw ZIP files older than 7 days
find ./data/raw/ -name "*.zip" -type f -mtime +7 -delete

# Remove temporary files
find ./data/ -name "*.aux.xml" -type f -delete
find ./data/ -name "*.ovr" -type f -delete

echo "Cleanup complete."
```

### Manual Cleanup

```python
# src/cleanup.py
from src.utils import clean_temp_files
from src.config import config

# Clean auxiliary files
count = clean_temp_files(config.PROCESSED_DATA_DIR, "*.tif.aux.xml")
print(f"Removed {count} temporary files")
```

---

**Last Updated:** February 9, 2026  
**Version:** 1.0  
**Author:** ONEKA AI Team
