"""
Tests for Sprint 1: Investigations context layer.

Covers:
  - PerplexityEnrichmentService: search term derivation, context building,
    Kenya bounds validation, warning generation, API error handling
  - Investigations router: POST create, POST enrich, PATCH context, GET status
  - Investigation ORM model round-trip
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.models.investigation import Investigation, InvestigationStatus
from src.schemas.investigation import ProjectContext
from src.services.perplexity_enrichment_service import (
    EnrichmentError,
    PerplexityEnrichmentService,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


GARISSA_PERPLEXITY_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "canonical_name": "Construction of Garissa County Government Headquarters",
                        "county": "Garissa",
                        "constituency": "Garissa Township",
                        "ward": "Garissa Township",
                        "coordinates": [-0.4536, 39.6401],
                        "project_type": "OTHER",
                        "estimated_value_kes": 550000000,
                        "contractor_name": "Munyaka General Contractors",
                        "procuring_entity": "Garissa County Government",
                        "award_date": "2021-04-01",
                        "fiscal_years": ["2021/2022", "2022/2023"],
                        "ministry": "State Department for Devolution",
                        "vote_head": 260,
                        "aliases": [
                            "Garissa County HQ",
                            "Garissa County Government HQ",
                        ],
                        "source_urls": [
                            "https://www.parliament.go.ke/pic_garissa.pdf"
                        ],
                        "confidence": 0.82,
                    }
                )
            }
        }
    ]
}


@pytest.fixture
def mock_perplexity_response():
    """Patch httpx.Client to return a canned Perplexity response."""

    class _MockResponse:
        status_code = 200

        def json(self):
            return GARISSA_PERPLEXITY_RESPONSE

    class _MockClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, *args, **kwargs):
            return _MockResponse()

    return _MockClient


@pytest.fixture
def sample_investigation(test_db):
    """A committed investigation row in CREATED status."""
    inv = Investigation(
        raw_project_name="Garissa County Headquarters",
        user_notes="Suspected ghost project",
        status=InvestigationStatus.CREATED.value,
        stage_statuses={},
    )
    test_db.add(inv)
    test_db.commit()
    test_db.refresh(inv)
    return inv


# ── PerplexityEnrichmentService unit tests ─────────────────────────────────────


class TestPerplexityEnrichmentService:

    def test_enrich_returns_correct_county(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, warnings = service.enrich("Garissa County Headquarters")
        assert ctx.county == "Garissa"

    def test_enrich_returns_canonical_name(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert ctx.canonical_name == "Construction of Garissa County Government Headquarters"

    def test_enrich_returns_aliases(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert "Garissa County HQ" in ctx.aliases
        assert "Garissa County Government HQ" in ctx.aliases

    def test_enrich_returns_fiscal_years(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert ctx.fiscal_years == ["2021/2022", "2022/2023"]

    def test_enrich_returns_valid_coordinates(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert ctx.coordinates is not None
        lat, lon = ctx.coordinates
        assert abs(lat - (-0.4536)) < 0.001
        assert abs(lon - 39.6401) < 0.001

    def test_enrich_sets_enrichment_source_to_perplexity(self, mock_perplexity_response):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert ctx.enrichment_source == "perplexity"
        assert ctx.enriched_at is not None

    def test_enrich_derives_search_terms_from_canonical_and_aliases(
        self, mock_perplexity_response
    ):
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        assert "Construction of Garissa County Government Headquarters" in ctx.search_terms
        assert "Garissa County HQ" in ctx.search_terms
        assert len(ctx.search_terms) >= 2

    def test_enrich_no_generic_terms_in_search_terms(self, mock_perplexity_response):
        """Generic words like 'Road', 'Building' must not appear in targeted search_terms."""
        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   mock_perplexity_response):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Garissa County Headquarters")
        for term in ctx.search_terms:
            assert term.lower() not in {"road", "building", "hospital", "school"}

    def test_enrich_low_confidence_produces_warning(self):
        low_conf_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "canonical_name": "Some Project",
                                "county": None,
                                "aliases": [],
                                "fiscal_years": [],
                                "confidence": 0.35,
                            }
                        )
                    }
                }
            ]
        }

        class _LowConfClient:
            def __init__(self, **kwargs): pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def post(self, *args, **kwargs):
                r = MagicMock()
                r.status_code = 200
                r.json.return_value = low_conf_response
                return r

        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   _LowConfClient):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, warnings = service.enrich("Some Vague Project Name")

        assert any("Low enrichment confidence" in w for w in warnings)
        assert ctx.enrichment_confidence == 0.35

    def test_enrich_coordinates_outside_kenya_are_discarded(self):
        out_of_bounds_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "canonical_name": "Test Project",
                                "county": "Nairobi",
                                "coordinates": [51.5074, -0.1278],  # London
                                "aliases": [],
                                "fiscal_years": [],
                                "confidence": 0.7,
                            }
                        )
                    }
                }
            ]
        }

        class _OutOfBoundsClient:
            def __init__(self, **kwargs): pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def post(self, *args, **kwargs):
                r = MagicMock()
                r.status_code = 200
                r.json.return_value = out_of_bounds_response
                return r

        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   _OutOfBoundsClient):
            service = PerplexityEnrichmentService(api_key="test-key")
            ctx, _ = service.enrich("Test Project")
        assert ctx.coordinates is None

    def test_enrich_missing_api_key_raises_enrichment_error(self):
        service = PerplexityEnrichmentService(api_key=None)
        # Temporarily clear the settings key
        with patch("src.services.perplexity_enrichment_service.settings") as mock_settings:
            mock_settings.perplexity_api_key = None
            mock_settings.perplexity_model = "sonar-pro"
            reloaded = PerplexityEnrichmentService(api_key=None)
            with pytest.raises(EnrichmentError, match="PERPLEXITY_API_KEY"):
                reloaded.enrich("Test Project")

    def test_enrich_api_error_raises_enrichment_error(self):
        import httpx as real_httpx

        class _FailingClient:
            def __init__(self, **kwargs): pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def post(self, *args, **kwargs):
                raise real_httpx.RequestError("connection refused")

        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   _FailingClient):
            service = PerplexityEnrichmentService(api_key="test-key")
            with pytest.raises(EnrichmentError, match="unreachable"):
                service.enrich("Test Project")

    def test_enrich_non_200_response_raises_enrichment_error(self):
        class _BadStatusClient:
            def __init__(self, **kwargs): pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def post(self, *args, **kwargs):
                r = MagicMock()
                r.status_code = 401
                return r

        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   _BadStatusClient):
            service = PerplexityEnrichmentService(api_key="bad-key")
            with pytest.raises(EnrichmentError, match="HTTP 401"):
                service.enrich("Test Project")

    def test_derive_search_terms_includes_county_type_fragment(self):
        service = PerplexityEnrichmentService(api_key="test-key")
        ctx = ProjectContext(
            project_name="Bungoma District Hospital",
            canonical_name="Construction of Bungoma District Hospital",
            county="Bungoma",
            project_type="HEALTH",
            aliases=["Bungoma District Hospital"],
        )
        terms = service._derive_search_terms(ctx)
        assert "Construction of Bungoma District Hospital" in terms
        assert "Bungoma District Hospital" in terms
        assert any("Bungoma" in t and "health" in t for t in terms)


# ── Investigation ORM model tests ──────────────────────────────────────────────


class TestInvestigationModel:

    def test_investigation_created_with_defaults(self, test_db):
        inv = Investigation(
            raw_project_name="Test Road Project",
            status=InvestigationStatus.CREATED.value,
            stage_statuses={},
        )
        test_db.add(inv)
        test_db.commit()
        test_db.refresh(inv)

        assert inv.investigation_id is not None
        assert inv.status == "created"
        assert inv.context_confirmed is False
        assert inv.project_context is None

    def test_investigation_stores_project_context_as_jsonb(self, test_db):
        ctx = ProjectContext(
            project_name="Test Project",
            county="Nairobi",
            aliases=["Test"],
            enrichment_confidence=0.75,
        )
        inv = Investigation(
            raw_project_name="Test Project",
            status=InvestigationStatus.ENRICHED.value,
            project_context=ctx.model_dump(mode="json"),
            stage_statuses={},
        )
        test_db.add(inv)
        test_db.commit()
        test_db.refresh(inv)

        loaded = ProjectContext(**inv.project_context)
        assert loaded.county == "Nairobi"
        assert loaded.enrichment_confidence == 0.75


# ── Router tests ───────────────────────────────────────────────────────────────


class TestInvestigationsRouter:

    def test_create_investigation_returns_201(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"project_name": "Garissa County Headquarters"},
        )
        assert r.status_code == 201
        data = r.json()
        assert "investigation_id" in data
        assert data["status"] == "created"
        assert data["raw_project_name"] == "Garissa County Headquarters"

    def test_create_investigation_strips_control_characters(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"project_name": "Garissa\x00\x1f County HQ"},
        )
        assert r.status_code == 201
        assert "\x00" not in r.json()["raw_project_name"]
        assert "\x1f" not in r.json()["raw_project_name"]

    def test_create_investigation_rejects_short_name(self, client):
        r = client.post(
            "/api/v1/investigations",
            json={"project_name": "AB"},
        )
        assert r.status_code == 422

    def test_enrich_investigation_success(self, client, test_db, mock_perplexity_response):
        # Create first
        r = client.post(
            "/api/v1/investigations",
            json={"project_name": "Garissa County Headquarters"},
        )
        inv_id = r.json()["investigation_id"]

        # Patch at the service level so API key check is bypassed in router test.
        # Service-level unit tests cover the full _call_api path.
        from src.schemas.investigation import ProjectContext
        mock_ctx = ProjectContext(
            project_name="Garissa County Headquarters",
            canonical_name="Construction of Garissa County Government Headquarters",
            county="Garissa",
            aliases=["Garissa County HQ", "Garissa County Government HQ"],
            fiscal_years=["2021/2022", "2022/2023"],
            search_terms=[
                "Construction of Garissa County Government Headquarters",
                "Garissa County HQ",
            ],
            enrichment_source="perplexity",
            enrichment_confidence=0.82,
        )
        with patch(
            "src.routers.investigations.PerplexityEnrichmentService.enrich",
            return_value=(mock_ctx, []),
        ):
            r2 = client.post(f"/api/v1/investigations/{inv_id}/enrich")

        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "enriched"
        assert data["context"]["county"] == "Garissa"
        assert len(data["context"]["aliases"]) == 2
        assert len(data["context"]["search_terms"]) >= 2

    def test_enrich_investigation_not_found(self, client):
        r = client.post(f"/api/v1/investigations/{uuid4()}/enrich")
        assert r.status_code == 404

    def test_enrich_investigation_perplexity_unavailable_returns_502(
        self, client
    ):
        import httpx as real_httpx

        class _FailingClient:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def post(self, *a, **kw): raise real_httpx.RequestError("down")

        r = client.post(
            "/api/v1/investigations",
            json={"project_name": "Garissa County Headquarters"},
        )
        inv_id = r.json()["investigation_id"]

        with patch("src.services.perplexity_enrichment_service.httpx.Client",
                   _FailingClient):
            with patch(
                "src.services.perplexity_enrichment_service.settings"
            ) as ms:
                ms.perplexity_api_key = "test-key"
                ms.perplexity_model = "sonar-pro"
                r2 = client.post(f"/api/v1/investigations/{inv_id}/enrich")
        assert r2.status_code == 502

    def test_patch_context_updates_county(
        self, client, test_db, sample_investigation, mock_perplexity_response
    ):
        inv_id = str(sample_investigation.investigation_id)

        from src.schemas.investigation import ProjectContext
        mock_ctx = ProjectContext(
            project_name="Garissa County Headquarters",
            county="Garissa",
            aliases=["Garissa County HQ"],
            search_terms=["Garissa County HQ"],
            enrichment_source="perplexity",
            enrichment_confidence=0.82,
        )
        with patch(
            "src.routers.investigations.PerplexityEnrichmentService.enrich",
            return_value=(mock_ctx, []),
        ):
            client.post(f"/api/v1/investigations/{inv_id}/enrich")

        # Correct the county
        r = client.patch(
            f"/api/v1/investigations/{inv_id}/context",
            json={"county": "Wajir"},
        )
        assert r.status_code == 200
        assert r.json()["context"]["county"] == "Wajir"

    def test_patch_context_confirms_context(
        self, client, test_db, sample_investigation, mock_perplexity_response
    ):
        # Save UUID before any requests (session may close after each request)
        saved_inv_id = sample_investigation.investigation_id
        inv_id = str(saved_inv_id)

        from src.schemas.investigation import ProjectContext
        mock_ctx = ProjectContext(
            project_name="Garissa County Headquarters",
            county="Garissa",
            aliases=["Garissa County HQ"],
            search_terms=["Garissa County HQ"],
            enrichment_source="perplexity",
            enrichment_confidence=0.82,
        )
        with patch(
            "src.routers.investigations.PerplexityEnrichmentService.enrich",
            return_value=(mock_ctx, []),
        ):
            client.post(f"/api/v1/investigations/{inv_id}/enrich")

        r = client.patch(
            f"/api/v1/investigations/{inv_id}/context",
            json={"context_confirmed": True},
        )
        assert r.status_code == 200

        # Re-query from DB using saved UUID (avoid DetachedInstanceError)
        inv = (
            test_db.query(Investigation)
            .filter(Investigation.investigation_id == saved_inv_id)
            .first()
        )
        assert inv.context_confirmed is True
        assert inv.context_confirmed_at is not None

    def test_get_status_returns_correct_shape(self, client, sample_investigation):
        inv_id = str(sample_investigation.investigation_id)
        r = client.get(f"/api/v1/investigations/{inv_id}/status")
        assert r.status_code == 200
        data = r.json()
        assert data["investigation_id"] == inv_id
        assert data["status"] == "created"
        assert isinstance(data["stage_statuses"], dict)

    def test_get_status_not_found(self, client):
        r = client.get(f"/api/v1/investigations/{uuid4()}/status")
        assert r.status_code == 404


# ── Sprint 5: Perplexity fallback tests ───────────────────────────────────────


class TestPerplexityFallback:
    """
    Sprint 5 — Perplexity fallback: user can supply manual context when
    Perplexity is unavailable and still trigger the scraping pipeline.
    """

    def test_enrich_failure_returns_502_and_keeps_created_status(
        self, client, test_db
    ):
        """When Perplexity is unavailable, POST /enrich returns 502 and the
        investigation status remains 'created' so the fallback path is usable."""
        inv = Investigation(
            raw_project_name="Turkana Water Project",
            status=InvestigationStatus.CREATED.value,
            stage_statuses={},
        )
        test_db.add(inv)
        test_db.commit()
        test_db.refresh(inv)
        saved_id = inv.investigation_id   # save before client call (avoid DetachedInstanceError)
        inv_id = str(saved_id)

        with patch(
            "src.routers.investigations.PerplexityEnrichmentService.enrich",
            side_effect=EnrichmentError("Perplexity unavailable"),
        ):
            r = client.post(f"/api/v1/investigations/{inv_id}/enrich")

        assert r.status_code == 502

        # Re-query from DB using saved UUID (router uses a different session)
        refreshed = (
            test_db.query(Investigation)
            .filter(Investigation.investigation_id == saved_id)
            .first()
        )
        assert refreshed.status == InvestigationStatus.CREATED.value

    def test_manual_context_patch_on_created_investigation(
        self, client, test_db
    ):
        """A CREATED investigation can receive manual context via PATCH /context
        and must persist the fields without advancing its status."""
        inv = Investigation(
            raw_project_name="Turkana Water Project",
            status=InvestigationStatus.CREATED.value,
            stage_statuses={},
        )
        test_db.add(inv)
        test_db.commit()
        test_db.refresh(inv)
        saved_id = inv.investigation_id   # save before client call
        inv_id = str(saved_id)

        r = client.patch(
            f"/api/v1/investigations/{inv_id}/context",
            json={
                "canonical_name": "Proposed Turkana Water Supply Project",
                "county": "Turkana",
                "fiscal_years": ["2023/2024"],
                "procuring_entity": "Ministry of Water & Sanitation",
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert data["context"]["county"] == "Turkana"
        assert data["context"]["canonical_name"] == "Proposed Turkana Water Supply Project"
        assert "2023/2024" in data["context"]["fiscal_years"]

        # Re-query from DB using saved UUID (router uses a different session)
        refreshed = (
            test_db.query(Investigation)
            .filter(Investigation.investigation_id == saved_id)
            .first()
        )
        assert refreshed.status == InvestigationStatus.CREATED.value
        assert refreshed.project_context["county"] == "Turkana"

    def test_full_fallback_path_enrich_fail_patch_then_scrape(
        self, client, test_db
    ):
        """Full Perplexity-fallback flow:
        1. POST /enrich fails with 502.
        2. User PATCHes context manually.
        3. POST /scrape succeeds with 202 because CREATED status is allowed.
        """
        inv = Investigation(
            raw_project_name="Turkana Water Project",
            status=InvestigationStatus.CREATED.value,
            stage_statuses={},
        )
        test_db.add(inv)
        test_db.commit()
        test_db.refresh(inv)
        inv_id = str(inv.investigation_id)

        # Step 1: Perplexity fails
        with patch(
            "src.routers.investigations.PerplexityEnrichmentService.enrich",
            side_effect=EnrichmentError("service down"),
        ):
            r = client.post(f"/api/v1/investigations/{inv_id}/enrich")
        assert r.status_code == 502

        # Step 2: user supplies context manually
        r = client.patch(
            f"/api/v1/investigations/{inv_id}/context",
            json={
                "canonical_name": "Proposed Turkana Water Supply Project",
                "county": "Turkana",
                "fiscal_years": ["2023/2024"],
            },
        )
        assert r.status_code == 200

        # Step 3: trigger scrape — CREATED status is in _RUNNABLE
        with patch("src.tasks.ingestion_tasks.investigate_project_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="fallback-task-abc")
            r = client.post(f"/api/v1/investigations/{inv_id}/scrape")

        assert r.status_code == 202
        assert r.json()["task_id"] == "fallback-task-abc"
