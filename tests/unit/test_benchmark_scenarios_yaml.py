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

# New INFRA scenarios authored in T053 (016-020) + T054 (021-025) +
# T055 (026-029). Each references its own fixture under fixtures/.
_NEW_INFRA_IDS = [
    "016_infra_db_connection_pool_exhausted",
    "017_infra_dns_resolution_failure",
    "018_infra_disk_space_full",
    "019_infra_memory_oom_killed",
    "020_infra_service_unavailable_503",
    "021_infra_tls_certificate_expired",
    "022_infra_load_balancer_timeout",
    "023_infra_port_already_in_use",
    "024_infra_network_partition",
    "025_infra_rate_limit_exceeded",
    "026_infra_container_restart_loop",
    "027_infra_volume_mount_failure",
    "028_infra_clock_skew",
    "029_infra_file_descriptor_limit",
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


# --- T053/T054/T055 new INFRA scenarios (016-029) ---

@pytest.mark.parametrize("scenario_id", _NEW_INFRA_IDS)
def test_new_infra_yaml_parses_and_is_infra(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    assert scenario.scenario_id == scenario_id
    assert scenario.category == "INFRA"
    assert scenario.expected_classification == "INFRA"
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)


@pytest.mark.parametrize("scenario_id", _NEW_INFRA_IDS)
def test_new_infra_fixture_exists_and_is_valid_ascii_json(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    expected = _FIXTURES_DIR / f"{scenario_id}.json"
    assert scenario.error_log_path == expected
    assert scenario.error_log_path.exists(), f"missing fixture: {expected}"
    raw = scenario.error_log_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{expected} contains non-ASCII characters"
    data = json.loads(raw)  # must be valid JSON
    assert isinstance(data, dict)


def test_infra_total_is_fifteen():
    """1 migrated (002) + 14 new (016-029) = 15 INFRA scenarios."""
    infra = [s for s in _load_scenarios() if s.category == "INFRA"]
    assert len(infra) == 15
