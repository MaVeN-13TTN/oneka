# ONEKA AI - Satellite Data Processing

**Purpose**: Satellite imagery processing pipeline for infrastructure monitoring using Sentinel-1 (SAR) and Sentinel-2 (optical) data.

## Overview

This module processes satellite imagery to detect infrastructure construction changes and generate training data for the ML-based ghost project detection system.

## Features

- **Multi-Layer Analysis**: NDVI, SAR backscatter, False Color, NDWI
- **Automated Downloads**: Copernicus Data Space API integration
- **Change Detection**: Pre/post construction comparison
- **ML Integration**: Feature extraction for Random Forest classifier

## Directory Structure

```
satellite/
├── src/                    # Source code
│   ├── download.py         # Copernicus API client
│   ├── process_ndvi.py     # Sentinel-2 NDVI calculation
│   ├── process_sar.py      # Sentinel-1 SAR processing
│   ├── utils.py            # Shared utilities
│   └── config.py           # Configuration management
├── data/                   # Data storage
│   ├── raw/                # Downloaded satellite scenes
│   ├── processed/          # Processed GeoTIFFs
│   └── training/           # Training dataset
├── tests/                  # Unit tests
├── docs/                   # Documentation
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variables template
```

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python packages
pip install -r requirements.txt

# Install SNAP toolbox (required for Sentinel-1 SAR processing)
# Download from: https://step.esa.int/main/download/snap-download/
```

### 2. Configure Credentials

```bash
cp .env.example .env
# Edit .env with your Copernicus credentials
```

### 3. Download Sample Imagery

```bash
python src/download.py --location "KIAMBU" --start-date "2024-01-01" --end-date "2024-12-31"
```

### 4. Process NDVI

```bash
python src/process_ndvi.py --scene-path "data/raw/S2A_MSIL2A_*.SAFE" --output "data/processed/"
```

## Data Sources

| Source     | Product               | Resolution | Revisit | Cost |
| ---------- | --------------------- | ---------- | ------- | ---- |
| Sentinel-2 | Level-2A (L2A)        | 10m        | 5 days  | Free |
| Sentinel-1 | Ground Range Detected | 10m        | 12 days | Free |

## Processing Workflows

### NDVI Calculation (Vegetation Index)

1. Download Sentinel-2 L2A scene
2. Extract B04 (Red) and B08 (NIR) bands
3. Calculate NDVI = (NIR - Red) / (NIR + Red)
4. Extract statistics for 500m radius AOI
5. Generate GeoTIFF and visualization

### SAR Backscatter Extraction

1. Download Sentinel-1 GRD scene
2. Apply orbit file correction
3. Radiometric calibration
4. Terrain correction (RTC)
5. Convert to dB scale
6. Extract VV/VH mean backscatter

## Integration with Backend

Processed satellite data populates the `satellite_analyses` table in PostgreSQL:

```python
POST /api/v1/satellite-analyses
{
    "project_uuid": "uuid-here",
    "sensor": "Sentinel-2",
    "acquisition_date": "2024-06-15",
    "ndvi_mean": 0.42,
    "ndvi_std": 0.12,
    "change_detected": true
}
```

## Sprint 1 Deliverables

- [x] Satellite processing environment setup
- [ ] 30 historical training projects identified
- [ ] 5 test sites with NDVI calculations
- [ ] SAR processing pipeline (prototype)
- [ ] Documentation (3 markdown files)

## Resources

- [Copernicus Data Space](https://dataspace.copernicus.eu/)
- [Satpy Documentation](https://satpy.readthedocs.io/)
- [PyroSAR Documentation](https://pyrosar.readthedocs.io/)
- [Sentinel-2 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi)
- [Sentinel-1 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar)

## Support

For questions or issues:

- Technical Lead: ML/Satellite Engineer
- Backend Integration: Backend Lead
- Sprint Planning: See `docs/05-implementation/sprint1-ml-satellite-tasks.md`

## License

MIT License - See main project LICENSE file
