# Satellite Processing Guide

## Overview

This guide covers the satellite imagery processing workflows for ONEKA AI's infrastructure monitoring system, including NDVI calculation, SAR backscatter extraction, and quality control procedures.

## NDVI Processing (Sentinel-2)

### Methodology

**NDVI (Normalized Difference Vegetation Index)** measures vegetation health and density.

**Formula:**

```
NDVI = (NIR - Red) / (NIR + Red)
```

**Bands Used:**

- NIR (Near-Infrared): Sentinel-2 Band 8 (B08) @ 10m resolution
- Red: Sentinel-2 Band 4 (B04) @ 10m resolution

**Value Interpretation:**
| NDVI Range | Interpretation | Construction Relevance |
|------------|----------------|------------------------|
| -1.0 to 0.0 | Water, bare soil, rock | Construction site, excavation |
| 0.0 to 0.1 | Barren areas, sand | Cleared land |
| 0.1 to 0.3 | Sparse vegetation | Recent clearing or regrowth |
| 0.3 to 0.6 | Moderate vegetation | Untouched or abandoned |
| 0.6 to 1.0 | Dense vegetation | Forest, farmland |

### Processing Workflow

#### Step 1: Scene Selection

```bash
# Download Sentinel-2 scenes
python src/download.py \
    --lat -1.0332 \
    --lon 36.8856 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --sensor sentinel-2 \
    --max-cloud 20 \
    --max-scenes 2
```

**Quality Criteria:**

- Cloud cover < 20% for the AOI
- Avoid rainy season for pre-construction baseline (March-May, Oct-Dec)
- Select scenes during dry season for clearer visualization

#### Step 2: NDVI Calculation

```bash
# Process NDVI
python src/process_ndvi.py \
    --scene ./data/raw/S2A_MSIL2A_*.SAFE \
    --lat -1.0332 \
    --lon 36.8856 \
    --output ./data/processed/
```

**Outputs:**

1. `{scene_id}_NDVI.tif` - GeoTIFF with NDVI values
2. `{scene_id}_NDVI.png` - Color-coded visualization

#### Step 3: Statistical Extraction

The processor automatically extracts statistics for a 500m radius AOI:

```python
{
    "mean": 0.42,      # Average NDVI
    "std": 0.12,       # Standard deviation
    "min": -0.05,      # Minimum value
    "max": 0.78,       # Maximum value
    "median": 0.45,    # Median value
    "p25": 0.35,       # 25th percentile
    "p75": 0.52        # 75th percentile
}
```

### Change Detection

**Construction Indicators:**

1. **NDVI Drop > 0.15**: Significant vegetation clearing

   ```
   Baseline NDVI: 0.55 (dense vegetation)
   After clearing: 0.12 (bare soil)
   Drop: 0.43 → Construction likely started
   ```

2. **Recovery > 50%**: Abandonment signal

   ```
   Post-clearing: 0.15
   6 months later: 0.48
   Recovery: 220% → Project stalled/abandoned
   ```

3. **Stable Low NDVI**: Active construction
   ```
   Month 1: 0.14
   Month 3: 0.18
   Month 6: 0.16
   Stability: Ongoing construction
   ```

### Quality Control

**Cloud Masking:**

- Use Scene Classification Layer (SCL) from Sentinel-2 L2A
- Mask pixels classified as clouds, cloud shadows, cirrus
- Minimum valid pixel threshold: 80% of AOI

**Edge Effects:**

- Exclude pixels within 50m of scene boundaries
- Avoid scenes where AOI is near edge

**Seasonal Filtering:**

- Compare scenes from same season (dry vs. dry, wet vs. wet)
- Kenya dry seasons: Jan-Feb, Jun-Sep
- Kenya wet seasons: Mar-May, Oct-Dec

## SAR Processing (Sentinel-1)

### Methodology

**SAR (Synthetic Aperture Radar)** uses microwave pulses to detect ground texture and structures.

**Advantages:**

- All-weather (penetrates clouds)
- Day/night imaging
- Sensitive to vertical structures (buildings)

**Polarizations:**

- **VV**: Vertical transmit, Vertical receive (penetrates vegetation)
- **VH**: Vertical transmit, Horizontal receive (sensitive to volume scattering)

**Backscatter Interpretation:**
| Backscatter (dB) | Surface Type | Construction Relevance |
|------------------|--------------|------------------------|
| -25 to -20 | Smooth surfaces (water, pavement) | Roads, cleared land |
| -20 to -15 | Rough surfaces (bare soil) | Active construction |
| -15 to -10 | Vegetation, grassland | Untouched land |
| -10 to -5 | Dense vegetation, forest | Natural land |
| -5 to 0 | Urban structures, buildings | Completed construction |

### Processing Workflow

#### Step 1: Download SAR Scenes

```bash
python src/download.py \
    --lat -1.0332 \
    --lon 36.8856 \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --sensor sentinel-1 \
    --max-scenes 2
```

#### Step 2: Geocoding and Calibration

**Prerequisites:**

- SNAP Toolbox installed (https://step.esa.int/main/download/snap-download/)
- PyroSAR configured with SNAP GPT

**Process:**

```bash
python src/process_sar.py \
    --scene ./data/raw/S1A_IW_GRDH_*.SAFE \
    --lat -1.0332 \
    --lon 36.8856 \
    --output ./data/processed/
```

**Processing Chain:**

1. **Apply Orbit File**: Correct satellite position
2. **Radiometric Calibration**: Convert DN to sigma0
3. **Terrain Correction**: Remove topographic distortion (RTC)
4. **Border Noise Removal**: Eliminate edge artifacts
5. **Conversion to dB**: Logarithmic scaling for visualization

#### Step 3: Backscatter Extraction

```python
{
    "VV": {
        "mean": -12.5,  # dB
        "std": 3.2,
        "min": -20.1,
        "max": -5.4
    },
    "VH": {
        "mean": -18.7,  # dB
        "std": 2.8,
        "min": -25.3,
        "max": -10.2
    }
}
```

### Change Detection

**Structure Emergence:**

```
Baseline VV: -15 dB (bare soil)
After construction: -8 dB (concrete structures)
Increase: +7 dB → Buildings detected
```

**Typical Backscatter Changes:**
| Surface Transition | VV Change (dB) | Interpretation |
|--------------------|----------------|----------------|
| Vegetation → Bare soil | -2 to -4 | Land clearing |
| Bare soil → Concrete | +5 to +8 | Construction |
| Bare soil → Vegetation | +3 to +5 | Abandonment |

### Quality Control

**Speckle Filtering:**

- SAR data has inherent speckle noise
- SNAP applies Lee Sigma filter (7×7 window)
- Reduces noise while preserving edges

**Incidence Angle:**

- Optimal: 30-40 degrees
- Avoid scenes with extreme angles (> 45°)

**Temporal Coherence:**

- Compare scenes from same orbit (ascending/descending)
- 12-day repeat cycle for Sentinel-1

## Multi-Layer Analysis

### False Color Composite

**Purpose:** Visual verification for training data labeling

**Bands:**

- R: NIR (B08)
- G: Red (B04)
- B: Green (B03)

**Interpretation:**

- Vegetation: Bright red/pink
- Infrastructure: Blue/cyan
- Bare soil: Brown/tan
- Water: Black/dark blue

**Creation:**

```python
from satpy import Scene

scn = Scene(reader='msi_safe', filenames=['*.SAFE'])
scn.load(['true_color'])
scn.save_datasets(writer='simple_image', filename='false_color_NIR.png')
```

### NDWI (Water Index)

**Purpose:** Filter false positives from seasonal flooding

**Formula:**

```
NDWI = (Green - NIR) / (Green + NIR)
```

**Threshold:** NDWI > 0.3 indicates water presence

**Use Case:**

```
NDVI drop from 0.6 to 0.2 detected
Check NDWI: 0.45 (water present)
Conclusion: Seasonal flooding, not construction
Action: Exclude this scene from analysis
```

## Storage and Output Formats

### GeoTIFF Format

**Specifications:**

- Data type: Float32
- Compression: LZW
- Nodata value: NaN
- CRS: EPSG:4326 (WGS84)
- Resolution: 10m (Sentinel-2 and Sentinel-1)

### Visualization Format

**PNG Specifications:**

- DPI: 150
- Dimensions: 1000×800 pixels
- Color map: RdYlGn (Red-Yellow-Green)
- Title: Scene ID + date

### Metadata JSON

```json
{
  "scene_id": "S2A_MSIL2A_20240615T073611",
  "sensor": "Sentinel-2",
  "acquisition_date": "2024-06-15",
  "processing_date": "2024-06-20",
  "analysis_type": "NDVI_change",
  "aoi": {
    "lat": -1.0332,
    "lon": 36.8856,
    "radius_m": 500
  },
  "statistics": {
    "ndvi_mean": 0.42,
    "ndvi_std": 0.12,
    "ndvi_min": -0.05,
    "ndvi_max": 0.78
  },
  "cloud_cover": 8.5,
  "quality_flags": {
    "valid_pixels_pct": 95.2,
    "cloud_masked": true
  }
}
```

## Best Practices

### 1. Temporal Baseline Selection

**Pre-Construction:**

- Use scene closest to award date
- Ensure vegetation is stable (not seasonal peak/trough)
- Verify no pre-existing construction

**Post-Construction:**

- Use scene from expected completion date
- Allow 1-2 months after completion for vegetation stabilization
- For ongoing projects: monthly monitoring

### 2. Seasonal Considerations

**Kenya Climate Zones:**

| Region                    | Dry Season       | Wet Season       |
| ------------------------- | ---------------- | ---------------- |
| Central (Nairobi, Kiambu) | Jan-Feb, Jun-Sep | Mar-May, Oct-Dec |
| Coast (Mombasa)           | Jan-Mar, Jul-Oct | Apr-Jun, Nov-Dec |
| Western (Kisumu)          | Jan-Feb, Jun-Aug | Mar-May, Sep-Dec |

**Recommendation:** Compare scenes from same season to avoid vegetation cycle effects

### 3. Multi-Sensor Fusion

**Optimal Workflow:**

1. Use Sentinel-2 NDVI during dry season (clear skies)
2. Use Sentinel-1 SAR during wet season (cloud-free)
3. Cross-validate: NDVI drop + SAR increase = high confidence

### 4. Error Handling

**Common Issues:**

| Issue                | Detection            | Mitigation              |
| -------------------- | -------------------- | ----------------------- |
| Cloud contamination  | NDVI < -0.5 in AOI   | Use SAR instead         |
| Missing bands        | File not found error | Re-download scene       |
| Geometric distortion | Misaligned overlays  | Reproject to common CRS |
| Speckle noise (SAR)  | High std deviation   | Apply Lee filter        |

## Performance Optimization

### Processing Time Estimates

| Task                  | Sentinel-2 | Sentinel-1 |
| --------------------- | ---------- | ---------- |
| Download (1 scene)    | 5-15 min   | 8-20 min   |
| NDVI calculation      | 2-5 min    | N/A        |
| SAR geocoding         | N/A        | 10-30 min  |
| Statistics extraction | < 1 min    | < 1 min    |
| Visualization         | < 1 min    | < 1 min    |

### Parallelization

```python
from concurrent.futures import ProcessPoolExecutor

def process_scene(scene_path):
    processor = NDVIProcessor(scene_path)
    return processor.process(lat, lon, output_dir)

# Process multiple scenes in parallel
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(process_scene, scene_paths))
```

## Integration with Backend

### API Submission

```python
import requests

results = processor.process(lat, lon, output_dir)

# Submit to backend
response = requests.post(
    f"{config.BACKEND_API_URL}/api/v1/satellite-analyses",
    json={
        "project_uuid": "abc-123-def",
        "sensor": results["sensor"],
        "acquisition_date": results["acquisition_date"],
        "analysis_type": "NDVI_change",
        "ndvi_mean": results["statistics"]["mean"],
        "ndvi_std": results["statistics"]["std"],
        "ndvi_min": results["statistics"]["min"],
        "ndvi_max": results["statistics"]["max"],
        "image_url": results["geotiff_path"],
        "processing_algorithm": "satpy",
    },
    headers={"Authorization": f"Bearer {config.BACKEND_API_KEY}"}
)
```

---

**Last Updated:** February 9, 2026  
**Version:** 1.0  
**Author:** ONEKA AI Team
