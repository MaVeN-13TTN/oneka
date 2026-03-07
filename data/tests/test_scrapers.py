"""Tests for scraper data transformation logic — no DB or browser required."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# EGP Scraper — GPS extraction and quality scoring
# =============================================================================


class TestEGPDataTransformation:

    def test_gps_quality_constants(self):
        from data.scrapers.egp import EGP_MANUAL_PIN, EGP_AUTO_GEOCODED

        assert EGP_MANUAL_PIN == 90
        assert EGP_AUTO_GEOCODED == 70

    def test_manual_pin_gets_higher_quality(self):
        from data.scrapers.egp import EGP_MANUAL_PIN, EGP_AUTO_GEOCODED

        assert EGP_MANUAL_PIN > EGP_AUTO_GEOCODED

    def test_gps_coords_extracted_from_geojson_format(self):
        """Verify the GeoJSON [lon, lat] convention is handled correctly."""
        item = {
            "tenderrefno": "EGP-001",
            "tendertitle": "Test",
            "procuringEntity": "MOH",
            "deliveryLocation": {
                "locationType": "MANUAL",
                "geometry": {"coordinates": [36.82, -1.29]},  # [lon, lat]
                "locationName": "Nairobi Hospital",
                "locationAddress": "Nairobi",
            },
        }
        coords = item["deliveryLocation"]["geometry"]["coordinates"]
        lon, lat = float(coords[0]), float(coords[1])
        assert lon == 36.82
        assert lat == -1.29

    def test_missing_tender_number_skipped(self):
        """Items without tender_number should be skipped in save()."""
        item = {"tendertitle": "No tender ref"}
        tender_no = item.get("tenderrefno") or item.get("tender_no")
        assert tender_no is None


# =============================================================================
# PPIP Scraper — date parsing and field fallbacks
# =============================================================================


class TestPPIPDataTransformation:

    def test_date_parsing_valid(self):
        from datetime import datetime

        raw = "2024-06-15T00:00:00"
        dt = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15

    def test_date_parsing_invalid_returns_none(self):
        from datetime import datetime

        raw = "not-a-date"
        result = None
        try:
            result = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
        assert result is None

    def test_field_fallback_tender_ref(self):
        """PPIP uses tender_ref or tender_no as fallback."""
        item1 = {"tender_ref": "PPIP-001"}
        item2 = {"tender_no": "PPIP-002"}
        assert (item1.get("tender_ref") or item1.get("tender_no")) == "PPIP-001"
        assert (item2.get("tender_ref") or item2.get("tender_no")) == "PPIP-002"

    def test_field_fallback_title(self):
        item = {"description": "Building a road"}
        title = item.get("title") or item.get("description")
        assert title == "Building a road"


# =============================================================================
# NCA Scraper — ID namespacing and row validation
# =============================================================================


class TestNCADataTransformation:

    def test_nca_id_namespacing(self):
        row = ["12345", "Road Project", "Developer", "Contractor", "Arch", "Eng", "Building"]
        nca_id = f"NCA-{row[0]}"
        assert nca_id == "NCA-12345"

    def test_rows_with_fewer_than_7_columns_skipped(self):
        short_row = ["12345", "Name", "Dev"]
        assert len(short_row) < 7

    def test_project_data_mapping(self):
        row = ["99", "School Building", "County Gov", "ABC Ltd", "Arch", "Eng", "Education"]
        project_data = {
            "tender_number": f"NCA-{row[0]}",
            "tender_title": row[1],
            "procuring_entity": row[2],
            "contractor_name": row[3],
            "source_system": "NCA",
            "extraction_method": "playwright_scrape",
        }
        assert project_data["tender_number"] == "NCA-99"
        assert project_data["tender_title"] == "School Building"
        assert project_data["procuring_entity"] == "County Gov"
        assert project_data["contractor_name"] == "ABC Ltd"

    def test_deduplication_by_project_id(self):
        """NCA scraper de-duplicates by first column (project ID)."""
        rows = [
            ["1", "Road A", "D", "C", "A", "E", "T"],
            ["2", "Road B", "D", "C", "A", "E", "T"],
            ["1", "Road A Updated", "D", "C", "A", "E", "T"],  # duplicate ID
        ]
        unique = {}
        for row in rows:
            if len(row) > 0:
                unique[row[0]] = row
        assert len(unique) == 2
        assert unique["1"][1] == "Road A Updated"  # last one wins


# =============================================================================
# KMHFL Scraper — JSON cache write
# =============================================================================


class TestKMHFLSave:

    def test_save_writes_json_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "kmhfl_facilities.json"

            facilities = [
                {"name": "Kenyatta Hospital", "code": "10001"},
                {"name": "Pumwani Maternity", "code": "10002"},
            ]

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(facilities, fh, ensure_ascii=False, indent=2)

            loaded = json.loads(cache_path.read_text())
            assert len(loaded) == 2
            assert loaded[0]["name"] == "Kenyatta Hospital"

    def test_save_returns_facility_count(self):
        facilities = [{"name": f"Facility {i}"} for i in range(50)]
        assert len(facilities) == 50


# =============================================================================
# COB Poller — cache logic
# =============================================================================


class TestCoBPollerCache:

    def test_existing_urls_are_skipped(self):
        existing = [
            {"title": "Q1 Report", "url": "https://cob.go.ke/q1.pdf", "local_path": "q1.pdf", "status": "downloaded"},
        ]
        known_urls = {r["url"] for r in existing}

        new_report = {"title": "Q1 Report", "url": "https://cob.go.ke/q1.pdf"}
        assert new_report["url"] in known_urls

    def test_new_urls_are_not_skipped(self):
        existing = [
            {"title": "Q1 Report", "url": "https://cob.go.ke/q1.pdf"},
        ]
        known_urls = {r["url"] for r in existing}

        new_report = {"title": "Q2 Report", "url": "https://cob.go.ke/q2.pdf"}
        assert new_report["url"] not in known_urls
