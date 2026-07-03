# Feature Specification: M4 MCP Enabler — Read API + Trace Propagation

**Feature Branch**: `feat/m4-mcp-enabler`
**Created**: 2026-07-03
**Status**: Draft
**Input**: Enable `devcontext-mcp` (project #3, MCP server) Phase 2 to call
AutoSentinel over HTTP. Purely additive API surface — no graph/agent changes.

## Why

The MCP server exposes `analyze_error_log`, `search_past_incidents`, and
`propose_fix` tools. Today AutoSentinel only offers a fire-and-forget
`POST /api/v1/alerts` (202 + job_id) with results landing on disk as markdown.
An MCP client needs: (a) a machine-readable result it can poll, (b) keyword
search over past incidents, (c) the ability to supply its own trace id so a
single trace spans MCP tool call → gateway → pipeline.

## User Scenarios & Testing

### User Story 1 - Poll a submitted alert for its structured result (P1)

An MCP tool submits a crash log, receives `job_id`, and polls
`GET /api/v1/alerts/{job_id}` until it gets a structured diagnosis + fix.

**Acceptance Scenarios**:
1. **Given** the pipeline completed for `job_id`, **When** the client GETs
   `/api/v1/alerts/{job_id}`, **Then** it receives 200 with
   `status="completed"`, a `diagnosis` object, a `fix` object, and
   `report_path`.
2. **Given** the alert is accepted but not yet processed, **When** the client
   GETs the same URL, **Then** it receives 200 with `status="processing"` and
   `diagnosis`/`fix`/`report_path` = null.
3. **Given** the pipeline raised for `job_id`, **Then** the client receives
   200 with `status="failed"` (diagnosis/fix null).
4. **Given** an unknown `job_id`, **Then** 404.

### User Story 2 - Search past incidents by keyword (P2)

An MCP tool queries `GET /api/v1/incidents?q=<query>&limit=<n>` and receives
`{incidents: [{id, title, resolution}]}` ranked by keyword relevance.

**Acceptance Scenarios**:
1. Query terms matching a stored incident's `error_type` / `service_name` /
   diagnosis summary / fix plan / raw payload message return that incident,
   best match first.
2. `limit` defaults to 5 and is clamped to 1..50 (no 422 for out-of-range).
3. No matches → `{"incidents": []}` (200, not 404).

### User Story 3 - Propagate a caller-supplied trace id (P3)

The MCP server generates a 32-hex trace id and supplies it via the
`X-Trace-Id` request header on `POST /api/v1/alerts`; the gateway uses it as
BOTH `job_id` and `trace_id` (preserving the Sprint-5 `job_id == trace_id`
invariant) so the Langfuse trace is continuous across services.

**Decision**: custom `X-Trace-Id` header, NOT W3C `traceparent`. The upstream
contract is a bare 32-hex OTel-compatible trace id with no span-context
(version/span-id/flags) semantics — a traceparent would carry fields we would
have to fabricate and ignore.

**Acceptance Scenarios**:
1. Valid header (`^[0-9a-f]{32}$`) → 202, response `job_id == trace_id ==`
   header value.
2. Invalid header (wrong length / uppercase / non-hex) → 400 with a clear
   message.
3. Header absent → current behavior unchanged (`secrets.token_hex(16)`).

**Collision behavior (documented, accepted)**: resubmitting the same
`X-Trace-Id` overwrites `data/incoming/{id}.json` and, on completion,
`output/{id}-result.json` — last write wins. Callers own id uniqueness.

## Functional Requirements

- **FR-001 (result sidecar)**: whenever `format_report` writes
  `output/{stem}-report.md`, it also writes `output/{stem}-result.json`:

  ```json
  {
    "trace_id": "<32hex>",
    "status": "completed",
    "diagnosis": {"category": "...", "severity": "...", "summary": "..."},
    "fix": {"fix_plan": "...", "risk_level": "...", "code_diff": ""},
    "service_name": "...",
    "error_type": "...",
    "report_path": "<abs path>"
  }
  ```

- **FR-002 (failed sidecar)**: when the queue worker's pipeline call raises,
  it writes `output/{job_id}-result.json` with `status="failed"` and an
  `error` string (no diagnosis/fix). Best-effort: a sidecar write failure is
  logged, never crashes the worker.

- **FR-003 (status route)**: `GET /api/v1/alerts/{job_id}` →
  `{job_id, trace_id, status, diagnosis|null, fix|null, report_path|null}`.
  Resolution order: `output/{job_id}-result.json` exists → return its content
  (status from file: completed/failed); else `data/incoming/{job_id}.json`
  exists → `status="processing"`; else 404.

- **FR-004 (incident search route)**: `GET /api/v1/incidents?q=&limit=` →
  `{incidents: [{id: <trace_id>, title, resolution}]}`. Case-insensitive
  term scoring (see plan.md); score 0 excluded; ties broken by id for
  determinism. No new dependencies.

- **FR-005 (X-Trace-Id)**: per User Story 3.

## Honest field-mapping (AgentState → sidecar)

The pipeline state does not natively produce the MCP-shaped fields; mapping is
deterministic and documented here — **no new LLM calls**:

| Sidecar field | Source | Notes |
|---|---|---|
| `trace_id` | `state["trace_id"]`, else the log-file stem | For API runs stem == job_id == trace_id; CLI v1-graph runs have no trace_id, stem is honest. |
| `diagnosis.category` | 1) multi-agent `error_category` (DiagnosisAgent): CODE→`runtime`, INFRA→`infra`, CONFIG→`config`, SECURITY→`unknown` (no MCP slot for security; do not disguise it as runtime). 2) else supervisor route `specialist`: code_fixer→`runtime`, infra_sre→`infra`. 3) else v1 `analysis_result.error_category`: connectivity→`infra`, resource_exhaustion→`infra`, configuration→`config`, application_logic→`runtime`. 4) else `unknown`. | |
| `diagnosis.severity` | `security_verdict`==HIGH_RISK or `approval_required` → `high`; otherwise **documented deterministic fallback `medium`** — no agent grades incident severity today. | Fallback, not signal. |
| `diagnosis.summary` | v1 `analysis_result.root_cause_hypothesis`; else supervisor `routing_decision` rationale; else `"{error_type} in {service_name}: {message}"`. | |
| `fix.fix_plan` | v1 `analysis_result.remediation_steps` joined; else `fix_artifact` (specialist output); else `fix_script`; else `""`. | |
| `fix.risk_level` | `security_verdict`: SAFE→`low`, CAUTION→`medium`, HIGH_RISK→`high`; absent (v1 graph has no security review) → fallback `medium`. | |
| `fix.code_diff` | Always `""`. The pipeline emits an **executable fix script** (`fix_artifact`/`fix_script`), not a unified diff; emitting the script as a fake diff would be dishonest. | Documented gap; see DEBT.md. |
| `service_name`/`error_type` | `state["error_log"]` | Parsed from the submitted payload. |

## Out of scope

- Auth, pagination, real severity grading, unified-diff generation,
  deleting/compacting `data/incoming` after completion, graph/agent changes.

## Success Criteria

- All new routes covered by integration tests following
  `tests/integration/test_api.py` patterns; sidecar mapping covered by unit
  tests; whole existing suite stays green; touched modules stay at 100%
  branch coverage (repo norm — note the repo-wide `--cov` gate already sits
  at 96.28% on main due to skip-guarded postgres/tracing paths).
