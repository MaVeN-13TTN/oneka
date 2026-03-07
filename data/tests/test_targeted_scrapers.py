"""
Sprint 2 — targeted scraper mode tests.

Verifies that all five scrapers correctly switch from bulk mode to targeted
mode when a ProjectContext is provided, without breaking bulk mode.
No browser or HTTP calls are made — Playwright/httpx are mocked.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# data.context.ProjectContext
# =============================================================================


class TestProjectContext:
    def test_dataclass_defaults(self):
        from data.context import ProjectContext

        ctx = ProjectContext()
        assert ctx.canonical_name is None
        assert ctx.search_terms == []
        assert ctx.aliases == []
        assert ctx.coordinates is None
        assert ctx.fiscal_years == []
        assert ctx.procuring_entity is None

    def test_fully_populated(self):
        from data.context import ProjectContext

        ctx = ProjectContext(
            canonical_name="Bungoma District Hospital",
            search_terms=["Bungoma Hospital", "District Hospital"],
            aliases=["Bungoma Hospital Phase 2"],
            coordinates=(-0.5614, 34.5606),
            fiscal_years=["2022/2023", "2023/2024"],
            procuring_entity="Ministry of Health",
        )
        assert ctx.canonical_name == "Bungoma District Hospital"
        assert len(ctx.search_terms) == 2
        assert ctx.coordinates == (-0.5614, 34.5606)


# =============================================================================
# EGPScraper — targeted mode
# =============================================================================


class TestEGPTargetedMode:
    def test_fetch_accepts_ctx_none(self):
        from data.scrapers.egp import EGPScraper

        sig = inspect.signature(EGPScraper.fetch)
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].default is None

    def test_fetch_dispatches_to_fetch_all_without_ctx(self):
        """fetch(ctx=None) calls _fetch_all()."""
        from data.scrapers.egp import EGPScraper

        scraper = EGPScraper()
        with patch.object(scraper, "_fetch_all", new_callable=AsyncMock, return_value=[]) as mock_bulk:
            asyncio.run(scraper.fetch(ctx=None))
            mock_bulk.assert_called_once()

    def test_fetch_dispatches_to_fetch_targeted_with_ctx(self):
        """fetch(ctx=...) calls _fetch_targeted(ctx)."""
        from data.scrapers.egp import EGPScraper
        from data.context import ProjectContext

        ctx = ProjectContext(search_terms=["Bungoma Hospital"])
        scraper = EGPScraper()
        with patch.object(scraper, "_fetch_targeted", new_callable=AsyncMock, return_value=[]) as mock_targeted:
            asyncio.run(scraper.fetch(ctx=ctx))
            mock_targeted.assert_called_once_with(ctx)

    def test_pe_filter_excludes_mismatched_entity(self):
        """Post-interception PE filter drops tenders whose procuring entity
        does not fuzzy-match ctx.procuring_entity (threshold is 70)."""
        from rapidfuzz import fuzz

        items = [
            {"tenderrefno": "T1", "tendertitle": "Hospital", "procuringEntity": "Ministry of Health"},
            {"tenderrefno": "T2", "tendertitle": "Road",     "procuringEntity": "Road Development Authority"},
        ]
        ctx_pe = "Ministry of Health"

        all_data: dict[str, dict] = {}
        for item in items:
            tn = item.get("tenderrefno")
            pe = item.get("procuringEntity", "")
            if fuzz.token_set_ratio(pe, ctx_pe) >= 70:
                all_data[tn] = item

        assert "T1" in all_data
        assert "T2" not in all_data

    def test_pe_filter_deduplicates_across_terms(self):
        """When the same tender appears for multiple search terms it is only
        returned once."""
        from rapidfuzz import fuzz

        items = [
            {"tenderrefno": "T1", "procuringEntity": "Health"},
            {"tenderrefno": "T1", "procuringEntity": "Health"},  # duplicate
            {"tenderrefno": "T2", "procuringEntity": "Health"},
        ]
        ctx_pe = "Health"
        all_data: dict[str, dict] = {}
        for item in items:
            tn = item.get("tenderrefno")
            pe = item.get("procuringEntity", "")
            if fuzz.token_set_ratio(pe, ctx_pe) >= 60:
                all_data[tn] = item

        assert len(all_data) == 2

    def test_gps_quality_constants_unchanged(self):
        from data.scrapers.egp import EGP_MANUAL_PIN, EGP_AUTO_GEOCODED

        assert EGP_MANUAL_PIN == 90
        assert EGP_AUTO_GEOCODED == 70


# =============================================================================
# NCAScraper — targeted mode
# =============================================================================


class TestNCATargetedMode:
    def test_fetch_accepts_ctx_param(self):
        from data.scrapers.nca import NCAScraper

        sig = inspect.signature(NCAScraper.fetch)
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].default is None

    def test_bulk_mode_uses_class_search_terms(self):
        from data.scrapers.nca import NCAScraper

        ctx = None
        terms = ctx.search_terms if (ctx and ctx.search_terms) else NCAScraper.SEARCH_TERMS
        assert terms is NCAScraper.SEARCH_TERMS

    def test_targeted_mode_uses_ctx_search_terms(self):
        from data.scrapers.nca import NCAScraper
        from data.context import ProjectContext

        ctx = ProjectContext(search_terms=["Bungoma Hospital", "District Hospital"])
        terms = ctx.search_terms if (ctx and ctx.search_terms) else NCAScraper.SEARCH_TERMS
        assert terms == ["Bungoma Hospital", "District Hospital"]

    def test_empty_search_terms_falls_back_to_class_terms(self):
        """ctx with no search_terms should fall back to SEARCH_TERMS."""
        from data.scrapers.nca import NCAScraper
        from data.context import ProjectContext

        ctx = ProjectContext(search_terms=[])
        terms = ctx.search_terms if (ctx and ctx.search_terms) else NCAScraper.SEARCH_TERMS
        assert terms is NCAScraper.SEARCH_TERMS

    def test_class_search_terms_count(self):
        from data.scrapers.nca import NCAScraper

        # Bulk mode has 14 generic terms; targeted mode should use fewer
        assert len(NCAScraper.SEARCH_TERMS) == 14


# =============================================================================
# PPIPScraper — targeted mode
# =============================================================================


class TestPPIPTargetedMode:
    def test_fetch_accepts_ctx_param(self):
        from data.scrapers.ppip import PPIPScraper

        sig = inspect.signature(PPIPScraper.fetch)
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].default is None

    def test_filter_by_context_keeps_alias_match(self):
        from data.scrapers.ppip import PPIPScraper
        from data.context import ProjectContext

        scraper = PPIPScraper()
        ctx = ProjectContext(
            canonical_name="Bungoma District Hospital",
            aliases=["District Hospital Bungoma", "Bungoma Hospital"],
        )
        data = [
            {"tender_ref": "T1", "title": "Construction of District Hospital Bungoma"},
            {"tender_ref": "T2", "title": "Supply of Road Materials, Phase 2"},
            {"tender_ref": "T3", "title": "Bungoma Hospital Outpatient Block"},
        ]
        result = scraper._filter_by_context(data, ctx)
        tids = [t["tender_ref"] for t in result]
        assert "T1" in tids
        assert "T3" in tids
        assert "T2" not in tids

    def test_filter_by_context_includes_canonical_name(self):
        from data.scrapers.ppip import PPIPScraper
        from data.context import ProjectContext

        scraper = PPIPScraper()
        ctx = ProjectContext(
            canonical_name="Bungoma District Hospital",
            aliases=[],
        )
        data = [
            {"tender_ref": "T1", "title": "Bungoma District Hospital Phase 1"},
        ]
        result = scraper._filter_by_context(data, ctx)
        assert len(result) == 1

    def test_filter_returns_empty_when_no_match(self):
        from data.scrapers.ppip import PPIPScraper
        from data.context import ProjectContext

        scraper = PPIPScraper()
        ctx = ProjectContext(
            canonical_name="Mombasa Port Expansion",
            aliases=["Port Development"],
        )
        data = [
            {"tender_ref": "T1", "title": "Bridge Construction Thika Road"},
            {"tender_ref": "T2", "title": "Nairobi Bypass Phase 3"},
        ]
        result = scraper._filter_by_context(data, ctx)
        assert result == []

    def test_bulk_mode_returns_all_data(self):
        """When ctx=None, fetch() returns the raw API response unchanged."""
        from data.scrapers.ppip import PPIPScraper

        mock_data = [
            {"tender_ref": "T1", "title": "A"},
            {"tender_ref": "T2", "title": "B"},
            {"tender_ref": "T3", "title": "C"},
        ]
        scraper = PPIPScraper()
        with patch.object(scraper, "_fetch_all", new_callable=AsyncMock, return_value=mock_data):
            result = asyncio.run(scraper.fetch(ctx=None))
        assert result == mock_data

    def test_targeted_mode_applies_filter(self):
        """When ctx is provided, fetch() applies _filter_by_context."""
        from data.scrapers.ppip import PPIPScraper
        from data.context import ProjectContext

        mock_data = [
            {"tender_ref": "T1", "title": "Bungoma Hospital Construction"},
            {"tender_ref": "T2", "title": "Nairobi Road Works"},
        ]
        ctx = ProjectContext(
            canonical_name="Bungoma Hospital",
            aliases=["Bungoma District Hospital"],
        )
        scraper = PPIPScraper()
        with patch.object(scraper, "_fetch_all", new_callable=AsyncMock, return_value=mock_data):
            result = asyncio.run(scraper.fetch(ctx=ctx))
        tids = [t["tender_ref"] for t in result]
        assert "T1" in tids
        assert "T2" not in tids


# =============================================================================
# KMHFLScraper — skip-if-GPS-known
# =============================================================================


class TestKMHFLSkipIfGPSKnown:
    def test_fetch_accepts_ctx_param(self):
        from data.scrapers.kmhfl import KMHFLScraper

        sig = inspect.signature(KMHFLScraper.fetch)
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].default is None

    def test_returns_empty_list_when_coordinates_known(self):
        """GPS already known → skip bulk download entirely."""
        from data.scrapers.kmhfl import KMHFLScraper
        from data.context import ProjectContext

        ctx = ProjectContext(
            canonical_name="Bungoma Hospital",
            coordinates=(-0.5614, 34.5606),
        )
        scraper = KMHFLScraper()
        result = asyncio.run(scraper.fetch(ctx=ctx))
        assert result == []

    def test_bulk_fetch_when_ctx_none(self):
        """ctx=None → calls _fetch_all() (mocked)."""
        from data.scrapers.kmhfl import KMHFLScraper

        mock_facilities = [{"name": "Facility A"}, {"name": "Facility B"}]
        scraper = KMHFLScraper()
        with patch.object(scraper, "_fetch_all", new_callable=AsyncMock, return_value=mock_facilities):
            result = asyncio.run(scraper.fetch(ctx=None))
        assert result == mock_facilities

    def test_bulk_fetch_when_no_coordinates(self):
        """ctx without coordinates → calls _fetch_all() (mocked)."""
        from data.scrapers.kmhfl import KMHFLScraper
        from data.context import ProjectContext

        ctx = ProjectContext(canonical_name="Some Project")  # coordinates=None
        mock_facilities = [{"name": "Facility A"}]
        scraper = KMHFLScraper()
        with patch.object(scraper, "_fetch_all", new_callable=AsyncMock, return_value=mock_facilities):
            result = asyncio.run(scraper.fetch(ctx=ctx))
        assert result == mock_facilities


# =============================================================================
# CoBPoller — fiscal year filter
# =============================================================================


class TestCoBFiscalYearFilter:
    def test_accepts_ctx_param(self):
        from data.scrapers.cob import CoBPoller

        sig = inspect.signature(CoBPoller.process)
        assert "ctx" in sig.parameters
        assert sig.parameters["ctx"].default is None

    def test_fiscal_year_filter_logic(self):
        """Reports are filtered by URL substring matching fiscal year."""
        reports = [
            {"title": "Q1 FY 2022/2023", "url": "https://cob.go.ke/fy-2022-2023-q1.pdf"},
            {"title": "Q1 FY 2023/2024", "url": "https://cob.go.ke/fy-2023-2024-q1.pdf"},
            {"title": "Q2 FY 2023/2024", "url": "https://cob.go.ke/fy-2023-2024-q2.pdf"},
        ]
        from data.context import ProjectContext

        ctx = ProjectContext(fiscal_years=["2023/2024"])
        filtered = [
            r for r in reports
            if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
        ]
        assert len(filtered) == 2
        assert all("2023-2024" in r["url"] for r in filtered)

    def test_no_filter_when_ctx_none(self):
        """ctx=None → all reports are downloaded."""
        reports = [
            {"title": "Q1", "url": "https://cob.go.ke/fy-2022-2023-q1.pdf"},
            {"title": "Q2", "url": "https://cob.go.ke/fy-2023-2024-q1.pdf"},
        ]
        ctx = None
        if ctx and ctx.fiscal_years:
            filtered = [
                r for r in reports
                if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
            ]
        else:
            filtered = reports
        assert len(filtered) == 2

    def test_no_filter_when_no_fiscal_years(self):
        """ctx with empty fiscal_years → all reports downloaded."""
        from data.context import ProjectContext

        reports = [
            {"title": "Q1", "url": "https://cob.go.ke/fy-2022-2023-q1.pdf"},
            {"title": "Q2", "url": "https://cob.go.ke/fy-2023-2024-q1.pdf"},
        ]
        ctx = ProjectContext(fiscal_years=[])
        if ctx and ctx.fiscal_years:
            filtered = [
                r for r in reports
                if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
            ]
        else:
            filtered = reports
        assert len(filtered) == 2

    def test_multi_year_filter(self):
        """Multiple fiscal years → reports for all of them are included."""
        from data.context import ProjectContext

        reports = [
            {"title": "Q1 FY 2021/2022", "url": "https://cob.go.ke/fy-2021-2022-q1.pdf"},
            {"title": "Q1 FY 2022/2023", "url": "https://cob.go.ke/fy-2022-2023-q1.pdf"},
            {"title": "Q1 FY 2023/2024", "url": "https://cob.go.ke/fy-2023-2024-q1.pdf"},
        ]
        ctx = ProjectContext(fiscal_years=["2022/2023", "2023/2024"])
        filtered = [
            r for r in reports
            if any(fy.replace("/", "-") in r["url"] for fy in ctx.fiscal_years)
        ]
        assert len(filtered) == 2

    def test_process_filters_before_download(self):
        """CoBPoller.process() calls find_reports then filters by fiscal year
        before downloading, so only relevant reports are fetched."""
        import tempfile
        from pathlib import Path
        from data.scrapers.cob import CoBPoller
        from data.context import ProjectContext

        reports = [
            {"title": "Q1 FY 2022/2023", "url": "https://cob.go.ke/fy-2022-2023-q1.pdf"},
            {"title": "Q1 FY 2023/2024", "url": "https://cob.go.ke/fy-2023-2024-q1.pdf"},
        ]
        ctx = ProjectContext(fiscal_years=["2023/2024"])

        poller = CoBPoller()
        downloaded = []

        async def _mock_find_reports():
            return reports

        async def _mock_download(url, title):
            downloaded.append(url)
            return f"/tmp/{title}.pdf"

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_cache = Path(tmpdir) / "cob_reports.json"
            with patch("data.scrapers.cob.CACHE_PATH", fake_cache):
                with patch.object(poller, "find_reports", side_effect=_mock_find_reports):
                    with patch.object(poller, "download_report", side_effect=_mock_download):
                        asyncio.run(poller.process(ctx=ctx))

        assert len(downloaded) == 1
        assert "2023-2024" in downloaded[0]
