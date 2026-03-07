# Oneka AI — Single-Project Pipeline Verification Plan

**Date:** March 7, 2026  
**Status:** Active  
**Scope:** End-to-end verification that the single-project investigation pipeline produces correct, real-data-backed outputs from user input through to investigation report

---

## 1. Purpose and Scope

This document defines exactly what "working as expected" means for the single-project investigation pipeline, how each stage is verified independently, and how the end-to-end chain is validated before the system is considered production-ready.

The pipeline under test:

```
User Input → Perplexity Enrichment → ProjectContext
    → [EGP + PPIP + NCA + CoB + KMHFL] targeted scrapers
    → IntelligentCoBParser (pdfplumber + GPT-4o Vision)
    → Concordance → Geolocation → Satellite → Divergence
    → Investigation Report (+ Certificate if HIGH/CRITICAL)
```

This plan does **not** test the ML risk scoring path. Per the design decision in Section 15 of the design doc, `RiskScoringService` is disabled in the MVP phase. The divergence-based assessment is the risk signal under test.

---

## 2. Reference Project: The Verification Fixture

All verification tests are anchored to a single real-world reference project with a known outcome. This project is used consistently across all stages.

**Reference Project: Garissa County Headquarters**

| Field                                | Value                                                               |
| ------------------------------------ | ------------------------------------------------------------------- |
| Project name                         | Garissa County Headquarters                                         |
| Canonical name (Perplexity expected) | Construction of Garissa County Government Headquarters              |
| County                               | Garissa                                                             |
| Constituency                         | Garissa Township                                                    |
| Estimated value                      | KES 550,000,000                                                     |
| Award date                           | 2021-04-01                                                          |
| Expected completion                  | 2023-03-31                                                          |
| Status (known outcome)               | **Ghost project**                                                   |
| Evidence source                      | Parliamentary Investments Committee (PIC) Investigation Report 2023 |
| Procuring entity                     | Garissa County Government                                           |
| Ministry / Vote head                 | State Department for Devolution / County Development Vote           |
| Fiscal years                         | 2021/2022, 2022/2023                                                |

This project appears in the existing `training_projects.csv` (row 008) as a confirmed ghost project with a verified label. It is a suitable reference because:

- It has a known label with a credible evidence source
- "Garissa County Headquarters" has distinctive search terms unlikely to match unrelated projects
- The COB BIRR would contain county government development expenditures for Garissa
- It is recent enough that Perplexity should surface meaningful web results

A secondary reference is used for a **non-ghost / successful project** for negative-case verification:

**Secondary Reference: Kiambu Level 4 Hospital Construction** (row 001 in training CSV)  
Status: success | Evidence: OAG Audit Report 2024 | Value: KES 350,000,000

---

## 3. Verification Environment Setup

### 3.1 Required services

```bash
# Backend stack (PostgreSQL + Redis + FastAPI + Celery)
docker-compose up -d postgres redis

cd backend && source venv-backend/bin/activate
alembic upgrade head
uvicorn src.main:app --reload --port 8000

# Celery worker (separate terminal)
celery -A src.celery_app worker --loglevel=info -Q investigations

# Data layer venv
source data/venv-data/bin/activate
```

### 3.2 Required environment variables for verification

```dotenv
# .env (add to existing file)
PERPLEXITY_API_KEY=pplx-...         # required for Stage V-1
PERPLEXITY_MODEL=sonar-pro

OPENAI_API_KEY=sk-...               # required for Stage V-3
OPENAI_VISION_MODEL=gpt-4o
VISION_MAX_PAGES_PER_PDF=20
VISION_CANDIDATE_MIN_SCORE=1
```

If API keys are unavailable, Stages V-1 and V-3 use the mock paths defined in Section 4.

### 3.3 Test data required

```bash
# Download one real COB BIRR PDF for parser verification (Stage V-3).
# Use the FY 2022/2023 Q4 consolidated report — publicly available.
# Save to: data/raw/cob/BIRR_Q4_2022_2023.pdf
# This is the period covering the Garissa County Headquarters project.
```

---

## 4. Mock Contracts for API-Gated Stages

Stages that require paid API keys must have mock contracts so verification can run in CI without incurring costs.

### 4.1 Perplexity mock (Stage V-1)

```python
# backend/tests/mocks/perplexity_mock.py

GARISSA_RESPONSE = {
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
        "County Headquarters Garissa",
    ],
    "source_urls": [
        "https://www.parliament.go.ke/sites/default/files/pic_report_garissa.pdf",
        "https://www.cob.go.ke/reports/...",
    ],
    "confidence": 0.82,
}
```

### 4.2 OpenAI Vision mock (Stage V-3)

```python
# data/tests/mocks/openai_vision_mock.py

GARISSA_VISION_RESPONSE = {
    "match": True,
    "approved_budget_kes": 275000000,
    "released_kes": 248500000,
    "absorbed_kes": 225300000,
    "absorption_rate_pct": 81.9,
    "reporting_period": "FY 2022/2023 Q4",
    "page_label": "County Gazetted Headquarters — Garissa County Vote 260",
}
```

---

## 5. Stage-by-Stage Verification

Each stage has: **Setup → Execute → Assert → Pass Criteria**.

---

### Stage V-1: Perplexity Enrichment

**What is being verified:** Given a raw project name and optional notes, `PerplexityEnrichmentService` returns a `ProjectContext` with enough information to target all five scrapers.

**Test A — Live API (integration test, requires PERPLEXITY_API_KEY)**

```python
# backend/tests/integration/test_enrichment_live.py

async def test_enrich_garissa_hq_live():
    service = PerplexityEnrichmentService()
    ctx = await service.enrich(
        project_name="Garissa County Headquarters",
        user_notes="Government building project, suspected ghost project"
    )
    assert ctx.county == "Garissa"
    assert ctx.coordinates is not None
    assert len(ctx.aliases) >= 1
    assert len(ctx.search_terms) >= 2
    assert ctx.enrichment_confidence >= 0.5
```

**Test B — Mocked (unit test, no API key needed)**

```python
# backend/tests/test_enrichment.py

async def test_enrich_returns_valid_context_from_mock():
    with patch.object(PerplexityEnrichmentService, '_call_api',
                      return_value=GARISSA_RESPONSE):
        ctx = await service.enrich("Garissa County Headquarters")
    assert ctx.county == "Garissa"
    assert ctx.estimated_value_kes == 550_000_000
    assert "Garissa County HQ" in ctx.aliases
    assert ctx.search_terms  # not empty
    assert ctx.fiscal_years == ["2021/2022", "2022/2023"]

async def test_enrich_derives_search_terms_from_aliases():
    ctx = ProjectContext(
        project_name="Garissa County Headquarters",
        canonical_name="Construction of Garissa County Government Headquarters",
        county="Garissa",
        aliases=["Garissa County HQ"],
        project_type="OTHER",
    )
    terms = PerplexityEnrichmentService()._derive_search_terms(ctx)
    assert "Construction of Garissa County Government Headquarters" in terms
    assert "Garissa County HQ" in terms
    assert len(terms) >= 2

async def test_enrich_handles_low_confidence_gracefully():
    # If Perplexity returns confidence < 0.6, context is still returned
    # but enrichment_source is flagged for user review.
    response = {**GARISSA_RESPONSE, "confidence": 0.4}
    with patch.object(PerplexityEnrichmentService, '_call_api', return_value=response):
        ctx = await service.enrich("Garissa County Headquarters")
    assert ctx.enrichment_confidence == 0.4
    # No exception raised — pipeline can continue with user review

async def test_enrich_perplexity_unavailable_raises_enrichment_error():
    with patch.object(PerplexityEnrichmentService, '_call_api',
                      side_effect=httpx.RequestError("timeout")):
        with pytest.raises(EnrichmentError):
            await service.enrich("Garissa County Headquarters")
```

**Pass criteria:**

- county is correctly extracted for all 10 validation projects
- aliases list has ≥1 entry for every project
- search_terms is non-empty for every project
- Low confidence (<0.6) produces a warning flag, not an exception
- API errors raise `EnrichmentError`, not unhandled exceptions

---

### Stage V-2: Targeted Scrapers

**What is being verified:** Each scraper, when given a `ProjectContext`, fetches only records relevant to the target project — not the full dataset.

#### V-2a: EGPScraper targeted mode

```python
# data/tests/test_targeted_scrapers.py

async def test_egp_targeted_returns_only_matching_tenders():
    ctx = build_test_context("Garissa County Headquarters", search_terms=["Garissa Headquarters"])
    mock_playwright, page, _ = _make_playwright_mock()
    # Intercept returns two tenders: one matching, one unrelated
    matching = {"tenderrefno": "GARISSA/001/2021", "tendertitle": "Construction Garissa HQ", ...}
    unrelated = {"tenderrefno": "NAIROBI/099/2021", "tendertitle": "Nairobi Road Works", ...}
    page.evaluate = AsyncMock(return_value=[matching, unrelated])
    with patch("data.scrapers.egp.async_playwright", mock_playwright):
        result = await EGPScraper().fetch(ctx=ctx)
    # Targeted mode only returns filtered results
    assert len(result) == 1
    assert result[0]["tenderrefno"] == "GARISSA/001/2021"

async def test_egp_bulk_mode_preserved_when_no_context():
    # Legacy behaviour: fetch(ctx=None) still returns all tenders
    ...
```

#### V-2b: NCAScraper targeted mode

```python
async def test_nca_uses_context_search_terms_not_generic_list():
    ctx = build_test_context(search_terms=["Garissa Headquarters", "County HQ"])
    mock_playwright, page, _ = _make_playwright_mock()
    search_calls = []
    # Capture what was typed into the search box
    page.fill = AsyncMock(side_effect=lambda sel, val: search_calls.append(val))
    page.evaluate = AsyncMock(return_value=[])
    with patch("data.scrapers.nca.async_playwright", mock_playwright):
        await NCAScraper().fetch(ctx=ctx)
    assert "Garissa Headquarters" in search_calls
    assert "County HQ" in search_calls
    # Generic terms like "Road", "Building" must NOT appear
    assert "Road" not in search_calls
    assert "Building" not in search_calls
```

#### V-2c: PPIPScraper filtered mode

```python
async def test_ppip_filters_by_aliases():
    ctx = build_test_context(
        aliases=["Garissa County HQ", "Garissa County Government HQ"],
        canonical_name="Construction of Garissa County Government Headquarters"
    )
    all_tenders = [
        {"title": "Garissa County HQ Construction", "tender_ref": "PPIP-001"},
        {"title": "Mombasa Ring Road Phase 2", "tender_ref": "PPIP-099"},
        {"title": "Construction Garissa County Government Headquarters", "tender_ref": "PPIP-002"},
    ]
    resp = _http_resp(200, {"data": all_tenders})
    with patch("data.scrapers.ppip.httpx.AsyncClient",
               return_value=_make_httpx_client([resp])):
        result = await PPIPScraper().fetch(ctx=ctx)
    assert len(result) == 2  # both Garissa records matched
    refs = {r["tender_ref"] for r in result}
    assert "PPIP-099" not in refs   # unrelated Mombasa record excluded
```

#### V-2d: CoBPoller fiscal year filter

```python
async def test_cob_poller_downloads_only_matching_fiscal_years():
    ctx = build_test_context(fiscal_years=["2021/2022", "2022/2023"])
    mock_playwright, page, _ = _make_playwright_mock()
    all_reports = [
        {"title": "FY 2021/2022 Q4 BIRR", "url": "https://cob.go.ke/fy-2021-2022-q4.pdf"},
        {"title": "FY 2022/2023 Q4 BIRR", "url": "https://cob.go.ke/fy-2022-2023-q4.pdf"},
        {"title": "FY 2019/2020 Q2 BIRR", "url": "https://cob.go.ke/fy-2019-2020-q2.pdf"},
    ]
    with patch.object(CoBPoller, 'find_reports', return_value=all_reports):
        with patch.object(CoBPoller, 'download_report', return_value="/tmp/test.pdf") as mock_dl:
            await CoBPoller().process(ctx=ctx)
    downloaded_urls = [call.args[0] for call in mock_dl.call_args_list]
    assert "https://cob.go.ke/fy-2021-2022-q4.pdf" in downloaded_urls
    assert "https://cob.go.ke/fy-2022-2023-q4.pdf" in downloaded_urls
    assert "https://cob.go.ke/fy-2019-2020-q2.pdf" not in downloaded_urls
```

#### V-2e: KMHFLScraper GPS skip

```python
async def test_kmhfl_skips_fetch_when_coordinates_known():
    ctx = build_test_context(coordinates=(-0.4536, 39.6401))
    result = await KMHFLScraper().fetch(ctx=ctx)
    assert result == []  # skipped entirely

async def test_kmhfl_fetches_when_coordinates_unknown():
    ctx = build_test_context(coordinates=None)
    resp = _http_resp(200, {"count": 1, "next": None, "results": [{"name": "KNH"}]})
    with patch("data.scrapers.kmhfl.httpx.AsyncClient",
               return_value=_make_httpx_client([resp])):
        result = await KMHFLScraper().fetch(ctx=ctx)
    assert len(result) == 1
```

**Pass criteria for V-2:**

- No unrelated procurement records inserted when all five scrapers run with the Garissa context
- `procurement_records` table contains ≥1 row with `tender_title` containing "Garissa" after a targeted investigation run
- Generic search terms ("Road", "Building") do not appear in NCA search calls when context is provided
- Bulk mode (ctx=None) behaviour is unaffected for all five scrapers

---

### Stage V-3: IntelligentCoBParser

**What is being verified:** The two-stage parser correctly identifies and extracts budget figures for the target project from a real BIRR PDF.

#### V-3a: Candidate page selection (pdfplumber — no API cost)

```python
# data/tests/test_intelligent_parser.py

def test_candidate_selection_finds_pages_with_garissa_keywords(sample_pdf_path):
    ctx = build_test_context(
        canonical_name="Construction of Garissa County Government Headquarters",
        county="Garissa",
        aliases=["Garissa County HQ"],
        ministry="State Department for Devolution",
        vote_head=260,
    )
    parser = IntelligentCoBParser(pdf_path=sample_pdf_path, ctx=ctx,
                                  openai_client=None)
    candidates = parser._select_candidates()
    assert len(candidates) > 0, "At least one candidate page must be found"
    # All returned indices must be valid page numbers
    import pdfplumber
    with pdfplumber.open(sample_pdf_path) as pdf:
        total_pages = len(pdf.pages)
    assert all(0 <= p < total_pages for p in candidates)

def test_candidate_selection_excludes_pages_without_any_keyword(sample_pdf_path):
    # A context with a project name that definitely does not appear in the PDF
    ctx = build_test_context(
        canonical_name="Completely Fabricated Project Name XYZ123",
        county="Fakeland",
        aliases=[],
    )
    parser = IntelligentCoBParser(pdf_path=sample_pdf_path, ctx=ctx,
                                  openai_client=None)
    candidates = parser._select_candidates()
    assert candidates == [], "No candidates expected for non-existent project"
```

#### V-3b: Page rendering

```python
def test_render_page_returns_png_bytes(sample_pdf_path):
    ctx = build_test_context()
    parser = IntelligentCoBParser(sample_pdf_path, ctx, None)
    png_bytes = parser._render_page(0)
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 1000       # not empty
    assert png_bytes[:4] == b'\x89PNG' # valid PNG header
```

#### V-3c: Vision extraction (mocked OpenAI)

```python
async def test_vision_extract_returns_financial_record_on_match(sample_pdf_path):
    ctx = build_garissa_context()
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(choices=[Mock(message=Mock(
            content=json.dumps(GARISSA_VISION_RESPONSE)
        ))])
    )
    parser = IntelligentCoBParser(sample_pdf_path, ctx, mock_client)
    page_bytes = parser._render_page(0)
    record = await parser._vision_extract(0, page_bytes)
    assert record is not None
    assert record["budget_allocated_kes"] == 275_000_000
    assert record["absorption_rate"] == 81.9
    assert record["match_method"] == "openai_vision_gpt4o"
    assert record["source_system"] == "COB"
    assert record["fiscal_year"] == "2021/2022"

async def test_vision_extract_returns_none_on_no_match(sample_pdf_path):
    ctx = build_garissa_context()
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=Mock(choices=[Mock(message=Mock(
            content=json.dumps({"match": False})
        ))])
    )
    parser = IntelligentCoBParser(sample_pdf_path, ctx, mock_client)
    record = await parser._vision_extract(0, b"fake_image")
    assert record is None

async def test_full_extract_returns_only_matching_records(sample_pdf_path):
    # Full two-stage run: candidate selection + mocked vision
    ctx = build_garissa_context()
    # Vision returns match on page 0, no-match on all others
    responses = [GARISSA_VISION_RESPONSE] + [{"match": False}] * 50
    mock_client = build_mock_openai_client(responses)
    parser = IntelligentCoBParser(sample_pdf_path, ctx, mock_client,
                                   max_vision_pages=5)
    results = await parser.extract()
    assert len(results) == 1
    assert results[0]["budget_absorbed_kes"] == 225_300_000
```

#### V-3d: Live extraction test (requires OPENAI_API_KEY + real PDF)

```python
@pytest.mark.integration
async def test_live_extraction_garissa_birr():
    """
    Requires:
      - OPENAI_API_KEY in environment
      - data/raw/cob/BIRR_Q4_2022_2023.pdf downloaded
    """
    pdf_path = Path("data/raw/cob/BIRR_Q4_2022_2023.pdf")
    if not pdf_path.exists():
        pytest.skip("Real BIRR PDF not available")
    ctx = build_garissa_context()
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    parser = IntelligentCoBParser(str(pdf_path), ctx, client)
    results = await parser.extract()
    assert len(results) >= 1, "Expected at least one budget record for Garissa"
    rec = results[0]
    # Budget must be in a plausible range for a KES 550M project
    assert rec["budget_allocated_kes"] > 50_000_000
    assert rec["budget_allocated_kes"] < 600_000_000
    assert 0 < rec["absorption_rate"] <= 100
```

**Pass criteria for V-3:**

- Candidate selection returns ≥1 page for reference project from a real BIRR PDF
- Candidate selection returns 0 pages for a fabricated project name
- Full extract returns ≥1 `FinancialRecord`-compatible dict for reference project
- No `FinancialRecord` returned for a project not mentioned in the PDF
- Live test: budget figures within 20% of known ground truth from PIC report

---

### Stage V-4: Concordance (Existing Service — Targeted Input Validation)

**What is being verified:** After targeted scraping, `ConcordanceService` correctly links all retrieved procurement records to one project without creating spurious duplicate project entries.

```python
# backend/tests/test_concordance_targeted.py

async def test_concordance_links_all_targeted_records_to_one_project(db):
    # Insert 3 procurement records that all describe the same project (different aliases)
    records = [
        create_procurement("Construction of Garissa County Government Headquarters",
                           source="NCA"),
        create_procurement("GARISSA COUNTY HQ BLOCK A", source="EGP"),
        create_procurement("Garissa County Headquarters Phase 1", source="PPIP"),
    ]
    for r in records: db.add(r); await db.commit()
    service = ConcordanceService(db)
    for r in records:
        await service.link_procurement_to_project(r.procurement_id)
    # All three must link to EXACTLY ONE project
    project_uuids = {r.project_uuid for r in records}
    await db.refresh(records[0]); await db.refresh(records[1]); await db.refresh(records[2])
    linked_uuids = {r.project_uuid for r in records}
    assert len(linked_uuids) == 1, (
        f"Expected 1 project, got {len(linked_uuids)}: {linked_uuids}"
    )

async def test_concordance_does_not_create_duplicate_projects(db):
    # Run reconcile_all_unlinked twice — should not create two projects for same tender
    ...
```

**Pass criteria:**

- 3 procurement records describing the same project in different alias forms → all link to exactly 1 project UUID
- Running concordance twice on the same records does not create duplicate Project rows
- `reconcile_all_unlinked()` processes the targeted investigation's records in <1 second

---

### Stage V-5: Geolocation (Tier 0 — Perplexity coordinates)

**What is being verified:** When `ctx.coordinates` is populated by Perplexity, geolocation resolves at Tier 0 (confidence ≥ 85) without calling KMHFL or the ward centroid fallback.

```python
# backend/tests/test_geolocation_targeted.py

async def test_tier0_resolution_uses_perplexity_coordinates(db):
    project = create_project("Garissa County Headquarters")
    ctx = build_garissa_context()  # ctx.coordinates = (-0.4536, 39.6401)
    service = GeolocationService(db)
    result = await service.resolve_from_context(project.project_uuid, ctx)
    assert result is not None
    assert result.tier == 0    # new tier for Perplexity-sourced GPS
    assert result.confidence >= 85
    assert abs(result.lat - (-0.4536)) < 0.001
    assert abs(result.lon - 39.6401) < 0.001
    assert result.method == "perplexity_web_search"

async def test_geolocation_falls_back_to_tier1_when_context_has_no_coords(db):
    ctx = build_garissa_context()
    ctx.coordinates = None  # force fallback
    # procurement record has EGP GPS embedded
    proc = create_procurement_with_gps(lat=-0.4536, lon=39.6401,
                                        gps_source="EGP_MANUAL_PIN")
    result = await GeolocationService(db).resolve(proc.procurement_id)
    assert result.tier == 1
    assert result.method in ("EGP_MANUAL_PIN", "EGP_AUTO_GEOCODED")
```

**Pass criteria:**

- For all 10 validation projects where Perplexity returns coordinates: Tier 0 resolution succeeds
- Tier 0 coordinates produce a `GeolocationRecord` with `match_confidence` ≥ 85
- Tier fallback chain still works when `ctx.coordinates` is None (existing tests remain green)

---

### Stage V-6: Satellite Analysis (Existing — Input Quality Validation)

**What is being verified:** The satellite analysis queue receives correct GPS coordinates from Stage V-5, and the resulting `SatelliteAnalysis` rows have real (non-NaN) `ndvi_slope` values after processing.

This stage does not make real Sentinel-2 API calls in verification. It verifies:

1. That `SatelliteService.queue_analysis()` is called with correct coordinates after geolocation
2. That mock spectral data produces a computable `ndvi_slope` via `compute_ndvi_slope()`
3. That the resulting feature is in the physically plausible range

```python
# backend/tests/test_satellite_targeted.py

async def test_satellite_queued_with_correct_coordinates(db):
    project = create_geolocated_project(lat=-0.4536, lon=39.6401)
    with patch("backend.src.tasks.satellite.celery_app.send_task") as mock_send:
        task_id = await SatelliteService(db).queue_analysis(project.project_uuid)
    assert mock_send.called
    call_kwargs = mock_send.call_args
    args = call_kwargs[0][1]  # positional args to the task
    assert abs(args[1] - (-0.4536)) < 0.001  # lat
    assert abs(args[2] - 39.6401) < 0.001    # lon

async def test_ndvi_slope_computed_from_two_real_analyses(db):
    project = create_project("Garissa County Headquarters")
    # Simulate two NDVI_change scenes 6 months apart
    create_satellite_analysis(project.project_uuid,
                               acquisition_date=date(2022, 6, 1), ndvi_mean=0.42)
    create_satellite_analysis(project.project_uuid,
                               acquisition_date=date(2022, 12, 1), ndvi_mean=0.18)
    slope = await SatelliteService(db).compute_ndvi_slope(project.project_uuid)
    assert slope is not None
    assert slope < 0, "Declining NDVI must produce negative slope"
    assert -0.20 <= slope <= 0, "Slope must be in physically plausible range"

async def test_ndvi_slope_feature_is_not_nan_after_two_scenes(db):
    """
    This is the core regression test for the ML feature completeness problem.
    After a real investigation has ≥2 satellite scenes, ndvi_slope MUST be a
    real float, not NaN. If this fails, the 7-NaN feature problem has regressed.
    """
    project = create_project_with_two_ndvi_scenes()
    slope = await SatelliteService(db).compute_ndvi_slope(project.project_uuid)
    assert slope is not None
    assert not math.isnan(slope), (
        "ndvi_slope is NaN — satellite pipeline is not populating this feature. "
        "This means RandomForest would receive NaN input. Fix before enabling ML."
    )
```

**Pass criteria:**

- `queue_analysis` is called with coordinates within 0.001° of the Perplexity-resolved GPS
- `compute_ndvi_slope` returns a non-NaN float when ≥2 NDVI_change scenes exist
- Slope is in range [−0.20, +0.10] for all 10 validation projects

---

### Stage V-7: Divergence Score (The Primary Risk Signal)

**What is being verified:** The divergence score correctly classifies the reference ghost project as CRITICAL and the reference successful project as LOW/MEDIUM. This is the highest-stakes assertion in the verification plan.

```python
# backend/tests/test_divergence_targeted.py

async def test_divergence_classifies_garissa_hq_as_critical(db):
    """
    Garissa County Headquarters: ~82% budget absorbed (COB data), ~15% physical
    progress (Sentinel-2 minimal NDVI change). Divergence = 67. Expect CRITICAL.
    """
    project = create_project("Garissa County Headquarters")
    # Seed a FinancialRecord matching IntelligentCoBParser output
    create_financial_record(project.project_uuid,
                            absorption_rate=81.9, fiscal_year="2022/2023")
    # Seed a SatelliteAnalysis with low ndvi_slope (slight decline — minimal activity)
    create_satellite_analysis(project.project_uuid,
                               ndvi_slope=-0.008,  # very slight — no real clearing
                               sar_backscatter_delta=0.3)  # weak SAR signal
    result = await DivergenceService(db).calculate_divergence(project.project_uuid)
    assert result["alert_level"] == "RED"
    assert result["divergence_score"] > 50
    assert result["financial_progress"] > 70
    assert result["physical_progress"] < 30

async def test_divergence_classifies_kiambu_hospital_as_low(db):
    """
    Kiambu Level 4 Hospital: completed project. High physical progress + normal absorption.
    Expect LOW or MEDIUM.
    """
    project = create_project("Kiambu Level 4 Hospital Construction")
    create_financial_record(project.project_uuid, absorption_rate=94.0)
    create_satellite_analysis(project.project_uuid,
                               ndvi_slope=-0.045,   # significant clearing = construction
                               sar_backscatter_delta=3.2)  # strong SAR = new structures
    result = await DivergenceService(db).calculate_divergence(project.project_uuid)
    assert result["alert_level"] == "GREEN"
    assert result["divergence_score"] < 20

async def test_divergence_returns_unknown_when_no_financial_data(db):
    project = create_project("Incomplete Investigation")
    # No FinancialRecord exists
    create_satellite_analysis(project.project_uuid, ndvi_slope=-0.03)
    result = await DivergenceService(db).calculate_divergence(project.project_uuid)
    assert result["alert_level"] == "UNKNOWN"
    assert result["financial_progress"] is None

async def test_divergence_result_written_to_project_risk_level(db):
    project = create_project("Garissa County Headquarters")
    create_financial_record(project.project_uuid, absorption_rate=81.9)
    create_satellite_analysis(project.project_uuid, ndvi_slope=-0.008,
                               sar_backscatter_delta=0.3)
    await DivergenceService(db).calculate_divergence(project.project_uuid)
    await db.refresh(project)
    assert project.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH)
```

**Pass criteria:**

- Reference ghost project (Garissa HQ) → alert_level = RED, divergence_score > 50
- Reference successful project (Kiambu Hospital) → alert_level = GREEN, divergence_score < 20
- Projects with missing financial data return `alert_level = UNKNOWN`, not an exception
- `Project.risk_level` is updated in the DB after `calculate_divergence()` completes

---

### Stage V-8: Investigation Report Endpoint

**What is being verified:** `GET /api/v1/investigations/{id}/report` returns a complete, correctly structured report after the full pipeline completes.

```python
# backend/tests/test_investigation_report.py

async def test_report_contains_all_required_fields(client, completed_investigation):
    response = await client.get(
        f"/api/v1/investigations/{completed_investigation.investigation_id}/report"
    )
    assert response.status_code == 200
    data = response.json()

    # Context section
    assert data["project_context"]["county"] == "Garissa"
    assert data["project_context"]["enrichment_confidence"] >= 0.5

    # Procurement section
    assert len(data["procurement_records"]) >= 1
    assert all("tender_title" in r for r in data["procurement_records"])

    # Financial section
    assert len(data["financial_records"]) >= 1
    rec = data["financial_records"][0]
    assert rec["budget_absorbed_kes"] is not None
    assert rec["match_method"] == "openai_vision_gpt4o"

    # Geolocation section
    assert data["geolocation"]["latitude"] is not None
    assert data["geolocation"]["confidence"] >= 20

    # Risk assessment section
    assert data["divergence_score"] is not None
    assert data["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert data["ghost_probability"] is None  # disabled in MVP phase
    assert "probabilistic" in data["ghost_probability_note"].lower()

    # Status
    assert data["status"] == "complete"

async def test_report_risk_level_consistent_with_divergence_score(client, completed_investigation):
    response = await client.get(
        f"/api/v1/investigations/{completed_investigation.investigation_id}/report"
    )
    data = response.json()
    score = data["divergence_score"]
    level = data["risk_level"]
    if score > 50:
        assert level == "CRITICAL"
    elif 20 <= score <= 50:
        assert level == "HIGH"
    else:
        assert level in ("LOW", "MEDIUM")
```

**Pass criteria:**

- All required top-level keys present in report JSON
- `ghost_probability` is `null` (ML disabled in MVP)
- `risk_level` is semantically consistent with `divergence_score`
- `financial_records[].match_method == "openai_vision_gpt4o"` for COB-sourced records
- Report endpoint returns 404 if investigation does not exist
- Report endpoint returns 409 if investigation has not yet completed

---

## 6. Feature Completeness Regression Test

This is a single assertion that guards against the core failure mode of the old system: features being NaN when the ML model is eventually activated.

```python
# satellite/tests/test_feature_completeness.py

VALIDATION_PROJECTS = [
    # Subset of 10 manually curated real projects
    # Each must have at least 2 satellite scenes and one COB financial record
    "test-investigation-garissa-hq",
    "test-investigation-kiambu-hospital",
    # ... (remaining 8 when curated)
]

@pytest.mark.parametrize("investigation_id", VALIDATION_PROJECTS)
async def test_all_10_features_populated_after_investigation(investigation_id, db):
    """
    After a complete investigation, FeatureEngineer.extract_features() must
    return a Series with zero NaN values. If any feature is NaN, the investigation
    pipeline has a gap that would compromise future ML accuracy.
    """
    project_data = await fetch_project_data_for_investigation(investigation_id, db)
    fe = FeatureEngineer()
    features = fe.extract_features(project_data)

    nan_features = [name for name, val in zip(FEATURES, features)
                    if math.isnan(float(val))]

    assert nan_features == [], (
        f"Investigation {investigation_id} has NaN features: {nan_features}\n"
        f"These features will be missing when ML model is activated at 50 investigations.\n"
        f"Fix the pipeline stage responsible for populating each NaN feature."
    )
```

---

## 7. ML Feature Readiness Gate

Before activating `RiskScoringService` in the growth phase (≥50 investigations), the following gate must pass:

```python
# backend/tests/test_ml_readiness_gate.py

async def test_ml_not_called_in_mvp_investigation_flow(client, completed_investigation):
    """Guard: RiskScoringService must NOT be called during MVP investigations."""
    with patch("backend.src.services.risk_scoring_service.RiskScoringService.score_project") \
            as mock_score:
        await client.post(
            f"/api/v1/investigations/{completed_investigation.investigation_id}/scrape"
        )
    mock_score.assert_not_called()

async def test_ml_readiness_gate_passes_at_50_real_investigations(db):
    """
    Before enabling ML: verify that ≥50 investigations have all 10 features populated.
    This test is run manually as a pre-upgrade check.
    """
    completed = await db.execute(
        select(Investigation)
        .where(Investigation.status == "complete")
        .order_by(Investigation.created_at)
    )
    rows = completed.scalars().all()
    verified_feature_vectors = []
    nan_counts = {}

    for inv in rows:
        project_data = await fetch_project_data(inv.project_uuid, db)
        features = FeatureEngineer().extract_features(project_data)
        if not any(math.isnan(float(v)) for v in features):
            verified_feature_vectors.append(features)
        else:
            for name, val in zip(FEATURES, features):
                if math.isnan(float(val)):
                    nan_counts[name] = nan_counts.get(name, 0) + 1

    assert len(verified_feature_vectors) >= 50, (
        f"Only {len(verified_feature_vectors)} complete feature vectors available. "
        f"Need 50 before enabling ML. NaN counts by feature: {nan_counts}"
    )
```

---

## 8. End-to-End Integration Test

The full E2E test simulates the complete investigation lifecycle using mocked external APIs, a real PostgreSQL test database, and the Celery task chain.

```python
# backend/tests/integration/test_e2e_single_project.py

@pytest.mark.integration
async def test_full_garissa_investigation_pipeline(client, db):
    """
    Full mocked E2E: POST investigation → enrich → scrape → parse → report.

    Mocks:
      - Perplexity API → GARISSA_RESPONSE
      - EGP Playwright → returns 1 matching tender
      - NCA Playwright → returns 1 matching project row
      - PPIP httpx → returns 0 matching tenders (not in active tenders)
      - CoB Playwright + httpx → returns 1 report downloaded
      - OpenAI Vision → returns GARISSA_VISION_RESPONSE for 1 page
      - Sentinel-2 / SAR → synthetic NDVI scene injected directly

    Real components:
      - PostgreSQL (test schema)
      - ConcordanceService
      - GeolocationService
      - DivergenceService
    """

    # Step 1: Create investigation
    r = await client.post("/api/v1/investigations",
                          json={"project_name": "Garissa County Headquarters",
                                "user_notes": "Suspected ghost project"})
    assert r.status_code == 201
    inv_id = r.json()["investigation_id"]

    # Step 2: Enrich with mocked Perplexity
    with patch_perplexity(GARISSA_RESPONSE):
        r = await client.post(f"/api/v1/investigations/{inv_id}/enrich")
    assert r.status_code == 200
    ctx = r.json()
    assert ctx["county"] == "Garissa"

    # Step 3: Confirm context (no changes needed)
    r = await client.patch(f"/api/v1/investigations/{inv_id}/context",
                           json={"context_confirmed": True})
    assert r.status_code == 200

    # Step 4: Trigger scraping with all scrapers mocked
    with patch_all_scrapers_for_garissa():
        with patch_openai_vision(GARISSA_VISION_RESPONSE):
            r = await client.post(f"/api/v1/investigations/{inv_id}/scrape")
    assert r.status_code == 202

    # Step 5: Wait for pipeline to complete (in test: run tasks synchronously)
    await wait_for_pipeline_completion(inv_id, db, timeout=30)

    # Step 6: Check status
    r = await client.get(f"/api/v1/investigations/{inv_id}/status")
    statuses = r.json()["stage_statuses"]
    assert all(v == "complete" for v in statuses.values()), \
        f"Some stages not complete: {statuses}"

    # Step 7: Assert report contents
    r = await client.get(f"/api/v1/investigations/{inv_id}/report")
    assert r.status_code == 200
    report = r.json()

    assert report["status"] == "complete"
    assert len(report["procurement_records"]) >= 1
    assert len(report["financial_records"]) >= 1
    assert report["financial_records"][0]["absorption_rate"] == 81.9
    assert report["geolocation"]["confidence"] >= 85  # Tier 0 from Perplexity
    assert report["risk_level"] == "CRITICAL"
    assert report["divergence_score"] > 50
    assert report["ghost_probability"] is None  # ML disabled in MVP

    # Step 8: Verify DB state
    project = await db.get(Project, report["project_uuid"])
    assert project.risk_level == RiskLevel.CRITICAL
    proc_records = await get_procurement_records_for_investigation(inv_id, db)
    assert all(r.investigation_id == inv_id for r in proc_records)
    fin_records = await get_financial_records_for_investigation(inv_id, db)
    assert all(r.investigation_id == inv_id for r in fin_records)
```

---

## 9. Verification Run Order

Run these in sequence. A failure at any stage should block progression to the next.

```
1.  data/venv-data/bin/pytest data/tests/test_targeted_scrapers.py -v
                                    → Stage V-2 (all 5 scrapers)

2.  data/venv-data/bin/pytest data/tests/test_intelligent_parser.py -v
                                    → Stage V-3a, V-3b, V-3c

3.  backend/venv-backend/bin/pytest backend/tests/test_enrichment.py -v
                                    → Stage V-1 (mocked)

4.  backend/venv-backend/bin/pytest backend/tests/test_concordance_targeted.py -v
                                    → Stage V-4

5.  backend/venv-backend/bin/pytest backend/tests/test_geolocation_targeted.py -v
                                    → Stage V-5

6.  backend/venv-backend/bin/pytest backend/tests/test_satellite_targeted.py -v
                                    → Stage V-6

7.  backend/venv-backend/bin/pytest backend/tests/test_divergence_targeted.py -v
                                    → Stage V-7

8.  backend/venv-backend/bin/pytest backend/tests/test_investigation_report.py -v
                                    → Stage V-8

9.  satellite/venv-satellite/bin/pytest satellite/tests/test_feature_completeness.py -v
                                    → Feature completeness regression

10. backend/venv-backend/bin/pytest backend/tests/test_ml_readiness_gate.py::test_ml_not_called_in_mvp_investigation_flow -v
                                    → ML guard

11. backend/venv-backend/bin/pytest backend/tests/integration/test_e2e_single_project.py -v
                                    → Full E2E
```

Single command for all unit-level checks (no API keys needed):

```bash
cd /home/meyvn/Desktop/K1NYANJU1/Cracked-Dev/oneka

data/venv-data/bin/pytest data/tests/test_targeted_scrapers.py \
                          data/tests/test_intelligent_parser.py \
                          -v --cov=data/scrapers --cov=data/parsers \
                          --cov-report=term-missing

backend/venv-backend/bin/pytest backend/tests/test_enrichment.py \
                                 backend/tests/test_concordance_targeted.py \
                                 backend/tests/test_geolocation_targeted.py \
                                 backend/tests/test_satellite_targeted.py \
                                 backend/tests/test_divergence_targeted.py \
                                 backend/tests/test_investigation_report.py \
                                 backend/tests/test_ml_readiness_gate.py \
                                 -v --cov=backend/src/services \
                                 --cov-report=term-missing
```

---

## 10. Pass Criteria Summary

The single-project pipeline is considered **verified and production-ready** when all of the following hold:

| #   | Criterion                                                                                                                         | Stage                |
| --- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| 1   | `PerplexityEnrichmentService` returns ≥1 alias and correct county for all 10 validation projects                                  | V-1                  |
| 2   | All 5 scrapers with targeted context produce 0 unrelated procurement rows for the Garissa reference                               | V-2                  |
| 3   | `IntelligentCoBParser` returns ≥1 `FinancialRecord` from a real BIRR PDF with correct absorption rate (within 5% of ground truth) | V-3                  |
| 4   | All targeted procurement records link to exactly 1 project UUID after concordance                                                 | V-4                  |
| 5   | Tier 0 GPS resolution succeeds for all validation projects where Perplexity returned coordinates                                  | V-5                  |
| 6   | `ndvi_slope` is a non-NaN float after ≥2 satellite scenes                                                                         | V-6                  |
| 7   | Garissa reference project → CRITICAL; Kiambu reference → GREEN                                                                    | V-7                  |
| 8   | `GET /investigations/{id}/report` returns complete report with `ghost_probability = null`                                         | V-8                  |
| 9   | `FeatureEngineer.extract_features()` returns 0 NaN values for all 10 validation projects                                          | Feature completeness |
| 10  | `RiskScoringService.score_project()` is never called in the MVP investigation flow                                                | ML guard             |
| 11  | Full E2E integration test passes in a clean Docker environment                                                                    | E2E                  |
| 12  | All new code at ≥80% test coverage across `data/` and `backend/src/`                                                              | Coverage gate        |
