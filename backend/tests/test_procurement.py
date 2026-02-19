"""
Tests for procurement endpoints and services.
"""

import pytest
from fastapi import status
from decimal import Decimal
from datetime import date
from unittest.mock import Mock, patch, MagicMock

from src.models.procurement import ProcurementRecord
from src.schemas.procurement import ProcurementRecordCreate, ScraperStats


class TestProcurementEndpoints:
    """Test procurement API endpoints"""

    def test_create_procurement_record(self, client, test_db):
        """Test creating a procurement record via API"""
        procurement_data = {
            "source_system": "PPIP",
            "tender_number": "TEST/2026/001",
            "tender_title": "Construction of Health Center",
            "procuring_entity": "Ministry of Health",
            "contract_sum_kes": "50000000.00",
            "contractor_name": "ABC Contractors Ltd",
            "extraction_method": "api",
        }

        response = client.post("/api/v1/procurement", json=procurement_data)

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["tender_number"] == "TEST/2026/001"
        assert data["source_system"] == "PPIP"
        assert "procurement_id" in data
        assert "created_at" in data

    def test_create_duplicate_tender_number(self, client, test_db):
        """Test that duplicate tender numbers are rejected"""
        procurement_data = {
            "source_system": "PPIP",
            "tender_number": "DUPLICATE/2026/001",
            "tender_title": "Test Tender",
            "procuring_entity": "Test Entity",
        }

        # Create first record
        response1 = client.post("/api/v1/procurement", json=procurement_data)
        assert response1.status_code == status.HTTP_201_CREATED

        # Attempt to create duplicate
        response2 = client.post("/api/v1/procurement", json=procurement_data)
        assert response2.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_procurement_record(self, client, test_db):
        """Test retrieving a procurement record by ID"""
        # Create a record first
        procurement_data = {
            "source_system": "PPIP",
            "tender_number": "GET/2026/001",
            "tender_title": "Test Tender",
        }
        create_response = client.post("/api/v1/procurement", json=procurement_data)
        procurement_id = create_response.json()["procurement_id"]

        # Get the record
        response = client.get(f"/api/v1/procurement/{procurement_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["procurement_id"] == procurement_id
        assert data["tender_number"] == "GET/2026/001"

    def test_get_nonexistent_procurement(self, client, test_db):
        """Test getting a procurement record that doesn't exist"""
        response = client.get("/api/v1/procurement/99999")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_procurement_records(self, client, test_db):
        """Test listing procurement records with pagination"""
        # Create multiple records
        for i in range(5):
            procurement_data = {
                "source_system": "PPIP",
                "tender_number": f"LIST/2026/{i:03d}",
                "tender_title": f"Test Tender {i}",
            }
            client.post("/api/v1/procurement", json=procurement_data)

        # List with pagination
        response = client.get("/api/v1/procurement?page=1&page_size=3")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 3
        assert len(data["records"]) == 3
        assert data["total"] >= 5

    def test_list_with_source_filter(self, client, test_db):
        """Test listing with source system filter"""
        # Create records with different sources
        client.post(
            "/api/v1/procurement",
            json={"source_system": "PPIP", "tender_number": "PPIP/001"},
        )
        client.post(
            "/api/v1/procurement",
            json={"source_system": "eGP", "tender_number": "EGP/001"},
        )

        # Filter by PPIP
        response = client.get("/api/v1/procurement?source_system=PPIP")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for record in data["records"]:
            assert record["source_system"] == "PPIP"

    def test_list_with_search(self, client, test_db):
        """Test listing with search query"""
        client.post(
            "/api/v1/procurement",
            json={
                "source_system": "PPIP",
                "tender_number": "SEARCH/001",
                "tender_title": "Hospital Construction",
            },
        )

        response = client.get("/api/v1/procurement?search=Hospital")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] >= 1
        assert any(
            "Hospital" in r["tender_title"]
            for r in data["records"]
            if r["tender_title"]
        )

    def test_get_by_tender_number(self, client, test_db):
        """Test getting procurement by tender number"""
        tender_number = "TENDER_NUM/2026/001"
        client.post(
            "/api/v1/procurement",
            json={
                "source_system": "PPIP",
                "tender_number": tender_number,
                "tender_title": "Test",
            },
        )

        # Use URL encoding for tender number with slashes
        import urllib.parse

        encoded_tender = urllib.parse.quote(tender_number, safe="")
        response = client.get(
            f"/api/v1/procurement/search?tender_number={encoded_tender}"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tender_number"] == tender_number

    def test_update_procurement_record(self, client, test_db):
        """Test updating a procurement record"""
        # Create record
        create_response = client.post(
            "/api/v1/procurement",
            json={
                "source_system": "PPIP",
                "tender_number": "UPDATE/001",
                "tender_title": "Original Title",
            },
        )
        procurement_id = create_response.json()["procurement_id"]

        # Update record
        update_data = {
            "tender_title": "Updated Title",
            "contractor_name": "New Contractor",
        }
        response = client.put(f"/api/v1/procurement/{procurement_id}", json=update_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tender_title"] == "Updated Title"
        assert data["contractor_name"] == "New Contractor"

    def test_delete_procurement_record(self, client, test_db):
        """Test deleting a procurement record"""
        # Create record
        create_response = client.post(
            "/api/v1/procurement",
            json={"source_system": "PPIP", "tender_number": "DELETE/001"},
        )
        procurement_id = create_response.json()["procurement_id"]

        # Delete record
        response = client.delete(f"/api/v1/procurement/{procurement_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify it's gone
        get_response = client.get(f"/api/v1/procurement/{procurement_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_procurement_statistics(self, client, test_db):
        """Test getting procurement statistics"""
        # Create some test records
        client.post(
            "/api/v1/procurement",
            json={"source_system": "PPIP", "tender_number": "STATS/001"},
        )
        client.post(
            "/api/v1/procurement",
            json={"source_system": "eGP", "tender_number": "STATS/002"},
        )

        response = client.get("/api/v1/procurement/stats/summary")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "total_records" in data
        assert "by_source_system" in data
        assert data["total_records"] >= 2


class TestProcurementService:
    """Test procurement service layer"""

    def test_create_procurement_service(self, test_db):
        """Test creating procurement via service"""
        from src.services.procurement_service import ProcurementService

        service = ProcurementService(test_db)

        procurement_data = ProcurementRecordCreate(
            source_system="PPIP",
            tender_number="SERVICE/001",
            tender_title="Test Service Creation",
        )

        record = service.create_procurement_record(procurement_data)

        assert record.procurement_id is not None
        # Type checker needs explicit string conversion for SQLAlchemy model attributes
        assert str(record.tender_number) == "SERVICE/001"
        assert record.created_at is not None
        test_db.commit()

    def test_prevent_duplicate_tender_numbers(self, test_db):
        """Test that service prevents duplicate tender numbers"""
        from src.services.procurement_service import ProcurementService

        service = ProcurementService(test_db)

        procurement_data = ProcurementRecordCreate(
            source_system="PPIP",
            tender_number="DUPLICATE_SERVICE/001",
            tender_title="Duplicate Test",
        )

        # Create first record
        service.create_procurement_record(procurement_data)
        test_db.commit()

        # Attempt duplicate
        with pytest.raises(ValueError, match="already exists"):
            service.create_procurement_record(procurement_data)

    def test_get_procurement_records_pagination(self, test_db):
        """Test pagination in service layer"""
        from src.services.procurement_service import ProcurementService

        service = ProcurementService(test_db)

        # Create 10 records
        for i in range(10):
            procurement_data = ProcurementRecordCreate(
                source_system="PPIP",
                tender_number=f"PAGE_{i:03d}",
                tender_title=f"Test Page {i}",
            )
            service.create_procurement_record(procurement_data)
        test_db.commit()

        # Get first page
        records, total = service.get_procurement_records(skip=0, limit=5)

        assert len(records) == 5
        assert total >= 10


class TestPPIPScraperMocked:
    """Test PPIP scraper with mocked HTTP requests"""

    @patch("src.services.ppip_scraper.requests.Session.get")
    def test_rate_limiting(self, mock_get):
        """Test that rate limiting is enforced"""
        from src.services.ppip_scraper import PPIPScraper
        import time

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Test</body></html>"
        mock_get.return_value = mock_response

        scraper = PPIPScraper()

        # Make first request
        start_time = time.time()
        scraper._make_request("http://test.com/page1")

        # Make second request (should be rate limited)
        scraper._make_request("http://test.com/page2")
        elapsed = time.time() - start_time

        # Should have waited at least 5 seconds between requests
        assert elapsed >= 5.0

    @patch("src.services.ppip_scraper.requests.Session.get")
    def test_retry_logic(self, mock_get):
        """Test retry logic on request failure"""
        from src.services.ppip_scraper import PPIPScraper
        import requests

        # Simulate timeout on first two attempts, success on third
        mock_get.side_effect = [
            requests.exceptions.Timeout(),
            requests.exceptions.Timeout(),
            Mock(status_code=200, text="Success"),
        ]

        scraper = PPIPScraper()
        response = scraper._make_request("http://test.com", max_retries=3)

        assert response is not None
        assert mock_get.call_count == 3

    def test_parse_amount(self):
        """Test monetary amount parsing"""
        from src.services.ppip_scraper import PPIPScraper

        assert PPIPScraper._parse_amount("KES 1,234,567.89") == Decimal("1234567.89")
        assert PPIPScraper._parse_amount("5000000") == Decimal("5000000")
        # Test None handling
        scraper = PPIPScraper()
        assert scraper._parse_amount("") is None
        assert PPIPScraper._parse_amount("Invalid") is None

    def test_calculate_data_quality(self):
        """Test data quality score calculation"""
        from src.services.ppip_scraper import PPIPScraper

        # All fields filled
        score1 = PPIPScraper._calculate_data_quality("Title", "Entity", "Contractor")
        assert score1 == 100

        # Two out of three fields
        score2 = PPIPScraper._calculate_data_quality("Title", "Entity", None)
        assert score2 == 66

        # No fields
        score3 = PPIPScraper._calculate_data_quality(None, None, None)
        assert score3 == 0
