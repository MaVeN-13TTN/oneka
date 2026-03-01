#!/usr/bin/env python3
"""
Environment validation script for ONEKA Satellite Processing.

This script checks that all required dependencies are installed correctly
and that the environment is properly configured.
"""

import sys
from pathlib import Path


def check_import(module_name, package_name=None):
    """
    Try to import a module and report status.

    Args:
        module_name: Name of module to import
        package_name: Display name (if different from module_name)
    """
    display_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✅ {display_name}")
        return True
    except ImportError as e:
        print(f"❌ {display_name} - {e}")
        return False


def main():
    """Run environment validation checks."""
    print("=" * 70)
    print("ONEKA AI - Satellite Processing Environment Validation")
    print("=" * 70)
    print()

    # Check Python version
    print("Python Version:")
    print(f"  {sys.version}")
    if sys.version_info < (3, 11):
        print("  ⚠️  Warning: Python 3.11+ recommended")
    else:
        print("  ✅ Python version OK")
    print()

    # Check core dependencies
    print("Core Dependencies:")
    all_ok = True

    deps = [
        ("numpy", "NumPy"),
        ("pandas", "Pandas"),
        ("scipy", "SciPy"),
        ("matplotlib", "Matplotlib"),
        ("PIL", "Pillow"),
    ]

    for module, name in deps:
        all_ok &= check_import(module, name)
    print()

    # Check geospatial libraries
    print("Geospatial Libraries:")
    geo_deps = [
        ("rasterio", "Rasterio"),
        ("shapely", "Shapely"),
        ("pyproj", "PyProj"),
        ("geopandas", "GeoPandas"),
    ]

    for module, name in geo_deps:
        all_ok &= check_import(module, name)
    print()

    # Check satellite processing libraries
    print("Satellite Processing:")
    sat_deps = [
        ("sentinelsat", "SentinelSat"),
    ]

    for module, name in sat_deps:
        all_ok &= check_import(module, name)

    # Check optional libraries
    print("\nOptional (will install later):")
    optional_deps = [
        ("satpy", "Satpy"),
        ("pyrosar", "PyroSAR"),
    ]

    for module, name in optional_deps:
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError:
            print(f"⚪ {name} (not yet installed)")
    print()

    # Check utility libraries
    print("Utility Libraries:")
    util_deps = [
        ("requests", "Requests"),
        ("boto3", "Boto3"),
        ("loguru", "Loguru"),
        ("dotenv", "Python-dotenv"),
        ("yaml", "PyYAML"),
        ("tqdm", "tqdm"),
    ]

    for module, name in util_deps:
        all_ok &= check_import(module, name)
    print()

    # Check development tools
    print("Development Tools:")
    dev_deps = [
        ("pytest", "pytest"),
        ("black", "Black"),
        ("flake8", "Flake8"),
    ]

    for module, name in dev_deps:
        all_ok &= check_import(module, name)
    print()

    # Check configuration
    print("Configuration:")
    config_file = Path(__file__).parent.parent / ".env"
    if config_file.exists():
        print(f"✅ .env file found")
    else:
        print(f"⚪ .env file not found (copy from .env.example)")

    # Check data directories
    data_dir = Path(__file__).parent.parent / "data"
    if data_dir.exists():
        print(f"✅ data/ directory exists")
        subdirs = ["raw", "processed", "training"]
        for subdir in subdirs:
            path = data_dir / subdir
            if path.exists():
                print(f"  ✅ {subdir}/")
            else:
                print(f"  ⚪ {subdir}/ (will be created on first use)")
    print()

    # Check training projects CSV
    training_csv = data_dir / "training" / "training_projects.csv"
    if training_csv.exists():
        import pandas as pd

        try:
            df = pd.read_csv(training_csv)
            print(f"✅ Training projects CSV: {len(df)} projects loaded")
            successful = len(df[df["status"] == "success"])
            ghost = len(df[df["status"] == "ghost"])
            print(f"  - {successful} successful projects")
            print(f"  - {ghost} ghost projects")
        except Exception as e:
            print(f"⚠️  Training projects CSV error: {e}")
    else:
        print(f"⚪ Training projects CSV not found")
    print()

    # Summary
    print("=" * 70)
    if all_ok:
        print("✅ Environment validation PASSED")
        print("\nNext steps:")
        print("1. Copy .env.example to .env and add Copernicus credentials")
        print("2. Install Satpy: pip install satpy")
        print("3. Install PyroSAR: pip install pyrosar")
        print("4. Download SNAP toolbox from https://step.esa.int/")
        return 0
    else:
        print("❌ Environment validation FAILED")
        print("\nSome dependencies are missing. Install with:")
        print("  pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
