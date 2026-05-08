# Feature Specification: Sprint 5 — Real LLM Integration

**Feature Branch**: `005-real-llm-integration`
**Created**: 2026-05-07
**Status**: Draft
**Input**: User description: "Sprint 5 — Replace mock agents with real LLM-backed reasoning across the 6-agent graph, introduce a single LLM client abstraction with cost guard and trace propagation, persist LangGraph state across processes, and extend the v1/v2 benchmark from 5 to 50 scenarios."

---

## Overview

Sprint 4 delivered the multi-agent topology (Supervisor + Diagnosis + 3 specialists +
SecurityReviewer + Verifier) with deterministic mock `run()` methods on every agent.
Sprint 5 swaps those mocks for real LLM-backed reasoning across five of the six
agents (Diagnosis, CodeFixer, InfraSRE, SecurityReviewer, Supervisor); the Verifier
remains deterministic. Every acceptance scenario established in Sprint 4 (SC-001
through SC-005) MUST continue to pass.

The Sprint takes its shape from five outcomes operators and reviewers should observe
once it is complete:

1. **Specialist agents reason for themselves.** Diagnosis, CodeFixer, InfraSRE, and
   SecurityReviewer are no longer fixtures; they consume incident input and emit
   structured output produced by an LLM.
2. **The Supervisor routes with judgment, not pattern-matching.** Routing decisions
   are produced by an LLM call against the Diagnosis output, with the routing
   rationale captured in `AgentState`.
3. **Cost is a first-class system concern.** Every outbound LLM request passes
   through a single guard that aborts the pipeline cleanly when configured budgets
   are reached, rather than silently overrunning a quota.
4. **Multi-agent runs are correlatable end-to-end.** A single `trace_id`, generated
   at the incident entry point, threads through all six agents and surfaces in the
   external LLMOps Dashboard as one parent trace with N child spans.
5. **The benchmark is statistically meaningful, not anecdotal.** The v1/v2 harness
   grows from 5 smoke scenarios to 50 ground-truth-labelled scenarios with a fixed
   category distribution, producing real latency and cost numbers rather than
   synthetic ones.

This spec is **outcome-level**. Concrete model names, SDK choices, provider
gateways, endpoint identifiers, prompt templates, and persistence schemas are
deliberately excluded — they are decided in `plan.md`. This separation is itself
a Sprint 5 deliverable: the LLM provider boundary added in Constitution v2.2.0
(Principle VII) is the durable contract; the providers behind it are not.

---

## User Stories

### User Story US1 — Real LLM-Backed Diagnosis & Fix Generation (Priority: P1)

When an incident reaches AutoSentinel, the four specialist agents (Diagnosis,
CodeFixer, InfraSRE, SecurityReviewer) reason about it using a real LLM rather
than returning a fixture. Their outputs — error category, fix artifact, and
security verdict — reflect the actual incident content, not a deterministic mock.
The pipeline survives process restarts: a `HIGH_RISK` interrupt raised in one
process can be resumed in another without re-running upstream work.

**Why this priority**: This is the core value of Sprint 5. Without real reasoning,
none of the other stories deliver visible impact — routing intelligence (US2) is
moot if the things being routed to are mocks, cost governance (US3) has nothing
to govern, and the benchmark (US5) measures only the harness. Cross-process
checkpoint persistence is folded into this story rather than split out, because
it is the prerequisite infrastructure that makes the LLM-driven HIGH_RISK
interrupt path usable beyond a single process; on its own it would not deliver
operator-visible value.

**Independent Test**: Submit two structurally different incidents (one CODE, one
INFRA). Assert that the four specialist agents each emit non-fixture output
sensitive to the incident content (e.g., different fix artifacts for different
inputs), that the SecurityReviewer's verdict is recorded with classifier identity
in the trace, and that a `HIGH_RISK` interrupt persisted in one process can be
resumed by a freshly-started process and reach the Verifier after approval.

---

### User Story US2 — Routing Intelligence via LLM Supervision (Priority: P1)

The Supervisor agent uses a real LLM to interpret the Diagnosis output and choose
the correct specialist (or specialists) for the incident, recording its rationale
in `AgentState`. The Verifier agent retains the deterministic Sprint 4 behaviour
(Docker-sandbox execution, pass/fail determined by container exit code) and is
explicitly NOT LLM-backed in Sprint 5. This selective application of LLM
reasoning — only where it adds judgment value, not where deterministic logic
suffices — is itself a Sprint 5 design property (see also Out of Scope).

**Why this priority**: Routing is the joint between Diagnosis and the specialists.
If the Supervisor remains rule-based while every other agent reasons with an LLM,
the system inherits the rigidity of the old pipeline at exactly the point where
multi-agent flexibility is supposed to live. Co-equal P1 with US1.

**Independent Test**: Inject four incidents whose ground-truth category is
non-obvious from surface keywords alone (e.g., a CONFIG drift that surfaces as a
runtime error with a stack trace, easily mistaken for CODE). Assert the
Supervisor routes each to the correct specialist as labelled in the ground-truth
set, and that the routing rationale captured in `AgentState` references the
Diagnosis output rather than a hard-coded mapping.

---

### User Story US3 — Cost & Budget Governance (Priority: P1)

Every outbound LLM request — from any of the six agents — passes through a single
cost-tracking layer. When cumulative spend within a pipeline run reaches the
configured budget, the pipeline aborts with a typed error rather than continuing
silently. Per-call cost data is exported to the external LLMOps Dashboard so
operators can monitor spend in flight.

**Why this priority**: Real LLM calls cost real money. A Sprint 5 release that
reasons correctly but has no upper bound on cumulative spend is not safely
operable. Co-equal P1 with US1 / US2 because the constitution (Principle VII.2)
elevates CostGuard to the same non-negotiable status as Test-First.

**Independent Test**: Configure a deliberately low budget. Run a multi-agent
pipeline known to exceed it. Assert that the pipeline aborts with a typed
budget-exceeded error after the budget is reached, that no agent issues an LLM
call once the guard has tripped, and that per-call cost telemetry up to the abort
point is observable in the dashboard.

---

### User Story US4 — Cross-Project Trace Correlation (Priority: P2)

When a single incident is processed by AutoSentinel, all LLM calls made by the
six agents share one parent `trace_id` that originates at the incident entry
point and is propagated through `AgentState`. In the LLMOps Dashboard, the
incident appears as one parent trace with child spans for each agent's LLM call,
tagged by project and component, regardless of which process or which checkpoint
phase the calls occurred in.

**Why this priority**: P2 because the system functions correctly without
end-to-end trace correlation — it just becomes much harder to debug. With it,
multi-agent reasoning is inspectable as a single coherent run; without it, every
LLM call is an orphan span. Critical for operability but not for first-pass
correctness.

**Independent Test**: Run one incident through the full multi-agent pipeline.
Inspect the LLMOps Dashboard and assert: exactly one parent trace exists for
the incident, the parent trace ID equals the `trace_id` recorded in
`AgentState`, the parent has at least one child span per agent that made an LLM
call, and every span carries the project/component tag for AutoSentinel.

---

### User Story US5 — Statistically Meaningful Benchmark (Priority: P2)

The v1/v2 comparison benchmark grows from 5 smoke scenarios to 50 scenarios
distributed across the four error categories (12 CODE, 15 INFRA, 8 SECURITY,
15 CONFIG). Each scenario carries a human-curated ground-truth label. Running
the benchmark produces a report on disk that contains real latency, real cost,
and real resolution-rate numbers for both pipelines, suitable for citation in
operational decisions.

**Why this priority**: P2 because the benchmark is what converts Sprint 5 from
"the system works" into "we can defend its behaviour quantitatively." It is
not on the critical path for the multi-agent pipeline functioning correctly,
but it is on the critical path for trusting any subsequent decision (e.g.,
retiring v1) made on the basis of comparative data.

**Independent Test**: Run the benchmark. Assert that the report file at
`output/benchmark-report.json` exists, parses as JSON, contains a `scenario_count`
of 50 with the prescribed category distribution, and reports three triplets of
metrics (latency, cost, resolution rate) for v1 and v2 — none of which are
`null` and at least one of which differs from its Sprint 4 5-scenario value
(i.e., the new scenarios actually contributed to the numbers rather than being
silently ignored).

---

## Functional Requirements

> **Numbering**: Sprint 5 functional requirements are namespaced as `FR-5xx` to
> remain non-overlapping with Sprint 4's `FR-0xx`. Acceptance scenarios continue
> the global counter at `SC-008` (Sprint 4 ended at `SC-007`).

### Category 1 — LLM Client Abstraction

- **FR-501**: A single LLM client abstraction MUST be the only path through which
  agent code may issue an LLM request. Direct provider-SDK imports from agent
  modules are prohibited; the boundary MUST be enforced by an automated
  AST-walking CI check (per Constitution VII.1). The abstraction's public surface
  MUST be provider-agnostic — switching providers MUST be expressible as
  configuration only.
- **FR-502**: Per-agent model assignment MUST be expressed declaratively, sourced
  from environment variables or a dedicated configuration module. Hard-coding a
  model name, endpoint URL, or provider gateway inside an agent's `run()` method
  is prohibited.
- **FR-503**: All structured inputs and outputs that cross the LLM boundary MUST
  be validated by a typed schema (Pydantic V2 or equivalent) before reaching agent
  business logic. Free-form text returned by the LLM MUST NOT be parsed directly
  as executable instructions, consistent with Constitution Principle V.
- **FR-504**: The provider SDK MUST be replaceable at the abstraction layer with
  a test double so that the LLM client and every agent that depends on it remain
  testable under Constitution Principle III's 100% branch-coverage requirement
  without issuing real provider calls.

### Category 2 — Cost Governance

- **FR-505**: A `CostGuard` component MUST sit in the LLM client abstraction
  layer such that every outbound LLM request passes through it before the SDK
  call is issued. There MUST be no path from any agent module to a provider
  SDK that bypasses `CostGuard`.
- **FR-506**: `CostGuard` MUST maintain a cumulative-spend counter for the
  current pipeline run and MUST raise a typed cost-exceeded error when a
  configured threshold is reached. The error MUST propagate to the LangGraph
  orchestrator and abort the pipeline cleanly; silent truncation or retry is
  prohibited.
- **FR-507**: Budget thresholds MUST be sourced from environment variables, not
  hard-coded. The default safe-floor budget for a single pipeline run SHOULD be
  set conservatively (a low-tens-of-USD order of magnitude is appropriate as a
  starting point) so that an accidental no-op deployment cannot exhaust a
  significant share of an operator's account before manual configuration.
- **FR-508**: Per-call cost telemetry — including token counts, model identity,
  and computed spend — MUST be exported to the external LLMOps Dashboard for
  every LLM call, regardless of whether the pipeline ultimately succeeds, fails,
  or is aborted by `CostGuard`.

### Category 3 — Tracing & Observability

- **FR-509**: A single `trace_id` MUST be generated at the incident entry point
  (the point where an incident first enters AutoSentinel's pipeline) and MUST be
  carried through `AgentState` from that point onward. The LLM client MUST NOT
  generate `trace_id` values internally; it MUST accept the externally-supplied
  ID and forward it to its tracing layer.
- **FR-510**: Every LLM call issued by any of the six agents MUST be recorded as
  a child span of the incident's parent trace, such that a single incident
  surfaces in the LLMOps Dashboard as one parent trace with up to six (or more,
  if any agent issues multiple calls) child spans.
- **FR-511**: Trace propagation MUST be unconditional — passing `trace_id`
  through to the LLM client is required at every agent boundary. Dropping or
  regenerating the `trace_id` between agents is a violation, consistent with
  Constitution VII.3.
- **FR-512**: Every LLM-call span MUST be tagged with project and component
  identifiers (the project tag identifying AutoSentinel, the component tag
  identifying which of the six agents made the call) so that dashboard filters
  can isolate AutoSentinel traffic from any other project sharing the LLMOps
  infrastructure.

### Category 4 — Cross-Process State Persistence

- **FR-513**: The LangGraph checkpointer MUST be a durable, out-of-process backing
  store — not the in-memory variant used in Sprint 4 — so that pipeline state
  survives process restart. Concrete persistence technology choice belongs to
  `plan.md`.
- **FR-514**: A `HIGH_RISK` interrupt raised in one process MUST be resumable
  by a different process that connects to the same persistent checkpoint.
  Resumption MUST NOT re-execute upstream agents whose results were already
  persisted; the pipeline MUST resume from the suspended interrupt point.
- **FR-515**: All credentials required by the persistent checkpointer (database
  URLs, passwords, etc.) MUST be sourced from environment variables; hard-coded
  credentials are prohibited.

### Category 5 — Benchmark Extension

- **FR-516**: The benchmark scenario set MUST be extended from 5 to 50 scenarios
  distributed as: 12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG. The scenario list
  MUST live in a structured data file (or equivalent first-class data structure),
  not inline in benchmark runner code, so that future expansions remain
  non-breaking — consistent with Sprint 4 FR-011.
- **FR-517**: Each of the 50 scenarios MUST carry a human-curated ground-truth
  label covering: expected error category, expected security verdict (where
  applicable), and expected resolution outcome. Ground-truth labels MUST NOT be
  generated by AI and verified by AI; the labelling methodology MUST be
  documented inside this Sprint 5 specification (or an explicitly-referenced
  companion artefact under `specs/005-real-llm-integration/`) so that any
  reviewer can audit how labels were obtained.
- **FR-518**: The benchmark report at `output/benchmark-report.json` MUST report
  three metric triplets — latency, cost, resolution rate — for both v1 and v2
  pipelines, computed from real LLM calls (not from mock fixtures). The report
  schema MUST remain a strict superset of the Sprint 4 schema so that downstream
  consumers reading Sprint 4 fields continue to work.
- **FR-519**: The benchmark MUST be runnable against the same `CostGuard`
  configuration as production. If a benchmark run would exceed the configured
  budget, it MUST abort with the same typed error as a production pipeline run
  rather than silently dropping scenarios.

---

## Acceptance Scenarios

> **Numbering**: Continues the global Sprint 4 counter. Sprint 4 ended at
> `SC-007`; Sprint 5 begins at `SC-008`.

- **SC-008** (US1, real reasoning): Two incidents whose surface text differs
  produce specialist outputs (fix artifact, security verdict) that also differ;
  outputs are not byte-equivalent fixtures. Verified by injecting two paired
  incidents into the pipeline and asserting structural divergence in the
  resulting `AgentState`.
- **SC-009** (US2, intelligent routing): On a held-out routing test set of at
  least 20 incidents whose ground-truth category is annotated independently of
  the routing prompt, the Supervisor's routing accuracy is **≥ 70 %**. The
  Supervisor's rationale is recorded in `AgentState` for every routed incident.
- **SC-010** (US3, cost ceiling): With the per-run LLM budget configured to a
  test floor, a deliberately budget-exceeding pipeline aborts with a typed
  cost-exceeded error before reaching the Verifier; no LLM call is issued after
  the guard has tripped.
- **SC-011** (US4, single parent trace): For one incident processed by the full
  pipeline, the LLMOps Dashboard shows exactly one parent trace whose ID equals
  the `trace_id` in `AgentState`, with at least one child span per agent that
  issued an LLM call, all tagged with the AutoSentinel project/component
  identifiers.
- **SC-012** (US5, real-data benchmark): The benchmark report at
  `output/benchmark-report.json` exists, parses as valid JSON, contains
  `scenario_count: 50` with the prescribed category distribution, and reports
  the three v1/v2 metric triplets with no `null` values.
- **SC-013** (US1 / Principle V outcome invariant — **strict equality**):
  Across the SECURITY-category subset of the 50-scenario benchmark — every
  scenario whose ground-truth label is `HIGH_RISK` — the SecurityReviewer's
  false-negative count is **= 0**. (A false negative is a `HIGH_RISK`
  ground-truth scenario for which the SecurityReviewer returns a non-`HIGH_RISK`
  verdict.) This threshold is not negotiable and is not subject to the
  conservative-range convention applied to other Sprint 5 SCs, because it is the
  outcome-level invariant on which Constitution Principle V rests.
- **SC-014** (US1, cross-process interrupt durability): A `HIGH_RISK` interrupt
  raised inside process A is resumable from process B, where process B is
  started after process A has fully exited. Resumption MUST NOT re-execute
  upstream specialist work and MUST reach the Verifier once approval is
  recorded.
- **SC-015** (Sprint 4 non-regression): Every Sprint 4 acceptance scenario
  (`SC-001` through `SC-005`) continues to pass after the Sprint 5 changes are
  merged. Sprint 5 MUST NOT introduce a regression in Sprint 4's core
  invariants — multi-agent topology, security gate enforcement, Verifier-as-sole-
  Docker-executor, full test-suite coverage, or routing correctness on the
  Sprint 4 smoke set.

---

## Out of Scope

The following are deliberately excluded from Sprint 5. Each entry includes the
reason, so that future sprints have explicit context for the deferral.

### Implementation-level decisions (belong to `plan.md`)

- **Specific LLM model names** (e.g., which model each agent uses).
  *Why*: Constitution VII.4 requires model routing to be declarative and
  configurable. Naming a model in the spec would make a configuration value
  load-bearing on a spec amendment.
- **Specific provider SDK choice** (e.g., which Python SDK package the LLM
  client wraps).
  *Why*: Constitution VII.1 makes provider isolation an architectural property,
  not a spec-level commitment. Sprint 5's contract is the abstraction; the
  provider behind it is a `plan.md` decision.
- **Specific provider gateway** (e.g., which provider's endpoint serves
  requests).
  *Why*: Same reasoning as SDK choice — gateway selection is configuration,
  not contract.
- **Endpoint identifiers / deployment IDs**.
  *Why*: These are environment-specific values, not properties of the system
  the spec describes.
- **Prompt templates and prompt-engineering specifics**.
  *Why*: Prompts are versioned alongside source code (Constitution V); they
  evolve faster than spec amendments and belong with the agent implementation.
- **Persistent checkpointer database schema** (table layouts, index choices,
  migration strategy).
  *Why*: A spec-level commitment to a schema would couple the spec to a
  concrete persistence technology, conflicting with the outcome-level framing
  of FR-513.

### Outside Sprint 5's scope

- **v1 pipeline retirement**.
  *Why*: Sprint 5 closes `TODO(SPRINT5_KEYWORD_REMOVAL)` (the Principle V
  keyword-list grandfathering) but explicitly does **not** close
  `TODO(SPRINT6_V1_RETIREMENT)`. The v1 pipeline remains grandfathered under
  Constitution I and VII.1 so that the v1/v2 benchmark comparison continues to
  produce meaningful contrasting numbers. Retirement is queued for Sprint 6 or
  later.
- **Verifier as an LLM-backed agent.**
  *Why*: The Verifier's responsibility is binary verification — does the fix
  make the container pass tests? Container exit code answers this
  deterministically; an LLM call would add cost and latency without changing
  the verdict. Constitution v2.2.0 Principle I makes LLM-backed Verifier
  constitutionally permissible, but Sprint 5 declines that option as a
  deliberate design choice. Reconsider in Sprint 6+ only if a concrete need
  emerges (e.g., classifying non-traceback failure modes).
- **Multi-agent parallel execution**.
  *Why*: Sprint 4 deferred parallel execution to a future sprint after switching
  to fully sequential ordering for security-gate correctness (US3, Sprint 4).
  Sprint 5 inherits the sequential ordering so that real LLM latency improvements
  can be measured against a known baseline rather than being entangled with a
  parallelism change.
- **Interrupt timeout / approval-expiry policy**.
  *Why*: Sprint 4 acknowledged this gap and deferred it. Sprint 5 expands the
  capability surface (durable cross-process interrupts) but does not commit to a
  timeout policy; that is a Sprint 5 follow-up.
- **A real human-approval UI**.
  *Why*: Approvals are still simulated by directly resuming the persisted
  checkpoint in tests. Building a production approval UI is a separate UX
  workstream and would expand Sprint 5 well beyond its core scope.

### Cross-project changes

- **Modifications to the LLMOps Dashboard repository itself**.
  *Why*: AutoSentinel is the producer of trace and cost telemetry; the dashboard
  is its consumer. Sprint 5 changes only the producer side; consumer-side
  improvements are scheduled in the dashboard project.
- **Changes to the DevDocs RAG repository**.
  *Why*: Same separation. AutoSentinel does not own that repository.
- **Changes to the DevContext MCP server**.
  *Why*: Same separation.

### Career / résumé packaging

- **Bullet-point updates, LinkedIn posts, or any external write-up of Sprint 5
  outcomes**.
  *Why*: These are post-merge activities. They depend on Sprint 5 being
  complete and verified; including them in the spec confuses delivery with
  promotion.

---

## Constitutional Alignment

Sprint 5 is the first feature delivered under Constitution **v2.2.0**
(ratified 2026-04-24, last amended 2026-05-07). Each principle below maps to
the Sprint 5 functional requirements that uphold it.

### Principle I — AI Agent Sandboxing

Sprint 5 inherits the Sprint 4 boundary — only the Verifier agent imports the
Docker SDK — and does not relax it. The v2.2.0 LLM-execution clarification is
honoured by FR-513 / FR-514: cross-process interrupt durability runs the LLM
calls themselves outside the sandbox container, while the workload under
verification continues to run inside it. No new module is added to the Docker
import allowlist. Sprint 5 declines the option to make the Verifier LLM-backed
(constitutionally permitted by the v2.2.0 clarification), keeping the agent
deterministic — see Out of Scope and US2.

### Principle II — Self-Healing First (MTTR Reduction)

Sprint 5 replaces deterministic mocks with real reasoning, so MTTR numbers
recorded by the benchmark (US5) become operationally meaningful for the first
time. The benchmark's three-metric triplet (latency / cost / resolution rate)
makes MTTR-relevant signals first-class, supporting Principle II's reporting
requirement.

### Principle III — Test-First (NON-NEGOTIABLE)

Sprint 5 preserves the 100 % branch-coverage commitment by routing every LLM
call through a substitutable test double at the LLM client layer (FR-504).
Test files for new modules MUST exist and be confirmed failing before
implementation, consistent with Sprint 4 SC-006's gate.

### Principle IV — Observability & Distributed Tracing

FR-509 / FR-510 / FR-511 / FR-512 directly implement Principle IV at the LLM
boundary: a single `trace_id` propagates across all agents, every LLM call
becomes a child span, and project/component tagging makes incident traces
identifiable in the LLMOps Dashboard.

### Principle V — LLM Reasoning Reliability

Sprint 5 closes `TODO(SPRINT5_KEYWORD_REMOVAL)` by replacing the mock-phase
keyword-list trigger with real LLM reasoning subject to the outcome-level
invariants codified in v2.2.0:
- (a) Coverage — the SecurityReviewer continues to gate every fix artifact
  (Sprint 4 invariant, preserved).
- (b) Interrupt obligation — `HIGH_RISK` verdicts continue to issue
  `interrupt()`, now durable across processes (FR-513 / FR-514).
- (c) Auditability — classifier identity (model name) and reasoning are
  persisted to the trace (FR-510 / FR-512).

`SC-013`'s strict false-negative-equals-zero requirement is the operational
expression of these invariants on the SECURITY-category benchmark subset.
**Sprint 5 does NOT close `TODO(SPRINT6_V1_RETIREMENT)`**; v1 nodes remain
grandfathered.

### Principle VI — Multi-Agent Governance

Sprint 5 changes how agents reason but not how they communicate. All inter-agent
flow continues through LangGraph state channels (Sprint 4 FR-003). The
Supervisor remains the sole router (US2). The SecurityReviewer remains the sole
gate before the Verifier (Sprint 4 invariant, preserved by SC-015's
non-regression requirement).

### Principle VII — LLM Provider Boundary & Cost Governance

This is the principle Sprint 5 most directly operationalises. Each sub-clause
maps to the Sprint 5 requirements that fulfil it:

- **VII.1 — LLM Provider Isolation (AST-enforced)**: FR-501 / FR-502 confine
  provider SDK imports to the LLM client abstraction layer; an AST-walking CI
  check enforces the boundary. v1-pipeline modules remain grandfathered as
  permitted by the constitution; the boundary check's allowlist tracks them
  explicitly.
- **VII.2 — Cost Guard Is Non-Negotiable**: FR-505 / FR-506 / FR-507 / FR-508
  ensure every LLM request passes through `CostGuard`, that the guard reads
  budgets from the environment, that exceeding the budget raises a typed
  pipeline-aborting error, and that per-call cost telemetry reaches the
  LLMOps Dashboard.
- **VII.3 — Trace Propagation Is Mandatory**: FR-509 / FR-510 / FR-511 require
  that `trace_id` originate at the incident entry point, propagate through
  `AgentState`, and reach the LLM client at every agent boundary without being
  dropped or regenerated.
- **VII.4 — Model-Routing Configuration Is Declarative**: FR-502 forbids
  hard-coding model identity inside agent `run()` methods; per-agent model
  assignment is sourced from environment or configuration only.

### Sprint 4 non-regression (binding)

Sprint 5 MUST NOT introduce a regression in any Sprint 4 acceptance scenario
`SC-001` through `SC-005`. This is captured operationally as `SC-015`. In
particular, the multi-agent topology, the security-gate enforcement, the
Verifier-as-sole-Docker-executor boundary, the 100 %-coverage Test-First gate,
and the smoke-benchmark v2 ≥ v1 resolution-rate property MUST all continue to
hold after Sprint 5 is merged.

---

## Open Questions

The following are spec-level questions that MUST be resolved before `/plan` is
run. They are explicitly out of scope for the spec itself; recording them here
keeps the deferral auditable.

Question 1 (Verifier-LLM scope) was resolved during spec review: path (a) —
Verifier stays deterministic. See US2 and Out of Scope.

1. **Precise SC threshold values.**
   The conservative ranges in this spec (e.g., `≥ 70 %` routing accuracy in
   SC-009) are deliberately loose, leaving room for `plan.md` and early
   benchmark calibration to set sharper numbers without forcing a spec
   amendment. The exception is `SC-013`'s false-negative count, which is fixed
   at `= 0` because Principle V's outcome invariants admit no slack.
   **Resolution target**: post-`/plan`, after preliminary benchmark calibration
   data is available; sharpened values to be reflected in `tasks.md` SC
   verifications, not in this spec.
2. **Ground-truth labelling collaboration flow.**
   FR-517 forbids AI-generates-and-AI-verifies for the 50-scenario ground-truth
   set. The concrete process — who labels, how disagreements are resolved,
   what artefact records the labelling decision, where the labelled set is
   stored — is undecided. **Resolution target**: before benchmark-extension
   work begins; documented either in this spec under a future revision or in a
   companion artefact under `specs/005-real-llm-integration/`.
