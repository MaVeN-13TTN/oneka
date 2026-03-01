# ONEKA AI - Satellite Module Quick Start

## Sprint 1 Environment Setup: ✅ COMPLETE

### What's Working Now

**✅ Fully Functional**:

- Virtual environment with Python 3.12.3
- 60+ packages installed (NumPy, Pandas, Rasterio, GeoPandas, Satpy)
- NDVI processing script (Sentinel-2)
- Satellite download script (Copernicus API)
- Training dataset (30 projects identified)
- Environment validation passing

**⚠️ Requires Additional Setup**:

- PyroSAR (needs GDAL system libraries)
- SNAP toolbox (optional for advanced SAR)
- Copernicus credentials (register at Copernicus Data Space)

---

## Next Steps to Start Processing

### 1. Install GDAL (Optional - for SAR processing)

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install libgdal-dev gdal-bin python3-gdal

# Activate venv
cd /home/meyvn/Desktop/K1NYANJU1/Cracked-Dev/oneka/satellite
source venv/bin/activate

# Install GDAL Python bindings
pip install gdal==$(gdal-config --version)

# Verify PyroSAR now works
python -c "import pyroSAR; print('✅ PyroSAR:', pyroSAR.__version__)"
```

### 2. Register for Copernicus Data Access

1. Go to https://dataspace.copernicus.eu/
2. Click "Register" and create account
3. Verify email
4. Note your username and password

### 3. Configure Credentials

```bash
cd /home/meyvn/Desktop/K1NYANJU1/Cracked-Dev/oneka/satellite
nano .env

# Add your credentials:
COPERNICUS_USERNAME=your_username_here
COPERNICUS_PASSWORD=your_password_here
```

### 4. Test Satellite Download (2 projects)

```bash
source venv/bin/activate

# Test 1: Kiambu Hospital (Success project)
python src/download.py \
  --lat -1.0332 \
  --lon 36.8856 \
  --start-date 2022-01-15 \
  --end-date 2022-06-15 \
  --sensor sentinel-2 \
  --max-cloud 20 \
  --max-scenes 2

# Test 2: Mombasa Road (Ghost project)
python src/download.py \
  --lat -4.0840 \
  --lon 39.6330 \
  --start-date 2021-06-01 \
  --end-date 2021-12-01 \
  --sensor sentinel-2 \
  --max-cloud 20 \
  --max-scenes 2
```

### 5. Process NDVI for Downloaded Scenes

```bash
# Find downloaded scene
ls data/raw/

# Process NDVI (example)
python src/process_ndvi.py \
  --scene ./data/raw/S2A_MSIL2A_20220315T073621_N0400_*.SAFE \
  --lat -1.0332 \
  --lon 36.8856 \
  --radius 500 \
  --output ./data/processed/
```

### 6. Analyze Results

```bash
# View NDVI GeoTIFF in QGIS or:
python -c "
import rasterio
import matplotlib.pyplot as plt

with rasterio.open('data/processed/kiambu_hospital_2022-03-15_ndvi.tif') as src:
    ndvi = src.read(1)
    plt.imshow(ndvi, cmap='RdYlGn', vmin=-1, vmax=1)
    plt.colorbar(label='NDVI')
    plt.title('Kiambu Hospital - NDVI')
    plt.show()
"
```

---

## Useful Commands

### Activate Environment

```bash
cd /home/meyvn/Desktop/K1NYANJU1/Cracked-Dev/oneka/satellite
source venv/bin/activate
```

### Validate Setup

```bash
python scripts/validate_environment.py
```

### View Training Projects

```bash
python scripts/load_training_projects.py
```

### List Installed Packages

```bash
pip list
```

### Run Tests

```bash
pytest tests/ -v
```

### Check Processing Scripts Help

```bash
python src/download.py --help
python src/process_ndvi.py --help
python src/process_sar.py --help
```

---

## Directory Structure

```
satellite/
├── data/
│   ├── raw/              # Downloaded satellite scenes
│   ├── processed/        # NDVI/SAR outputs
│   └── training/         # Training projects CSV
├── src/
│   ├── config.py          # Configuration management
│   ├── utils.py           # Utility functions
│   ├── download.py        # Download Sentinel scenes
│   ├── process_ndvi.py    # NDVI processing
│   └── process_sar.py     # SAR processing
├── scripts/
│   ├── validate_environment.py    # Check setup
│   └── load_training_projects.py  # Analyze training data
├── docs/
│   ├── DATA_ACCESS.md             # Copernicus guide
│   ├── PROCESSING_GUIDE.md        # Processing methodology
│   ├── STORAGE_STRUCTURE.md       # File organization
│   └── TRAINING_DATA_PLAN.md      # Data collection plan
├── tests/                # Unit tests
├── .env                  # Configuration (add credentials here)
├── requirements.txt      # Dependencies
└── README.md             # Project overview
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'osgeo'"

**Issue**: PyroSAR requires GDAL  
**Solution**: Install GDAL system libraries (see Step 1 above)

### "Authentication failed" when downloading

**Issue**: Copernicus credentials not configured  
**Solution**: Add credentials to `.env` file (see Step 3 above)

### "No scenes found"

**Issue**: Date range or cloud cover too restrictive  
**Solution**: Expand date range or increase `--max-cloud` threshold

### "Memory error" when processing

**Issue**: Large satellite scenes (100+ MB)  
**Solution**: Reduce AOI radius with `--radius 250` or use Satpy backend

---

## Key Files

- **Training Dataset**: [data/training/training_projects.csv](data/training/training_projects.csv)
- **Environment Config**: [.env](.env)
- **Sprint 1 Report**: [SPRINT1_COMPLETION.md](SPRINT1_COMPLETION.md)
- **Project README**: [README.md](README.md)

---

## Support & Documentation

- **Copernicus API Docs**: https://documentation.dataspace.copernicus.eu/
- **SentinelSat Guide**: https://sentinelsat.readthedocs.io/
- **Satpy Documentation**: https://satpy.readthedocs.io/
- **PyroSAR Documentation**: https://pyrosar.readthedocs.io/

---

## Sprint 1 Status: ✅ COMPLETE

**Ready for**: Data collection and processing (Sprint 2)

**Last Updated**: February 10, 2026
