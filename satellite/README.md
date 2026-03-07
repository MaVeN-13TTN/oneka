# ONEKA AI — Satellite Processing Module

**Sentinel-1 SAR and Sentinel-2 optical imagery processing for infrastructure construction monitoring and ghost project detection.**

This module downloads satellite scenes, computes vegetation and backscatter indices, generates web map tiles, engineers ML features, and trains the ghost project classifier.

## Processing Pipeline

```
1. DOWNLOAD           Copernicus Data Space API → .SAFE directories
       │
2. WATER FILTER       NDWIProcessor → skip sites with standing water
       │
3. OPTICAL ANALYSIS   NDVIProcessor → vegetation index + 500m AOI statistics
       │                              → temporal slope (NDVI/month)
       │
4. SAR ANALYSIS       SARProcessor  → VV/VH backscatter in dB (via SNAP)
       │
5. TILE GENERATION    TileGenerator  → XYZ tile pyramid (z8–z18) → S3
       │
6. FEATURE ENGINEERING FeatureEngineer → 10-feature vector
       │
7. ML CLASSIFICATION  RandomForest   → ghost probability (0–1)
                                     → LOW / MEDIUM / HIGH / CRITICAL
```

## Directory Structure

```
satellite/
├── src/                           # Core source code
│   ├── config.py                  # Centralized configuration (Copernicus, AWS, thresholds)
│   ├── download.py                # CopernicusDownloader — search + download scenes
│   ├── process_ndvi.py            # NDVIProcessor — Sentinel-2 vegetation analysis
│   ├── process_ndwi.py            # NDWIProcessor — water detection pre-filter
│   ├── process_sar.py             # SARProcessor — Sentinel-1 backscatter (PyroSAR/SNAP)
│   ├── feature_engineering.py     # FeatureEngineer — 10-feature ML vector
│   ├── train_model.py             # RandomForest + SMOTE training pipeline
│   ├── generate_tiles.py          # TileGenerator — XYZ web tiles from GeoTIFF
│   └── utils.py                   # Shared helpers (bbox, stats, logging, validation)
├── tests/                         # 122 isolated unit tests
│   ├── test_utils.py              # Core utility functions (parse_coords, bbox, NDVI, NDWI, stats)
│   ├── test_utils_extended.py     # Extended utils (scene IDs, filenames, file size, date ranges, dirs, statistics)
│   ├── test_feature_engineering.py # FeatureEngineer + all helper functions (48 tests)
│   ├── test_ndvi.py               # compute_ndvi_slope linear regression (7 tests)
│   ├── test_ndwi.py               # NDWIResult + NDWI formula (6 tests)
│   ├── test_config.py             # Config class constants and validation (15 tests)
│   └── test_tiles.py              # TileGenerator colormaps, constants, colormap application (10 tests)
├── scripts/
│   ├── run_training.py            # CLI entry point for model training
│   ├── validate_environment.py    # Dependency + environment checker
│   └── load_training_projects.py  # Training data analysis + visualization
├── models/                        # Trained model artefacts
│   ├── ghost_detector_v1.pkl      # Serialized sklearn pipeline (389 KB)
│   ├── model_metrics.json         # Cross-validation scores
│   ├── feature_importance.csv     # Feature importance rankings
│   ├── confusion_matrix.png       # CV confusion matrix
│   └── roc_curve.png              # ROC curve
├── data/
│   └── training/
│       └── training_projects.csv  # 30 labelled Kenya projects (20 success, 10 ghost)
├── docs/                          # Detailed documentation
│   ├── DATA_ACCESS.md
│   ├── PROCESSING_GUIDE.md
│   ├── STORAGE_STRUCTURE.md
│   └── model_performance_report.md
└── requirements.txt
```

## Quick Start

```bash
cd satellite/

# 1. Create virtual environment
uv venv venv-satellite --python 3.12

# 2. Install dependencies
uv pip install -r requirements.txt --python venv-satellite/bin/python

# 3. Configure credentials
cp .env.example .env
# Edit .env with Copernicus Data Space and AWS credentials

# 4. Validate environment
venv-satellite/bin/python scripts/validate_environment.py

# 5. Train model (from existing CSV data)
venv-satellite/bin/python scripts/run_training.py \
  --data data/training/training_projects.csv \
  --output models/
```

## Processors

### NDVI (Vegetation Index) — `src/process_ndvi.py`

Computes NDVI from Sentinel-2 Level-2A scenes: `NDVI = (B08_NIR - B04_Red) / (B08_NIR + B04_Red)`

- Loads 10m bands (B04, B08) via rasterio
- Extracts statistics for 500m radius AOI around project coordinates
- Outputs: GeoTIFF + PNG visualization (RdYlGn colormap)
- `compute_ndvi_slope()` — linear regression over time series (NDVI units/month; negative = clearing)

```bash
python src/process_ndvi.py --scene data/raw/S2A_*.SAFE --lat -1.28 --lon 36.82 --output data/processed/
```

### NDWI (Water Detection) — `src/process_ndwi.py`

Pre-filter using `NDWI = (B03_Green - B08_NIR) / (B03_Green + B08_NIR)`

- Returns `NDWIResult` with `water_present=True` when mean NDWI > 0.3
- Sites with standing water are excluded from NDVI analysis to avoid false positives
- No file output — purely a gating mechanism

### SAR (Backscatter) — `src/process_sar.py`

Processes Sentinel-1 GRD products via PyroSAR + ESA SNAP toolbox:

1. Orbit correction
2. Radiometric calibration
3. Terrain correction (Copernicus 30m DEM)
4. Border noise removal
5. Output in dB scale at 10m resolution
6. Extract VV/VH statistics for 500m AOI

```bash
python src/process_sar.py --scene data/raw/S1A_*.zip --lat -1.28 --lon 36.82 --output data/processed/
```

**Requires:** SNAP Toolbox 9.0+ (~5 GB) — [Download](https://step.esa.int/main/download/snap-download/)

### Tile Generation — `src/generate_tiles.py`

Converts processed GeoTIFFs into XYZ tile pyramids for web mapping:

- Reprojection to Web Mercator (EPSG:3857) via rasterio WarpedVRT
- Zoom levels 8–18, 256x256 PNG tiles
- Percentile clipping (2nd/98th) for normalization
- Colormaps: RdYlGn (NDVI), grayscale (SAR), Blues (NDWI)
- NaN pixels → transparent

## ML Feature Engineering — `src/feature_engineering.py`

10-feature vector for the ghost project classifier:

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 0 | `ndvi_slope` | Sentinel-2 | NDVI change rate per month (negative = clearing) |
| 1 | `sar_backscatter_delta` | Sentinel-1 | Max VV delta vs baseline (dB) |
| 2 | `divergence_score` | Backend DB | Financial progress minus physical progress (0–100) |
| 3 | `months_to_clearing` | S2 + DB | Months from award to first NDVI drop below 0.3 |
| 4 | `absorption_anomaly` | Financial | Actual minus expected linear spend (pp) |
| 5 | `contract_value_log` | Tender | log10(contract_sum_kes) |
| 6 | `project_type_encoded` | Project | health=0, education=1, roads=2, water=3, other=4 |
| 7 | `county_cloud_risk` | Static | Annual cloud fraction (0–1, all 47 Kenya counties) |
| 8 | `contractor_tier` | Contractor | NCA tier 1–8 (1 = highest capacity) |
| 9 | `phase_on_schedule` | Financial | Binary: spend within +/-20pp of linear baseline |

## Model Training — `src/train_model.py`

```
SimpleImputer(strategy='median', keep_empty_features=True)
  → StandardScaler()
  → SMOTE(k_neighbors=3)
  → RandomForestClassifier(n_estimators=200, max_depth=8, class_weight='balanced')
```

- 5-fold stratified cross-validation
- SMOTE applied inside each CV fold (not on validation data)
- `keep_empty_features=True` is critical — without it, all-NaN satellite columns collapse the feature matrix from 10 to 3

### Current Performance (CSV-only, 30 samples)

| Metric | Value | Target |
|--------|-------|--------|
| AUC | 0.56 | >= 0.80 |
| Precision (ghost) | 0.37 | >= 0.75 |
| Recall (ghost) | 0.40 | >= 0.70 |

Low performance is expected — 7 of 10 features are NaN when training from CSV only. AUC improves substantially once satellite data populates the `satellite_analyses` table.

### Feature Importance (current)

| Feature | Importance |
|---------|------------|
| `contract_value_log` | 0.431 |
| `project_type_encoded` | 0.294 |
| `county_cloud_risk` | 0.274 |
| All satellite/financial features | 0.000 (all-NaN, imputed) |

### Re-training

```bash
cd satellite
venv-satellite/bin/python scripts/run_training.py \
  --data data/training/training_projects.csv \
  --output models/ \
  --seed 42
```

Outputs: `ghost_detector_v1.pkl`, `model_metrics.json`, `feature_importance.csv`, `confusion_matrix.png`, `roc_curve.png`

## Risk Thresholds

| Ghost Probability | Risk Level |
|-------------------|------------|
| 0.00 – 0.30 | LOW |
| 0.31 – 0.60 | MEDIUM |
| 0.61 – 0.80 | HIGH |
| 0.81 – 1.00 | CRITICAL |

## Training Data

`data/training/training_projects.csv` — 30 labelled Kenya infrastructure projects:

- 20 success projects, 10 ghost projects
- 30 different counties
- Budget range: KES 45M – KES 980M
- Project types: health, roads, schools, water, markets, airports, stadiums
- Evidence: OAG Audit Reports, EACC Investigations, Parliamentary Reports

## Testing

```bash
cd satellite/

# Run full test suite (122 tests, isolated — no Copernicus, S3, or SNAP required)
venv-satellite/bin/python -m pytest tests/ -v --tb=short
```

**Test status:** 122 passed

### Test Files

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_feature_engineering.py` | 48 | All FeatureEngineer helper functions (`_classify_project_type`, `_county_cloud_risk`, `_safe_log10`, `_parse_contractor_tier`, `_months_between`, `_safe_float`), `extract_features()`, `build_training_dataframe()`, `_compute_absorption_anomaly`, `_compute_phase_on_schedule` |
| `tests/test_config.py` | 15 | Config class: singleton, paths, thresholds (NDVI, SAR, NDWI), bands, polarizations, backend URL, debug flag, validate() |
| `tests/test_utils.py` | 8 | Core utils: `parse_coordinates`, `create_bbox`, `calculate_ndvi`, `calculate_ndwi`, `extract_statistics` |
| `tests/test_utils_extended.py` | 18 | Extended utils: `format_scene_id`, `create_output_filename`, `format_file_size`, `validate_date_range`, `list_safe_directories`, `clean_temp_files`, `ensure_directory`, `extract_statistics` edge cases, `create_bbox` edge cases |
| `tests/test_tiles.py` | 10 | TileGenerator: `get_colormap_for_layer` (6 layers), constants (CRS, tile size, zoom range), `_apply_colormap` (shape, NaN handling, uniform data), `_tile_to_pixel_coords` (overlapping vs out-of-bounds) |
| `tests/test_ndvi.py` | 7 | `compute_ndvi_slope`: declining/increasing/constant trends, edge cases (too few dates, NaN values, all-NaN, two-point) |
| `tests/test_ndwi.py` | 6 | `NDWIResult` dataclass fields + defaults, `calculate_ndwi` formula correctness, clipping to [-1, 1], division-by-zero handling |

All tests run in isolation using pure computation — no Copernicus API, no S3, no SNAP toolbox, no database required.

## Backend Integration

The satellite module integrates with the backend via:

- **`RiskScoringService`** imports `FeatureEngineer` from `satellite/src/feature_engineering.py`
- **`satellite_tasks.py`** invokes satellite processing as Celery async tasks
- **`tile_tasks.py`** uses `TileGenerator` for background tile generation → S3
- Processed data populates the `satellite_analyses` PostgreSQL table
- Tiles stored in S3: `tiles/{project_uuid}/{layer}/{z}/{x}/{y}.png`

### Cross-module Import Pattern

When importing from the backend, use:
```python
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "satellite" / "src"))
from feature_engineering import FeatureEngineer  # correct
# NOT: from src.feature_engineering import ...   # conflicts with backend's src/
```

## Data Sources

| Source | Product | Resolution | Revisit | Cost |
|--------|---------|------------|---------|------|
| Sentinel-2 | Level-2A (L2A) | 10m | 5 days | Free |
| Sentinel-1 | Ground Range Detected (GRD) | 10m | 12 days | Free |

## Configuration

Key settings in `src/config.py` (reads from `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `COPERNICUS_USERNAME` | **(required)** | ESA Copernicus Data Space credentials |
| `COPERNICUS_PASSWORD` | **(required)** | ESA Copernicus Data Space credentials |
| `AWS_ACCESS_KEY_ID` | — | S3 credentials for tile/scene storage |
| `AWS_S3_BUCKET` | `oneka-satellite-data` | S3 bucket |
| `MAX_CLOUD_COVER` | 20 | Max cloud cover % for scene selection |
| `SNAP_INSTALL_DIR` | `/usr/local/snap` | ESA SNAP toolbox path |
| `NUM_WORKERS` | 4 | Parallel processing workers |

### Analysis Thresholds

| Threshold | Value | Purpose |
|-----------|-------|---------|
| NDVI clearing | 0.15 | Min drop to detect land clearing |
| NDVI healthy vegetation | 0.30 | Healthy vegetation baseline |
| SAR structure detection | 3.0 dB | Backscatter increase indicating structures |
| NDWI water | 0.30 | Water presence threshold |
| AOI radius | 500m | Analysis area around project coordinates |

## Dependencies

| Category | Key Packages |
|----------|-------------|
| Satellite Processing | satpy, pyrosar, rasterio, gdal, xarray, dask, netCDF4 |
| Data Access | sentinelsat, requests, boto3 |
| Geospatial | pyproj, geopandas, shapely, rasterstats |
| Image Processing | Pillow, opencv-python, matplotlib |
| Machine Learning | scikit-learn 1.4.0, imbalanced-learn 0.12.0, joblib |
| Data | numpy, pandas, scipy |

**System requirements:**
- GDAL system libraries: `sudo apt install gdal-bin libgdal-dev`
- SNAP Toolbox 9.0+ (for SAR processing): [Download](https://step.esa.int/main/download/snap-download/)

## Resources

- [Copernicus Data Space](https://dataspace.copernicus.eu/)
- [Sentinel-2 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi)
- [Sentinel-1 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar)
- [PyroSAR Documentation](https://pyrosar.readthedocs.io/)
- [Processing Guide](docs/PROCESSING_GUIDE.md)
- [Data Access Guide](docs/DATA_ACCESS.md)
- [Storage Structure](docs/STORAGE_STRUCTURE.md)

---

**ONEKA AI** — *Making the Invisible, Actionable*
