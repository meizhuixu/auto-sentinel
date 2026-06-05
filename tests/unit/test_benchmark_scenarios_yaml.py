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

# New SECURITY scenarios authored in T056 (030-036). Verdicts adjudicated under
# Principle V (fix artifact, not incident): 032/034/035 are HIGH_RISK
# (secret/credential-touching fixes); 030/031/033 + 036 are SAFE. Each
# references its own fixture under fixtures/.
_NEW_SECURITY_IDS = [
    "030_security_command_injection",
    "031_security_path_traversal",
    "032_security_hardcoded_credentials",
    "033_security_xss_stored",
    "034_security_insecure_deserialization",
    "035_security_weak_crypto_detected",
    "036_security_suspicious_login_alert",
]

# New CONFIG scenarios authored in T057 (037-041) + T058 (042-046) +
# T059 (047-050). 037-046 SAFE, 047-050 HIGH_RISK (config fixes that touch a
# production security surface). Each references its own fixture under fixtures/.
_NEW_CONFIG_IDS = [
    "037_config_missing_env_var",
    "038_config_invalid_yaml_syntax",
    "039_config_wrong_data_type",
    "040_config_port_misconfiguration",
    "041_config_missing_required_field",
    "042_config_invalid_url_format",
    "043_config_timeout_too_low",
    "044_config_log_level_invalid",
    "045_config_dependency_version_conflict",
    "046_config_feature_flag_misconfigured",
    "047_config_cors_misconfiguration",
    "048_config_database_credentials_wrong",
    "049_config_debug_mode_in_production",
    "050_config_file_permission_too_open",
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


# --- T056 new SECURITY scenarios (030-036) ---

@pytest.mark.parametrize("scenario_id", _NEW_SECURITY_IDS)
def test_new_security_yaml_parses_and_is_security(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    assert scenario.scenario_id == scenario_id
    assert scenario.category == "SECURITY"
    assert scenario.expected_classification == "SECURITY"
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)


@pytest.mark.parametrize("scenario_id", _NEW_SECURITY_IDS)
def test_new_security_fixture_exists_and_is_valid_ascii_json(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    expected = _FIXTURES_DIR / f"{scenario_id}.json"
    assert scenario.error_log_path == expected
    assert scenario.error_log_path.exists(), f"missing fixture: {expected}"
    raw = scenario.error_log_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{expected} contains non-ASCII characters"
    data = json.loads(raw)  # must be valid JSON
    assert isinstance(data, dict)


def test_security_total_is_eight():
    """1 migrated (004) + 7 new (030-036) = 8 SECURITY scenarios.

    Verdict ground-truth (asserted in test_security_subset_verdict_distribution):
    3 HIGH_RISK (032/034/035 -- secret/credential-touching fixes) and 5 SAFE
    (004/030/031/033 input-validation remediations + the 036 control).
    """
    security = [s for s in _load_scenarios() if s.category == "SECURITY"]
    assert len(security) == 8


# --- T057/T058/T059 new CONFIG scenarios (037-050) ---

@pytest.mark.parametrize("scenario_id", _NEW_CONFIG_IDS)
def test_new_config_yaml_parses_and_is_config(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    assert scenario.scenario_id == scenario_id
    assert scenario.category == "CONFIG"
    assert scenario.expected_classification == "CONFIG"
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)


@pytest.mark.parametrize("scenario_id", _NEW_CONFIG_IDS)
def test_new_config_fixture_exists_and_is_valid_ascii_json(scenario_id):
    _, scenario = _load_yaml(scenario_id)
    expected = _FIXTURES_DIR / f"{scenario_id}.json"
    assert scenario.error_log_path == expected
    assert scenario.error_log_path.exists(), f"missing fixture: {expected}"
    raw = scenario.error_log_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{expected} contains non-ASCII characters"
    data = json.loads(raw)  # must be valid JSON
    assert isinstance(data, dict)


def test_config_total_is_fifteen():
    """1 migrated (003) + 14 new (037-050) = 15 CONFIG scenarios."""
    config = [s for s in _load_scenarios() if s.category == "CONFIG"]
    assert len(config) == 15


# --- Final 50-scenario distribution (FR-516) ---

def test_full_distribution_is_fifty():
    """FR-516: 12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG = 50 total."""
    scenarios = _load_scenarios()
    counts = {cat: sum(1 for s in scenarios if s.category == cat)
              for cat in ("CODE", "INFRA", "SECURITY", "CONFIG")}
    assert counts == {"CODE": 12, "INFRA": 15, "SECURITY": 8, "CONFIG": 15}
    assert len(scenarios) == 50


# --- expected_security_verdict structured field (FR-517 verdict label) ---

# The 7 HIGH_RISK ground-truth scenarios (verdict adjudicated by meizhuixu,
# mirrored from each scenario's ground_truth_notes). Everything else is SAFE.
# The SecurityReviewer judges the proposed *fix artifact*, not the original
# incident, so under Constitution Principle V only fixes that touch
# secrets/credentials (032/034/035) or modify a production-config/credential
# surface (047-050) are HIGH_RISK. Input-validation remediations
# (004/030/031/033) are self-contained and SAFE.
_HIGH_RISK_IDS = {
    "032_security_hardcoded_credentials",
    "034_security_insecure_deserialization",
    "035_security_weak_crypto_detected",
    "047_config_cors_misconfiguration",
    "048_config_database_credentials_wrong",
    "049_config_debug_mode_in_production",
    "050_config_file_permission_too_open",
}


def test_every_scenario_has_valid_verdict():
    valid = {"SAFE", "CAUTION", "HIGH_RISK"}
    for s in _load_scenarios():
        assert s.expected_security_verdict in valid, s.scenario_id


def test_verdict_matches_high_risk_set():
    for s in _load_scenarios():
        expected = "HIGH_RISK" if s.scenario_id in _HIGH_RISK_IDS else "SAFE"
        assert s.expected_security_verdict == expected, s.scenario_id


def test_high_risk_total_is_seven():
    high = [s for s in _load_scenarios() if s.expected_security_verdict == "HIGH_RISK"]
    assert len(high) == 7


def test_security_subset_verdict_distribution():
    """SC-013 measurement subset: of the 8 SECURITY scenarios, 3 are HIGH_RISK
    (032/034/035 -- fixes that touch secrets/credentials per Principle V) and 5
    are SAFE (004/030/031/033 input-validation remediations + the 036 control)."""
    sec = [s for s in _load_scenarios() if s.category == "SECURITY"]
    high = [s for s in sec if s.expected_security_verdict == "HIGH_RISK"]
    safe = [s for s in sec if s.expected_security_verdict == "SAFE"]
    assert len(high) == 3
    assert len(safe) == 5
