# Implementation Plan: Fix Verification Integrity & Pipeline Consolidation

**Branch**: `006-fix-verification-integrity` | **Date**: 2026-07-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-fix-verification-integrity/spec.md`

## Summary

Sprint 6 closes the post-Sprint-5 integrity gaps: (1) the fix-artifact ↔
Verifier execution-format contract is fixed belt-and-braces — producer prompts
+ `compile()` validation demand a complete runnable script, while the Verifier
gains a deterministic normalization fallback and switches from `python -c` to
write-to-file + read-only-mount execution; (2) the benchmark `resolved`
definition tightens to require sandbox exit 0, followed by one real-LLM
50-scenario re-baseline whose honest number replaces the 0.98 headline in
README; (3) broad CI lands (`ruff` + `mypy` + full pytest + AST boundary gates,
with the :5434 checkpointer Postgres as a CI service and an anti-silent-skip
escalation); (4) the v1 single-agent pipeline is retired (v1-only modules,
benchmark v1 arm, env flag, boundary-allowlist entries, constitution
grandfathering clauses → v2.3.0); (5) small items: factory config path
anchored to the package, `uv sync --extra dev` onboarding, `setup-plan.sh`
clobber guard. All design decisions in [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.11 (CI pins 3.11; sandbox image `python:3.10-alpine` unchanged)
**Primary Dependencies**: LangGraph, OpenAI SDK (base_url → Volcano Ark), Docker SDK, Pydantic v2, psycopg (checkpointer); dev: pytest, pytest-cov, ruff ≥0.4, mypy ≥1.10 (added to `dev` extra — uv.lock already pins them)
**Storage**: PostgreSQL 16 (LangGraph PostgresSaver checkpointer, localhost:5434; CI service container mirrors `infra/docker-compose.checkpointer.yml`)
**Testing**: pytest (100% branch coverage policy), AST boundary gates as unit tests, MockLLMClient fixtures for zero-spend LLM paths
**Target Platform**: Linux/macOS dev hosts + `ubuntu-latest` GitHub Actions (Docker daemon available)
**Project Type**: single Python package (`autosentinel/`) + scripts + benchmark corpus
**Performance Goals**: no new latency budget; P50/P95 re-measured in the re-baseline (Sprint 5 real-trace data point: 44.9s vs 30s P50 target — reported honestly, not gated)
**Constraints**: sandbox invariants unchanged (`mem_limit=64m`, `network_mode=none`, 5s wait timeout, force-remove); re-baseline spend ≤ ¥150 CNY via existing CostGuard; zero real-provider traffic in tests (mock/fixture only)
**Scale/Scope**: 50 benchmark scenarios; 6 agents; ~7 production modules touched + 1 new workflow file + constitution amendment

## Constitution Check

*GATE: evaluated against Constitution v2.2.0. Re-checked after Phase 1 — PASS (no violations, no Complexity Tracking entries).*

| Principle | Impact / Compliance |
|-----------|---------------------|
| I — Sandboxing | **Strengthened.** Verifier remains the sole Docker importer; retirement deletes the grandfathered `nodes/execute_fix.py` and shrinks the docker-boundary allowlist. New execution format keeps read-only mount, no network, mem/CPU limits. Amendment removes the Principle I grandfathering clause (v2.2.0 → 2.3.0, MINOR per the Principle V precedent). |
| II — Self-Healing/MTTR | Re-baseline reports honest resolution + latency; partial outcomes (`failure`/`timeout`) reported distinctly. |
| III — Test-First (NON-NEGOTIABLE) | Every behavior change lands red-test-first: normalization pure-function tests, producer-validation tests (MockLLMClient), scoring tests, boundary-allowlist shrink tests, checkpointer escalation test. Failing tests committed before implementation, per house rhythm. |
| V — LLM Reasoning Reliability | Unaffected: SecurityReviewer coverage/interrupt/audit invariants untouched; fix normalization happens *after* security review and does not alter the reviewed artifact semantics (wrap-and-call executes the same statements). |
| VI — Multi-Agent Governance | Unaffected: state-channel-only communication preserved; normalization lives inside VerifierAgent.run() / a pure helper, no new inter-agent surface. |
| VII — Provider Boundary & Cost | **Strengthened.** VII.1 grandfathering clause removed with v1; AST gate now runs in CI on every PR (previously local-only). Re-baseline run passes through the untouched CostGuard (VII.2); no new LLM call paths; producer retry reuses the existing `LLMClient.complete()` path with trace_id (VII.3). |
| Development Workflow | This sprint *implements* the constitution's "PRs MUST pass all CI checks" requirement, which until now had no enforcement vehicle. |

## Project Structure

### Documentation (this feature)

```text
specs/006-fix-verification-integrity/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 — 8 decisions
├── data-model.md        # Phase 1 — NormalizedArtifact, scoring, summary schema
├── quickstart.md        # Phase 1 — dev loop, CI-local parity, re-baseline runbook
├── contracts/
│   ├── fix-artifact.md  # Producer ⇄ Verifier contract (the P1 deliverable)
│   └── ci-gate.md       # Quality-gate contract (jobs, services, anti-skip)
├── checklists/requirements.md
└── tasks.md             # /speckit.tasks output — NOT created by /speckit.plan
```

### Source Code (repository root)

```text
autosentinel/
├── __init__.py                     # run_pipeline(): drop v1 branch + env flag (US4)
├── graph.py                        # DELETE — v1 graph builder (US4)
├── models.py                       # remove DiagnosticState if unreferenced (US4)
├── nodes/
│   ├── parse_log.py                # KEEP — shared with v2 graph
│   ├── format_report.py            # KEEP — shared with v2 graph
│   ├── analyze_error.py            # DELETE — v1-only (US4)
│   └── execute_fix.py              # DELETE — v1-only, grandfathered docker import (US4)
├── agents/
│   ├── verifier.py                 # normalization fallback + file-mount execution (US1)
│   ├── _artifact_normalizer.py     # NEW — pure normalize_fix_artifact() (US1)
│   ├── code_fixer.py               # compile() validation + one retry (US1)
│   ├── infra_sre.py                # compile() validation + one retry (US1)
│   └── prompts/{code_fixer,infra_sre}.py  # standalone-script contract wording (US1)
└── llm/factory.py                  # _DEFAULT_ROUTING_PATH anchored to __file__ (US5)

scripts/run_benchmark.py            # tightened `resolved`; delete _run_v1 + v1 summary (US2, US4)
.github/workflows/ci.yml            # NEW — lint / typecheck / test + pg service (US3)
.github/workflows/scenario-authorship.yml  # untouched
pyproject.toml                      # ruff+mypy into dev extra; mypy/ruff config (US3)
.specify/memory/constitution.md     # amendment 2.2.0 → 2.3.0 (US4)
.specify/scripts/bash/setup-plan.sh # plan.md clobber guard (US5)
README.md                           # re-baseline section + onboarding step (US2, US5)
CLAUDE.md                           # onboarding + sprint-start notes (US5)
DEBT.md                             # flip resolved entries [X]

tests/
├── unit/
│   ├── test_artifact_normalizer.py # NEW — exhaustive pure-function cases (US1)
│   ├── test_verifier_agent.py      # file-mount execution, honest failure paths (US1)
│   ├── test_code_fixer_agent.py    # validation + retry via MockLLMClient (US1)
│   ├── test_infra_sre_agent.py     # same (US1)
│   ├── test_model_routing.py       # non-root-CWD regression (US5)
│   ├── test_docker_import_boundary.py    # allowlist shrinks (US4)
│   ├── test_llm_provider_isolation.py    # grandfathered entries removed (US4)
│   ├── test_analyze_error.py       # DELETE (US4)
│   └── test_execute_fix.py         # DELETE (US4)
├── integration/
│   ├── _pr4_helpers.py             # AUTOSENTINEL_REQUIRE_CHECKPOINTER escalation (US3)
│   ├── test_pipeline.py            # v1 arm removed (US4)
│   └── (routing/security/checkpointer suites unchanged)
└── test_benchmark.py               # scoring-definition tests (US2)
```

**Structure Decision**: existing single-package layout; one new production
module (`agents/_artifact_normalizer.py`, keeping VerifierAgent thin and the
normalizer independently unit-testable) and one new workflow file. Everything
else is modification/deletion in place.

## Delivery Shape (feeds /speckit.tasks)

Four PRs off this branch, in order (research.md Decision 8):

1. **PR-1 — US1 contract fix**: normalizer + Verifier execution format +
   producer prompts/validation. Gate: the 008 KeyError fixture's fix executes
   without format-induced SyntaxError; genuinely-broken fixes still fail.
2. **PR-2 — US2 scoring + US4 retirement + amendment**: tightened `resolved`,
   v1 surface deleted, boundary allowlists shrunk, constitution v2.3.0.
   Gate: full suite green with v1 gone; mock benchmark smoke shows failing
   fixes counted unresolved.
3. **PR-3 — US3 CI + US5 small items**: ci.yml + dev-extra toolchain + factory
   path fix + onboarding docs + setup-plan.sh guard. Gate: CI green on the PR
   itself; checkpointer tests observed executing in CI logs (SC-003).
4. **PR-4 — re-baseline + publication**: one real 50-scenario run
   (`--budget 150`), README/PROJECT.md/DEBT.md updated. Gate: SC-001 (zero
   format-induced failures in the run) + SC-002 (honest number published).

Each PR follows Test-First (failing tests committed first). `git push` / PR
open / merge require developer confirmation per CLAUDE.md.

## Complexity Tracking

No constitution violations — table intentionally empty.
