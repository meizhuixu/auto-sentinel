"""Unit tests for the M4 structured result sidecar (specs/m4-mcp-enabler).

Covers FR-001 (format_report writes output/{stem}-result.json with the
documented deterministic AgentState -> sidecar mapping) and FR-002's helper
(write_failed_result is best-effort and never raises).
"""

import json
from pathlib import Path

import pytest

from autosentinel.nodes.format_report import format_report


TRACE_ID = "ab" * 16  # valid ^[0-9a-f]{32}$


def _make_state(tmp_path, stem="crash-test", **overrides):
    """Minimal v1-shaped state accepted by format_report, dict-based."""
    log_path = tmp_path / f"{stem}.json"
    log_path.write_text("{}")
    state = {
        "log_path": str(log_path),
        "error_log": {
            "timestamp": "2026-07-03T10:00:00Z",
            "service_name": "payment-service",
            "error_type": "ConnectionTimeout",
            "message": "DB timed out",
            "stack_trace": None,
        },
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "fix_script": None,
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
    }
    state.update(overrides)
    return state


def _run_and_load(tmp_path, monkeypatch, state, stem):
    monkeypatch.chdir(tmp_path)
    format_report(state)
    sidecar = tmp_path / "output" / f"{stem}-result.json"
    assert sidecar.exists(), "format_report must write output/{stem}-result.json"
    return json.loads(sidecar.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# FR-001 — sidecar existence + top-level shape
# ---------------------------------------------------------------------------

def test_sidecar_written_with_completed_status_and_identity_fields(tmp_path, monkeypatch):
    state = _make_state(tmp_path, stem=TRACE_ID, trace_id=TRACE_ID)
    data = _run_and_load(tmp_path, monkeypatch, state, TRACE_ID)
    assert data["status"] == "completed"
    assert data["trace_id"] == TRACE_ID
    assert data["service_name"] == "payment-service"
    assert data["error_type"] == "ConnectionTimeout"
    assert data["report_path"].endswith(f"{TRACE_ID}-report.md")
    assert Path(data["report_path"]).exists()


def test_sidecar_trace_id_falls_back_to_log_stem(tmp_path, monkeypatch):
    # CLI v1-graph runs carry no trace_id in state; the stem is the honest id.
    state = _make_state(tmp_path, stem="crash-cli")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-cli")
    assert data["trace_id"] == "crash-cli"


# ---------------------------------------------------------------------------
# diagnosis.category mapping (spec.md table)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("error_category", "expected"),
    [("CODE", "runtime"), ("INFRA", "infra"), ("CONFIG", "config"),
     ("SECURITY", "unknown")],
)
def test_category_from_multi_agent_error_category(tmp_path, monkeypatch, error_category, expected):
    state = _make_state(tmp_path, error_category=error_category)
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["category"] == expected


@pytest.mark.parametrize(
    ("specialist", "expected"),
    [("code_fixer", "runtime"), ("infra_sre", "infra")],
)
def test_category_from_supervisor_specialist_route(tmp_path, monkeypatch, specialist, expected):
    state = _make_state(tmp_path, specialist=specialist)
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["category"] == expected


@pytest.mark.parametrize(
    ("v1_category", "expected"),
    [("connectivity", "infra"), ("resource_exhaustion", "infra"),
     ("configuration", "config"), ("application_logic", "runtime"),
     ("something-new", "unknown")],
)
def test_category_from_v1_analysis_result(tmp_path, monkeypatch, v1_category, expected):
    state = _make_state(
        tmp_path,
        analysis_result={
            "error_category": v1_category,
            "root_cause_hypothesis": "hypothesis",
            "confidence": 0.9,
            "remediation_steps": ["step 1"],
        },
    )
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["category"] == expected


def test_category_unknown_when_no_signal(tmp_path, monkeypatch):
    data = _run_and_load(tmp_path, monkeypatch, _make_state(tmp_path), "crash-test")
    assert data["diagnosis"]["category"] == "unknown"


def test_category_unrecognised_error_category_falls_through_to_unknown(tmp_path, monkeypatch):
    state = _make_state(tmp_path, error_category="BOGUS")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["category"] == "unknown"


# ---------------------------------------------------------------------------
# diagnosis.severity — documented deterministic fallback
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("overrides", "expected"),
    [({"security_verdict": "HIGH_RISK"}, "high"),
     ({"approval_required": True}, "high"),
     ({"security_verdict": "CAUTION"}, "medium"),
     ({"security_verdict": "SAFE"}, "medium"),
     ({}, "medium")],
)
def test_severity_mapping(tmp_path, monkeypatch, overrides, expected):
    state = _make_state(tmp_path, **overrides)
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["severity"] == expected


# ---------------------------------------------------------------------------
# diagnosis.summary precedence
# ---------------------------------------------------------------------------

def test_summary_prefers_v1_root_cause_hypothesis(tmp_path, monkeypatch):
    state = _make_state(
        tmp_path,
        analysis_result={
            "error_category": "connectivity",
            "root_cause_hypothesis": "Database host unreachable.",
            "confidence": 0.92,
            "remediation_steps": ["Check DNS"],
        },
        routing_decision="should not win",
    )
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["summary"] == "Database host unreachable."


def test_summary_falls_back_to_supervisor_rationale(tmp_path, monkeypatch):
    state = _make_state(tmp_path, routing_decision="Code-level KeyError; route to code_fixer.")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["diagnosis"]["summary"] == "Code-level KeyError; route to code_fixer."


def test_summary_composed_from_error_log_as_last_resort(tmp_path, monkeypatch):
    data = _run_and_load(tmp_path, monkeypatch, _make_state(tmp_path), "crash-test")
    assert data["diagnosis"]["summary"] == (
        "ConnectionTimeout in payment-service: DB timed out"
    )


# ---------------------------------------------------------------------------
# fix mapping
# ---------------------------------------------------------------------------

def test_fix_plan_prefers_v1_remediation_steps(tmp_path, monkeypatch):
    state = _make_state(
        tmp_path,
        analysis_result={
            "error_category": "connectivity",
            "root_cause_hypothesis": "h",
            "confidence": 0.9,
            "remediation_steps": ["Check DNS", "Verify firewall rules"],
        },
        fix_artifact="print('should not win')",
    )
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["fix"]["fix_plan"] == "Check DNS\nVerify firewall rules"


def test_fix_plan_falls_back_to_fix_artifact_then_fix_script(tmp_path, monkeypatch):
    state = _make_state(tmp_path, fix_artifact="data.get('key')")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["fix"]["fix_plan"] == "data.get('key')"

    state = _make_state(tmp_path, fix_script="echo fix")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["fix"]["fix_plan"] == "echo fix"


def test_fix_plan_empty_when_nothing_produced(tmp_path, monkeypatch):
    data = _run_and_load(tmp_path, monkeypatch, _make_state(tmp_path), "crash-test")
    assert data["fix"]["fix_plan"] == ""


@pytest.mark.parametrize(
    ("verdict", "expected"),
    [("SAFE", "low"), ("CAUTION", "medium"), ("HIGH_RISK", "high"),
     (None, "medium")],
)
def test_risk_level_from_security_verdict(tmp_path, monkeypatch, verdict, expected):
    state = _make_state(tmp_path, security_verdict=verdict)
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["fix"]["risk_level"] == expected


def test_code_diff_is_always_empty_string(tmp_path, monkeypatch):
    # Documented gap: the pipeline emits an executable fix script, never a
    # unified diff — the sidecar must not disguise the script as a diff.
    state = _make_state(tmp_path, fix_artifact="print('fix')")
    data = _run_and_load(tmp_path, monkeypatch, state, "crash-test")
    assert data["fix"]["code_diff"] == ""


# ---------------------------------------------------------------------------
# FR-002 helper — write_failed_result is best-effort
# ---------------------------------------------------------------------------

def test_write_failed_result_writes_failed_sidecar(tmp_path, monkeypatch):
    from autosentinel.api.results import write_failed_result

    monkeypatch.chdir(tmp_path)
    write_failed_result(
        TRACE_ID,
        trace_id=TRACE_ID,
        service_name="payment-service",
        error="pipeline exploded",
    )
    data = json.loads(
        (tmp_path / "output" / f"{TRACE_ID}-result.json").read_text(encoding="utf-8")
    )
    assert data["status"] == "failed"
    assert data["trace_id"] == TRACE_ID
    assert data["service_name"] == "payment-service"
    assert data["error"] == "pipeline exploded"
    assert data["diagnosis"] is None
    assert data["fix"] is None


def test_write_failed_result_uses_job_id_when_trace_id_empty(tmp_path, monkeypatch):
    from autosentinel.api.results import write_failed_result

    monkeypatch.chdir(tmp_path)
    write_failed_result("job-1", trace_id="", service_name="svc", error="boom")
    data = json.loads(
        (tmp_path / "output" / "job-1-result.json").read_text(encoding="utf-8")
    )
    assert data["trace_id"] == "job-1"


def test_write_failed_result_swallows_os_errors(tmp_path, monkeypatch):
    from autosentinel.api.results import write_failed_result

    monkeypatch.chdir(tmp_path)

    def _boom(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _boom)
    # Must not raise — the worker's failure path may never crash the worker.
    write_failed_result("job-2", trace_id="", service_name="svc", error="boom")
    assert not (tmp_path / "output" / "job-2-result.json").exists()
