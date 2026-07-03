# Implementation Plan: M4 MCP Enabler

**Branch**: `feat/m4-mcp-enabler` | **Spec**: `specs/m4-mcp-enabler/spec.md`

## Tech context

- Python 3.11, FastAPI, Pydantic v2 — all already in `pyproject.toml`.
  **No new dependencies.**
- Storage is the existing filesystem convention (CWD-relative, matching the
  gateway): `data/incoming/{job_id}.json` (payload) and
  `output/{stem}-report.md` (report). This feature adds
  `output/{stem}-result.json` (structured sidecar).
- Test-First is non-negotiable: failing tests are committed before the
  implementation commits.

## Touched files

| File | Change |
|---|---|
| `autosentinel/nodes/format_report.py` | After writing the markdown report, also write the `output/{stem}-result.json` sidecar via pure helper functions (`_derive_category` / `_derive_severity` / `_derive_summary` / `_derive_fix`). Node return value unchanged (LangGraph state schema untouched). |
| `autosentinel/api/results.py` (new) | Sidecar/search helpers: `result_path(job_id)`, `load_result(job_id)`, `write_failed_result(...)` (best-effort, logs on OSError), `search_incidents(q, limit)` with the scoring below. Keeps `main.py` wiring-thin and the logic unit-testable. |
| `autosentinel/api/models.py` | `DiagnosisResult`, `FixResult`, `AlertStatusResponse`, `IncidentSummary`, `IncidentSearchResponse`. Fields are `str` (not `Literal`) on the read path — the models render what is on disk; the writer enforces the vocabulary. |
| `autosentinel/api/main.py` | `GET /api/v1/alerts/{job_id}`, `GET /api/v1/incidents`, optional `X-Trace-Id` header on `POST /api/v1/alerts` (regex `^[0-9a-f]{32}$`, 400 on mismatch, used as job_id AND trace_id when valid). |
| `autosentinel/api/queue.py` | In the worker's existing `except` branch, call `write_failed_result(...)` so a crashed pipeline yields `status="failed"` instead of a forever-"processing" job. |

## Incident search scoring (FR-004)

- Corpus: every `output/*-result.json`; for each, the sibling
  `data/incoming/{stem}.json` payload (if present) contributes its `message`
  and `stack_trace` to the haystack.
- Fields searched: `error_type`, `service_name`, `diagnosis.summary`,
  `fix.fix_plan`, payload `message`, payload `stack_trace`.
- Terms: `q.lower().split()`. Score = number of (term, field) hits, i.e.
  `sum(1 for term in terms for field in fields if term in field.lower())`.
- Score 0 → excluded. Sort by `(-score, id)`. `limit` clamped to 1..50,
  default 5. Unparseable sidecar files are skipped (defensive).
- `title` = `"{error_type} in {service_name}"` when both are non-empty, else
  the first 80 chars of the summary, else the id.
  `resolution` = `fix.fix_plan` or `diagnosis.summary` or `""`.

## Status route resolution (FR-003)

```
output/{job_id}-result.json exists
    → 200 {status: <file.status>, diagnosis/fix/report_path from file}
elif data/incoming/{job_id}.json exists
    → 200 {status: "processing", diagnosis: null, fix: null, report_path: null}
else
    → 404
```

`trace_id` in the response = sidecar's `trace_id` if available, else `job_id`
(they are equal by the Sprint-5 invariant).

## Constitution check

- No provider model named; no LLM calls added (mapping is deterministic).
- Observability: new failure path logs through the existing structured
  `event_gateway` logger.
- Test-First: see tasks.md ordering; failing tests commit precedes
  implementation commits.
