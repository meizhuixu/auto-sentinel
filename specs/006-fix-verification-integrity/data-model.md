# Data Model — Fix Verification Integrity & Pipeline Consolidation

**Feature**: `006-fix-verification-integrity` | **Date**: 2026-07-03

## 1. NormalizedArtifact (new, in `autosentinel/agents/_artifact_normalizer.py`)

Result of the Verifier-side deterministic normalization
(`normalize_fix_artifact(artifact: str) -> NormalizedArtifact`, pure function).

| Field | Type | Notes |
|-------|------|-------|
| `code` | `str` | The script the sandbox will execute. Equal to input when `outcome == "verbatim"`; wrapped form when `"wrapped"`; empty when `"rejected"`. |
| `outcome` | `Literal["verbatim", "wrapped", "rejected"]` | See transitions below. |
| `reason` | `str \| None` | Populated iff `rejected` (e.g. the `SyntaxError` text, or `"empty artifact"`). |

State transitions (exhaustive):

```text
input artifact
├─ empty / whitespace-only ────────────────────────────→ rejected("empty artifact")
├─ compile() OK ───────────────────────────────────────→ verbatim
└─ compile() SyntaxError
   ├─ fragment symptom ('return' outside function,
   │   'yield' outside function)
   │   └─ wrap: indent body under def __autosentinel_fix__():
   │            + trailing call; re-compile()
   │      ├─ OK ───────────────────────────────────────→ wrapped
   │      └─ still SyntaxError ────────────────────────→ rejected(error text)
   └─ any other SyntaxError ───────────────────────────→ rejected(error text)
```

Invariants:
- `rejected` never launches a container; VerifierAgent returns an honest
  `ExecutionResult(status="failure", stderr=reason, return_code=None)`.
- `outcome` is written into `agent_trace` context / trace metadata so a
  `wrapped` run is distinguishable from a contract-compliant `verbatim` run
  in post-incident review (Constitution V(c) auditability spirit).
- Wrapping preserves statement semantics: a bare top-level `return` becomes a
  function return; the artifact reviewed by SecurityReviewer is the *input*
  artifact — normalization happens strictly after the SAFE verdict and adds
  no new statements beyond the wrapper `def` + call.

## 2. ExecutionResult (existing, `autosentinel/models.py` — unchanged shape)

No schema change. Semantics sharpened:

| Status | Produced when |
|--------|---------------|
| `success` | sandbox `return_code == 0` |
| `failure` | non-zero exit **or** `rejected` normalization (no container run) |
| `timeout` | container wait exceeded 5s (unchanged) |
| `skipped` | `fix_artifact is None` (unchanged) |

## 3. Benchmark scoring (existing `BenchmarkResult`, redefined `passed`)

`BenchmarkResult` (`autosentinel/benchmark.py`) keeps its schema. The
assignment in `scripts/run_benchmark.py` changes:

```text
OLD  passed := report_text is not None and execution_error is None
NEW  passed := report_text is not None
               and execution_error is None
               and execution_result is not None
               and execution_result.status == "success"
```

Consequences: `skipped`, `failure`, `timeout`, docker-level errors, and
rejected artifacts all count **unresolved**. There is exactly one
`resolution_rate`; pipeline-completion is not reported under that name.

## 4. Benchmark summary schema (v1 arm removed)

`summary.json` drops the `v1` block and the v1/v2 nesting:

```json
{
  "run_id": "YYYYMMDD-HHMMSS-<git_short_sha>",
  "scenario_count": 50,
  "category_distribution": {"CODE": n, "INFRA": n, "SECURITY": n, "CONFIG": n},
  "pipeline": {
    "latency_ms": {"p50": 0, "p95": 0},
    "total_cost": "0.00",
    "cost_currency": "CNY",
    "resolution_rate": 0.0,
    "resolved_definition": "report_text present AND no execution_error AND execution_result.status == 'success'"
  },
  "security_subset": {
    "count": 0,
    "false_negative_count": 0,
    "false_negative_scenario_ids": []
  }
}
```

(`resolved_definition` embedded so a summary file is self-describing —
supports FR-005's "definition published with the number".)

## 5. CI quality gate (declarative, `.github/workflows/ci.yml`)

| Job | Command | Hard dependency |
|-----|---------|-----------------|
| lint | `uv run ruff check .` | dev extra installed |
| typecheck | `uv run mypy autosentinel` | dev extra installed |
| test | `uv run pytest` | postgres:16 service on 5434 (healthy) + `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1` + Docker daemon |

Escalation contract: with `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1`, an
unreachable checkpointer DB turns `requires_checkpointer` skips into failures
(`tests/integration/_pr4_helpers.py`).

## 6. Constitution version

`2.2.0 → 2.3.0` (MINOR): Principle I grandfathering clause removed, Principle
VII.1 grandfathering clause removed, `TODO(SPRINT6_V1_RETIREMENT)` closed.
`LAST_AMENDED_DATE` = merge date of PR-2.
