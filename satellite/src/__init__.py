"""
ONEKA AI - Satellite Data Processing Module

This package provides tools for processing Sentinel-1 and Sentinel-2 satellite
imagery for infrastructure monitoring and ghost project detection.
"""

__version__ = "0.1.0"
__author__ = "ONEKA AI Team"
__license__ = "MIT"

# Package metadata
PACKAGE_NAME = "oneka-satellite"
DESCRIPTION = "Satellite imagery processing for infrastructure auditing"

# Supported sensors
SUPPORTED_SENSORS = ["Sentinel-1", "Sentinel-2", "SkySat"]

# Analysis types
ANALYSIS_TYPES = [
    "NDVI_change",
    "SAR_backscatter",
    "False_Color",
    "NDWI_water",
]
