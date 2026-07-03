# Tasks: M4 MCP Enabler

**Input**: `specs/m4-mcp-enabler/` (spec.md, plan.md)
**Tests**: Test-First is NON-NEGOTIABLE — T001/T002 are committed and
confirmed failing before T003+.

## Phase 1: Tests (write first — confirm failing, commit RED)

- [X] T001 Unit tests `tests/unit/test_result_sidecar.py` — `format_report`
      writes `output/{stem}-result.json`; every documented mapping arm:
      category (error_category CODE/INFRA/CONFIG/SECURITY, specialist
      code_fixer/infra_sre, v1 analysis categories, unknown fallback),
      severity (HIGH_RISK/approval_required → high, else medium), summary
      precedence, fix_plan precedence, risk_level (SAFE/CAUTION/HIGH_RISK/
      absent), `code_diff == ""`, trace_id stem fallback; plus
      `write_failed_result` happy path and OSError best-effort path.
- [X] T002 Integration tests `tests/integration/test_mcp_enabler_api.py`
      (follow `test_api.py` patterns: `client` fixture, `_drain`) —
      X-Trace-Id valid/invalid/absent; GET `/api/v1/alerts/{id}` completed
      (fabricated sidecar) / processing / failed (worker-raising pipeline) /
      404; GET `/api/v1/incidents` happy path + ranking, limit default +
      clamp both ends, no-match empty list, title/resolution fallbacks,
      unparseable sidecar skipped.

## Phase 2: Implementation (after RED confirmed)

- [X] T003 Sidecar writer + mapping helpers in
      `autosentinel/nodes/format_report.py` (FR-001).
- [X] T004 `autosentinel/api/results.py`: `result_path` / `load_result` /
      `write_failed_result` / `search_incidents` (FR-002 helper, FR-004).
- [X] T005 Response models in `autosentinel/api/models.py`.
- [X] T006 Routes + X-Trace-Id in `autosentinel/api/main.py`
      (FR-003/FR-004/FR-005); worker failed-sidecar hook in
      `autosentinel/api/queue.py` (FR-002).
- [X] T007 Full suite green; touched modules at 100% branch coverage.

## Phase 3: Docs

- [X] T008 DEBT.md entry (code_diff gap); docs/PROJECT.md snapshot one-liner
      noting the `feat/m4-mcp-enabler` branch exists (not merged).
