# Feature Specification: Fix Verification Integrity & Pipeline Consolidation

**Feature Branch**: `006-fix-verification-integrity`
**Created**: 2026-07-03
**Status**: Draft
**Input**: User description: "Sprint 6: Fix Verification Integrity & Pipeline Consolidation. Scope (from PORTFOLIO M2): (1) fix-artifact ↔ Verifier execution-format contract mismatch; (2) tighten benchmark `resolved` definition + 50-scenario re-baseline with honest fix-success rate; (3) broad CI (lint + types + tests + provider-boundary gate + checkpointer service); (4) retire the v1 single-agent pipeline; (5) small items: config-path CWD dependency, dev-dependency onboarding step, feature-directory pointer bump. Success criteria: CI fully green + honest re-baseline numbers published in README."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generated fixes survive sandbox verification (Priority: P1)

An on-call operator feeds a real error log into the system. The pipeline diagnoses
the incident, generates a code fix, and sends it to sandbox verification. Today,
most code-class fixes fail verification not because the fix is wrong, but because
the fix-producing agents and the verifying agent disagree about the artifact's
shape: fixers emit code *fragments* (often containing a bare top-level `return`),
while the verifier executes the artifact as a *standalone script* — an unconditional
syntax failure. After this sprint, a well-formed fix is executed in the sandbox in
the form its producer intended, so verification outcomes reflect fix **quality**,
not a format accident.

**Why this priority**: This is the core value proposition of the product — "fixes
are verified in a sandbox before anyone trusts them". While the contract is broken,
sandbox verification is systematically meaningless for code-class incidents, and
every downstream metric built on it is noise. Nothing else in this sprint matters
if this stays broken.

**Independent Test**: Run the pipeline end-to-end on a known code-class incident
(e.g. the dict-KeyError benchmark fixture that reproduced the bug). The fix
artifact reaches the sandbox, executes, and the verification verdict is determined
by the fix's behavior — not by a syntax error caused by artifact shape.

**Acceptance Scenarios**:

1. **Given** a code-class incident whose generated fix contains function-body
   constructs (e.g. a `return` statement), **When** the verifier executes the fix
   in the sandbox, **Then** execution does not fail with a format-induced syntax
   error.
2. **Given** a genuinely broken fix (wrong logic, crashes at runtime), **When**
   the verifier executes it, **Then** verification still honestly reports failure —
   the contract fix must not mask real fix defects.
3. **Given** any fix produced by either fix-producing agent (code or infra
   specialist), **When** it is handed to the verifier, **Then** both producers
   and the verifier follow one documented artifact contract (no per-agent special
   cases).

---

### User Story 2 - Honest resolution metric and re-baseline (Priority: P2)

A stakeholder reads the project README to judge how well the system actually fixes
incidents. Today the headline number (0.98 "resolution rate") measures *pipeline
completion* — a scenario counts as resolved even when the fix failed sandbox
execution. After this sprint, a scenario only counts as resolved when its fix
**verifiably succeeded** in the sandbox, the full 50-scenario benchmark is re-run
under this stricter definition, and the honest number — whatever it is — is
published in the README.

**Why this priority**: An overstated metric is worse than a low one; it undermines
trust in every other claim the project makes. This depends on User Story 1 landing
first (re-baselining against a broken contract would measure the bug, not the
system).

**Independent Test**: Run the benchmark on a small subset containing at least one
scenario whose fix completes the pipeline but fails sandbox execution; confirm
that scenario is counted as unresolved under the new definition.

**Acceptance Scenarios**:

1. **Given** a scenario whose pipeline completes but whose fix exits the sandbox
   unsuccessfully, **When** the benchmark scores it, **Then** it counts as
   **unresolved**.
2. **Given** a scenario whose fix executes successfully in the sandbox, **When**
   the benchmark scores it, **Then** it counts as resolved.
3. **Given** the tightened definition, **When** the full 50-scenario benchmark is
   re-run, **Then** the resulting resolution rate and run conditions are recorded
   in the README, replacing the old overstated number.

---

### User Story 3 - Every change is gated by full CI (Priority: P3)

A contributor opens a pull request. Today only a narrow scenario-authorship check
runs; lint, type checks, the test suite, and the provider-boundary rule are
enforced only on whoever remembers to run them locally. After this sprint, every
pull request automatically runs the full quality gate — style, types, the complete
test suite (including the cross-process checkpointer tests, which require their
database dependency to be available in CI), and the architectural boundary check —
and a red gate blocks merging.

**Why this priority**: The two fixes above are only durable if regressions get
caught automatically. This also closes a long-standing debt item: cross-process
persistence guarantees are currently never verified in CI.

**Independent Test**: Open a PR containing a deliberate lint violation (or type
error, or boundary violation); CI goes red. Fix it; CI goes green, including the
checkpointer-dependent tests actually executing rather than skipping.

**Acceptance Scenarios**:

1. **Given** a PR with a style, type, test, or provider-boundary violation,
   **When** CI runs, **Then** the corresponding job fails and the PR is blocked.
2. **Given** CI running the test suite, **When** the cross-process checkpointer
   tests execute, **Then** their database dependency is provisioned in CI and the
   tests genuinely run (not skip).
3. **Given** a clean PR, **When** CI runs, **Then** all jobs pass.

---

### User Story 4 - Single production pipeline (Priority: P4)

A maintainer reads the codebase to change pipeline behavior. Today two pipelines
coexist: the retired-in-spirit v1 single-agent pipeline and the v2 multi-agent
pipeline, with v1 kept alive by grandfathering exemptions in the project
constitution and a v1 comparison arm in the benchmark. After this sprint, v1 is
gone: one production pipeline, no grandfathering exemptions, no dead code paths.

**Why this priority**: Pure consolidation — valuable but has no user-facing
behavior change; safe to do after the correctness and measurement work.

**Independent Test**: Search the codebase for v1 pipeline entry points and the
constitution's grandfathering markers; none remain, and the full test suite is
green without them.

**Acceptance Scenarios**:

1. **Given** the v1 pipeline code and its tests, **When** retirement lands,
   **Then** the v1 entry points are removed and no production code path can invoke
   the single-agent pipeline.
2. **Given** the constitution's v1 grandfathering exemptions (sandboxing and
   provider-boundary principles), **When** retirement lands, **Then** the
   exemptions are removed via a constitution amendment and the boundary checks
   apply uniformly.
3. **Given** the benchmark's v1 comparison arm, **When** retirement lands,
   **Then** the benchmark measures only the production pipeline.

---

### User Story 5 - Frictionless developer onboarding and tooling (Priority: P5)

A developer clones the repo on a fresh machine, follows the documented setup, and
everything works: tests run against the project's own environment (dev
dependencies installed by the documented command), tests pass regardless of the
directory they are invoked from (no working-directory-dependent config loading),
and starting the next sprint cannot silently overwrite the previous sprint's
planning documents (the feature-directory pointer is updated as part of starting a
new feature, or the manual step is documented where it cannot be missed).

**Why this priority**: Small, known paper cuts with known fixes; batched last.

**Independent Test**: On a clean checkout, follow only the documented onboarding
steps and run a single test file from a non-root working directory — it passes.

**Acceptance Scenarios**:

1. **Given** a fresh clone, **When** the developer follows documented onboarding,
   **Then** the test runner uses the project environment with dev dependencies
   (no silent fallback to system tooling).
2. **Given** a single test file run from an arbitrary working directory, **When**
   configuration is loaded, **Then** it resolves relative to the project, not the
   process working directory.
3. **Given** a new sprint is started, **When** the feature workflow initializes
   the new feature, **Then** the previous feature's planning documents cannot be
   clobbered (pointer auto-updated, or a mandatory documented step).

---

### Edge Cases

- A fix artifact that is *already* a complete runnable script (e.g. produced under
  the new contract, or an infra remediation with no function-body constructs) must
  still verify correctly — the contract change must be shape-agnostic or clearly
  versioned, not "wrap everything blindly".
- An empty or whitespace-only fix artifact reaching the verifier: must produce an
  honest verification failure, not a crash or a false success.
- A fix that succeeds syntactically but hangs: existing sandbox timeout behavior
  must be preserved under the new execution format.
- Benchmark scenarios where the sandbox is unavailable (e.g. Docker down):
  must count as unresolved/errored, never as resolved — same as today.
- CI on a fork or a branch without database service support: the checkpointer
  tests must fail loudly or be visibly reported, not silently skip and go green.
- Retiring v1 while some tests import v1 modules: those tests must be migrated or
  deleted in the same change, keeping the suite green at every commit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST define a single documented contract for the shape of
  a fix artifact exchanged between fix-producing agents and the verifier, and both
  sides MUST comply with it.
- **FR-002**: The verifier MUST execute well-formed fix artifacts without
  format-induced syntax failures, for artifacts produced by every fix-producing
  agent.
- **FR-003**: The verifier MUST continue to report honest failures for fixes that
  are genuinely defective (wrong logic, runtime errors, timeouts, empty
  artifacts).
- **FR-004**: The benchmark MUST count a scenario as resolved only when the fix
  executed successfully in the sandbox (successful execution status), in addition
  to the pipeline completing.
- **FR-005**: The full 50-scenario benchmark MUST be re-run under the tightened
  definition, and the README MUST publish the resulting resolution rate together
  with the definition used and run conditions.
- **FR-006**: Continuous integration MUST run on every pull request and enforce:
  code style, static type checks, the full test suite, and the LLM
  provider-boundary check.
- **FR-007**: The CI test job MUST provision the checkpointer database dependency
  so that cross-process persistence tests genuinely execute in CI rather than
  skipping.
- **FR-008**: The v1 single-agent pipeline MUST be removed from the codebase,
  including its entry points, dead tests, and the benchmark's v1 comparison arm.
- **FR-009**: The constitution's v1 grandfathering exemptions (sandboxing
  principle and provider-boundary principle) MUST be removed via a proper
  constitution amendment as part of retirement.
- **FR-010**: Configuration files MUST be located relative to the project
  installation, not the process working directory, so tests and tools work from
  any directory.
- **FR-011**: Documented onboarding MUST include the step that installs dev
  dependencies into the project environment, eliminating the silent fallback to
  system tooling.
- **FR-012**: Starting a new feature MUST NOT be able to silently overwrite a
  previous feature's planning documents: the feature-directory pointer is updated
  automatically by the feature-creation workflow, or a mandatory manual step is
  documented in the workflow itself.

### Key Entities

- **Fix artifact**: The remediation payload produced by a fix-producing agent and
  consumed by the verifier. Key attributes: its shape (fragment vs. complete
  runnable form), its producing agent, and the contract version it complies with.
- **Verification result**: The sandbox execution outcome for a fix artifact —
  success/failure status, exit information, and captured output. The sole input
  to "did the fix work".
- **Benchmark scenario**: One of 50 human-authored incident cases with ground-truth
  labels. Scored as resolved/unresolved per run.
- **Resolution rate**: Share of benchmark scenarios whose fix verifiably succeeded
  in the sandbox. Published in the README with its definition and run conditions.
- **Quality gate (CI)**: The set of automated checks (style, types, tests,
  provider boundary) that every pull request must pass.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the full benchmark, **zero** code-class scenarios fail sandbox
  verification due to artifact-format syntax errors (the failure class reproduced
  on real runs pre-sprint drops to 0).
- **SC-002**: The README's published resolution rate is produced under the
  tightened definition (sandbox execution success required) from a full
  50-scenario re-baseline run; the old completion-based 0.98 figure no longer
  appears as the headline number.
- **SC-003**: CI runs on every pull request; on the sprint's final state, all CI
  jobs are green on the main branch, and the cross-process checkpointer tests are
  observed to execute (not skip) in the CI logs.
- **SC-004**: A codebase search for v1 pipeline entry points and the two
  constitution grandfathering markers returns zero results, with the full test
  suite green.
- **SC-005**: A fresh-clone onboarding following only the documented steps yields
  a passing test run, including a single-file test invocation from a non-root
  working directory.

## Assumptions

- The contract direction (producers emit complete runnable scripts vs. verifier
  normalizes fragments) is a design decision deferred to planning; the spec only
  requires that exactly one documented contract exists and both sides comply.
- The re-baselined resolution rate may be substantially lower than 0.98; the
  sprint's success is measured by the honesty and reproducibility of the number,
  not its magnitude. No minimum resolution-rate target is set for this sprint.
- The 50 benchmark scenarios and their ground-truth labels are reused as-is
  (they are human-authored tracked data); re-baselining changes scoring, not
  scenario content. The real-LLM re-baseline run has an associated API cost,
  assumed to stay within the project's existing cost-guard budget (Sprint 5
  budget mechanism remains in force).
- CI has access to a database service for the checkpointer tests (supported by
  the repository's existing CI runner, as proven by the live scenario-authorship
  workflow).
- The v1 pipeline has no remaining external consumers; the event-gateway API and
  benchmark are the only invocation paths, and both move to (or already use) the
  multi-agent pipeline.
- Latency re-baselining (the 44.9s vs 30s P50 observation from the real-trace
  smoke run) is folded into the benchmark re-baseline reporting, not a separate
  workstream.
