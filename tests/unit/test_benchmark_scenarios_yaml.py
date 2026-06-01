"""T049: the 5 migrated Sprint-4 scenarios as yaml files under
benchmarks/scenarios/ must each parse cleanly into a BenchmarkScenario
(T048 schema), match the contracts/benchmark-scenario.md Migration map, and
contain no non-ASCII characters (code + data files are English-only).
"""

from datetime import date
from pathlib import Path

import pytest
import yaml

from autosentinel.benchmark import BenchmarkScenario

_SCENARIOS_DIR = Path("benchmarks/scenarios")

# scenario_id → (expected category, expected error_log_path) per the
# contracts/benchmark-scenario.md Migration map. s05 is reclassified
# UNKNOWN → CODE; its fixture keeps the historical "unknown" filename.
_MIGRATION_MAP = {
    "001_code_null_user_context": ("CODE", "data/benchmark/benchmark-code.json"),
    "002_infra_db_connection_refused": ("INFRA", "data/benchmark/benchmark-infra.json"),
    "003_config_jwt_secret_missing": ("CONFIG", "data/benchmark/benchmark-config.json"),
    "004_security_sql_injection_attempt": ("SECURITY", "data/benchmark/benchmark-security.json"),
    "005_code_weird_exception": ("CODE", "data/benchmark/benchmark-unknown.json"),
}


@pytest.mark.parametrize("scenario_id", sorted(_MIGRATION_MAP))
def test_migrated_yaml_parses_and_matches_map(scenario_id):
    expected_category, expected_log_path = _MIGRATION_MAP[scenario_id]
    yaml_path = _SCENARIOS_DIR / f"{scenario_id}.yaml"
    assert yaml_path.exists(), f"missing scenario yaml: {yaml_path}"

    raw = yaml_path.read_text(encoding="utf-8")
    assert raw.isascii(), f"{yaml_path} contains non-ASCII characters"

    data = yaml.safe_load(raw)
    scenario = BenchmarkScenario.model_validate(data)

    assert scenario.scenario_id == scenario_id
    assert scenario.category == expected_category
    assert scenario.error_log_path == Path(expected_log_path)
    assert scenario.error_log_path.exists(), (
        f"referenced fixture does not exist: {scenario.error_log_path}"
    )
    assert scenario.human_labeled_by == "meizhuixu"
    assert scenario.labeled_at == date(2026, 5, 9)
    # Ground-truth labelling fields must be present and non-empty (FR-517).
    assert scenario.expected_classification
    assert scenario.expected_resolution_action
    assert scenario.ground_truth_notes


def test_exactly_five_migrated_scenarios_present():
    found = sorted(p.stem for p in _SCENARIOS_DIR.glob("0*.yaml"))
    assert found == sorted(_MIGRATION_MAP)
