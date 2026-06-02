"""Unit tests for the BenchmarkScenario / BenchmarkResult Pydantic schemas
(T048, data-model.md §9).

Covers the §9 invariants T048 calls out: frozen immutability, the
scenario_id regex, numeric fields ≥ 0, human_labeled_by non-empty, and
Decimal cost precision (no float coercion loss).
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from autosentinel.benchmark import BenchmarkResult, BenchmarkScenario


def _valid_scenario(**overrides) -> BenchmarkScenario:
    kwargs = dict(
        scenario_id="001_code_null_pointer",
        category="CODE",
        error_log_path=Path("data/benchmark/benchmark-code.json"),
        expected_classification="CODE",
        expected_resolution_action="Add null-check guard",
        ground_truth_notes="defensive null-check at access point",
        expected_security_verdict="SAFE",
        human_labeled_by="meizhuixu",
        labeled_at=date(2026, 5, 9),
    )
    kwargs.update(overrides)
    return BenchmarkScenario(**kwargs)


def _valid_result(**overrides) -> BenchmarkResult:
    kwargs = dict(
        scenario_id="001_code_null_pointer",
        actual_classification="CODE",
        actual_resolution="added null check",
        passed=True,
        latency_ms=1234,
        cost=Decimal("0.0001"),
        trace_id="0" * 32,
    )
    kwargs.update(overrides)
    return BenchmarkResult(**kwargs)


# --- BenchmarkScenario ---

class TestBenchmarkScenario:
    def test_valid_scenario_constructs(self):
        s = _valid_scenario()
        assert s.scenario_id == "001_code_null_pointer"
        assert s.category == "CODE"

    def test_frozen_is_immutable(self):
        s = _valid_scenario()
        with pytest.raises(ValidationError):
            s.scenario_id = "002_code_other"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "good_id",
        [
            "001_code_null_pointer",
            "047_security_sql_injection_in_orders",
            "015_code_a",
            "999_infra_x9y",
        ],
    )
    def test_scenario_id_regex_accepts_valid(self, good_id):
        assert _valid_scenario(scenario_id=good_id).scenario_id == good_id

    @pytest.mark.parametrize(
        "bad_id",
        [
            "1_code_x",                 # not 3 digits
            "0001_code_x",              # 4 digits
            "001_CODE_x",               # uppercase category segment
            "001_code_X",               # uppercase in slug
            "abc_code_null",            # leading non-digits
            "001code_null",             # missing separators
            "001_code",                 # missing slug segment
            "001_code_null-pointer",    # hyphen not allowed
        ],
    )
    def test_scenario_id_regex_rejects_invalid(self, bad_id):
        with pytest.raises(ValidationError):
            _valid_scenario(scenario_id=bad_id)

    @pytest.mark.parametrize("bad_category", ["code", "UNKNOWN", "", "Code"])
    def test_category_literal_rejects_invalid(self, bad_category):
        with pytest.raises(ValidationError):
            _valid_scenario(category=bad_category)

    def test_human_labeled_by_must_be_non_empty(self):
        with pytest.raises(ValidationError):
            _valid_scenario(human_labeled_by="")

    def test_labeled_at_is_a_date(self):
        s = _valid_scenario(labeled_at=date(2026, 5, 8))
        assert s.labeled_at == date(2026, 5, 8)

    @pytest.mark.parametrize("verdict", ["SAFE", "CAUTION", "HIGH_RISK"])
    def test_expected_security_verdict_accepts_valid(self, verdict):
        assert _valid_scenario(expected_security_verdict=verdict).expected_security_verdict == verdict

    @pytest.mark.parametrize("bad_verdict", ["safe", "RISKY", "", "high_risk", "UNKNOWN"])
    def test_expected_security_verdict_rejects_invalid(self, bad_verdict):
        with pytest.raises(ValidationError):
            _valid_scenario(expected_security_verdict=bad_verdict)

    def test_expected_security_verdict_is_required(self):
        kwargs = dict(
            scenario_id="001_code_null_pointer",
            category="CODE",
            error_log_path=Path("data/benchmark/benchmark-code.json"),
            expected_classification="CODE",
            expected_resolution_action="Add null-check guard",
            ground_truth_notes="defensive null-check at access point",
            human_labeled_by="meizhuixu",
            labeled_at=date(2026, 5, 9),
        )  # no expected_security_verdict
        with pytest.raises(ValidationError):
            BenchmarkScenario(**kwargs)


# --- BenchmarkResult ---

class TestBenchmarkResult:
    def test_valid_result_constructs(self):
        r = _valid_result()
        assert r.passed is True
        assert r.error is None  # default

    def test_frozen_is_immutable(self):
        r = _valid_result()
        with pytest.raises(ValidationError):
            r.passed = False  # type: ignore[misc]

    def test_latency_ms_rejects_negative(self):
        with pytest.raises(ValidationError):
            _valid_result(latency_ms=-1)

    def test_latency_ms_accepts_zero(self):
        assert _valid_result(latency_ms=0).latency_ms == 0

    def test_cost_rejects_negative(self):
        with pytest.raises(ValidationError):
            _valid_result(cost=Decimal("-0.01"))

    def test_cost_is_decimal_with_preserved_precision(self):
        r = _valid_result(cost=Decimal("0.000000123456"))
        assert isinstance(r.cost, Decimal)
        assert r.cost == Decimal("0.000000123456")

    def test_error_field_optional_and_settable_at_construction(self):
        r = _valid_result(error="pipeline raised before Verifier")
        assert r.error == "pipeline raised before Verifier"
