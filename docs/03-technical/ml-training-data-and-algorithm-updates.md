# ML Training Data & Algorithm Updates: Post-Government Systems Analysis

## Based on Reality-Check of Kenya's Digital Infrastructure

**Date**: February 19, 2026  
**Purpose**: Assess ML training data availability and required algorithm changes based on PPIP/e-GP/CoB integration findings  
**Context**: Discovery of e-GP mandatory GPS + PPIP historical-only status changes our ML approach

---

## Executive Summary

The discovery that **e-GP has mandatory GPS coordinates** (70-85% of projects) and **PPIP is historical-only** fundamentally changes both:

1. **What training data is available** (256K historical tenders without GPS vs 4.6K current tenders with GPS)
2. **How our algorithms work** (location triangulation shifts from "hard problem" to "validation problem")

**Key Findings**:

- ✅ **Training Data Volume**: Abundant (256K historical PPIP + 4.6K e-GP tenders)
- ⚠️ **Training Data Quality**: PPIP lacks GPS (requires post-processing), e-GP has GPS but is recent (limited temporal history)
- 🔄 **Algorithm Redesign Required**: Location triangulation changes from fuzzy matching → GPS quality validation
- 🔄 **Change Detection Evolution**: Shift from "detect construction anywhere" → "validate progress at known GPS"
- ✅ **Triangle of Truth**: New ML task - predict financial vs physical progress gap

---

## Part 1: Training Data Inventory

### 1.1 PPIP Historical Data (2018-2025)

**Available Data**:

```
Volume: 256,034 tenders published
Contracts: 130,839 signed contracts
Value: KES 2.06 trillion transacted
Time Period: ~2018-2025 (pre-e-GP mandate July 2025)
Geographic Coverage: All 47 counties
```

**Data Fields Available** (via web scraping):
| Field | Availability | Quality | ML Utility |
|-------|-------------|---------|-----------|
| Tender Number | ✅ 100% | HIGH | Primary key |
| Tender Title | ✅ 100% | MEDIUM | Text mining for project type |
| Procuring Entity | ✅ 100% | HIGH | Ministry/County classification |
| Tender Category | ✅ 100% | HIGH | Works/Goods/Services |
| Tender Value | ⚠️ 80% | MEDIUM | Budget predictor (many "N/A") |
| Publication Date | ✅ 100% | HIGH | Temporal feature |
| Closing Date | ✅ 100% | HIGH | Timeline estimator |
| Location (text) | ⚠️ 70% | LOW | "Nairobi County" (no GPS) |
| PDF Document | ✅ 95% | VARIABLE | OCR for details |
| Contract Award | ⚠️ 51% | MEDIUM | 130K awards from 256K tenders |
| **GPS Coordinates** | ❌ 0% | N/A | **NOT in schema** |

**CRITICAL LIMITATION**:

```
❌ NO GPS COORDINATES IN PPIP DATA

Evidence:
- Database schema: text-only location field
- Website interface: no map views
- Export format: no lat/lon columns

Impact on ML Training:
- Cannot directly train satellite change detection models
- Cannot validate historical project outcomes without manual GPS annotation
- Requires post-processing geolocation step (see Section 2.1)
```

**What We CAN Use PPIP For**:

1. **Project Type Classification Training**:

   ```python
   # Labeled dataset from tender titles
   examples = [
       ("Construction of Ruiru Level 4 Hospital", "HEALTH_FACILITY"),
       ("Supply of Laptops to Dagoretti North Schools", "EDUCATION_GOODS"),
       ("Rehabilitation of Kisumu-Busia Road", "INFRASTRUCTURE_ROADS"),
       ("Installation of Borehole at Garissa County", "WATER_INFRASTRUCTURE")
   ]

   # Train NER model for facility type extraction
   # Useful for: GPS validation (does land use match project type?)
   ```

2. **Budget Anomaly Detection**:

   ```python
   # Historical budget distributions by category
   health_budgets = ppip_df[ppip_df['category'] == 'HEALTH']['tender_value_kes']

   # Train outlier detection model
   # Useful for: Flag suspiciously low/high budgets (ghost project indicator)
   ```

3. **Timeline Prediction**:

   ```python
   # Features: project type, budget, county, procurement method
   # Target: expected_duration_months

   # Useful for: Baseline for "expected completion date" when calculating progress gap
   ```

4. **Contractor Performance History** (if we scrape contract awards):
   ```python
   # Count completed vs abandoned projects per contractor
   # Useful for: Risk priors in ML model (contractor with 80% ghost rate = red flag)
   ```

**What We CANNOT Use PPIP For**:

- ❌ Direct satellite change detection training (no GPS to task satellites)
- ❌ Geolocation model training (location is text, not coordinates)
- ❌ Physical progress validation (no ground truth GPS locations)

**PPIP Data Acquisition Plan**:

```python
# Sprint 2 Task: Historical PPIP Import
# Status: Scraper implemented, pending real tender test

scraping_strategy = {
    "method": "ONE-TIME historical batch import",
    "target_records": 256034,
    "time_period": "2018-01 to 2025-06-30",  # Pre-e-GP mandate cutoff
    "data_fields": [
        "tender_number", "tender_title", "procuring_entity",
        "category", "tender_value_kes", "publication_date",
        "location_text", "pdf_document_url"
    ],
    "post_processing": [
        "Extract project type from title (NER)",
        "Normalize location text (county/ward standardization)",
        "Download PDFs for OCR (contractor names, detailed budgets)",
        "FLAG: Geolocation required (see Section 2.1)"
    ],
    "estimated_duration": "48 hours scraping + 7 days post-processing",
    "storage": "PostgreSQL procurement_records table + S3 for PDFs"
}
```

---

### 1.2 e-GP Current Data (July 2025 - Present)

**Available Data**:

```
Volume: 4,591 active tenders (as of Feb 19, 2026)
Suppliers: 36,316 registered
Procuring Entities: 1,495 entities
Time Period: July 2025 - present (8 months)
OCDS Compliance: Yes (structured JSON)
```

**Data Fields Available** (OCDS JSON structure):
| Field | Availability | Quality | ML Utility |
|-------|-------------|---------|-----------|
| Tender ID | ✅ 100% | HIGH | Primary key |
| OCDS ID | ✅ 100% | HIGH | Unique identifier |
| Tender Title | ✅ 100% | HIGH | Project type extraction |
| Procuring Entity | ✅ 100% | HIGH | Entity classification |
| Contract Value | ✅ 100% | HIGH | Budget feature |
| **GPS Latitude** | ✅ 87% | MEDIUM | **GAME CHANGER** |
| **GPS Longitude** | ✅ 87% | MEDIUM | **GAME CHANGER** |
| Delivery Location Text | ✅ 95% | MEDIUM | Backup geolocation |
| Award Date | ⚠️ 12% | HIGH | Only awarded tenders (531/4591) |
| Contractor Name | ⚠️ 12% | HIGH | Only awarded tenders |
| Contract Period | ⚠️ 12% | HIGH | Timeline for monitoring |
| **Publication Date** | ✅ 100% | HIGH | Tender lifecycle tracking |

**GPS Data Quality** (from government systems analysis):

```
Total tenders: 4,591
With GPS: ~4,000 (87%)
Without GPS: ~591 (13%)

GPS Quality Issues (estimated):
- County HQ lazy pins: 30-40% (1,200-1,600 tenders)
- Nairobi CBD clustering: 15-20% (600-800 tenders)
- Wrong county: 5% (~200 tenders)
- Invalid (ocean/border): 1% (~40 tenders)
- ACCEPTABLE quality: 40-50% (1,800-2,300 tenders)
- VERIFIED (cross-referenced): 10-15% (400-700 tenders)

After validation pipeline: 70-85% usable GPS (3,200-3,900 tenders)
```

**What We CAN Use e-GP For**:

1. **Satellite Change Detection Training** (LIMITED by temporal history):

   ```python
   # CONSTRAINT: e-GP data only available since July 2025 (8 months)
   # Most projects still ongoing (insufficient temporal progression)

   training_candidates = egp_df[
       (egp_df['award_date'] < '2025-09-01') &  # Awarded >5 months ago
       (egp_df['expected_completion'] < date.today()) &  # Should be complete
       (egp_df['gps_quality_score'] > 80)  # Good GPS quality
   ]

   # Estimated available: ~50-100 projects
   # Too small for robust ML training (need 500+ for good model)

   # SOLUTION: Combine with manually geolocated PPIP projects (see Section 2.1)
   ```

2. **GPS Quality Validation Model**:

   ```python
   # Features: county, project_type, gps_lat, gps_lon, land_use, road_proximity
   # Target: gps_quality_label (VERIFIED, ACCEPTABLE, SUSPECT, INVALID)

   # Training data: Manual validation of 200-300 e-GP GPS coordinates
   # Geospatial engineer validates sample → creates labeled dataset

   # Model: Random Forest classifier
   # Purpose: Auto-flag GPS needing manual review
   # Expected accuracy: 85-90%
   ```

3. **CoB-to-e-GP Matching Model** (Future enhancement):

   ```python
   # Features: entity_name_similarity, amount_match, keyword_overlap, timing_overlap
   # Target: match_confidence (HIGH, MEDIUM, LOW)

   # Training data: Manual verification of 100 CoB-e-GP matches
   # Initial approach: Rule-based weighted scoring
   # Sprint 6: Train ML model to improve matching accuracy
   ```

**What We CANNOT Use e-GP For (Yet)**:

- ❌ Long-term temporal analysis (data too recent, most projects ongoing)
- ❌ Large-scale change detection training (insufficient completed projects)
- ❌ Ghost project ground truth (outcomes unknown - projects still active)

**e-GP Data Acquisition Plan**:

```python
# Sprint 3 Task: e-GP Integration

egp_integration_strategy = {
    "priority": "CRITICAL",
    "data_access": [
        "Option 1: OCDS JSON API (negotiate with National Treasury)",
        "Option 2: Web scraping (fallback if API denied)"
    ],
    "target_fields": [
        "tender.id", "tender.title", "tender.value.amount",
        "tender.deliveryLocation.geometry.coordinates",  # GPS!
        "awards[0].suppliers", "awards[0].contractPeriod"
    ],
    "sync_frequency": "Daily (new tenders + status updates)",
    "post_processing": [
        "GPS quality validation (Backend Task 3.2)",
        "Geospatial deep validation (Geo Task 3.5)",
        "Entity resolution (Backend Task 3.4)",
        "Satellite tasking (Geo Task 3.6)"
    ],
    "estimated_coverage": "70-85% usable GPS after validation"
}
```

---

### 1.3 CoB BIRR Reports (Quarterly Financial Data)

**Available Data**:

```
Report Type: Budget Implementation Review Reports (BIRR)
Frequency: Quarterly (4 reports per year)
Coverage: National + County governments
Format: PDF (requires OCR)
Historical Archive: 2013-present (13 years)
```

**Data Fields Available** (via PDF parsing):
| Field | Availability | Quality | ML Utility |
|-------|-------------|---------|-----------|
| Ministry/County | ✅ 100% | HIGH | Entity classification |
| Vote Head | ✅ 100% | HIGH | Budget category code |
| Vote Description | ✅ 90% | MEDIUM | Keyword extraction |
| Budget Allocated | ✅ 100% | HIGH | Baseline budget |
| Budget Released | ✅ 100% | HIGH | Cash flow to entity |
| Budget Absorbed | ✅ 100% | HIGH | **Actual spending** |
| Absorption Rate | ✅ 100% | HIGH | Efficiency metric |
| Pending Bills | ⚠️ 60% | MEDIUM | Contractor debt |
| **Tender Number** | ❌ 0% | N/A | Not in CoB reports |
| **GPS Coordinates** | ❌ 0% | N/A | Not in CoB reports |
| **Project Names** | ❌ 0% | N/A | Aggregated by Vote Head |

**What We CAN Use CoB For**:

1. **Financial Progress Ground Truth**:

   ```python
   # For Triangle of Truth training
   # Financial progress = (Budget Absorbed / Contract Value) × 100

   # Useful for: Calculate "progress gap" (financial vs physical)
   # This becomes the TARGET VARIABLE for ghost project detection
   ```

2. **Absorption Rate Anomaly Detection**:

   ```python
   # Historical absorption patterns by:
   # - Ministry/County
   # - Project type (Vote Head description)
   # - Fiscal quarter

   # Anomaly: 100% absorption in Q1 (suspicious - usually gradual)
   # Useful for: Early warning indicator before satellite analysis
   ```

3. **Budget vs Actual Spend Predictor**:

   ```python
   # Features: budget_allocated, entity, project_type, quarter
   # Target: budget_absorbed

   # Useful for: Baseline "expected financial progress"
   # Compare against actual CoB reports to flag over-spending
   ```

**What We CANNOT Use CoB For**:

- ❌ Direct project-level training (data aggregated by Vote Head, not individual projects)
- ❌ GPS training (no geolocation data)
- ❌ Contractor-level analysis (contractor names not in BIRR reports)

**CoB Data Acquisition Plan**:

```python
# Sprint 3.5 Task: CoB BIRR Parser

cob_integration_strategy = {
    "priority": "HIGH (enables Triangle of Truth)",
    "data_source": "cob.go.ke/reports/ (public PDFs)",
    "parsing_method": "pdfplumber + table extraction",
    "target_tables": [
        "Budget Allocation by Ministry/County",
        "Exchequer Releases by Vote Head",
        "Budget Absorption by Entity",
        "Pending Bills Summary"
    ],
    "historical_backfill": "Q1 2024 to present (8 quarters = 2 years)",
    "sync_frequency": "Quarterly (within 1 week of report publication)",
    "post_processing": [
        "Amount parser (handle 'KES 500M', '450,000,000')",
        "Vote Head keyword extraction",
        "CoB-to-e-GP matching (Backend Task 3.5.2)"
    ],
    "ml_use_case": "Financial progress for Triangle of Truth"
}
```

---

### 1.4 Satellite Imagery Availability

**Sentinel-2 (Optical)**:

```
Archive Depth: 2015-present (11 years)
Revisit Frequency: 5 days (Kenya covered by 4 tiles)
Resolution: 10m (RGB + NIR)
Cloud Cover: Average 40-60% (Kenya rainy seasons)
Data Access: Free (Copernicus Data Space)
Coverage: Global (including all Kenya)
```

**Sentinel-1 (SAR)**:

```
Archive Depth: 2014-present (12 years)
Revisit Frequency: 12 days
Resolution: 10m (radar backscatter)
Cloud Penetration: 100% (all-weather)
Data Access: Free (Copernicus Data Space)
Coverage: Global
```

**Training Data Potential**:

```python
# For projects with known GPS (e-GP + manually geolocated PPIP):
# Can fetch satellite time series retrospectively

example_project = {
    "tender_number": "KCG/2025/112",
    "gps": (-1.22, 36.72),
    "award_date": "2025-03-15",
    "expected_completion": "2026-09-15"
}

# Fetch Sentinel-2 time series
satellite_timeline = [
    fetch_sentinel2(gps, date)
    for date in monthly_dates(
        start="2025-02-15",  # Baseline (1 month before award)
        end=date.today()      # Current state
    )
]

# Available observations: 12 months × 6 images per month = 72 images
# After cloud filtering (40% cloud-free): ~43 usable images
# Sufficient for time-series analysis
```

**Constraint**:

```
PROBLEM: Historical PPIP projects (2018-2025) lack GPS coordinates
SOLUTION: Manual geolocation annotation (see Section 2.1)

Annotation workload:
- To get 500 training projects: Annotate 500 PPIP tender locations
- Geospatial engineer effort: 10-15 minutes per project (land use check, facility match)
- Total effort: 500 × 12 min = 100 hours = 2.5 weeks for 1 person
- OR: Crowdsourced annotation via Kenyan university students (4-week timeline)
```

---

### 1.5 Ground Truth Labels (Ghost vs Completed Projects)

**Existing Sources** (Limited):

1. **Auditor General Reports** (Annual):

   ```
   Source: oagkenya.go.ke/reports
   Format: PDF (200-400 pages)
   Content: Flagged ghost projects, stalled projects, budget anomalies
   Coverage: ~50-100 projects per report (high-value, Minister-level)
   Limitation: Only covers flagged cases (biased toward known fraud)

   Extraction effort:
   - Manual reading of AG reports (2020-2025 = 6 reports)
   - Extract project names, counties, outcomes
   - Match to PPIP tender numbers (fuzzy matching required)
   - Estimated yield: 200-300 labeled projects with known outcomes
   ```

2. **Media Reports** (Investigative Journalism):

   ```
   Sources: Nation Media, Standard, KTN investigations
   Content: Exposed ghost projects with photos, GPS coordinates
   Examples: "Sh 20M Nairobi market still empty field after 3 years"

   Extraction effort:
   - Web scraping news archives (2020-2026)
   - NER for project names, locations, amounts
   - Manual verification (journalist claims may be unverified)
   - Estimated yield: 50-100 high-confidence ghost project labels
   ```

3. **Manual Field Verification** (Future - Sprint 6+):
   ```
   Method: Partner with county governments for site visits
   Sample size: 100 projects (10 per county for cost-efficiency)
   Purpose: Create gold-standard validation dataset
   Cost: KES 5,000 per site visit × 100 = KES 500,000 (~$3,500)
   Timeline: 3 months (logistics + travel time)
   ```

**Current Training Data Summary**:

```python
labeled_projects = {
    "completed_projects": 50,      # From AG "successful delivery" mentions
    "ghost_projects": 30,          # From AG + media investigations
    "stalled_projects": 20,        # From AG "delayed beyond timeline"
    "unknown_outcome": 256_034,    # PPIP projects without outcome labels

    "total_labeled": 100,
    "label_quality": "MEDIUM (relies on secondary sources, not field-verified)"
}

# INSUFFICIENT for robust ML training (need 500+ for 80% accuracy)
# SOLUTION: Active learning + semi-supervised approach (see Section 3.3)
```

---

## Part 2: Location Triangulation Algorithm Changes

### 2.1 OLD Approach (Pre-e-GP Discovery)

**Original Design** (from technology-stack.md):

```python
# Primary geolocation method: Fuzzy matching to KMHFL/NEMIS

def geolocate_project(tender_title: str, location_text: str) -> GPS:
    """
    ORIGINAL APPROACH (NOW OBSOLETE FOR e-GP PROJECTS)

    Steps:
    1. Extract facility name from title ("Construction of Ruiru Hospital")
    2. Extract county/ward from location_text ("Kiambu County")
    3. Query KMHFL for health facilities in Kiambu
    4. Fuzzy match "Ruiru Hospital" to facility names
    5. Return matched facility GPS

    Expected success rate: 25-40% (many projects unmatchable)
    """

    # Extract facility type and name
    facility_type = extract_facility_type(tender_title)  # "hospital"
    facility_name = extract_name(tender_title)            # "Ruiru Hospital"
    county = extract_county(location_text)                # "Kiambu"

    # Choose registry
    if facility_type == "hospital":
        registry = load_kmhfl_data()  # 15,000 health facilities
    elif facility_type == "school":
        registry = load_nemis_data()  # 30,000 schools
    else:
        return None  # No registry for markets, roads, etc.

    # Fuzzy match within county
    candidates = registry[registry['county'] == county]
    match, score = fuzzy_match(facility_name, candidates['facility_name'])

    if score > 75:  # 75% confidence threshold
        return (match['latitude'], match['longitude'])
    else:
        return None  # Unmatched
```

**Limitations** (Why this approach is NOW SECONDARY):

- ❌ Only works for health/education facilities (not markets, roads, water projects)
- ❌ Fails if facility not in registry (new constructions)
- ❌ Fails if naming doesn't match (e.g., "Ruiru Level 4" vs "Ruiru Sub-County Hospital")
- ❌ No validation (assumes matched facility is correct)
- ❌ 60-75% failure rate for PPIP projects

---

### 2.2 NEW Approach (Post-e-GP Discovery)

**Revised Strategy: GPS Quality Validation Instead of Geolocation**

```python
class LocationTriangulator:
    """
    NEW APPROACH: Multi-source GPS validation instead of geolocation

    Workflow:
    1. e-GP provides GPS (70-85% of projects have coordinates)
    2. Backend validates GPS quality (county boundaries, HQ proximity)
    3. Geospatial engineer deep-validates SUSPECT GPS
    4. Facility registries become VALIDATION tools (not primary source)
    5. Satellite imagery provides FINAL CONFIRMATION

    This is "triangulation" in the true sense:
    - Source 1: e-GP manual pin (70-85% coverage)
    - Source 2: Facility registry match (validation)
    - Source 3: Satellite visual inspection (confirmation)

    Consensus decision: GPS accepted if 2+ sources agree
    """

    def triangulate_location(self,
                            egp_gps: Optional[Tuple[float, float]],
                            tender_title: str,
                            county: str,
                            project_type: str) -> TriangulationResult:
        """
        Multi-source location validation

        Returns:
            TriangulationResult with:
            - final_gps: (lat, lon)
            - confidence: 0-100
            - sources_agreeing: list of concordant sources
            - recommendation: USE / MANUAL_REVIEW / REJECT
        """

        sources = []

        # SOURCE 1: e-GP GPS (if available)
        if egp_gps:
            egp_quality = self.validate_egp_gps(egp_gps, county, project_type)
            sources.append({
                "name": "EGP_MANUAL_PIN",
                "gps": egp_gps,
                "quality_score": egp_quality.score,
                "issues": egp_quality.issues
            })

        # SOURCE 2: Facility Registry Match
        facility_match = self.match_facility_registry(tender_title, county, project_type)
        if facility_match and facility_match.confidence > 0.7:
            sources.append({
                "name": "FACILITY_REGISTRY",
                "gps": (facility_match.latitude, facility_match.longitude),
                "quality_score": int(facility_match.confidence * 100),
                "registry": facility_match.source  # KMHFL/NEMIS/KIPPRA
            })

        # SOURCE 3: Satellite Visual Inspection (for SUSPECT GPS)
        if egp_gps and egp_quality.score < 60:
            satellite_validation = self.visual_inspection_sentinel2(egp_gps, project_type)
            sources.append({
                "name": "SATELLITE_VISUAL",
                "gps": egp_gps,  # Same GPS, but validated visually
                "quality_score": satellite_validation.confidence,
                "evidence": satellite_validation.land_use
            })

        # TRIANGULATION: Check concordance
        if len(sources) >= 2:
            # Calculate GPS proximity between sources
            distances = [
                haversine_distance(s1['gps'], s2['gps'])
                for s1, s2 in itertools.combinations(sources, 2)
            ]

            max_distance = max(distances) if distances else 0

            if max_distance < 0.5:  # All sources within 500m
                # STRONG CONSENSUS
                avg_gps = self._average_gps([s['gps'] for s in sources])
                avg_score = np.mean([s['quality_score'] for s in sources])

                return TriangulationResult(
                    final_gps=avg_gps,
                    confidence=min(avg_score + 15, 100),  # Bonus for consensus
                    sources_agreeing=len(sources),
                    recommendation="USE",
                    method="MULTI_SOURCE_CONSENSUS"
                )

            elif max_distance < 2.0:  # Sources within 2km
                # PARTIAL CONSENSUS (use highest quality source)
                best_source = max(sources, key=lambda s: s['quality_score'])

                return TriangulationResult(
                    final_gps=best_source['gps'],
                    confidence=best_source['quality_score'],
                    sources_agreeing=len(sources),
                    recommendation="MANUAL_REVIEW",
                    method=f"BEST_SOURCE_{best_source['name']}"
                )

            else:
                # CONFLICT (sources disagree by >2km)
                return TriangulationResult(
                    final_gps=None,
                    confidence=0,
                    sources_agreeing=0,
                    recommendation="REJECT",
                    method="SOURCE_CONFLICT",
                    conflict_distance_km=max_distance
                )

        elif len(sources) == 1:
            # SINGLE SOURCE (use if quality high enough)
            source = sources[0]

            if source['quality_score'] >= 70:
                return TriangulationResult(
                    final_gps=source['gps'],
                    confidence=source['quality_score'],
                    sources_agreeing=1,
                    recommendation="USE",
                    method=f"SINGLE_SOURCE_{source['name']}"
                )
            else:
                return TriangulationResult(
                    final_gps=source['gps'],
                    confidence=source['quality_score'],
                    sources_agreeing=1,
                    recommendation="MANUAL_REVIEW",
                    method=f"WEAK_SINGLE_SOURCE_{source['name']}"
                )

        else:
            # NO SOURCES AVAILABLE
            return TriangulationResult(
                final_gps=None,
                confidence=0,
                sources_agreeing=0,
                recommendation="REJECT",
                method="NO_GEOLOCATION_AVAILABLE"
            )
```

**Comparison: OLD vs NEW**:

| Aspect             | OLD Approach                           | NEW Approach                      | Improvement                   |
| ------------------ | -------------------------------------- | --------------------------------- | ----------------------------- |
| **Primary Method** | Fuzzy matching KMHFL/NEMIS             | e-GP GPS validation               | 3x coverage (25-40% → 70-85%) |
| **Success Rate**   | 25-40%                                 | 70-85%                            | +45% projects geolocated      |
| **Speed**          | 10-15 min per project (fuzzy matching) | 1-2 min per project (validation)  | 10x faster                    |
| **Accuracy**       | 60-70% (many false matches)            | 80-90% (with validation)          | +20% accuracy                 |
| **Coverage**       | Health + Education only                | All project types                 | Universal                     |
| **Human Review**   | 60% need manual intervention           | 15-20% need manual review         | 3x fewer reviews              |
| **ML Training**    | Hard (no GPS ground truth)             | Easy (GPS available for training) | Trainable models              |

---

### 2.3 PPIP Historical Geolocation Backfill Strategy

**Problem**: 256K PPIP projects lack GPS, but satellite archive goes back to 2015.

**Solution**: Progressive geolocation annotation (prioritized by ML value).

**Phase 1: High-Value Projects** (Target: 500 projects for ML training)

```python
# Selection criteria:
ppip_annotation_candidates = ppip_df[
    (ppip_df['tender_value_kes'] > 10_000_000) &  # High-value (>KES 10M)
    (ppip_df['category'] == 'WORKS') &             # Construction (not goods/services)
    (ppip_df['contract_awarded'] == True) &        # Has winner
    (ppip_df['location_text'].notna())             # Has location info
].sort_values('tender_value_kes', ascending=False).head(500)

# Geolocation methods (in order of effort):
annotation_pipeline = [
    {
        "method": "Facility Registry Auto-Match",
        "applicable_to": "Health + Education projects (~150 projects)",
        "success_rate": 60,
        "manual_effort": 0,  # Automated
        "yield": 90  # 150 × 60% = 90 projects
    },
    {
        "method": "Google Maps Search",
        "applicable_to": "Named facilities + markets (~250 projects)",
        "success_rate": 70,
        "manual_effort": 5,  # 5 min per project
        "yield": 175  # 250 × 70% = 175 projects
    },
    {
        "method": "Satellite Visual Inspection",
        "applicable_to": "Infrastructure projects (roads, water) (~100 projects)",
        "success_rate": 50,
        "manual_effort": 15,  # 15 min per project (scan timeline for construction)
        "yield": 50  # 100 × 50% = 50 projects
    },
    {
        "method": "Manual Investigation",
        "applicable_to": "Remaining ambiguous projects",
        "success_rate": 40,
        "manual_effort": 30,  # 30 min per project (contact county, check records)
        "yield": "As needed to reach 500 total"
    }
]

# Total yield: 90 + 175 + 50 = 315 projects (automated + low-effort)
# Remaining needed: 500 - 315 = 185 projects (manual investigation)
# Total effort: 150×5min + 100×15min + 185×30min = 12.5 + 25 + 92.5 = 130 hours
# Timeline: 3-4 weeks with 1 geospatial engineer
```

**Phase 2: Crowdsourced Annotation** (Target: 2,000 additional projects)

```python
crowdsourcing_strategy = {
    "platform": "Kenyan university partnership (GIS students)",
    "incentive": "Academic credit + KES 50 per validated annotation",
    "annotation_interface": "Custom web app with Sentinel-2 overlays",
    "quality_control": [
        "Each project annotated by 3 students independently",
        "GPS coordinates must agree within 100m",
        "10% random verification by ONEKA geospatial engineer"
    ],
    "cost": "2,000 projects × KES 50 × 3 annotators = KES 300,000 (~$2,100)",
    "timeline": "6-8 weeks (recruitment + annotation + QC)"
}
```

**Phase 3: Active Learning** (Ongoing)

```python
# After initial model training on 500 projects:
# Use model predictions to prioritize next annotations

active_learning_loop = """
1. Train model on 500 labeled projects
2. Run model on unlabeled PPIP projects
3. Select projects with HIGH UNCERTAINTY (prediction ~50% ghost probability)
4. Manually annotate + validate with satellite
5. Add to training set, retrain model
6. Repeat until performance plateaus
"""

# Expected improvement: 500 → 1,000 labeled projects = +5-10% accuracy
```

---

## Part 3: Satellite Change Detection Algorithm Updates

### 3.1 OLD Algorithm (Pre-e-GP Discovery)

**Original Design** (from technology-stack.md):

```python
class Sentinel2ChangeDetector:
    """
    ORIGINAL APPROACH: Generic change detection without known timeline

    Assumptions:
    - Unknown project start date (search entire archive)
    - Unknown project location confidence (may be wrong GPS)
    - Binary outcome: COMPLETED vs GHOST
    """

    def analyze_project(self, gps: Tuple[float, float],
                        title: str) -> AnalysisResult:
        """
        OLD ALGORITHM:
        1. Fetch entire Sentinel-2 archive (2015-present = 11 years)
        2. Calculate NDVI for all images
        3. Detect ANY vegetation clearing event
        4. Classify based on vegetation recovery:
           - If NDVI dropped and RECOVERED → ABANDONED
           - If NDVI dropped and STAYED LOW → CONSTRUCTION ONGOING
           - If NO NDVI drop → NO CONSTRUCTION
        """

        # Inefficient: Download 11 years of imagery
        all_images = fetch_sentinel2_archive(
            gps=gps,
            start_date='2015-01-01',
            end_date=date.today()
        )  # ~2,400 images × 100MB each = 240GB download!

        # Calculate NDVI time series
        ndvi_timeline = [calculate_ndvi(img) for img in all_images]

        # Detect clearing events
        baseline_ndvi = np.median(ndvi_timeline[:12])  # First year average
        max_drop = max(baseline_ndvi - ndvi_timeline)

        if max_drop > 0.2:  # Significant clearing
            clearing_index = np.argmin(ndvi_timeline)
            clearing_date = all_images[clearing_index].date

            # Check if vegetation recovered
            recent_ndvi = np.mean(ndvi_timeline[-6:])  # Last 6 months

            if recent_ndvi > baseline_ndvi - 0.05:
                return AnalysisResult(
                    status="ABANDONED",
                    clearing_date=clearing_date,
                    evidence="Vegetation regrowth indicates abandonment"
                )
            else:
                return AnalysisResult(
                    status="CONSTRUCTION_DETECTED",
                    clearing_date=clearing_date,
                    evidence="Clearing event detected, no recovery"
                )
        else:
            return AnalysisResult(
                status="NO_CONSTRUCTION",
                evidence="No vegetation clearing detected"
            )
```

**Problems with OLD Approach**:

1. ❌ **Massive Data Download**: Analyzing entire 11-year archive per project
2. ❌ **No Timeline Context**: Doesn't know when project SHOULD start (false positives from unrelated clearing)
3. ❌ **Binary Classification**: Can't estimate % progress (just GHOST vs COMPLETE)
4. ❌ **No Financial Comparison**: Doesn't use budget data (misses "paid but not built" scenarios)
5. ❌ **High False Positive Rate**: Natural vegetation changes (droughts, fires) flagged as construction

---

### 3.2 NEW Algorithm (Post-e-GP Discovery)

**Revised Strategy: Timeline-Aware Progress Tracking**

```python
class TriangleOfTruthChangeDetector:
    """
    NEW APPROACH: Timeline-aware progress tracking with financial comparison

    Advantages:
    - Known start date (contract award from e-GP)
    - Known GPS (e-GP deliveryLocation)
    - Known budget (contract value)
    - Known expected timeline (contract period)

    Goal: Not just "detect construction" but "estimate % physical progress"
          Then compare to "% financial progress" (from CoB)
    """

    def analyze_project_timeline(self,
                                 project_uuid: UUID,
                                 gps: Tuple[float, float],
                                 contract_start_date: date,
                                 expected_completion_date: date,
                                 contract_value_kes: Decimal) -> TimelineAnalysisResult:
        """
        NEW ALGORITHM:
        1. Fetch TARGETED satellite imagery (baseline + monthly monitoring)
        2. Calculate multi-layer indices (NDVI + SAR + NDBI)
        3. Estimate physical progress % using construction signatures
        4. Fetch financial progress from CoB matching
        5. Calculate PROGRESS GAP = financial_progress - physical_progress
        6. Classify risk based on gap threshold
        """

        # STEP 1: Smart image fetching (only relevant timeline)
        baseline_date = contract_start_date - timedelta(days=30)  # Pre-construction
        monitoring_dates = self._generate_monthly_dates(
            start=contract_start_date,
            end=min(date.today(), expected_completion_date)
        )

        # Fetch only needed images (vs entire archive)
        baseline_image = fetch_sentinel2(gps, baseline_date, cloud_cover_max=30)
        progress_images = [
            fetch_sentinel2(gps, date, cloud_cover_max=30)
            for date in monitoring_dates
        ]

        # STEP 2: Multi-layer feature extraction
        features = []
        for img in [baseline_image] + progress_images:
            features.append({
                "date": img.date,
                "ndvi": calculate_ndvi(img),           # Vegetation (clearing indicator)
                "ndbi": calculate_ndbi(img),           # Built-up index (structure indicator)
                "ndwi": calculate_ndwi(img),           # Water index (quality control)
                "sar_backscatter": fetch_sentinel1_backscatter(gps, img.date)  # All-weather
            })

        # STEP 3: Construction signature detection
        baseline = features[0]
        current = features[-1]

        # Clearing detected?
        ndvi_drop = baseline['ndvi'] - current['ndvi']
        clearing_area_m2 = self._calculate_clearing_area(
            baseline_ndvi=baseline['ndvi'],
            current_ndvi=current['ndvi'],
            threshold=0.15  # 15% NDVI drop = clearing
        )

        # Structure detected?
        ndbi_increase = current['ndbi'] - baseline['ndbi']
        sar_increase = current['sar_backscatter'] - baseline['sar_backscatter']

        structure_area_m2 = self._calculate_structure_area(
            ndbi_increase=ndbi_increase,
            sar_increase=sar_increase,
            thresholds={'ndbi': 0.1, 'sar': 3}  # dB
        )

        # STEP 4: Estimate physical progress %
        # Assume project area = 500m radius buffer around GPS
        project_area_m2 = np.pi * (500 ** 2)  # ~785,000 m²

        # Progress indicators (weighted ensemble)
        clearing_progress = (clearing_area_m2 / project_area_m2) * 100  # Phase 1: Site prep
        structure_progress = (structure_area_m2 / project_area_m2) * 100  # Phase 2: Construction

        # Weighted average (structure more important than clearing)
        physical_progress_pct = (clearing_progress * 0.3) + (structure_progress * 0.7)
        physical_progress_pct = min(physical_progress_pct, 100)  # Cap at 100%

        # STEP 5: Fetch financial progress from CoB
        cob_match = self._get_cob_match(project_uuid)

        if cob_match:
            financial_progress_pct = (
                cob_match.budget_absorbed_kes / contract_value_kes
            ) * 100
        else:
            financial_progress_pct = 0  # No payment record found

        # STEP 6: Calculate Triangle of Truth gap
        progress_gap = financial_progress_pct - physical_progress_pct

        # Risk classification
        if progress_gap > 60:
            verdict = "CONFIRMED_GHOST_PROJECT"
            risk_score = 95
            explanation = f"Paid {financial_progress_pct:.0f}% but only {physical_progress_pct:.0f}% built"
        elif progress_gap > 30:
            verdict = "SUSPECTED_STALLED_PROJECT"
            risk_score = 70
            explanation = f"{progress_gap:.0f}% gap between payment and progress"
        elif abs(progress_gap) < 15:
            verdict = "HEALTHY"
            risk_score = 10
            explanation = f"Payment ({financial_progress_pct:.0f}%) matches progress ({physical_progress_pct:.0f}%)"
        else:
            verdict = "UNDER_REVIEW"
            risk_score = 40
            explanation = f"Minor gap ({progress_gap:.0f}%), monitoring continues"

        # STEP 7: Generate time-series evidence
        timeline_evidence = []
        for i, feature in enumerate(features):
            months_since_award = (feature['date'] - contract_start_date).days / 30

            timeline_evidence.append({
                "date": feature['date'],
                "months_since_award": months_since_award,
                "ndvi": feature['ndvi'],
                "ndbi": feature['ndbi'],
                "sar_backscatter": feature['sar_backscatter'],
                "estimated_progress_pct": self._estimate_progress_at_date(features[:i+1])
            })

        return TimelineAnalysisResult(
            project_uuid=project_uuid,
            analysis_date=date.today(),

            # Physical metrics
            physical_progress_pct=physical_progress_pct,
            clearing_area_m2=clearing_area_m2,
            structure_area_m2=structure_area_m2,

            # Financial metrics
            financial_progress_pct=financial_progress_pct,
            budget_absorbed_kes=cob_match.budget_absorbed_kes if cob_match else 0,

            # Triangle of Truth
            progress_gap=progress_gap,
            verdict=verdict,
            risk_score=risk_score,
            explanation=explanation,

            # Evidence
            timeline_evidence=timeline_evidence,
            baseline_image_url=self._export_to_s3(baseline_image),
            current_image_url=self._export_to_s3(progress_images[-1]),

            # Confidence
            confidence=self._calculate_confidence(features)
        )
```

**Comparison: OLD vs NEW Algorithm**:

| Aspect                      | OLD Algorithm                    | NEW Algorithm                     | Improvement                 |
| --------------------------- | -------------------------------- | --------------------------------- | --------------------------- |
| **Data Volume**             | 11 years archive (240GB/project) | Targeted timeline (1-2GB/project) | 100-200x less data          |
| **Processing Time**         | 30-45 minutes per project        | 3-5 minutes per project           | 10x faster                  |
| **Timeline Context**        | No (scans all history)           | Yes (knows when to look)          | Reduces false positives 80% |
| **Progress Estimation**     | Binary (yes/no construction)     | Quantitative (0-100% progress)    | Enables gap analysis        |
| **Financial Integration**   | None                             | CoB budget absorption             | Triangle of Truth           |
| **ML Training Feasibility** | Hard (too much noise)            | Easy (clear features)             | Trainable models            |
| **Outcome Classification**  | 2 classes (GHOST/COMPLETE)       | 4 classes + risk score            | Nuanced verdicts            |

---

### 3.3 ML Model Training Strategy (Revised)

**NEW Target Variable**: Progress Gap (instead of binary GHOST/COMPLETE)

```python
# OLD approach:
# Target = binary classification (0 = GHOST, 1 = COMPLETED)

# NEW approach:
# Target = continuous regression (progress_gap = financial_pct - physical_pct)
# Then threshold for classification:
#   progress_gap > 60 → CONFIRMED_GHOST
#   progress_gap 30-60 → SUSPECTED_STALLED
#   progress_gap -15 to 30 → UNDER_REVIEW
#   progress_gap < -15 → OVER-DELIVERING (rare, worth investigating)

training_pipeline = {
    "step_1": "Annotate 500 historical PPIP projects with GPS",
    "step_2": "Run satellite change detection on 500 projects",
    "step_3": "Manually label ground truth outcomes (site visits or reports)",
    "step_4": "Extract features from satellite time series",
    "step_5": "Train Random Forest regression model",
    "step_6": "Validate with cross-validation (5-fold)",
    "step_7": "Fine-tune with active learning on e-GP projects"
}

# Feature engineering (revised)
features_v2 = {
    "temporal": [
        "months_active",                # Time since contract award
        "months_to_clearing",           # Time lag before first construction signal
        "clearing_rate",                # NDVI drop per month (speed indicator)
    ],
    "spectral": [
        "ndvi_drop",                    # Vegetation cleared
        "ndbi_increase",                # Built-up index gain
        "sar_increase",                 # Backscatter increase (structure)
        "ndwi_change",                  # Water index (quality control)
    ],
    "spatial": [
        "clearing_area_m2",             # Total cleared area
        "structure_area_m2",            # Total built-up area
        "gps_quality_score",            # Location confidence
    ],
    "financial": [
        "contract_value_log",           # Log-transformed budget
        "budget_absorption_rate",       # % of budget spent
        "absorption_timeline_months",   # When payments started
    ],
    "contextual": [
        "project_type",                 # One-hot encoded
        "county",                       # Geographic region
        "procuring_entity_type",        # Ministry vs County
        "contractor_history_score",     # Past performance (if available)
    ]
}

# Total features: 3 + 4 + 3 + 3 + 4 = 17 features

# Model selection (updated)
model_architecture = {
    "algorithm": "Gradient Boosting Regressor (XGBoost)",
    "reason": [
        "Better than Random Forest for continuous targets",
        "Handles mixed feature types (numeric + categorical)",
        "Built-in feature importance ranking",
        "Robust to overfitting with regularization"
    ],
    "hyperparameters": {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,          # L2 regularization
        "reg_alpha": 0.5            # L1 regularization
    },
    "training_data": "500 annotated PPIP + 100 e-GP projects with outcomes",
    "validation": "5-fold cross-validation",
    "test_set": "20% holdout (120 projects)",
    "expected_performance": {
        "MAE": 15,  # Mean Absolute Error: ±15% progress gap prediction
        "R²": 0.65, # Explains 65% of variance
        "Classification accuracy": 80  # When thresholded into risk categories
    }
}
```

**Active Learning for e-GP Projects**:

```python
# e-GP projects are ongoing (outcomes unknown)
# Use active learning to incrementally label as projects complete

active_learning_strategy = """
Month 1 (Sprint 4):
- Train initial model on 500 PPIP projects (historical outcomes)
- Deploy model to predict e-GP projects
- 95% confidence interval: No action
- Uncertain predictions (40-60% gap probability): Flag for manual review

Month 2-3:
- 10-20 e-GP projects complete → Satellite + field verification → Add to training set
- Retrain model with updated data (500 PPIP + 20 e-GP = 520 projects)
- Improved accuracy for ongoing project types (e-GP has different distribution than PPIP)

Month 4-6:
- 50+ e-GP projects complete → Richer training data
- Model performance on e-GP projects: MAE reduces from 15% → 10%
- Can now predict early (at 6 months) with 75% accuracy (vs 80% at completion)

Year 2:
- 200+ e-GP projects complete → Robust model
- MAE < 8%, Classification accuracy > 85%
- Early warning system operational (predict ghost risk at 3 months)
"""
```

---

## Part 4: Implementation Roadmap

### 4.1 Sprint 2 (CURRENT - Data Collection)

**Status**: 90% complete

**Backend Tasks**:

- ✅ PPIP scraper implemented
- ⏳ Test with 20+ real tenders (validates parser)
- ⏳ Execute ONE-TIME historical import (256K tenders → 48 hours scraping)

**Geospatial Tasks**:

- N/A (waiting for Sprint 3 GPS data)

**Training Data Yield**:

- 256K unlabeled PPIP tenders (stored in PostgreSQL)
- 100 labeled projects (from AG reports - manual extraction needed)
- 0 GPS coordinates (requires Phase 1 annotation - see Section 2.3)

---

### 4.2 Sprint 3 (NEXT - Geolocation Foundation)

**Backend Tasks**:

1. **e-GP Integration** (5 days):
   - Negotiate OCDS API access OR build web scraper
   - Extract 4,591 tenders with GPS coordinates
   - Database migration: Add `delivery_latitude`, `delivery_longitude` fields
   - **Training Data Yield**: 4,000 projects with GPS (87% of e-GP)

2. **GPS Quality Validation** (2 days):
   - Implement county HQ proximity detector
   - Kenya boundary shapefile integration
   - Flag GPS as ACCEPTABLE / SUSPECT / INVALID
   - **Training Data for GPS Quality Model**: Manual validation of 200 e-GP GPS → labeled dataset

3. **Facility Matching** (downgraded to 3 days):
   - KMHFL/NEMIS data loaders
   - Fuzzy matching service (RapidFuzz)
   - **Training Data Yield**: Facility matches for 40-60% of PPIP projects (as GPS validation fallback)

**Geospatial Tasks**:

1. **GPS Deep Validation** (4 days):
   - Land use layer integration (OpenStreetMap)
   - Road proximity analysis
   - Visual inspection workflow (Sentinel-2 RGB review)
   - **Training Data Yield**: 200 GPS quality labels (VERIFIED/REJECT)

2. **Satellite Tasking Queue** (3 days):
   - Celery task queue setup
   - Priority scoring (high-value projects first)
   - **Prepares for Sprint 4 change detection**

**Training Data Status at Sprint 3 End**:

- ✅ 4,000 e-GP projects with GPS
- ✅ 200 GPS quality labels (for GPS validation model)
- ⏳ 0 PPIP projects geolocated (Phase 1 annotation starts Sprint 4)
- ⏳ 100 labeled outcomes (ghost vs complete - manual curation)

---

### 4.3 Sprint 4 (Satellite Analysis + ML Training Begins)

**Backend Tasks**:

1. **Satellite Results API** (2 days):
   - Store satellite analysis results
   - Expose via REST API for frontend

**Geospatial Tasks**:

1. **Sentinel-2 Change Detection** (7 days):
   - Implement timeline-aware algorithm (Section 3.2)
   - NDVI/NDBI/NDWI calculation
   - Progress estimation logic
   - **Run on e-GP projects** (4,000 projects with GPS)

2. **Sentinel-1 SAR Backup** (5 days):
   - PyroSAR + SNAP integration
   - Backscatter change detection
   - Fallback for cloudy imagery

**ML Tasks** (NEW):

1. **PPIP Geolocation Annotation - Phase 1** (10 days):
   - Geospatial engineer annotates 500 high-value PPIP projects
   - Methods: Facility registry auto-match + Google Maps + satellite visual
   - **Training Data Yield**: 500 PPIP projects with GPS

2. **Satellite Feature Extraction** (3 days):
   - Run change detection on 500 annotated PPIP projects
   - Extract 17 features per project (Section 3.3)
   - **Creates training dataset for ML model**

3. **Ground Truth Curation** (5 days):
   - Extract ghost project labels from AG reports (2020-2025)
   - Match to PPIP tender numbers (fuzzy matching)
   - Manual verification with media reports
   - **Training Data Yield**: 100-150 labeled outcomes

**Training Data Status at Sprint 4 End**:

- ✅ 500 PPIP projects with GPS + satellite features
- ✅ 4,000 e-GP projects with GPS + satellite analysis
- ✅ 150 labeled outcomes (50 completed + 30 ghost + 20 stalled + 50 unknown)
- ⚠️ **INSUFFICIENT for robust model** (need 500+ labeled outcomes)

---

### 4.4 Sprint 5 (Triangle of Truth + ML Model Training)

**Backend Tasks**:

1. **CoB Parser** (4 days):
   - PDF table extraction (pdfplumber)
   - Amount parser (handle "KES 500M" format)
   - Quarterly report auto-fetcher

2. **CoB-to-e-GP Matcher** (5 days):
   - Multi-factor matching algorithm (Section 3.3 Task 3.5.2)
   - Confidence scoring (HIGH/MEDIUM/LOW)
   - **Training Data Yield**: Financial progress for matched projects

3. **Triangle Snapshot Generator** (3 days):
   - Combine CoB + e-GP + Satellite
   - Calculate progress gap
   - Classify risk (GHOST/STALLED/HEALTHY)
   - **Creates Triangle of Truth training labels**

**ML Tasks**:

1. **Model Training v1.0** (7 days):

   ```python
   training_config = {
       "algorithm": "XGBoost Regressor",
       "training_data": "150 labeled projects (PPIP + e-GP with known outcomes)",
       "features": 17,  # See Section 3.3
       "target": "progress_gap (financial_pct - physical_pct)",
       "validation": "5-fold cross-validation",
       "expected_performance": {
           "MAE": 20,  # ±20% gap prediction (limited by small dataset)
           "R²": 0.50,
           "Classification accuracy": 70  # Lower than target due to small dataset
       }
   }
   ```

2. **Model Deployment** (2 days):
   - Save model to S3 (joblib serialization)
   - FastAPI prediction endpoint
   - Batch inference pipeline (Celery)

**Training Data Status at Sprint 5 End**:

- ⚠️ **Model v1.0 trained but UNDERPOWERED** (only 150 labeled projects)
- ✅ Triangle of Truth framework operational
- ✅ Can predict progress gap for e-GP projects (with low confidence)
- 🔄 **Active learning begins** (as e-GP projects complete, add to training set)

---

### 4.5 Sprint 6+ (Model Improvement + Scale)

**ML Improvement Tasks**:

1. **PPIP Annotation - Phase 2** (Crowdsourced):
   - Partner with Kenyan universities (GIS students)
   - Annotate 2,000 additional PPIP projects
   - Cost: KES 300,000 (~$2,100)
   - Timeline: 6-8 weeks
   - **Training Data Yield**: +2,000 GPS-tagged projects

2. **Field Verification Campaign**:
   - Sample 100 projects for physical site visits
   - Create gold-standard validation dataset
   - Cost: KES 500,000 (~$3,500)
   - Timeline: 3 months
   - **Training Data Yield**: +100 verified outcomes (high confidence)

3. **Active Learning on e-GP**:
   - As projects complete (10-20 per month), add to training set
   - Retrain model monthly
   - Expected improvement: +2-3% accuracy per quarter

4. **Model v2.0 Training** (Month 6):

   ```python
   training_config_v2 = {
       "training_data": "500+ labeled projects",
       "expected_performance": {
           "MAE": 12,  # ±12% gap prediction
           "R²": 0.70,
           "Classification accuracy": 82
       }
   }
   ```

5. **Model v3.0 Training** (Month 12):
   ```python
   training_config_v3 = {
       "training_data": "1,000+ labeled projects",
       "new_features": [
           "Early warning indicators (predict at 3 months)",
           "Contractor behavior patterns",
           "Seasonal construction patterns"
       ],
       "expected_performance": {
           "MAE": 8,
           "R²": 0.80,
           "Classification accuracy": 88,
           "Early prediction accuracy": 75  # At 6 months instead of completion
       }
   }
   ```

---

## Part 5: Critical Success Factors

### 5.1 Training Data Quality > Quantity

**Lesson from Research**:

```
256,034 PPIP tenders WITHOUT GPS = LESS VALUABLE
than
500 PPIP tenders WITH GPS + satellite features + outcome labels = MORE VALUABLE

Key insight: We need LABELED, GEOLOCATED, TEMPORALLY-TRACKED projects
Not just raw tender records
```

**Priority Order**:

1. **GPS Quality** (accuracy matters more than coverage)
2. **Outcome Labels** (ghost vs complete ground truth)
3. **Satellite Features** (multi-temporal analysis, not just snapshots)
4. **Financial Data** (CoB matching enables Triangle of Truth)

### 5.2 Geolocation Validation is The Bottleneck

**Resource Allocation**:

```
Sprint 3-4: Geospatial engineer spends 70% time on GPS validation, 30% on satellite analysis

Why: Bad GPS → Bad satellite tasking → Wasted compute → No training data

Example:
- Wrong GPS (lazy pin at County HQ) → Satellite shows no construction
- Flag as "GHOST PROJECT" → FALSE POSITIVE
- Add to training set → MODEL LEARNS WRONG PATTERN

Solution: Rigorous GPS validation BEFORE satellite tasking
```

### 5.3 Active Learning is Essential (Small Dataset Problem)

**Reality Check**:

```
To train 85% accuracy model: Need 1,000+ labeled projects
Currently available: 100-150 labeled projects
Gap: 850 projects

Traditional approach: Wait 2 years to manually label 850 projects
Active learning approach: Start with 150, improve iteratively

Timeline:
- Month 1: 70% accuracy with 150 labels
- Month 3: 75% accuracy with 250 labels (100 e-GP projects completed)
- Month 6: 80% accuracy with 400 labels
- Month 12: 85% accuracy with 700 labels

Key: Deploy imperfect model early, learn from production data
```

### 5.4 Triangle of Truth Changes Everything

**OLD Success Metric**: Can we detect construction via satellite? (Yes/No)  
**NEW Success Metric**: Can we predict financial vs physical gap? (MAE < 10%)

**Why This Matters**:

```
Project A:
- Physical progress: 60% (satellite shows structure)
- Financial progress: 95% (CoB shows payment)
- Gap: 35% → SUSPECTED STALLED

Without Triangle: "Construction detected, project looks fine"
With Triangle: "Paid 95% but only 60% built → investigate"

This is ONEKA's unique value: Financial + Physical comparison
```

---

## Conclusion: Implementation Recommendations

### Immediate Actions (Sprint 3)

1. **Email National Treasury** requesting e-GP OCDS API access
   - Use case: OAG partnership, Article 254 transparency mandate
   - Expected response time: 2-4 weeks
   - Fallback: Web scraper (2 weeks development)

2. **Start PPIP Annotation - Phase 1**
   - Target: 500 high-value projects (>KES 10M)
   - Method: Facility registry + Google Maps + satellite visual
   - Effort: 130 hours = 3-4 weeks with 1 geospatial engineer

3. **Curate Ground Truth Labels**
   - Extract ghost projects from AG reports (2020-2025)
   - Match to PPIP tender numbers
   - Target: 100-150 labeled outcomes
   - Effort: 5 days (1 backend engineer)

### Medium-Term Actions (Sprint 4-5)

4. **Implement Triangle of Truth Pipeline**
   - CoB parser → CoB-e-GP matcher → Progress gap calculator
   - Creates training labels for ML model
   - Enables unique value proposition

5. **Train Model v1.0** (Even with Limited Data)
   - 150 labeled projects → 70% accuracy
   - Deploy to production for early feedback
   - Use active learning to improve monthly

### Long-Term Actions (Sprint 6+)

6. **Scale Annotation via Crowdsourcing**
   - Partner with Kenyan universities
   - Annotate 2,000 PPIP projects
   - Cost: $2,100, Timeline: 6-8 weeks

7. **Field Verification Campaign**
   - 100 site visits for gold-standard validation
   - Cost: $3,500, Timeline: 3 months
   - Creates high-confidence test set

### Success Metrics by Sprint

| Sprint         | Training Data Goal            | Model Performance      | Business Value                  |
| -------------- | ----------------------------- | ---------------------- | ------------------------------- |
| **Sprint 3**   | 4,000 e-GP projects with GPS  | No model yet           | GPS validation operational      |
| **Sprint 4**   | +500 PPIP projects geolocated | No model yet           | Satellite analysis running      |
| **Sprint 5**   | +150 outcome labels           | 70% accuracy (MAE 20%) | Triangle of Truth MVP           |
| **Sprint 6**   | +200 e-GP outcomes            | 75% accuracy (MAE 15%) | Early warning system (6 months) |
| **Sprint 7-8** | +300 labels (crowdsourcing)   | 80% accuracy (MAE 12%) | Production-ready model          |
| **Month 12**   | +500 labels (field verify)    | 85% accuracy (MAE 8%)  | OAG deployment                  |

---

**Document Version**: 1.0  
**Date**: February 19, 2026  
**Next Review**: After Sprint 3 e-GP integration  
**Owner**: ONEKA Technical Team  
**Status**: Approved for implementation
