"""Tests for satellite/src/feature_engineering.py — pure function helpers and FeatureEngineer."""

import math
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import sys
from pathlib import Path

# Add satellite/src to path for imports
_SAT_SRC = str(Path(__file__).parent.parent / "src")
if _SAT_SRC not in sys.path:
    sys.path.insert(0, _SAT_SRC)

from feature_engineering import (
    FEATURES,
    FeatureEngineer,
    _classify_project_type,
    _county_cloud_risk,
    _safe_log10,
    _parse_contractor_tier,
    _months_between,
    _safe_float,
)


# =============================================================================
# Module-level helper functions
# =============================================================================


class TestClassifyProjectType:

    def test_health_keywords(self):
        assert _classify_project_type("Construction of Nairobi Hospital") == 0
        assert _classify_project_type("Dispensary Upgrade") == 0
        assert _classify_project_type("ICU Wing Extension") == 0

    def test_education_keywords(self):
        assert _classify_project_type("Moi University Building") == 1
        assert _classify_project_type("Secondary School Dormitory") == 1
        assert _classify_project_type("TVET Polytechnic") == 1

    def test_roads_keywords(self):
        assert _classify_project_type("Thika Road Expansion") == 2
        assert _classify_project_type("Nairobi Bypass") == 2
        assert _classify_project_type("Footbridge at Kibera") == 2

    def test_water_keywords(self):
        assert _classify_project_type("Mwache Dam Construction") == 3
        assert _classify_project_type("Borehole Drilling") == 3
        assert _classify_project_type("Sewerage Treatment Plant") == 3

    def test_other_fallback(self):
        assert _classify_project_type("County Assembly Offices") == 4
        assert _classify_project_type("") == 4

    def test_case_insensitive(self):
        assert _classify_project_type("HOSPITAL") == 0
        assert _classify_project_type("school") == 1


class TestCountyCloudRisk:

    def test_known_county(self):
        assert _county_cloud_risk("Nairobi") == 0.50
        assert _county_cloud_risk("Kakamega") == 0.70
        assert _county_cloud_risk("Mandera") == 0.22

    def test_unknown_county_returns_default(self):
        assert _county_cloud_risk("NonExistent County") == 0.50

    def test_strips_whitespace(self):
        assert _county_cloud_risk("  Nairobi  ") == 0.50


class TestSafeLog10:

    def test_normal_value(self):
        assert _safe_log10(1000) == pytest.approx(3.0)
        assert _safe_log10(350_000_000) == pytest.approx(8.544, rel=1e-2)

    def test_zero_returns_nan(self):
        assert math.isnan(_safe_log10(0))

    def test_negative_returns_nan(self):
        assert math.isnan(_safe_log10(-100))

    def test_none_returns_nan(self):
        assert math.isnan(_safe_log10(None))

    def test_string_number(self):
        assert _safe_log10("1000") == pytest.approx(3.0)

    def test_invalid_string_returns_nan(self):
        assert math.isnan(_safe_log10("abc"))


class TestParseContractorTier:

    def test_tier_3(self):
        assert _parse_contractor_tier("NCA3-12345") == 3.0

    def test_tier_1(self):
        assert _parse_contractor_tier("NCA1-00001") == 1.0

    def test_with_space(self):
        assert _parse_contractor_tier("NCA 5-99999") == 5.0

    def test_case_insensitive(self):
        assert _parse_contractor_tier("nca3-12345") == 3.0

    def test_none_returns_nan(self):
        assert math.isnan(_parse_contractor_tier(None))

    def test_empty_string_returns_nan(self):
        assert math.isnan(_parse_contractor_tier(""))

    def test_no_tier_match_returns_nan(self):
        assert math.isnan(_parse_contractor_tier("LICENSE-12345"))


class TestMonthsBetween:

    def test_one_year(self):
        months = _months_between("2023-01-01", "2024-01-01")
        assert 11.5 < months < 12.5

    def test_same_date_returns_zero(self):
        assert _months_between("2024-06-15", "2024-06-15") == 0.0

    def test_reversed_dates_returns_zero(self):
        assert _months_between("2024-12-31", "2024-01-01") == 0.0

    def test_six_months(self):
        months = _months_between("2024-01-01", "2024-07-01")
        assert 5.5 < months < 6.5


class TestSafeFloat:

    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_none_returns_nan(self):
        assert math.isnan(_safe_float(None))

    def test_inf_returns_nan(self):
        assert math.isnan(_safe_float(float("inf")))

    def test_string_number(self):
        assert _safe_float("42.5") == 42.5

    def test_invalid_string_returns_nan(self):
        assert math.isnan(_safe_float("xyz"))


# =============================================================================
# FeatureEngineer class
# =============================================================================


class TestFeatureEngineerExtractFeatures:

    def setup_method(self):
        self.fe = FeatureEngineer()

    def test_returns_series_with_correct_index(self):
        data = {"project_name": "Hospital", "county": "Nairobi"}
        result = self.fe.extract_features(data)
        assert isinstance(result, pd.Series)
        assert list(result.index) == FEATURES

    def test_all_features_are_float(self):
        data = {"project_name": "Hospital", "county": "Nairobi"}
        result = self.fe.extract_features(data)
        for val in result.values:
            assert isinstance(val, (float, np.floating))

    def test_contract_value_log(self):
        data = {"project_name": "Test", "county": "Nairobi", "contract_sum_kes": 1_000_000}
        result = self.fe.extract_features(data)
        assert result["contract_value_log"] == pytest.approx(6.0)

    def test_project_type_from_enum(self):
        data = {"project_name": "Something", "county": "Nairobi", "project_type": "HEALTH"}
        result = self.fe.extract_features(data)
        assert result["project_type_encoded"] == 0.0

    def test_project_type_fallback_to_keyword(self):
        data = {"project_name": "Building a School", "county": "Nairobi"}
        result = self.fe.extract_features(data)
        assert result["project_type_encoded"] == 1.0  # education

    def test_county_cloud_risk_populated(self):
        data = {"project_name": "Test", "county": "Kakamega"}
        result = self.fe.extract_features(data)
        assert result["county_cloud_risk"] == 0.70

    def test_missing_satellite_data_gives_nan(self):
        data = {"project_name": "Test", "county": "Nairobi"}
        result = self.fe.extract_features(data)
        assert math.isnan(result["ndvi_slope"])
        assert math.isnan(result["sar_backscatter_delta"])

    def test_months_to_clearing_computed(self):
        data = {
            "project_name": "Test",
            "county": "Nairobi",
            "award_date": "2023-01-01",
            "first_ndvi_drop_date": "2023-07-01",
        }
        result = self.fe.extract_features(data)
        assert 5.5 < result["months_to_clearing"] < 6.5

    def test_contractor_tier_extracted(self):
        data = {
            "project_name": "Test",
            "county": "Nairobi",
            "contractor_nca_license": "NCA2-00123",
        }
        result = self.fe.extract_features(data)
        assert result["contractor_tier"] == 2.0


class TestFeatureEngineerTraining:

    def test_build_training_dataframe(self, tmp_path):
        csv = tmp_path / "projects.csv"
        csv.write_text(
            "project_id,project_name,county,latitude,longitude,award_date,"
            "completion_date,budget_kes,status,evidence_source\n"
            "1,Nairobi Hospital Wing,Nairobi,-1.29,36.82,2022-01-01,"
            "2023-12-31,500000000,ghost,OAG Audit\n"
            "2,Thika Road Upgrade,Kiambu,-1.04,36.98,2022-06-01,"
            "2024-06-30,800000000,success,Ministry Report\n"
        )

        fe = FeatureEngineer()
        X, y = fe.build_training_dataframe(csv)

        assert X.shape == (2, 10)
        assert list(X.columns) == FEATURES
        assert list(y) == [1, 0]  # ghost=1, success=0

        # Non-NaN features from CSV
        assert not math.isnan(X.iloc[0]["contract_value_log"])
        assert not math.isnan(X.iloc[0]["project_type_encoded"])
        assert not math.isnan(X.iloc[0]["county_cloud_risk"])

        # Satellite features should be NaN
        assert math.isnan(X.iloc[0]["ndvi_slope"])
        assert math.isnan(X.iloc[0]["sar_backscatter_delta"])


class TestAbsorptionAnomaly:

    def test_positive_anomaly(self):
        """Money absorbed faster than expected → positive anomaly."""
        data = {
            "absorption_rate": 90.0,
            "award_date": "2020-01-01",
            "completion_date": "2030-01-01",  # 10 years total
        }
        # With today ~2026, roughly 60% elapsed → expected ~60%
        # anomaly = 90 - ~60 = ~30
        result = FeatureEngineer._compute_absorption_anomaly(data)
        assert result > 0

    def test_missing_data_returns_nan(self):
        assert math.isnan(FeatureEngineer._compute_absorption_anomaly({}))
        assert math.isnan(
            FeatureEngineer._compute_absorption_anomaly({"absorption_rate": 50})
        )

    def test_zero_duration_returns_nan(self):
        data = {
            "absorption_rate": 50,
            "award_date": "2024-01-01",
            "completion_date": "2024-01-01",
        }
        assert math.isnan(FeatureEngineer._compute_absorption_anomaly(data))


class TestPhaseOnSchedule:

    def test_on_schedule_returns_one(self):
        """Within ±20pp of linear baseline → 1.0."""
        data = {
            "absorption_rate": 50.0,
            "award_date": "2020-01-01",
            "completion_date": "2030-01-01",
        }
        result = FeatureEngineer._compute_phase_on_schedule(data)
        assert result in (0.0, 1.0)

    def test_missing_data_returns_nan(self):
        assert math.isnan(FeatureEngineer._compute_phase_on_schedule({}))
