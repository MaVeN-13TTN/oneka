"""
Tests for database models.
"""

import pytest
from sqlalchemy import select
from datetime import datetime, date
from decimal import Decimal

from src.models import (
    Project,
    ProjectStatus,
    ProjectType,
    RiskLevel,
    ProcurementRecord,
    GeolocationRecord,
    FinancialRecord,
    SatelliteAnalysis,
)


class TestProjectModel:
    """Test Project model"""

    def test_create_project(self, test_db):
        """Test creating a project"""
        project = Project(
            project_name="Test Hospital",
            project_type=ProjectType.HEALTH,
            county="Nairobi",
            ward="Westlands",
            status=ProjectStatus.AWARDED,
            estimated_value_kes=Decimal("500000000.00"),
        )

        test_db.add(project)
        test_db.commit()
        test_db.refresh(project)

        assert project.project_uuid is not None
        assert project.project_name == "Test Hospital"
        assert project.project_type == ProjectType.HEALTH
        assert project.status == ProjectStatus.AWARDED
        assert project.created_at is not None

    def test_project_relationships(self, test_db):
        """Test project relationships cascade"""
        project = Project(
            project_name="Test Road",
            project_type=ProjectType.ROADS,
            county="Kiambu",
            status=ProjectStatus.ONGOING,
        )

        test_db.add(project)
        test_db.commit()

        # Add related records
        procurement = ProcurementRecord(
            project_uuid=project.project_uuid,
            source_system="PPIP",
            tender_number="TEST/2026/001",
            contractor_name="ABC Construction",
        )
        test_db.add(procurement)
        test_db.commit()

        # Verify relationship
        test_db.refresh(project)
        assert len(project.procurement_records) == 1
        assert project.procurement_records[0].tender_number == "TEST/2026/001"


class TestProcurementRecordModel:
    """Test ProcurementRecord model"""

    def test_create_procurement_record(self, test_db):
        """Test creating procurement record"""
        project = Project(
            project_name="Test Project",
            project_type=ProjectType.WATER,
            county="Mombasa",
            status=ProjectStatus.AWARDED,
        )
        test_db.add(project)
        test_db.commit()

        procurement = ProcurementRecord(
            project_uuid=project.project_uuid,
            source_system="PPIP",
            tender_number="MOH/2026/0089",
            contractor_name="XYZ Ltd",
            award_date=date(2026, 1, 15),
            contract_sum_kes=Decimal("250000000.00"),
        )

        test_db.add(procurement)
        test_db.commit()
        test_db.refresh(procurement)

        assert procurement.tender_number == "MOH/2026/0089"
        assert procurement.award_date == date(2026, 1, 15)


class TestGeolocationRecordModel:
    """Test GeolocationRecord model"""

    def test_create_geolocation_record(self, test_db):
        """Test creating geolocation record"""
        project = Project(
            project_name="GPS Test",
            project_type=ProjectType.EDUCATION,
            county="Nakuru",
            status=ProjectStatus.ONGOING,
        )
        test_db.add(project)
        test_db.commit()

        geolocation = GeolocationRecord(
            project_uuid=project.project_uuid,
            latitude=Decimal("-1.2921"),
            longitude=Decimal("36.8219"),
            verified=True,
            match_confidence=Decimal("95.5"),
        )

        test_db.add(geolocation)
        test_db.commit()
        test_db.refresh(geolocation)

        assert geolocation.latitude == Decimal("-1.2921")
        assert geolocation.longitude == Decimal("36.8219")
        assert geolocation.verified is True


class TestFinancialRecordModel:
    """Test FinancialRecord model"""

    def test_create_financial_record(self, test_db):
        """Test creating financial record"""
        project = Project(
            project_name="Finance Test",
            project_type=ProjectType.OTHER,
            county="Kisumu",
            status=ProjectStatus.ONGOING,
        )
        test_db.add(project)
        test_db.commit()

        financial = FinancialRecord(
            project_uuid=project.project_uuid,
            source_system="COB",
            fiscal_year="2025/2026",
            budget_allocated_kes=Decimal("300000000.00"),
            budget_absorbed_kes=Decimal("180000000.00"),
            absorption_rate=Decimal("60.0"),
        )

        test_db.add(financial)
        test_db.commit()
        test_db.refresh(financial)

        assert financial.budget_allocated_kes == Decimal("300000000.00")
        assert financial.absorption_rate == Decimal("60.0")


class TestSatelliteAnalysisModel:
    """Test SatelliteAnalysis model"""

    def test_create_satellite_analysis(self, test_db):
        """Test creating satellite analysis"""
        project = Project(
            project_name="Satellite Test",
            project_type=ProjectType.OTHER,
            county="Eldoret",
            status=ProjectStatus.ONGOING,
        )
        test_db.add(project)
        test_db.commit()

        satellite = SatelliteAnalysis(
            project_uuid=project.project_uuid,
            sensor="Sentinel-2",
            acquisition_date=date(2026, 2, 9),
            analysis_type="NDVI_change",
            ndvi_mean=Decimal("0.65"),
            sar_vv_mean=Decimal("-12.42"),
            change_detected=True,
        )

        test_db.add(satellite)
        test_db.commit()
        test_db.refresh(satellite)

        assert satellite.sensor == "Sentinel-2"
        assert satellite.ndvi_mean == Decimal("0.65")
        assert satellite.change_detected is True
