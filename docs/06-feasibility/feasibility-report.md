# Oneka AI: Independent Feasibility Report

**Document Type:** Fact-Checked Feasibility Assessment  
**Prepared By:** Research & Verification Agent (Oneka AI Team)  
**Reference Date:** March 1, 2026  
**Scope:** Cross-verification of project documentation against primary sources, technical literature, and Kenyan statutory frameworks  
**Classification:** Internal Working Document — Hackathon Submission Support

---

## 1. Executive Summary

**Oneka AI** is a decision-support system designed to combat "ghost projects" in Kenya's public infrastructure landscape by triangulating financial disbursement data (from IFMIS and Controller of Budget reports) against physical ground-truth evidence derived from satellite change detection (Sentinel-1 SAR and Sentinel-2 optical imagery). The platform targets the Office of the Auditor General (OAG) as its primary user and is designed to multiply audit capacity by shifting the model from random sampling to algorithmic risk targeting.

This feasibility report synthesises findings from:

1. A full review of all project documentation (`docs/01-concept` through `docs/05-implementation`).
2. An independent research verification exercise conducted on March 1, 2026, cross-referencing claims against primary sources including the OAG website, NCA official registry, ESA Copernicus pages, Planet Labs, PPIP live portal, and Kenyan constitutional law repositories.

**Overall Verdict:** **Conditionally Viable — High Strategic Potential, Manageable Technical Risk.**

The core problem is real, the financial magnitude is verified, the satellite technology is proven, and the legal framework is navigable. The primary risks are (a) the **geolocation data void** in historical procurement records (PPIP/legacy), which is partially resolved by the July 2025 mandatory e-GP transition with its geolocation field; (b) the **Section 106B legal admissibility challenge**, which the proposed automated certificate module directly addresses; and (c) **spatial resolution limits** of free Sentinel-2 imagery (10m/pixel) for small-footprint projects such as single classrooms.

---

## 2. The Problem: Verified Evidence Base

### 2.1 Financial Magnitude

The following core financial claims underpinning Oneka AI's value proposition have been independently verified:

| Claim | Verification Status | Evidence |
|---|---|---|
| ~**KES 304 Billion** locked in stalled/delayed projects across Kenya | ✅ **VERIFIED** | Auditor-General Nancy Gathungu, National Assembly testimony, June 2, 2025 (AllAfrica/Capital FM). Figure refers to underutilised budget in 14 flagship projects over 5 years. |
| **Mombasa Gate Bridge**: KES 48.11B dormant; only KES 938.2M (2%) spent since Dec 2019 | ✅ **VERIFIED** | Same primary source. Exact figures confirmed; commitment fee penalties verified as a fiscal liability. |
| **KES 750+ billion** annual infrastructure allocation | ⚠️ **PARTIALLY VERIFIED** | National Government development spending was KES 708.85B (FY 2023/24) and KES 643.9B (FY 2024/25). The 750B figure is plausible as a combined national + county + off-budget figure, but requires scope clarification. Recommend updating to "approximately KES 700+ billion." |
| **KES 270 Billion** lost annually to procurement inefficiencies | ❓ **UNVERIFIED** | No traceable primary source citation. This figure appears in the documentation as a standalone assertion. It may be a composite estimate derived from the 304B stalled total, but presenting it as an *annual* loss without a citation is a credibility risk. **Recommend removing or replacing with the verified KES 304B figure with correct attribution.** |
| Traditional audits take **18-24 months** and cost **KES 2-5M per project** | ❓ **UNVERIFIED** | No primary source found. The timeline is directionally consistent with OAG annual report cycles. The KES 2-5M cost per project is an unattributed internal estimate. Acceptable as an approximation in a hackathon pitch but must be sourced before formal publication. |
| OAG physically samples less than **5% of projects annually** | ⚠️ **PARTIALLY VERIFIED** | Cited from OAG internal reports and consistent with the known auditor-to-project ratio following 2013 devolution. The 5% is an internal OAG-cited estimate, not an independently published statistic. Directionally robust. |
| **East Africa Skills for Transformation Project** (Meru Polytechnic) stalled on construction | ⚠️ **PARTIALLY VERIFIED** | Project confirmed by AllAfrica (61% absorption of KES 1.1B budget). The specific KES 444M construction sub-figure is from OAG Donor Projects Report 2023/24 (not independently accessible, but is a cited OAG primary source). |

### 2.2 Structural Problem: The Three-Part Data Disconnect

The documentation's core diagnostic — a three-way disconnect between procurement data (PPIP/e-GP), financial data (IFMIS/COB), and physical data (satellite) — is technically accurate and well-substantiated. The PPIP live portal (accessed March 1, 2026) confirmed:

- **257,402 tenders** published (KES 2.066 trillion transacted since approximately 2018)
- **Zero geolocation fields** — the portal's schema is text-only for location ("Location: Nairobi County")
- **No public API** — data must be scraped or downloaded via document review

The e-GP portal confirms 1,495 procuring entities and 37,329 registered suppliers, with OCDS-compliant data architecture. Critically, the **mandatory geolocation field** introduced with e-GP (post-July 2025) is a game-changing input for Oneka AI's geolocation engine — new tenders will carry GPS coordinates that historical PPIP records never did.

---

## 3. Legal and Regulatory Framework: Verified

### 3.1 Constitutional Mandate

| Claim | Status | Detail |
|---|---|---|
| **Article 229** of Kenya's Constitution mandates the Auditor General to verify "lawful and effective" use of public resources | ✅ **VERIFIED** | Article 229(7) is well-established constitutional law. Article 228 (verified via COB website) governs the Controller of Budget — a distinct office. |
| **Article 228** governs the Controller of Budget | ✅ **VERIFIED** | Confirmed directly from the COB website's mandate page. |
| **PFM Act Section 81(4)** reduced the audit reporting window from 6 months (constitutional) to 3 months | ⚠️ **PARTIALLY VERIFIED** | Cited in OAG summary reports as a key structural constraint. Consistent with the OAG's narrative about the "Verification Vacuum." Primary PFM Act text not directly accessed during this review — confirm against the gazetted act text. |

### 3.2 Evidence Admissibility

| Claim | Status | Detail |
|---|---|---|
| **Section 106B, Evidence Act (Cap 80)** requires a certificate of authenticity for electronic evidence | ✅ **VERIFIED** | Well-established provision in Kenyan jurisprudence, consistent with multiple legal academic sources. The requirement for a certification from a "responsible official" for any "computer output" is accurately described. |
| Proposed **automated Section 106B certificate** generation | **TECHNICALLY FEASIBLE** | The certificate itself is a structured document with defined fields. Its automation is legally neutral — what matters is who signs it and whether they hold responsible authority over the data processing system. The legal strategy requires an MOU between OAG/EACC and either ESA or a certified Copernicus data distributor to establish signing authority. This is a policy challenge, not a technical one. |

### 3.3 Procurement Law

| Claim | Status | Detail |
|---|---|---|
| Kenya signatory to **Open Contracting Data Standard (OCDS)** | ⚠️ **PARTIALLY VERIFIED** | OCDS is a data standard, not a treaty. Kenya formally adopted it through its e-GP architecture (confirmed from e-GP website). The word "signatory" is imprecise. Accurate framing: "Kenya has adopted the OCDS standard via its e-GP system." |
| **National Construction Authority (NCA)** contractor classifications; NCA-1 unlimited value, NCA-2 capped at KES 500M (buildings) / KES 750M (roads) | ✅ **VERIFIED** | Confirmed directly from the NCA official website (nca.go.ke/local-contractors). The tiered classification table is publicly available and matches the documentation exactly. |
| e-GP became **mandatory for all procuring entities in July 2025** | ❓ **UNVERIFIED (specific date)** | The transition is confirmed as ongoing via PPIP's active redirect notices. The specific "July 2025" date was not found in any accessible gazette or PPRA circular. May be accurate from internal team research but requires a citation to a specific PPRA directive. |

---

## 4. Technical Feasibility: Satellite & Data Systems

### 4.1 Core Satellite Technology

| Claim | Status | Detail |
|---|---|---|
| **Sentinel-2**: 5-day revisit, 10m resolution | ✅ **VERIFIED** | Confirmed from ESA's official Sentinel-2 Facts and Figures page. Now a 3-satellite constellation (2A, 2B, 2C) since September 2024, offering potentially 3–4 day revisit. |
| **Sentinel-1 SAR**: ~12-day revisit over East Africa | ⚠️ **NEEDS UPDATE** | 12 days was the single-satellite repeat orbital period (accurate during 2022–2024 after Sentinel-1B decommissioning). As of late 2024 and November 2025 (1C and 1D launches), the constellation provides 3–6 day coverage over East Africa. Digital Earth Africa confirms 6–12 day revisit for operational planning purposes. **Update documentation to reflect the expanded constellation.** |
| **SAR "Double Bounce"** algorithm for construction detection | **TECHNICALLY SOUND** | The use of SAR backscatter coefficient changes to detect vertical structure emergence (walls, metal roofing) is established in remote sensing literature. The physics of radar double-bounce from corner reflectors (building edges) is well-documented. The challenge is calibration — distinguishing construction from natural backscatter changes requires careful baseline establishment and threshold tuning. |
| **NDVI change detection** for vegetation clearance monitoring | **TECHNICALLY SOUND** | NDVI drop from 0.6–0.8 (dense vegetation) to 0.0–0.2 (bare soil/construction) is a validated and reproducible signal in Sentinel-2 imagery. Standard practice in agricultural and urban land-use change detection studies. |

### 4.2 Resolution Constraints

**Critical Technical Limitation:** Sentinel-2's 10m/pixel resolution imposes fundamental limits on detecting small-footprint infrastructure.

- A standard Kenyan Ministry of Education classroom block (approximately 10m × 20m) occupies only 2–3 pixels in a Sentinel-2 image.
- "Mixed pixels" — where a single pixel straddles both the building and surrounding bare earth — create spectral averaging that reduces detection confidence.
- **Implication:** Oneka AI is most reliable for large footprint infrastructure: dams, roads, stadiums, multi-ward hospitals, and large market complexes. It is a **triage tool, not a precise measurement instrument**, for small rural infrastructure.
- **Mitigation Path:** Integration of commercial imagery (Planet SkySat at 50cm, verified) for high-priority Red Flag sites at investigative stage. Costs are approximately $12–$40/km² (SkySat), making selective tasking economically viable.

### 4.3 Data Source Accessibility

| Source | Accessibility | Integration Status |
|---|---|---|
| **Sentinel-1/2 via Copernicus Data Space** | ✅ Free, API-accessible | Working in codebase (`data/scrapers/ppip.py`, `nca.py`) |
| **KMHFL/KMHFR API** | ⚠️ Recently migrated | Old URL (`api.kmhfl.health.go.ke`) now redirects to `api.kmhfr.health.go.ke`. Update required in codebase. ~13,000–14,000+ facilities, GPS coordinates available. |
| **PPIP (tenders.go.ke)** | ✅ Public, no API | Scraping-based; 257,402+ historical tenders; useful as ML training data archive (pre-July 2025) |
| **e-GP (egpkenya.go.ke)** | ⚠️ Auth required | OCDS-compliant; geolocation fields confirmed; requires integration partnership with PPRA for automated feed |
| **Controller of Budget (BIRR reports)** | ✅ Public PDFs | OCR pipeline required; quarterly public reports; no API |
| **Open Schools Kenya** | ❓ Status uncertain | Website intermittently accessible; verify direct CSV download path before depending on it |

### 4.4 Machine Learning Model

The proposed Random Forest classifier trained on historical satellite time-series is technically sound:

- **Training data target:** 30+ confirmed completed vs. stalled projects (with GPS, award date, completion date)
- **Features:** NDVI slope, SAR backscatter change, spending rate, S-Curve deviation score
- **Target accuracy:** 80–85% (5-fold cross-validation)
- **Key risk:** Small training set size (30 projects). A Random Forest with 30 samples, 15+ features, and high class imbalance (stalled projects are rarer than successful ones) risks overfitting. Recommend augmentation with synthetic data via SMOTE or bootstrapping, and a strict holdout test set.

---

## 5. Infrastructure & Architecture Assessment

The proposed tech stack is appropriate, modern, and well-suited to the problem:

| Component | Choice | Assessment |
|---|---|---|
| Backend | FastAPI (Python 3.11+) | Correct for geospatial and async processing. Production-grade. |
| Database | PostgreSQL 15 + PostGIS 3.3 | Industry standard for geospatial workloads. ST_DWithin and ST_Distance functions directly applicable to facility proximity matching. |
| Satellite Processing | Satpy + rasterio + xarray | Appropriate library stack for Sentinel SAFE format ingestion. |
| Frontend | Next.js + CesiumJS + Google 3D Tiles | Google Photorealistic 3D Tiles confirmed operational in Kenya for major urban centres (Nairobi, Mombasa). Rural areas revert to terrain mesh — documented and acceptable. |
| Cloud | AWS (S3, Lambda, Fargate) | Appropriate event-driven architecture for document ingestion pipelines. |
| Entity Resolution | RapidFuzz (token_set_ratio) | Correct algorithm choice. Threshold of >90% auto-accept, 70–90% human review is a well-calibrated approach backed by the documentation. |

---

## 6. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **Geolocation void in legacy PPIP data** | High | Certain (confirmed) | Use KMHFR proxy geolocation for brownfield projects; rely on e-GP's mandatory GPS field for all post-July 2025 tenders |
| **Section 106B admissibility challenge** | High | High (requires policy action) | Draft MOU with OAG/EACC and ESA/Copernicus data distributor; automate certificate fields but require human official signature |
| **Cloud cover blocking Sentinel-2 in Central Kenya** | Medium | Certain (seasonal) | Use Sentinel-1 SAR as primary layer for Highland counties during Long/Short Rains |
| **Small training dataset (30 projects)** | Medium | Likely if not expanded | Use PPIP archive (2018–2025) to build training set; apply SMOTE oversampling |
| **KMHFL API URL deprecated** | Low | Confirmed | Update all references to `api.kmhfr.health.go.ke` |
| **Sentinel-1 constellation change** | Low | Confirmed (already resolved) | Update documentation to reflect 3–6 day revisit with current 1A/1C/1D constellation |
| **Resistance from procuring entities (data access)** | High | Likely | Frame Oneka as OAG/COB decision-support tool, not a surveillance mechanism; formal integration via PPRA MOU |
| **Political interference / data suppression** | High | Possible at scale | Store all satellite data with immutable timestamps in AWS S3 with audit trails; chain of custody built-in |

---

## 7. Minimum Viable Product (MVP) Scope Assessment

The 8-week MVP roadmap is realistic for the core loop:

```
Tender Ingestion (PPIP/e-GP) → Proxy Geolocation (KMHFR/NEMIS fuzzy match) 
→ Satellite Query (Sentinel-1/2 via Copernicus API) 
→ Change Detection (NDVI + SAR backscatter score) 
→ Risk Flag (Red/Yellow/Green) 
→ Dashboard (CesiumJS map + Risk Heat Map)
```

The **Section 106B certificate generator** and **predictive ML model** are appropriately scoped as Sprint 2+ deliverables beyond the core MVP loop.

---

## 8. Financial Model

| Scenario | Annual Saving | Basis |
|---|---|---|
| 1% reactivation of stalled KES 304B portfolio | **KES 3 Billion** | Verified: extrapolated from OAG-confirmed figure |
| OAG audit cost reduction (if 50% of field visits prevented) | **KES 50–100M** | Estimated based on unverified audit cost per project figure; treat as indicative only |
| Donor fund absorption improvement | **Multi-billion** | Plausible; AllAfrica confirms systemic absorption crisis at 11–61% for major projects |

The "KES 3 Billion annually from 1% reactivation" headline is the most defensible and verified ROI claim in the documentation. It should remain the primary financial hook.

---

## 9. Summary: Verified vs. Needs-Fixing

### Claims to Keep (High Confidence)
- KES 304 Billion stalled portfolio (OAG-verified)
- Mombasa Gate Bridge exact figures (OAG-verified)
- Article 229 constitutional mandate
- Section 106B Evidence Act requirement
- NCA registration tiers (NCA website-verified)
- Sentinel-2 accuracy specs (ESA-verified)
- 47 counties since 2013 devolution
- PPIP is text-only with no GPS fields (confirmed live)
- e-GP is OCDS-compliant (confirmed from portal)

### Claims to Correct Before Submission
1. **KES 270B annual loss** → Replace with "KES 304B in stalled projects" (cite Auditor-General, June 2025)
2. **KES 750B annual infrastructure** → Update to "approximately KES 700B" with national dev. budget source
3. **Sentinel-1 12-day revisit** → Update to "6–12 days (expanding to 3–6 days with 2024–2025 constellation additions)"
4. **KMHFL API URL** → Update to `api.kmhfr.health.go.ke`
5. **e-GP mandatory July 2025** → Add PPRA gazette citation or soften to "mandatory transition milestone targeted for mid-2025"
6. **PlanetScope "~3m"** → Update to "~3.7m (SuperDove GSD)" for technical accuracy
7. **OCDS "signatory"** → Change to "adopted OCDS standard" or "OCDS-committed"

---

## 10. Conclusion

Oneka AI addresses a well-documented, financially significant, and legally tractable problem in Kenya's public financial management landscape. The core technology (SAR + optical satellite change detection, NLP-driven entity resolution, risk scoring) is proven and deployable within a hackathon timeline for demonstration purposes, and within 12 months for a production system.

The platform's most innovative contribution — **combining satellite immutability with a legal evidence chain for criminal prosecution** — is the "kill shot" that elevates it from a monitoring dashboard to an anti-corruption instrument. The Section 106B automation module, if executed with proper institutional backing from the OAG, transforms satellite intelligence into courtroom-admissible evidence: a capability no comparable Kenyan government system currently provides.

The principal recommendation for immediate action is to open a formal dialogue with the Public Procurement Regulatory Authority (PPRA) and the Office of the Auditor General to establish the data sharing agreements and institutional legitimacy that will determine whether Oneka AI remains a hackathon prototype or becomes Kenya's infrastructure audit standard.
