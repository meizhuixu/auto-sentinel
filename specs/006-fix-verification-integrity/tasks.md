# Tasks: Fix Verification Integrity & Pipeline Consolidation

**Input**: Design documents from `/specs/006-fix-verification-integrity/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED and mandatory — Constitution III (Test-First, NON-NEGOTIABLE):
every behavior change lands as a failing test committed *before* the
implementation commit. "Write failing test" tasks below are commit boundaries,
not just authoring steps.

**Organization**: phases follow spec.md story priority (US1–US5) + a final
re-baseline phase. Execution/PR order differs (see Implementation Strategy —
research.md Decision 8): PR-1=US1, PR-2=US2+US4, PR-3=US3+US5, PR-4=re-baseline.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[Story]**: US1–US5 traceability to spec.md

## Phase 1: Setup (no commits — environment sanity)

- [ ] T001 Verify dev environment: `uv sync --extra dev`; start checkpointer via `infra/docker-compose.checkpointer.yml`; confirm `uv run pytest` collects and the suite is green on branch `006-fix-verification-integrity`

## Phase 2: Foundational

*None — the five stories share no blocking prerequisite beyond Setup.*

---

## Phase 3: User Story 1 — Generated fixes survive sandbox verification (P1) 🎯 MVP

**Goal**: one documented fix-artifact contract (`contracts/fix-artifact.md`):
producers emit complete runnable scripts (compile-validated, one retry);
Verifier adds deterministic normalization and file-mount execution. Format-induced
SyntaxError false-failures become impossible.

**Independent Test**: pipeline run on the `008_code_key_error_dict` fixture —
fix executes in the sandbox; verdict reflects fix behavior, not artifact shape.
Genuinely broken fixes still fail honestly.

### Tests (write first, confirm RED, commit before implementation)

- [ ] T002 [P] [US1] Failing unit tests for `normalize_fix_artifact()` in tests/unit/test_artifact_normalizer.py — cases per data-model.md §1: compile-clean → `verbatim`; bare top-level `return` → `wrapped` (and wrapped form compiles + preserves statements); top-level `yield` → `wrapped`; non-fragment SyntaxError → `rejected` with reason; empty/whitespace-only → `rejected("empty artifact")`; fragment that still fails after wrap → `rejected`
- [ ] T003 [P] [US1] Failing unit tests for VerifierAgent in tests/unit/test_verifier_agent.py — executes via temp-file + read-only `/workspace` mount (not `python -c`); `rejected` artifact → `ExecutionResult(status="failure", stderr=reason)` with NO container launched; `wrapped` artifact runs; existing timeout/skipped/docker-error paths preserved
- [ ] T004 [P] [US1] Failing unit tests for CodeFixerAgent producer validation in tests/unit/test_code_fixer_agent.py — MockLLMClient returns fragment then valid script: exactly one retry with compile error appended to prompt; retry-still-broken → artifact passed through without raising; compile-clean first response → no retry
- [ ] T005 [P] [US1] Failing unit tests for InfraSREAgent (same validation contract) in tests/unit/test_infra_sre_agent.py
- [ ] T006 [US1] Failing integration test in tests/integration/test_multi_agent_graph_routing.py (or a new test_fix_artifact_contract.py) — via the `build_multi_agent_graph(agents=)` seam with a MockLLMClient CodeFixer emitting a bare-`return` fragment: pipeline completes with `execution_result.status == "success"` and normalization outcome recorded (zero real-provider traffic)

### Implementation (each lands after its tests are RED-committed)

- [ ] T007 [US1] Implement `NormalizedArtifact` + `normalize_fix_artifact()` in autosentinel/agents/_artifact_normalizer.py (pure function; fragment symptoms limited to `'return' outside function` / `'yield' outside function` per contracts/fix-artifact.md) → T002 GREEN
- [ ] T008 [US1] Rewrite VerifierAgent execution in autosentinel/agents/verifier.py — call normalizer; `rejected` short-circuits to honest failure; write `fix.py` to temp dir, mount read-only at `/workspace`, run `["python", "/workspace/fix.py"]`; keep `python:3.10-alpine`, `mem_limit=64m`, `network_mode=none`, 5s wait, kill-on-timeout, force-remove → T003 GREEN
- [ ] T009 [P] [US1] Update producer prompts to the contract wording (standalone script, exit-code semantics, no fences) in autosentinel/agents/prompts/code_fixer.py and autosentinel/agents/prompts/infra_sre.py
- [ ] T010 [US1] Add compile()-validation + single retry to autosentinel/agents/code_fixer.py and autosentinel/agents/infra_sre.py (retry through the same `LLMClient.complete()` path — CostGuard/trace_id intact) → T004/T005 GREEN
- [ ] T011 [US1] Record normalization outcome (`verbatim`/`wrapped`/`rejected` + reason) into agent trace context in autosentinel/agents/verifier.py (+ tracing metadata if the tracing extra is active) → T006 GREEN
- [ ] T012 [US1] Real-trace smoke verification: `uv run python scripts/run_real_trace.py` on fixture 008 (≈¥0.03 spend, within budget) — sandbox execution no longer fails with format-induced SyntaxError; record result in the PR description

**Checkpoint**: US1 complete = PR-1 scope. Suite green, contract live both sides.

---

## Phase 4: User Story 2 — Honest resolution metric (P2)

**Goal**: `resolved` requires sandbox success (exit 0); summary is
self-describing. (The paid 50-scenario re-baseline itself is Phase 8 — it must
run after US1+US4 land.)

**Independent Test**: mock benchmark subset containing a scenario whose fix
fails sandbox execution → counted unresolved.

### Tests (write first, confirm RED, commit before implementation)

- [ ] T013 [US2] Failing tests for the tightened scoring in tests/test_benchmark.py — per data-model.md §3: report present + `execution_result.status=="failure"` → unresolved; `"timeout"` → unresolved; `execution_result is None` → unresolved; `"success"` → resolved; summary carries `resolved_definition` string

### Implementation

- [ ] T014 [US2] Tighten `passed` assignment and add `resolved_definition` to the summary in scripts/run_benchmark.py → T013 GREEN
- [ ] T015 [US2] Zero-cost verification: `uv run python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 150 --use-mock` on a subset including a failing-fix scenario — confirm it scores unresolved; attach summary snippet to the PR description

**Checkpoint**: scoring is honest; headline number production deferred to Phase 8.

---

## Phase 5: User Story 3 — Full CI gate (P3)

**Goal**: `.github/workflows/ci.yml` per contracts/ci-gate.md — ruff, mypy,
full pytest with the :5434 checkpointer service; boundary AST gates run inside
pytest; checkpointer tests cannot silently skip in CI.

**Independent Test**: PR with a deliberate violation goes red; clean PR goes
green with checkpointer tests in the executed set.

### Tests (write first, confirm RED, commit before implementation)

- [ ] T016 [US3] Failing unit test for the anti-silent-skip escalation in tests/unit/test_checkpointer_guard.py — with `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1` and an unreachable DB probe, the guard fails instead of skipping; without the env var, skip behavior unchanged

### Implementation

- [ ] T017 [US3] Implement the escalation in tests/integration/_pr4_helpers.py (`requires_checkpointer` → fail when required-but-unavailable) → T016 GREEN
- [ ] T018 [US3] Add `ruff>=0.4.0` + `mypy>=1.10.0` to the `dev` extra in pyproject.toml (re-sync with uv.lock's existing pins) plus minimal `[tool.ruff]` / `[tool.mypy]` baseline config (mypy pragmatic: `ignore_missing_imports`, no strict flags)
- [ ] T019 [US3] Run `uv run ruff check .` and fix (or explicitly configure away) all violations across autosentinel/, scripts/, tests/
- [ ] T020 [US3] Run `uv run mypy autosentinel` and fix (or baseline-scope) all errors; record any deliberate exclusions in DEBT.md
- [ ] T021 [US3] Create .github/workflows/ci.yml per contracts/ci-gate.md — jobs lint/typecheck/test; postgres:16 service on 5434 with health check; `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1`; triggers `pull_request` + `push: main`; scenario-authorship.yml untouched
- [ ] T022 [US3] CI-parity local run: `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1 uv run pytest` with the 5434 container up — full suite green; then verify on the PR that all three jobs pass and checkpointer tests appear in the executed (not skipped) set → SC-003 evidence

**Checkpoint**: US3 complete; every subsequent PR is gated.

---

## Phase 6: User Story 4 — Single production pipeline (P4)

**Goal**: v1 single-agent pipeline retired — modules, env flag, benchmark arm,
boundary-allowlist entries, constitution grandfathering (→ v2.3.0). Verified
inventory in research.md Decision 5 (`nodes/parse_log.py` + `format_report.py`
are shared with v2 and MUST stay).

**Independent Test**: quickstart.md §"v1 retirement sanity" greps return no
hits; full suite green.

### Tests (write first, confirm RED, commit before implementation)

- [ ] T023 [US4] Shrink boundary-test allowlists (RED until deletions land): remove `autosentinel/nodes/execute_fix.py` from tests/unit/test_docker_import_boundary.py and the v1 grandfathered entries from tests/unit/test_llm_provider_isolation.py (verify the actual allowlist contents first)

### Implementation

- [ ] T024 [US4] Delete autosentinel/graph.py, autosentinel/nodes/analyze_error.py, autosentinel/nodes/execute_fix.py; update autosentinel/nodes/__init__.py; KEEP parse_log.py and format_report.py
- [ ] T025 [US4] Simplify `run_pipeline()` in autosentinel/__init__.py — drop the `AUTOSENTINEL_MULTI_AGENT` flag and the v1 else-branch; remove `DiagnosticState` from autosentinel/models.py if nothing references it after deletion
- [ ] T026 [US4] Delete/migrate v1 tests: remove tests/unit/test_analyze_error.py and tests/unit/test_execute_fix.py; strip v1 arms from tests/integration/test_pipeline.py and tests/unit/test_run_pipeline.py (keep tests/unit/test_parse_log.py and test_format_report.py) → T023 GREEN
- [ ] T027 [US4] Remove `_run_v1()` + the `v1` summary block from scripts/run_benchmark.py; adopt the single-pipeline summary schema of data-model.md §4 (extend T013's tests to cover the new schema in the same commit rhythm)
- [ ] T028 [US4] Constitution amendment in .specify/memory/constitution.md — remove the Principle I grandfathering clause and the Principle VII.1 grandfathering clause, close `TODO(SPRINT6_V1_RETIREMENT)`, version 2.2.0 → 2.3.0 with sync-impact report, update `LAST_AMENDED_DATE`
- [ ] T029 [US4] Retirement sanity: run quickstart.md §"v1 retirement sanity" greps (`AUTOSENTINEL_MULTI_AGENT`, `DiagnosticState`, `_run_v1`, `SPRINT6_V1_RETIREMENT` → zero hits) + full suite green → SC-004 evidence

**Checkpoint**: one pipeline; US2+US4 together = PR-2 scope.

---

## Phase 7: User Story 5 — Developer experience small items (P5)

**Goal**: config loading works from any CWD; onboarding installs dev extras;
sprint-start cannot clobber prior planning docs.

**Independent Test**: fresh-clone onboarding per docs; single test file passes
from a non-root working directory.

### Tests (write first, confirm RED, commit before implementation)

- [ ] T030 [P] [US5] Failing regression test in tests/unit/test_model_routing.py — routing config resolves when process CWD is not the repo root (monkeypatch CWD or subprocess from a temp dir); env-var override still takes precedence

### Implementation

- [ ] T031 [US5] Anchor `_DEFAULT_ROUTING_PATH` in autosentinel/llm/factory.py to `Path(__file__).resolve().parents[2] / "config" / "model_routing.yaml"` → T030 GREEN
- [ ] T032 [P] [US5] Onboarding docs: add `uv sync --extra dev` as the mandatory setup step in README.md and CLAUDE.md (note the system-Python fallback pitfall)
- [ ] T033 [P] [US5] Add clobber guard to .specify/scripts/bash/setup-plan.sh — refuse to overwrite an existing non-empty plan.md unless `--force`; document the sprint-start feature.json step alongside
- [ ] T034 [US5] Flip the DEBT.md entries resolved by this sprint (`[ ]`→`[X]`, same-commit-as-fix policy): factory CWD path, uv sync onboarding, feature.json kickoff check, CI gap, fix↔Verifier contract + `resolved` definition (as their fixes land in PR-1/2/3 — this task is the final consistency sweep)

**Checkpoint**: US3+US5 together = PR-3 scope.

---

## Phase 8: Re-baseline & Publication (completes US2's SC-002; depends on US1+US2+US4)

- [ ] T035 THE re-baseline run (developer go-ahead for spend): `uv run python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 150` over all 50 scenarios; archive `benchmarks/results/<run_id>/` output; verify SC-001 in results.jsonl (zero format-induced SyntaxError failures)
- [ ] T036 Publish in README.md — "Benchmark (Sprint 6 re-baseline)" section: resolution rate under the new definition, P50/P95 latency, total cost + CNY, run_id, `resolved_definition`; demote the 0.98 completion-rate figure to a historical footnote with its old definition
- [ ] T037 Update docs/PROJECT.md 当前状态 snapshot (Sprint 6 outcomes, re-baseline numbers, constitution v2.3.0) and final DEBT.md consistency check
- [ ] T038 Quickstart validation pass: execute every command block in specs/006-fix-verification-integrity/quickstart.md end-to-end; fix drift → SC-005 evidence

**Checkpoint**: Phase 8 = PR-4 scope. Sprint 6 done: CI green + honest numbers in README.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: none
- **Phases 3–7 (US1–US5)**: only Setup; mutually independent EXCEPT
  T027 (US4, benchmark v1-arm removal) touches scripts/run_benchmark.py after
  T014 (US2) — do T014 first or land both in PR-2 (chosen: same PR)
- **Phase 8**: hard-depends on US1 (contract), US2 (scoring), US4 (v1 gone);
  soft-depends on US3 (CI green is part of "final state" SC-003)

### Within Each Story (Constitution III)

- Failing tests committed BEFORE implementation commits — no exceptions
- T007 → T008 → T011 sequential (same/adjacent Verifier surface); T009 ∥ T010 order flexible but T010 depends on T004/T005
- T024 → T025 → T026 sequential (deletions cascade)

### Parallel Opportunities

- T002–T005 (four different test files) in parallel; T009 parallel to T007/T008
- T030/T032/T033 in parallel (different files)
- Whole stories US3 and US5 parallel to US1/US2/US4 if desired — but PR
  sequencing below is the agreed shape

## Implementation Strategy (PR mapping — research.md Decision 8)

1. **PR-1 = Phase 3 (US1)** — MVP: contract fixed both sides, format false-failures dead
2. **PR-2 = Phase 4 + Phase 6 (US2+US4)** — honest scoring + v1 retired + constitution v2.3.0 (both touch run_benchmark.py; retire before the paid run)
3. **PR-3 = Phase 5 + Phase 7 (US3+US5)** — CI gate + DX items; from here every PR is machine-gated
4. **PR-4 = Phase 8** — the one paid re-baseline run + publication

Per CLAUDE.md: local commits at Claude Code's discretion (Test-First rhythm);
`git push` / PR open / merge require developer confirmation. `[X]` write-back
per the tasks.md policy in CLAUDE.md.
