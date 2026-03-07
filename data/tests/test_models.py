"""Tests for data/models.py — SQLAlchemy Core table definitions."""

import pytest

from data.models import metadata, procurement_records, geolocation_records


class TestProcurementRecordsTable:

    def test_table_name(self):
        assert procurement_records.name == "procurement_records"

    def test_primary_key(self):
        pk_cols = [c.name for c in procurement_records.primary_key]
        assert pk_cols == ["procurement_id"]

    def test_tender_number_unique(self):
        col = procurement_records.c.tender_number
        assert col.unique is True
        assert col.nullable is False

    def test_has_gps_columns(self):
        col_names = [c.name for c in procurement_records.columns]
        assert "delivery_latitude" in col_names
        assert "delivery_longitude" in col_names
        assert "gps_source" in col_names
        assert "gps_quality_score" in col_names

    def test_has_egp_tender_id(self):
        col_names = [c.name for c in procurement_records.columns]
        assert "egp_tender_id" in col_names

    def test_source_system_max_length(self):
        col = procurement_records.c.source_system
        assert col.type.length == 50

    def test_project_uuid_nullable(self):
        col = procurement_records.c.project_uuid
        assert col.nullable is True


class TestGeolocationRecordsTable:

    def test_table_name(self):
        assert geolocation_records.name == "geolocation_records"

    def test_primary_key(self):
        pk_cols = [c.name for c in geolocation_records.primary_key]
        assert pk_cols == ["geolocation_id"]

    def test_lat_lon_not_nullable(self):
        assert geolocation_records.c.latitude.nullable is False
        assert geolocation_records.c.longitude.nullable is False

    def test_has_match_fields(self):
        col_names = [c.name for c in geolocation_records.columns]
        assert "match_confidence" in col_names
        assert "match_method" in col_names
        assert "match_score" in col_names

    def test_verified_default(self):
        col = geolocation_records.c.verified
        assert col.default is not None


class TestMetadata:

    def test_both_tables_in_metadata(self):
        table_names = list(metadata.tables.keys())
        assert "procurement_records" in table_names
        assert "geolocation_records" in table_names
