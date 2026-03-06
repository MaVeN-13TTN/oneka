"""
Phase 7 — FinancialService tests.

Covers src/services/financial_service.py — especially ingest_cob_report().
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.models.financial import FinancialRecord
from src.models.project import Project, ProjectStatus


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_project(db, name="Test Project", county="Nairobi"):
    p = Project(
        project_uuid=uuid4(),
        project_name=name,
        county=county,
        status=ProjectStatus.ONGOING,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_financial_record(db, project_uuid, fiscal_year="2023/2024",
                           budget_allocated=1000000, budget_absorbed=800000):
    fr = FinancialRecord(
        project_uuid=project_uuid,
        source_system="COB",
        fiscal_year=fiscal_year,
        vote_head=1001,
        ministry="Infrastructure",
        programme="Roads",
        budget_allocated_kes=Decimal(str(budget_allocated)),
        budget_absorbed_kes=Decimal(str(budget_absorbed)),
        absorption_rate=budget_absorbed / budget_allocated if budget_allocated else 0,
    )
    db.add(fr)
    db.commit()
    db.refresh(fr)
    return fr


# =============================================================================
# ingest_cob_report
# =============================================================================


class TestIngestCobReport:
    """Tests for FinancialService.ingest_cob_report()."""

    def test_ingest_success_inserts_records(self, test_db):
        """Parses and inserts financial records from mocked COB parser."""
        from src.services.financial_service import FinancialService

        mock_parser_cls = MagicMock()
        mock_parser = mock_parser_cls.return_value
        mock_parser.extract_financial_records.return_value = [
            {
                "source_system": "COB",
                "fiscal_year": "2023/2024",
                "vote_head": 1001,
                "ministry": "Health",
                "programme": "Hospitals",
                "budget_allocated_kes": 5000000,
                "budget_absorbed_kes": 4000000,
                "absorption_rate": 0.8,
                "document_source": "/tmp/cob.pdf",
            },
            {
                "source_system": "COB",
                "fiscal_year": "2023/2024",
                "vote_head": 1002,
                "ministry": "Education",
                "programme": "Schools",
                "budget_allocated_kes": 3000000,
                "budget_absorbed_kes": 2000000,
                "absorption_rate": 0.67,
                "document_source": "/tmp/cob2.pdf",
            },
        ]

        mock_module = MagicMock()
        mock_module.CoBParser = mock_parser_cls

        svc = FinancialService(test_db)
        with patch.dict("sys.modules", {
            "data": MagicMock(),
            "data.parsers": MagicMock(),
            "data.parsers.cob": mock_module,
        }):
            count = svc.ingest_cob_report("/tmp/cob.pdf", "2023/2024")

        assert count == 2

    def test_ingest_skips_duplicates(self, test_db):
        """Duplicate records (same document_source + fiscal_year + programme) are skipped."""
        from src.services.financial_service import FinancialService

        # Pre-insert a record matching the duplicate check criteria
        existing = FinancialRecord(
            source_system="COB",
            fiscal_year="2023/2024",
            vote_head=1001,
            ministry="Health",
            programme="Hospitals",
            document_source="/tmp/cob.pdf",
        )
        test_db.add(existing)
        test_db.commit()

        mock_parser_cls = MagicMock()
        mock_parser = mock_parser_cls.return_value
        mock_parser.extract_financial_records.return_value = [
            {
                "source_system": "COB",
                "fiscal_year": "2023/2024",
                "vote_head": 1001,
                "ministry": "Health",
                "programme": "Hospitals",
                "budget_allocated_kes": 5000000,
                "budget_absorbed_kes": 4000000,
                "absorption_rate": 0.8,
                "document_source": "/tmp/cob.pdf",
            },
        ]

        mock_module = MagicMock()
        mock_module.CoBParser = mock_parser_cls

        svc = FinancialService(test_db)
        with patch.dict("sys.modules", {
            "data": MagicMock(),
            "data.parsers": MagicMock(),
            "data.parsers.cob": mock_module,
        }):
            count = svc.ingest_cob_report("/tmp/cob.pdf", "2023/2024")

        assert count == 0

    def test_ingest_import_error_returns_zero(self, test_db):
        """ImportError when CoBParser unavailable returns 0."""
        from src.services.financial_service import FinancialService

        svc = FinancialService(test_db)
        with patch.dict("sys.modules", {"data": None, "data.parsers": None, "data.parsers.cob": None}):
            with patch("builtins.__import__", side_effect=ImportError("no cob parser")):
                count = svc.ingest_cob_report("/tmp/cob.pdf", "2023/2024")

        assert count == 0

    def test_ingest_empty_records(self, test_db):
        """Parser returning empty list inserts 0 records."""
        from src.services.financial_service import FinancialService

        mock_parser_cls = MagicMock()
        mock_parser = mock_parser_cls.return_value
        mock_parser.extract_financial_records.return_value = []

        mock_module = MagicMock()
        mock_module.CoBParser = mock_parser_cls

        svc = FinancialService(test_db)
        with patch.dict("sys.modules", {
            "data": MagicMock(),
            "data.parsers": MagicMock(),
            "data.parsers.cob": mock_module,
        }):
            count = svc.ingest_cob_report("/tmp/cob.pdf", "2023/2024")

        assert count == 0


# =============================================================================
# get_financial_records / calculate_absorption_gap
# =============================================================================


class TestFinancialQueries:
    """Tests for query and calculation methods."""

    def test_absorption_gap_calculation(self, test_db):
        """Correct arithmetic for absorption gap."""
        from src.services.financial_service import FinancialService

        project = _make_project(test_db)
        _make_financial_record(
            test_db, project.project_uuid,
            budget_allocated=1000000, budget_absorbed=600000,
        )

        svc = FinancialService(test_db)
        gap = svc.calculate_absorption_gap(project.project_uuid)

        assert gap["total_allocated_kes"] > 0
        assert gap["total_absorbed_kes"] > 0
        assert gap["gap_kes"] == gap["total_allocated_kes"] - gap["total_absorbed_kes"]

    def test_absorption_gap_no_records(self, test_db):
        """No records returns zero values."""
        from src.services.financial_service import FinancialService

        svc = FinancialService(test_db)
        gap = svc.calculate_absorption_gap(uuid4())

        assert gap["total_allocated_kes"] == 0
        assert gap["total_absorbed_kes"] == 0
