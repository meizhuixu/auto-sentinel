# Research — Fix Verification Integrity & Pipeline Consolidation

**Feature**: `006-fix-verification-integrity` | **Date**: 2026-07-03

All Technical Context unknowns resolved below. Code facts were verified against
the working tree at branch creation (main `55ce956`).

## Decision 1 — Fix-artifact contract direction: complete script + deterministic Verifier fallback

**Decision**: The contract is "`fix_artifact` is a complete, standalone-runnable
Python script". Enforced belt-and-braces (developer-approved 2026-07-03):

- **Producer side (best-effort layer)**: `CodeFixerAgent` / `InfraSREAgent`
  prompts (`autosentinel/agents/prompts/code_fixer.py`, `infra_sre.py`) are
  rewritten to demand a standalone script (no bare `return`, no undefined
  surrounding scope). After `strip_markdown_fence()`, the agent validates the
  artifact with `compile(artifact, "<fix>", "exec")`; on `SyntaxError` it
  retries the LLM call once with the error appended to the prompt, then falls
  through to the Verifier fallback (never crashes the pipeline).
- **Verifier side (deterministic guarantee layer)**: before container launch,
  a pure function `normalize_fix_artifact(artifact) -> NormalizedArtifact`
  runs `compile()` on the host: pass → execute as-is; `SyntaxError` matching
  fragment symptoms (`'return' outside function`, `'yield' outside function`)
  → wrap the body in a function (indent + `def __autosentinel_fix__():` +
  trailing call) and re-`compile()`; still failing or empty/whitespace-only →
  honest `failure` ExecutionResult without launching a container. The
  normalization outcome (`verbatim` / `wrapped` / `rejected`) is recorded so
  reports and traces can distinguish contract-compliant fixes from rescued
  fragments.

**Rationale**: LLM output has no hard guarantee, so a prompt-only fix cannot
pin SC-001 (format-induced failures = 0); a Verifier-only fix leaves the
human-facing artifact a fragment and guesses semantics. Two independent layers
mirror the proven Sprint 5 SECURITY pattern (LLM primary + deterministic
override pinned SC-013). Producer validation is testable with `MockLLMClient`
at zero spend; normalization is a pure function with exhaustive unit tests.

**Alternatives considered**: producer-only (rejected: LLM long tail re-opens
the false-failure class); Verifier-only (rejected: artifact stays unreadable
as a fragment; wrapping semantics are a guess rather than a fallback).

## Decision 2 — Sandbox execution format: write-to-file + read-only mount, replacing `python -c`

**Decision**: `VerifierAgent` writes the (normalized) artifact to a host temp
dir as `fix.py` and runs `["python", "/workspace/fix.py"]` with the temp dir
mounted read-only at `/workspace`. All existing sandbox parameters are
unchanged: `python:3.10-alpine`, `mem_limit=64m`, `network_mode=none`, detach +
`wait(timeout=5s)`, kill-on-timeout, force-remove in `finally`.

**Rationale**: removes the shell-arg transport (`python -c`, fragile for
quoting/size), gives real `__main__` semantics and line numbers in tracebacks
(better stderr in reports), and keeps the artifact on disk for post-incident
audit. Read-only mount + no-network preserves the Principle I sandbox posture.

**Alternatives considered**: keep `python -c` with host-side normalization
only (workable — a complete script runs identically under `-c` — but keeps
the transport weakness and worse tracebacks); stdin piping (interacts badly
with detached containers).

## Decision 3 — Tightened `resolved` definition

**Decision**: in `scripts/run_benchmark.py`, a scenario counts as resolved iff
`report_text is not None and execution_error is None and
execution_result is not None and execution_result.status == "success"`
(i.e. sandbox `return_code == 0`). `skipped` / `failure` / `timeout` statuses
and missing execution results all count as unresolved. The old
completion-based definition (line 190 pre-sprint) is deleted, not kept as a
second metric; pipeline-completion may be reported as a separate diagnostic
field but never as `resolution_rate`.

**Rationale**: FR-004; the 0.98 figure measured pipeline completion, not fix
success. `status == "success"` is already the deterministic exit-0 judgment
the Verifier makes (Constitution I: Verifier stays LLM-free).

## Decision 4 — Re-baseline protocol

**Decision**: one full real-LLM 50-scenario run at the end of the sprint,
after contract fix + scoring fix + v1 retirement land, using the existing
CostGuard budget (`--budget 150`, CNY). README gets a "Benchmark (Sprint 6
re-baseline)" section publishing: resolution rate under the new definition,
P50/P95 latency, total cost + currency, run id, and the definition itself.
The old 0.98 headline is replaced (kept only as a historical footnote with
its definition). Latency re-baselining (Sprint 5's 44.9s real-trace data
point vs the 30s P50 target) is folded into the same table — no separate
workstream.

**Rationale**: FR-005/SC-002; running once after all behavior changes avoids
paying for a number that is stale a week later. Mock-mode (`--use-mock`)
smoke runs remain free for development.

## Decision 5 — v1 retirement inventory (verified against code)

**Decision**: retire exactly the v1-only surface:

- `autosentinel/graph.py` (v1 graph builder)
- `autosentinel/nodes/analyze_error.py`, `autosentinel/nodes/execute_fix.py`
- **Keep** `autosentinel/nodes/parse_log.py` and `nodes/format_report.py` —
  verified reused by `multi_agent_graph.py` (lines 30–31); they are shared
  nodes, not v1-only.
- `run_pipeline()` (`autosentinel/__init__.py`): drop the
  `AUTOSENTINEL_MULTI_AGENT` env flag and the `DiagnosticState` else-branch;
  multi-agent becomes the only path. `DiagnosticState` removed from
  `models.py` if nothing else references it (verify at implementation).
- `scripts/run_benchmark.py`: delete `_run_v1()` and the `v1` summary block;
  summary schema becomes single-pipeline.
- Tests: delete/migrate `tests/unit/test_analyze_error.py`,
  `test_execute_fix.py`, the v1 arm of `tests/integration/test_pipeline.py`
  and `tests/unit/test_run_pipeline.py`. `test_parse_log.py` /
  `test_format_report.py` stay (shared nodes).
- Boundary allowlists: remove `autosentinel/nodes/execute_fix.py` from
  `test_docker_import_boundary.py`; remove the v1 grandfathered entries from
  `test_llm_provider_isolation.py` (verify actual list at implementation —
  the constitution names `nodes/analyze_error.py`).
- Constitution amendment: remove the Principle I grandfathering clause
  (v2.1.1) and the Principle VII.1 grandfathering clause (v2.2.0), close
  `TODO(SPRINT6_V1_RETIREMENT)`. Version 2.2.0 → **2.3.0** (MINOR — precedent:
  the Principle V keyword-list clause removal was MINOR in 2.1.1→2.2.0;
  removing an exemption tightens principles without redefining them).

**Rationale**: FR-008/FR-009/SC-004; scope pinned by imports, not by memory —
the naive "delete `nodes/`" would break the v2 graph.

## Decision 6 — CI design (single workflow, three jobs)

**Decision**: add `.github/workflows/ci.yml` alongside the existing
`scenario-authorship.yml` (untouched). Trigger: `pull_request` +
`push: branches: [main]`. Jobs:

1. **lint**: `astral-sh/setup-uv` → `uv sync --extra dev` → `uv run ruff check .`
2. **typecheck**: `uv run mypy autosentinel`
3. **test**: `services: checkpointer: postgres:16` with health check, ports
   `5434:5432`, `POSTGRES_USER/PASSWORD/DB=postgres` (mirrors
   `infra/docker-compose.checkpointer.yml`); env
   `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1`; `uv run pytest`. Docker is available
   on `ubuntu-latest` for the Verifier/sandbox tests. The AST boundary gates
   (`test_docker_import_boundary.py`, `test_llm_provider_isolation.py`)
   already live inside the pytest suite — no separate step needed.

**Anti-silent-skip guarantee**: the `requires_checkpointer` skipif guard in
`tests/integration/_pr4_helpers.py` (probe of `localhost:5434`) gains an
escalation: when `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1` is set and the probe
fails, the tests **fail** instead of skipping. CI sets the variable; local
runs without the container keep today's skip behavior.

**Toolchain packaging**: `ruff>=0.4.0` and `mypy>=1.10.0` are added to the
`dev` extra in `pyproject.toml` — `uv.lock` already carries exactly these
pins with `extra == 'dev'` markers (lock and manifest drifted; this re-syncs
them). mypy starts with a pragmatic baseline (`ignore_missing_imports`, no
strict flags) so the gate lands green; tightening is future work, recorded in
DEBT.md if any exclusions prove necessary.

**Rationale**: FR-006/FR-007/SC-003 and the DEBT.md CI-gap entry, including
its explicit requirement that the checkpointer service back T029/T036/T044c.

## Decision 7 — Small-item mechanics

- **Factory config path (FR-010)**: `factory.py:93`
  `_DEFAULT_ROUTING_PATH = Path("config/model_routing.yaml")` becomes anchored:
  `Path(__file__).resolve().parents[2] / "config" / "model_routing.yaml"`
  (factory.py → llm → autosentinel → repo root). The existing env-var override
  (line 97) keeps precedence. Regression test runs a subprocess (or monkeypatched
  CWD) from a non-root directory.
- **Onboarding (FR-011)**: README setup section + CLAUDE.md gain
  `uv sync --extra dev` as the mandatory first step, with a note that plain
  `uv sync` leaves pytest to fall back to system Python.
- **feature.json clobber guard (FR-012)**: the current speckit-specify
  workflow already persists `.specify/feature.json` (verified: it worked for
  this sprint). Remaining deterministic guard: `setup-plan.sh` refuses to
  overwrite an existing non-empty `plan.md` unless `--force` is passed —
  turning the Sprint 5 data-loss failure mode into a loud error. Plus a
  one-line documented step in CLAUDE.md's sprint-start notes. The
  corresponding DEBT.md entries flip `[X]` in the same commits.

## Decision 8 — Delivery shape (feeds /speckit.tasks)

**Decision**: four PRs off `006-fix-verification-integrity`, mapped to user
stories: PR-1 = US1 contract (producer + Verifier + execution format);
PR-2 = US2 scoring + US4 v1 retirement (both touch `run_benchmark.py`;
retiring v1 before the paid run avoids benchmarking a dead arm) + constitution
amendment; PR-3 = US3 CI + US5 small items; PR-4 = real re-baseline run +
README/PROJECT.md/DEBT.md updates. Test-First rhythm within each PR
(Constitution III). The real-LLM run happens exactly once, in PR-4.
