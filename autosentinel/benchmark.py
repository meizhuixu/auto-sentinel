"""Sprint 4 smoke benchmark — runs 5 scenarios through v1 and v2 pipelines."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from autosentinel import run_pipeline

SCENARIOS: list[dict] = [
    {
        "id": "s01",
        "category": "CODE",
        "log_file": "benchmark-code.json",
        "log_content": {
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "app-service",
            "error_type": "UnhandledError",
            "message": "unexpected None value in user context object",
            "stack_trace": None,
        },
        "expected_verdict": "SAFE",
    },
    {
        "id": "s02",
        "category": "INFRA",
        "log_file": "benchmark-infra.json",
        "log_content": {
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "payment-service",
            "error_type": "ConnectionTimeout",
            "message": "connection refused to database host db.internal:5432",
            "stack_trace": None,
        },
        "expected_verdict": "SAFE",
    },
    {
        "id": "s03",
        "category": "CONFIG",
        "log_file": "benchmark-config.json",
        "log_content": {
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "auth-service",
            "error_type": "ConfigurationError",
            "message": "required environment variable JWT_SECRET_KEY is not set",
            "stack_trace": None,
        },
        "expected_verdict": "SAFE",
    },
    {
        "id": "s04",
        "category": "SECURITY",
        "log_file": "benchmark-security.json",
        "log_content": {
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "data-service",
            "error_type": "SecurityException",
            "message": "sql injection attempt detected in query parameter",
            "stack_trace": None,
        },
        # SECURITY category routes to CodeFixerAgent whose _get_fix_for_security()
        # returns 'print("Applying security patch...")' — SAFE.
        # To exercise the HIGH_RISK path in CI, override _get_fix_for_security in tests.
        "expected_verdict": "SAFE",
    },
    {
        "id": "s05",
        "category": "UNKNOWN",
        "log_file": "benchmark-unknown.json",
        "log_content": {
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "misc-service",
            "error_type": "WeirdException",
            "message": "something unexpected happened during processing",
            "stack_trace": None,
        },
        "expected_verdict": "SAFE",
    },
]


def _write_scenario_logs(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for scenario in SCENARIOS:
        log_path = data_dir / scenario["log_file"]
        if not log_path.exists():
            log_path.write_text(json.dumps(scenario["log_content"]), encoding="utf-8")


def _run_scenario(log_path: Path, use_v2: bool) -> tuple[bool, float]:
    """Run a single scenario; return (resolved, duration_ms)."""
    env = os.environ.copy()
    if use_v2:
        env["AUTOSENTINEL_MULTI_AGENT"] = "1"
    else:
        env.pop("AUTOSENTINEL_MULTI_AGENT", None)

    original = os.environ.copy()
    try:
        if use_v2:
            os.environ["AUTOSENTINEL_MULTI_AGENT"] = "1"
        else:
            os.environ.pop("AUTOSENTINEL_MULTI_AGENT", None)

        start = time.monotonic()
        try:
            run_pipeline(log_path)
            resolved = True
        except Exception:
            resolved = False
        duration_ms = (time.monotonic() - start) * 1000
        return resolved, duration_ms
    finally:
        os.environ.clear()
        os.environ.update(original)


def run_benchmark() -> dict:
    """Run 5 smoke scenarios through v1 and v2 pipelines; write JSON report."""
    data_dir = Path("data/benchmark")
    _write_scenario_logs(data_dir)

    v1_results: list[tuple[bool, float]] = []
    v2_results: list[tuple[bool, float]] = []

    for scenario in SCENARIOS:
        log_path = data_dir / scenario["log_file"]
        v1_ok, v1_ms = _run_scenario(log_path, use_v2=False)
        v2_ok, v2_ms = _run_scenario(log_path, use_v2=True)
        v1_results.append((v1_ok, v1_ms))
        v2_results.append((v2_ok, v2_ms))

    v1_resolved = sum(1 for ok, _ in v1_results if ok)
    v2_resolved = sum(1 for ok, _ in v2_results if ok)
    v1_avg_ms = int(sum(ms for _, ms in v1_results) / len(v1_results))
    v2_avg_ms = int(sum(ms for _, ms in v2_results) / len(v2_results))

    report = {
        "scenario_count": len(SCENARIOS),
        "v1_resolution_rate": round(v1_resolved / len(SCENARIOS), 2),
        "v2_resolution_rate": round(v2_resolved / len(SCENARIOS), 2),
        "v1_avg_ms": v1_avg_ms,
        "v2_avg_ms": v2_avg_ms,
    }

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "benchmark-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result, indent=2))
