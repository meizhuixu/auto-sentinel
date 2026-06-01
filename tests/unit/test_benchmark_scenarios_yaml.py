"""Scenario-yaml gates (T049 migrated + T051/T052 new CODE scenarios).

Every scenario yaml under benchmarks/scenarios/ must parse into a
BenchmarkScenario (T048 schema), reference an on-disk fixture, and be
ASCII-only (code + data files are English-only). New CODE scenarios
006-015 (T051: 006-010, T052: 011-015) additionally each carry their own
fixture JSON under benchmarks/scenarios/fixtures/.
"""

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from autosentinel.benchmark import BenchmarkScenario, _load_scenarios

_SCENARIOS_DIR = Path("benchmarks/scenarios")
_FIXTURES_DIR = _SCENARIOS_DIR / "fixtures"

# scenario_id -> (expected category, expected error_log_path) per the
# contracts/benchmark-scenario.md Migration map. s05 is reclassified
# UNKNOWN -> CODE; its fixture keeps the historical "unknown" filename.
_MIGRATION_MAP = {
    "001_code_null_user_context": ("CODE", "data/benchmark/benchmark-code.json"),
    "002_infra_db_connection_refused": ("INFRA", "data/benchmark/benchmark-infra.json"),
    "003_config_jwt_secret_missing": ("CONFIG", "data/benchmark/benchmark-config.json"),
    "004_security_sql_injection_attempt": ("SECURITY", "data/benchmark/benchmark-security.json"),
    "005_code_weird_exception": ("CODE", "data/benchmark/benchmark-unknown.json"),
}

# New CODE scenarios authored in T051 (006-010) + T052 (011-015). Each
# references its own fixture at benchmarks/scenarios/fixtures/<id>.json.
_NEW_CODE_IDS = [
    "006_code_index_out_of_range",
    "007_code_division_by_zero",
    "008_code_key_error_dict",
    "009_code_type_mismatch",
    "010_code_attribute_error",
    "011_code_unhandled_exception",
    "012_code_infinite_recursion",
    "013_code_off_by_one_loop",
    "014_code_json_parse_error",
    "015_code_unicode_decode_error",
]


def _load_yaml(scenario_id: str) -> tuple[str, BenchmarkScenario]:
    yaml_path = _SCENARIOS_DIR / f"{scenario_id}.yaml"
    assert yaml_path.exists(), f"missing scenario yaml: {yaml_path}"
    raw = yaml_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{yaml_path} contains non-ASCII characters"
    return raw, BenchmarkScenario.model_validate(yaml.safe_load(raw))


# --- T049 migrated scenarios ---

@pytest.mark.parametrize("scenario_id", sorted(_MIGRATION_MAP))
def test_migrated_yaml_parses_and_matches_map(scenario_id):
    expected_category, expected_log_path = _MIGRATION_MAP[scenario_id]
    _, scenario = _load_yaml(scenario_id)
    assert scenario.scenario_id == scenario_id
    assert scenario.category == expected_category
    assert scenario.error_log_path == Path(expected_log_path)
    assert scenario.error_log_path.exists()
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)
    assert scenario.expected_classification
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes


def test_migrated_five_present():
    loaded = {s.scenario_id for s in _load_scenarios()}
    assert set(_MIGRATION_MAP).issubset(loaded)


# --- T051/T052 new CODE scenarios (006-015) ---

@pytest.mark.parametrize("scenario_id", _NEW_CODE_IDS)
def test_new_code_yaml_parses_and_is_code(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    assert scenario.scenario_id == scenario_id
    assert scenario.category == "CODE"
    assert scenario.expected_classification == "CODE"
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)


@pytest.mark.parametrize("scenario_id", _NEW_CODE_IDS)
def test_new_code_fixture_exists_and_is_valid_ascii_json(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    expected = _FIXTURES_DIR / f"{scenario_id}.json"
    assert scenario.error_log_path == expected
    assert scenario.error_log_path.exists(), f"missing fixture: {expected}"
    raw = scenario.error_log_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{expected} contains non-ASCII characters"
    data = json.loads(raw)  # must be valid JSON
    assert isinstance(data, dict)


def test_code_total_is_twelve():
    """2 migrated (001, 005) + 10 new (006-015) = 12 CODE scenarios."""
    code = [s for s in _load_scenarios() if s.category == "CODE"]
    assert len(code) == 12
