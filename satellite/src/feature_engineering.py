"""
Feature engineering pipeline for the ghost project ML classifier.

Supports two modes:
  - Training mode : build_training_dataframe(csv_path) — reads the 30-project
                    labelled CSV and computes the features available without
                    live satellite data. Satellite features → NaN (imputed later).
  - Inference mode: extract_features(project_data) — takes a pre-fetched dict
                    assembled from the backend DB and computes all 10 features.

Feature vector (always in this column order — any missing values are NaN and are
imputed with column medians by the model Pipeline before scoring):

  0  ndvi_slope             Rate of NDVI change per month (negative = clearing)
  1  sar_backscatter_delta  Max SAR VV delta vs. baseline scene (dB, positive = new structures)
  2  divergence_score       financial_progress − physical_progress (0–100)
  3  months_to_clearing     Months from award_date to first NDVI drop below 0.3
  4  absorption_anomaly     Actual absorption minus expected linear spend (percentage points)
  5  contract_value_log     log10(contract_sum_kes) — normalise scale
  6  project_type_encoded   health=0, education=1, roads=2, water=3, other=4
  7  county_cloud_risk      Annual cloud fraction for county (0.0 = clear, 1.0 = cloudy)
  8  contractor_tier        NCA tier 1–8 (1 = highest capacity)
  9  phase_on_schedule      Binary 1/0: spend rate within ±20 pp of linear baseline
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


# ── Feature name list (canonical order matches the trained model) ─────────────

FEATURES: list[str] = [
    "ndvi_slope",
    "sar_backscatter_delta",
    "divergence_score",
    "months_to_clearing",
    "absorption_anomaly",
    "contract_value_log",
    "project_type_encoded",
    "county_cloud_risk",
    "contractor_tier",
    "phase_on_schedule",
]


# ── County cloud-cover lookup (annual cloud fraction, MODIS climatology) ──────
# Source: MODIS MOD09GA cloud mask annual mean, Kenya, 2015–2024.
# Grouped by climate zone: West Kenya basin > highlands > coast > ASAL.

_COUNTY_CLOUD_RISK: dict[str, float] = {
    # Lake Victoria basin — highest mean cloud fraction
    "Kakamega": 0.70,
    "Vihiga": 0.69,
    "Siaya": 0.68,
    "Kisii": 0.67,
    "Busia": 0.67,
    "Nyamira": 0.65,
    "Kisumu": 0.65,
    "Homa Bay": 0.66,
    "Migori": 0.64,
    "Kericho": 0.63,
    "Bungoma": 0.62,
    "Nyandarua": 0.62,
    # Western / Rift Valley highlands
    "Trans Nzoia": 0.60,
    "Nandi": 0.60,
    "Bomet": 0.60,
    "Nyeri": 0.58,
    "Murang'a": 0.57,
    "Kiambu": 0.56,
    "Elgeyo-Marakwet": 0.55,
    "Uasin Gishu": 0.55,
    "Kirinyaga": 0.55,
    # Coast
    "Mombasa": 0.55,
    "Kwale": 0.53,
    "Kilifi": 0.52,
    # Central Kenya
    "West Pokot": 0.52,
    "Nakuru": 0.52,
    "Meru": 0.52,
    # Nairobi / Embu
    "Nairobi": 0.50,
    "Embu": 0.50,
    # Eastern highlands
    "Tharaka Nithi": 0.48,
    "Narok": 0.48,
    "Taita Taveta": 0.45,
    "Machakos": 0.45,
    # Southern / Eastern
    "Laikipia": 0.42,
    "Makueni": 0.42,
    "Baringo": 0.40,
    "Kitui": 0.40,
    "Lamu": 0.40,
    "Kajiado": 0.40,
    # ASAL — semi-arid / arid, lowest cloud fraction
    "Samburu": 0.35,
    "Tana River": 0.35,
    "Isiolo": 0.32,
    "Marsabit": 0.30,
    "Garissa": 0.28,
    "Turkana": 0.28,
    "Wajir": 0.25,
    "Mandera": 0.22,
}
_DEFAULT_CLOUD_RISK: float = 0.50


# ── Project type keyword mappings ─────────────────────────────────────────────
# Encoding: health=0, education=1, roads=2, water=3, other=4

_TYPE_KEYWORDS: dict[int, list[str]] = {
    0: [
        "hospital",
        "health",
        "clinic",
        "dispensary",
        "maternity",
        "icu",
        "medical",
        "laboratory",
        " lab ",
        "pharmacy",
    ],
    1: [
        "school",
        "polytechnic",
        "college",
        "university",
        "education",
        "institute",
        "tvet",
        "hostel",
        "secondary",
        "primary",
        "classroom",
        "dormitory",
    ],
    2: [
        "road",
        "bridge",
        "street",
        "highway",
        "link road",
        "footbridge",
        "airstrip",
        "airport",
        "pier",
        "runway",
        "bypass",
    ],
    3: [
        "water",
        "dam",
        "irrigation",
        "sewerage",
        "borehole",
        "treatment plant",
        "sanitation",
        "drainage",
    ],
}


# ── Helper functions ──────────────────────────────────────────────────────────


def _classify_project_type(name: str) -> int:
    """Classify project type (0–4) from tender/project name keywords."""
    lower = name.lower()
    for enc, keywords in _TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return enc
    return 4  # other


def _county_cloud_risk(county: str) -> float:
    """Return annual cloud fraction for a county; defauls to 0.50 if unknown."""
    return _COUNTY_CLOUD_RISK.get(str(county).strip(), _DEFAULT_CLOUD_RISK)


def _safe_log10(value: Optional[float]) -> float:
    """Return log10 of a positive value, NaN otherwise."""
    if value is None:
        return float("nan")
    try:
        v = float(value)
        if math.isnan(v) or v <= 0:
            return float("nan")
        return math.log10(v)
    except (TypeError, ValueError):
        return float("nan")


def _parse_contractor_tier(license_str: Optional[str]) -> float:
    """Extract NCA tier as a float from a string like 'NCA3-12345' → 3.0."""
    if not license_str:
        return float("nan")
    s = str(license_str).upper()
    for tier in range(1, 9):
        if f"NCA{tier}" in s or f"NCA {tier}" in s:
            return float(tier)
    return float("nan")


def _months_between(start: str, end: str) -> float:
    """Return months elapsed between two ISO date strings. Returns 0 if negative."""
    d0 = datetime.strptime(str(start)[:10], "%Y-%m-%d")
    d1 = datetime.strptime(str(end)[:10], "%Y-%m-%d")
    return max(0.0, (d1 - d0).days / 30.44)


def _safe_float(value) -> float:
    """Convert to float or return NaN."""
    if value is None:
        return float("nan")
    try:
        v = float(value)
        return v if math.isfinite(v) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


# ── Main class ────────────────────────────────────────────────────────────────


class FeatureEngineer:
    """
    Compute the 10-feature vector used by the ghost project RandomForest classifier.

    Usage — training from CSV::

        fe = FeatureEngineer()
        X, y = fe.build_training_dataframe(Path("data/training/training_projects.csv"))

    Usage — live inference from pre-fetched DB data::

        project_data = {
            "project_name": "...", "county": "Nairobi",
            "project_type": "HEALTH", "contract_sum_kes": 350_000_000,
            "ndvi_slope": -0.04, "sar_backscatter_delta": 2.1,
            "divergence_score": 35.0, "award_date": "2022-01-15",
            "first_ndvi_drop_date": "2022-04-10",
            "completion_date": "2023-12-31",
            "absorption_rate": 88.0,
            "contractor_nca_license": "NCA3-00123",
        }
        features = fe.extract_features(project_data)
    """

    FEATURES: list[str] = FEATURES

    # ── Training mode ──────────────────────────────────────────────────────────

    def build_training_dataframe(
        self, projects_csv: Path
    ) -> tuple[pd.DataFrame, pd.Series]:
        """
        Build feature matrix X and label vector y from the 30-project training CSV.

        Satellite features (ndvi_slope, sar_backscatter_delta, divergence_score,
        months_to_clearing, absorption_anomaly, contractor_tier, phase_on_schedule)
        are set to NaN because the labelled CSV contains no satellite or financial
        data. The model pipeline imputes these as column medians during training.

        Args:
            projects_csv: Path to ``training_projects.csv``.

        Returns:
            Tuple of (X DataFrame shape (n, 10), y Series with 1=ghost / 0=success).
        """
        df = pd.read_csv(projects_csv, dtype=str)

        rows: list[dict] = []
        for _, row in df.iterrows():
            rows.append(self._features_from_csv_row(row))

        X = pd.DataFrame(rows, columns=self.FEATURES).astype(float)
        y = pd.Series(
            [1 if str(r).strip().lower() == "ghost" else 0 for r in df["status"]],
            name="is_ghost",
            dtype=int,
        )
        return X, y

    def _features_from_csv_row(self, row: "pd.Series") -> dict:
        """Compute features from a single training CSV row."""
        nan = float("nan")
        return {
            "ndvi_slope": nan,
            "sar_backscatter_delta": nan,
            "divergence_score": nan,
            "months_to_clearing": nan,
            "absorption_anomaly": nan,
            "contract_value_log": _safe_log10(row.get("budget_kes")),
            "project_type_encoded": float(
                _classify_project_type(str(row.get("project_name", "")))
            ),
            "county_cloud_risk": _county_cloud_risk(str(row.get("county", ""))),
            "contractor_tier": nan,
            "phase_on_schedule": nan,
        }

    # ── Inference mode ─────────────────────────────────────────────────────────

    def extract_features(self, project_data: dict) -> pd.Series:
        """
        Compute the full 10-feature vector from a pre-fetched project data dict.

        Args:
            project_data: dict assembled by ``RiskScoringService._fetch_project_data()``.
                Keys (all optional except project_name/county):
                  project_name, county, project_type (str enum value),
                  contract_sum_kes, contractor_nca_license,
                  ndvi_slope, sar_backscatter_delta, divergence_score,
                  award_date (ISO str), first_ndvi_drop_date (ISO str or None),
                  completion_date (ISO str or None),
                  absorption_rate (float 0–100).

        Returns:
            pd.Series indexed by FEATURES with dtype float.
        """
        nan = float("nan")

        # project_type_encoded — prefer DB enum value, fall back to keyword
        ptype_map = {"HEALTH": 0, "EDUCATION": 1, "ROADS": 2, "WATER": 3}
        ptype_str = str(project_data.get("project_type", "")).upper()
        project_type_encoded = float(
            ptype_map.get(
                ptype_str,
                _classify_project_type(str(project_data.get("project_name", ""))),
            )
        )

        # months_to_clearing
        award_date = project_data.get("award_date")
        first_drop = project_data.get("first_ndvi_drop_date")
        months_to_clearing = (
            _months_between(str(award_date), str(first_drop))
            if award_date and first_drop
            else nan
        )

        features = {
            "ndvi_slope": _safe_float(project_data.get("ndvi_slope")),
            "sar_backscatter_delta": _safe_float(
                project_data.get("sar_backscatter_delta")
            ),
            "divergence_score": _safe_float(project_data.get("divergence_score")),
            "months_to_clearing": months_to_clearing,
            "absorption_anomaly": self._compute_absorption_anomaly(project_data),
            "contract_value_log": _safe_log10(project_data.get("contract_sum_kes")),
            "project_type_encoded": project_type_encoded,
            "county_cloud_risk": _county_cloud_risk(
                str(project_data.get("county", ""))
            ),
            "contractor_tier": _parse_contractor_tier(
                project_data.get("contractor_nca_license")
            ),
            "phase_on_schedule": self._compute_phase_on_schedule(project_data),
        }
        return pd.Series(features, index=self.FEATURES, dtype=float)

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _compute_absorption_anomaly(data: dict) -> float:
        """
        Deviation from linear spend baseline (percentage points).

        expected_at_month_M = (M / contract_duration_months) × 100
        anomaly = actual_absorption_rate − expected_absorption_rate

        A large positive anomaly means money was absorbed faster than expected —
        a ghost project signature.
        """
        absorption_rate = data.get("absorption_rate")
        award_date = data.get("award_date")
        completion_date = data.get("completion_date")
        if absorption_rate is None or not award_date or not completion_date:
            return float("nan")
        try:
            total_months = _months_between(str(award_date), str(completion_date))
            if total_months <= 0:
                return float("nan")
            today_iso = date.today().isoformat()
            elapsed = min(_months_between(str(award_date), today_iso), total_months)
            expected = (elapsed / total_months) * 100.0
            return float(absorption_rate) - expected
        except Exception:
            return float("nan")

    @staticmethod
    def _compute_phase_on_schedule(data: dict) -> float:
        """
        Binary feature: 1 if actual absorption is within ±20 pp of linear baseline,
        0 if outside tolerance, NaN if data unavailable.

        A value of 0 (off-schedule) can indicate either a ghost project
        (absorbed too fast) or a stalled project (too slow).
        """
        absorption_rate = data.get("absorption_rate")
        award_date = data.get("award_date")
        completion_date = data.get("completion_date")
        if absorption_rate is None or not award_date or not completion_date:
            return float("nan")
        try:
            total_months = _months_between(str(award_date), str(completion_date))
            if total_months <= 0:
                return float("nan")
            today_iso = date.today().isoformat()
            elapsed = min(_months_between(str(award_date), today_iso), total_months)
            expected = (elapsed / total_months) * 100.0
            deviation = abs(float(absorption_rate) - expected)
            return 1.0 if deviation <= 20.0 else 0.0
        except Exception:
            return float("nan")
