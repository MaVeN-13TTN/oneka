# ONEKA System Integration Reality Check (2026)

## Reconciling the "Ground Truth" of Kenya's Digital Infrastructure with ONEKA's Implementation Plan

**Date**: February 19, 2026  
**Status**: Critical Technical Review  
**Purpose**: Align ONEKA architecture with the actual state of government systems post-July 2025 e-GP mandate

---

## Executive Summary

Based on the "Ground Truth" of Kenya's digital infrastructure following the **mandatory e-GP rollout in July 2025**, this document reconciles ONEKA's current architecture against the real-world status of three critical government systems:

1. **PPIP** (tenders.go.ke) - Legacy system
2. **e-GP** (egpkenya.go.ke) - The new mandatory standard
3. **CoB** (cob.go.ke) - Financial oversight system

**Critical Finding**: Our existing documentation correctly identifies the systems but **underestimates the severity of the integration gap** between e-GP (procurement) and CoB (finance). The user's "Ground Truth" reveals that:

- ✅ **We got RIGHT**: The three-system architecture (procurement, finance, physical)
- ⚠️ **We got INCOMPLETE**: The severity of the e-GP/CoB disconnect
- ❌ **We MISSED**: The mandatory geolocation field in e-GP (this is a GAME CHANGER)
- ❌ **We MISSED**: PPIP's complete lack of geolocation data (it's not just incomplete, it's ABSENT by design)

---

## Part 1: The Three Systems - Reality Check

### 1.1 PPIP (tenders.go.ke) - The Legacy Archive

#### **What We Thought** (from interoperability-architecture.md):

```
PPIP (tenders.go.ke) - Tender publication
- Accessibility: ✅ Public HTML (no API)
- Data Quality: Medium (OCR needed for PDFs)
- Identifier: Tender Number
```

#### **The Ground Truth** (February 2026):

```
PPIP Status: ACTIVE BUT DEPRECATED (Read-Only Archive)
Reality Check:
- ✅ Still online as "transparency notice board" per PPRA
- ❌ NEW PROJECTS: No longer posted here (e-GP mandatory since July 2025)
- ❌ GEOLOCATION: Does NOT and WILL NOT have Lat/Long data
  └─ Built on old schema requiring only text fields ("Location: Nairobi")
- ✅ HISTORICAL VALUE: 2018-2025 data for ML training
  └─ Use for "completed" vs "stalled" pattern recognition
- ❌ LIVE AUDITING: DO NOT use for current projects (data incomplete)
```

#### **Impact on ONEKA**:

| Original Plan                   | Reality-Based Adjustment                                      |
| ------------------------------- | ------------------------------------------------------------- |
| Scrape PPIP for current tenders | ❌ **STOP** - Only scrape for historical data (pre-July 2025) |
| Attempt geolocation from PPIP   | ❌ **IMPOSSIBLE** - No GPS data in schema                     |
| Use PPIP as primary data source | ❌ **DOWNGRADE** - Training data only                         |
| Weekly PPIP ingestion           | ✅ **ONE-TIME** - Historical batch import, then STOP          |

**CODE CHANGE REQUIRED**:

```python
# OLD (from our current pipeline)
def ingest_ppip_tenders():
    """Weekly ingestion of new tenders from PPIP"""  # ❌ WRONG ASSUMPTION

# NEW (reality-aligned)
def ingest_ppip_historical():
    """ONE-TIME ingestion of PPIP archive (2018-2025) for ML training"""
    cutoff_date = datetime(2025, 7, 1)  # e-GP mandatory date
    # Only scrape tenders BEFORE July 2025
    # Tag all records with: source='PPIP_ARCHIVE', geolocation_viable=False
```

---

### 1.2 e-GP (egpkenya.go.ke) - The New Mandatory Standard

#### **What We Thought**:

```
eGP Kenya - E-procurement portal
- Accessibility: ⚠️ Requires vendor login
- Data Quality: High (structured database)
- Geolocation: Not mentioned as mandatory
```

#### **The Ground Truth** (Post-July 2025 Ruling):

```
e-GP Status: MANDATORY & OPERATIONAL (The "Source of Truth")
Legal Mandate: ALL Procuring Entities MUST use this system
Manual tendering: NOW ILLEGAL

GAME CHANGER: MANDATORY GEOLOCATION FIELD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ System enforces "Geotag" at Requisition Stage
✅ Procurement officer CANNOT publish tender without dropping a map pin
✅ Stores specific deliveryLocation object with latitude/longitude
⚠️ QUALITY ISSUE: Lazy officers drop pins on County HQs (validation needed)
```

#### **The Data Structure** (e-GP delivers):

```json
{
  "tenderId": "KCG/2026/045",
  "tenderTitle": "Construction of Ruiru Market",
  "procuringEntity": "Kiambu County Government",
  "contractValue": 15000000,
  "deliveryLocation": {
    "latitude": -1.14,
    "longitude": 36.96,
    "accuracy": "manual_pin", // NOT GPS-verified
    "placeName": "Ruiru Town"
  }
}
```

#### **Impact on ONEKA**:

| Original Plan                           | Reality-Based Adjustment                          |
| --------------------------------------- | ------------------------------------------------- |
| Geolocation via fuzzy matching KMHFL    | ✅ **KEEP** but as validation layer               |
| Primary GPS source: External registries | ❌ **CHANGE** - e-GP is PRIMARY source            |
| Geolocation confidence: 25-40%          | ✅ **UPGRADE** - Now 70-85% (but need validation) |
| Manual review for unmatched projects    | ✅ **REDUCE** - Only for quality checks           |

**CRITICAL NEW REQUIREMENT**: Geolocation Validation Pipeline

```python
def validate_egp_geolocation(tender_data):
    """
    Validate e-GP GPS coordinates against known issues

    Common Errors:
    1. County HQ pin drop (all projects at -1.2833, 36.8167 = Nairobi)
    2. Ministry office location (Nairobi CBD coordinates)
    3. Obviously wrong coordinates (ocean, neighboring country)
    """
    lat, lon = tender_data['deliveryLocation']['latitude'], tender_data['deliveryLocation']['longitude']

    # Check 1: Is this a County HQ? (compare against 47 county coordinates)
    if is_county_headquarters(lat, lon):
        return {
            'status': 'SUSPECT',
            'confidence': 40,
            'issue': 'LAZY_PIN_DROP',
            'recommendation': 'Cross-reference with facility registries'
        }

    # Check 2: Is this within project county boundaries?
    if not point_in_county(lat, lon, tender_data['county']):
        return {
            'status': 'INVALID',
            'confidence': 0,
            'issue': 'WRONG_COUNTY',
            'recommendation': 'Flag for manual review'
        }

    # Check 3: Does it match KMHFL/NEMIS facility?
    facility_match = fuzzy_match_facility(tender_data['tenderTitle'], lat, lon)
    if facility_match and facility_match['distance_km'] < 0.5:
        return {
            'status': 'VERIFIED',
            'confidence': 95,
            'matched_facility': facility_match['name']
        }

    return {
        'status': 'ACCEPTABLE',
        'confidence': 70,
        'note': 'e-GP pin accepted but unverified'
    }
```

---

### 1.3 CoB (cob.go.ke) - The Financial Gap

#### **What We Thought**:

```
Controller of Budget - Budget execution oversight
- Source: BIRR quarterly reports (PDFs)
- Challenge: Not project-specific, aggregated by ministry
- Solution: Inference matching
```

#### **The Ground Truth** (February 2026):

```
CoB Status: LAGGING / NON-INTEGRATED
The Critical Disconnect:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT e-GP KNOWS:
  Tender No. KCG/2026/045
  Project: Construction of Ruiru Market
  Location: Lat -1.14, Lon 36.96
  Contractor: ABC Construction Ltd
  Contract Value: KES 15M

WHAT CoB REPORT SHOWS:
  Vote Head 3042 - Construction of Markets
  Amount Paid: KES 15M
  Contractor: [NOT LISTED]
  Project ID: [NOT LISTED]
  Location: [NOT LISTED]

THE GAP: Money (CoB) does NOT automatically talk to Map (e-GP)
```

#### **Why This Matters**:

The CoB reports are **still generated from budget codes, not procurement codes**. This means:

1. ❌ **No Direct Link**: Cannot automatically match "KES 15M paid" to "Ruiru Market project"
2. ⚠️ **Inference Required**: Must use contractor name matching + amount matching
3. 🔴 **Ghost Project Risk**: A contractor can claim payment for "Ruiru Market" while funds actually went to a different Vote Head

#### **Impact on ONEKA**:

Our current inference matching approach was **CORRECT** but we need to make it more sophisticated:

```python
# ENHANCED: Multi-factor matching
def match_cob_to_egp(cob_record, egp_database):
    """
    Match CoB payment to e-GP tender using multiple signals

    Matching Signals (weighted):
    1. Contractor Name (40%) - fuzzy match
    2. Amount (30%) - within 10% tolerance
    3. Ministry/County (20%) - exact match
    4. Timing (10%) - payment within contract period
    """

    candidates = []

    for tender in egp_database:
        score = 0

        # Signal 1: Contractor match
        contractor_match = fuzz.token_set_ratio(
            cob_record['contractor_name'],
            tender['contractor_name']
        )
        score += (contractor_match / 100) * 40

        # Signal 2: Amount match (within 10%)
        amount_diff = abs(cob_record['amount'] - tender['contract_value'])
        amount_tolerance = tender['contract_value'] * 0.10
        if amount_diff <= amount_tolerance:
            score += 30

        # Signal 3: Entity match
        if cob_record['ministry'] in tender['procuring_entity']:
            score += 20

        # Signal 4: Timing
        if is_within_contract_period(cob_record['payment_date'], tender):
            score += 10

        candidates.append({
            'tender': tender,
            'match_score': score,
            'confidence': 'HIGH' if score > 80 else 'MEDIUM' if score > 50 else 'LOW'
        })

    return sorted(candidates, key=lambda x: x['match_score'], reverse=True)[0]
```

---

## Part 2: The "Triangle of Truth" Workflow

### 2.1 The Reverse Pipeline (CoB → e-GP → Satellite)

The user's "Ground Truth" reveals ONEKA's **actual operational workflow**:

```
TRADITIONAL AUDIT (FAILED):
CoB Report → "Money Paid" → Assume Project Exists → Loss Discovered 2 Years Later

ONEKA WORKFLOW (THE FIX):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1: THE TRIGGER (CoB Report)
  Input: "Paid 20M to M/s Juma Construction for Wangige Market"
  Data: Contractor Name + Vague Location
  Missing: GPS Coordinates

STEP 2: THE HUNT (e-GP Database Search)
  Query: contractor=="M/s Juma Construction" AND project_keyword=="Wangige Market"
  Hit: Tender KCG/2025/112
  Extract: GPS (-1.22, 36.72) + Full Project Details

STEP 3: THE AUDIT (Satellite Analysis)
  Input: Coordinates (-1.22, 36.72)
  Analysis: Sentinel-2/1 change detection
  Output: Physical Progress Score

STEP 4: THE VERDICT (Triangle Comparison)
  CoB Status: 🔴 PAID (100%)
  e-GP Status: 🟢 AWARDED
  Satellite Status: ⚫ NON-EXISTENT

  ONEKA VERDICT: 🚨 FRAUD DETECTED
```

### 2.2 Implementation in Our Current Architecture

**WHAT WE HAVE** (from interoperability-architecture.md):

```python
# Pipeline 2: Financial Data Ingestion
def ingest_cob_quarterly_report(pdf_url):
    # Extract tables
    # Store aggregated data
    # Inference match to projects
```

**WHAT WE NEED** (aligned with Ground Truth):

```python
# ENHANCED: CoB-Triggered Audit Pipeline
def cob_triggered_audit_pipeline(cob_record):
    """
    Reverse pipeline: Start from CoB payment, find e-GP tender, task satellite

    Input: CoB Record
      {
        'ministry': 'Ministry of Health',
        'contractor': 'M/s Juma Construction',
        'project_desc': 'Wangige Market',
        'amount_paid': 20000000,
        'payment_date': '2026-01-15'
      }

    Output: Audit Result
      {
        'tender_id': 'KCG/2025/112',
        'gps_coordinates': (-1.22, 36.72),
        'satellite_verified': False,
        'risk_score': 95,
        'verdict': 'POTENTIAL_GHOST_PROJECT'
      }
    """

    # STEP 1: Search e-GP database
    egp_matches = search_egp_database(
        contractor=cob_record['contractor'],
        project_keywords=extract_keywords(cob_record['project_desc']),
        amount_range=(cob_record['amount_paid'] * 0.9, cob_record['amount_paid'] * 1.1)
    )

    if not egp_matches:
        return {
            'status': 'UNMATCHED',
            'risk_score': 85,
            'issue': 'CoB payment has no corresponding e-GP tender',
            'recommendation': 'Priority investigation - possible off-system procurement'
        }

    best_match = egp_matches[0]  # Highest confidence

    # STEP 2: Extract GPS from e-GP
    gps = best_match['deliveryLocation']

    # STEP 3: Validate GPS (is it a lazy pin?)
    validation = validate_egp_geolocation(best_match)

    if validation['confidence'] < 50:
        # Attempt secondary geolocation
        gps = fuzzy_match_kmhfl(best_match['tenderTitle'])

    # STEP 4: Task satellite analysis
    satellite_result = trigger_satellite_analysis(
        project_uuid=best_match['project_uuid'],
        latitude=gps['latitude'],
        longitude=gps['longitude']
    )

    # STEP 5: Calculate Triangle of Truth
    financial_progress = (cob_record['amount_paid'] / best_match['contractValue']) * 100
    physical_progress = satellite_result['physical_progress_pct']

    progress_gap = financial_progress - physical_progress

    # STEP 6: Generate Verdict
    if progress_gap > 60:
        verdict = 'CONFIRMED_GHOST_PROJECT'
        risk_score = 95
    elif progress_gap > 30:
        verdict = 'SUSPECTED_STALLED_PROJECT'
        risk_score = 70
    else:
        verdict = 'HEALTHY'
        risk_score = 10

    return {
        'tender_id': best_match['tenderId'],
        'gps_coordinates': (gps['latitude'], gps['longitude']),
        'financial_progress': financial_progress,
        'physical_progress': physical_progress,
        'progress_gap': progress_gap,
        'verdict': verdict,
        'risk_score': risk_score,
        'evidence': {
            'cob_payment': cob_record,
            'egp_tender': best_match,
            'satellite_analysis': satellite_result
        }
    }
```

---

## Part 3: The ONEKA Dashboard Visualization

### 3.1 What the User Described

```
ONEKA Dashboard (for Auditor General):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Financial Status (from CoB):    🔴 PAID (100%)
Procurement Status (from e-GP):  🟢 AWARDED
Physical Status (from Satellite): ⚫ NON-EXISTENT

ONEKA VERDICT: 🚨 FRAUD DETECTED
```

### 3.2 What We Currently Have

From our **interoperability-architecture.md** (Section 3.1):

```
╔═══════════════════════════════════════════════════════════════╗
║  GITHURAI LEVEL 4 HOSPITAL                       🔴 HIGH RISK ║
╚═══════════════════════════════════════════════════════════════╝

📋 PROCUREMENT DATA
💰 FINANCIAL DATA
📍 GEOLOCATION DATA
🛰️ SATELLITE ANALYSIS
⚠️ RISK ASSESSMENT
```

### 3.3 What We SHOULD Have (Aligned with Triangle of Truth)

**NEW SECTION: Triangle of Truth Status**

```
═══════════════════════════════════════════════════════════════
TRIANGLE OF TRUTH ANALYSIS
═══════════════════════════════════════════════════════════════

📊 FINANCIAL LEG (Controller of Budget)
   Source: CoB BIRR Q3 2024
   Status: 🔴 PAID
   Progress: 60% of contract value disbursed (KES 270M)
   Last Payment: 2025-09-15
   ├─ Budget Allocated: KES 450M
   ├─ Budget Released: KES 270M
   └─ Budget Absorbed: KES 270M (100% absorption)

🏗️ PROCUREMENT LEG (e-GP Kenya)
   Source: e-GP Tender Database
   Status: 🟢 AWARDED
   Tender ID: KCG/2025/112
   ├─ Award Date: 2025-03-15
   ├─ Contract Value: KES 450M
   ├─ Contractor: ABC Construction Ltd (NCA-1 #12345)
   ├─ Expected Completion: 2026-03-15 (18 months)
   └─ GPS Coordinates: -1.22°, 36.72° (e-GP pin drop)
       Validation: ⚠️ SUSPECT (County HQ proximity, needs verification)

🛰️ PHYSICAL LEG (Satellite Analysis)
   Source: Sentinel-2 + Sentinel-1
   Status: ⚫ NO CONSTRUCTION DETECTED
   Analysis Period: 2025-03-15 → 2026-02-19
   ├─ NDVI Change: +0.05 (vegetation INCREASED)
   ├─ SAR Backscatter: -12 dB (bare soil, no structures)
   └─ Physical Progress: 0% complete

═══════════════════════════════════════════════════════════════
⚠️ ONEKA VERDICT
═══════════════════════════════════════════════════════════════
Risk Level: 🔴 CRITICAL (95/100)

Triangle Gap Analysis:
├─ Financial Progress: 60% (KES 270M paid)
├─ Physical Progress:   0% (no construction detected)
└─ Progress Gap:       60 percentage points

Classification: 🚨 CONFIRMED GHOST PROJECT

Without ONEKA:
  ✗ Auditor sees CoB payment → assumes market exists
  ✗ e-GP shows pin on map → no verification
  ✗ Loss discovered 2 years later in audit report

With ONEKA:
  ✓ Payment linked to empty plot in real-time
  ✓ Evidence package ready for prosecution
  ✓ KES 180M prevented from further disbursement
```

---

## Part 4: Critical Implementation Changes Required

### 4.1 Database Schema Updates

**NEW TABLE**: `triangle_of_truth_snapshots`

```sql
CREATE TABLE triangle_of_truth_snapshots (
    snapshot_id UUID PRIMARY KEY,
    project_uuid UUID REFERENCES projects(project_uuid),
    snapshot_date DATE NOT NULL,

    -- Financial Leg (CoB)
    cob_source_document TEXT,  -- URL to BIRR PDF
    budget_allocated_kes DECIMAL(15,2),
    budget_released_kes DECIMAL(15,2),
    budget_absorbed_kes DECIMAL(15,2),
    financial_progress_pct DECIMAL(5,2),
    financial_status VARCHAR(20),  -- 'PAID', 'PARTIAL', 'PENDING'

    -- Procurement Leg (e-GP)
    egp_tender_id TEXT,
    egp_contract_value_kes DECIMAL(15,2),
    egp_awarded_date DATE,
    egp_gps_latitude DECIMAL(10,7),
    egp_gps_longitude DECIMAL(10,7),
    egp_gps_validation_status VARCHAR(20),  -- 'VERIFIED', 'SUSPECT', 'INVALID'
    procurement_status VARCHAR(20),  -- 'AWARDED', 'ONGOING', 'COMPLETED'

    -- Physical Leg (Satellite)
    satellite_analysis_id UUID REFERENCES satellite_analyses(analysis_id),
    physical_progress_pct DECIMAL(5,2),
    satellite_interpretation TEXT,
    physical_status VARCHAR(20),  -- 'DETECTED', 'NON_EXISTENT', 'UNCLEAR'

    -- Triangle Analysis
    progress_gap DECIMAL(5,2),  -- financial_progress - physical_progress
    verdict VARCHAR(50),  -- 'GHOST_PROJECT', 'STALLED', 'HEALTHY', 'UNDER_REVIEW'
    risk_score INTEGER,  -- 0-100

    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.2 API Endpoint Updates

**NEW ENDPOINT**: Triangle of Truth Status

```python
@router.get("/projects/{project_uuid}/triangle-status")
async def get_triangle_of_truth_status(project_uuid: UUID):
    """
    Get the current Triangle of Truth status for a project

    Returns:
    {
        "financial_leg": {
            "status": "PAID",
            "progress_pct": 60,
            "amount_kes": 270000000,
            "source": "CoB BIRR Q3 2024"
        },
        "procurement_leg": {
            "status": "AWARDED",
            "tender_id": "KCG/2025/112",
            "gps": {"lat": -1.22, "lon": 36.72},
            "gps_quality": "SUSPECT"
        },
        "physical_leg": {
            "status": "NON_EXISTENT",
            "progress_pct": 0,
            "last_analysis": "2026-02-19"
        },
        "verdict": {
            "classification": "GHOST_PROJECT",
            "risk_score": 95,
            "progress_gap": 60,
            "evidence_package_url": "/api/evidence/550e8400..."
        }
    }
    """
    pass
```

### 4.3 Sprint Planning Updates

**SPRINT 3 CHANGES** (Entity Resolution):

| Original Plan                        | Updated Plan (Reality-Aligned)               |
| ------------------------------------ | -------------------------------------------- |
| Build fuzzy matching for geolocation | ✅ KEEP but add e-GP validation layer        |
| Primary source: KMHFL/NEMIS          | ❌ CHANGE to Primary: e-GP, Secondary: KMHFL |
| Target: 25-40% geolocation success   | ✅ UPGRADE to 70-85% (e-GP mandatory pins)   |
| Implement string similarity          | ✅ KEEP for contractor/entity name matching  |

**NEW SPRINT 3.5** (Triangle of Truth Integration):

1. **CoB-to-e-GP Matching Engine**
   - Multi-factor matching (contractor, amount, timing, entity)
   - Confidence scoring (HIGH >80%, MEDIUM 50-80%, LOW <50%)
2. **e-GP GPS Validation Pipeline**
   - County HQ proximity detection
   - Facility registry cross-reference
   - Quality flag assignment
3. **Triangle Snapshot Generator**
   - Automated monthly snapshots
   - Historical trend analysis
   - Progress gap alerts

---

## Part 5: The Value Proposition (Updated)

### 5.1 What We Say Now

From **solution-overview.md**:

> "Oneka AI uses Satellite Remote Sensing to automatically audit physical progress against financial spend"

### 5.2 What We SHOULD Say (Triangle of Truth)

**NEW POSITIONING**:

> "ONEKA is the ONLY link between three disconnected government systems. We connect the payment (CoB) to the map (e-GP) to the empty plot of land (Satellite). Without ONEKA, the Auditor General sees money paid and assumes the project exists. Without ONEKA, e-GP shows a pin on a map but doesn't know if money was lost. **We connect the payment to the empty plot of land.**"

### 5.3 The Elevator Pitch (Updated)

```
OLD PITCH:
"We use satellites to find ghost projects"

NEW PITCH (Triangle of Truth):
"The government has three systems that don't talk to each other:
1. Controller of Budget: Tracks MONEY (who got paid what)
2. e-GP Portal: Tracks CONTRACTS (where the project should be)
3. Reality: What's ACTUALLY on the ground

ONEKA is the bridge. We link:
- The KES 20M paid to ABC Construction (from CoB report)
- To Tender #KCG/2025/112 for Wangige Market (from e-GP)
- To GPS coordinates -1.22, 36.72 (from e-GP)
- To satellite images showing an empty field (our analysis)

Result: We prove the 20M was stolen. Without ONEKA, these dots never connect."
```

---

## Part 6: Action Items

### 6.1 Immediate (This Week)

- [ ] Update database schema with `triangle_of_truth_snapshots` table
- [ ] Create e-GP geolocation validation function
- [ ] Update PPIP scraper to historical-only mode (pre-July 2025)
- [ ] Document "Triangle of Truth" workflow in technical architecture

### 6.2 Sprint 3 Additions

- [ ] Build CoB-to-e-GP matching engine
- [ ] Implement multi-factor matching algorithm
- [ ] Create Triangle status dashboard component
- [ ] Add GPS validation layer for e-GP coordinates

### 6.3 Documentation Updates

- [ ] Update `interoperability-architecture.md` with Triangle of Truth section
- [ ] Revise `solution-overview.md` elevator pitch
- [ ] Add "System Integration Reality" section to tech docs
- [ ] Create `egp-integration-guide.md` for mandatory geolocation handling

---

## Conclusion: The Gap We Didn't Know We Had

**What the "Ground Truth" Revealed**:

1. **e-GP Mandatory Geolocation** = GAME CHANGER
   - We assumed geolocation would be our hardest problem
   - Reality: 70-85% of projects NOW HAVE GPS (but need validation)
2. **PPIP is Dead for New Projects**
   - We planned weekly scraping
   - Reality: One-time historical import, then ignore
3. **CoB/e-GP Disconnect is WORSE Than We Thought**
   - We knew integration was missing
   - Reality: Payment systems use completely different identifiers
   - Our inference matching is CRITICAL (not just nice-to-have)

**The Fix**:

ONEKA's value is NOT just satellite analysis. It's being the **ONLY system** that links:

- Money (CoB) → Map (e-GP) → Physical Reality (Satellite)

This is our moat. This is why we win.

---

**Document Version**: 1.0  
**Date**: February 19, 2026  
**Next Action**: Review with technical team, update sprint backlog
