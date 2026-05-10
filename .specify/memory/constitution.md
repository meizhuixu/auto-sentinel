<!--
SYNC IMPACT REPORT
==================
Version change: 2.1.1 → 2.2.0 (MINOR — new Principle VII added for LLM provider
boundary and cost governance; Principle V refactored from keyword-list implementation
detail to outcome-level invariants; Principle I clarified for Verifier LLM execution
boundary. Driven by Sprint 5 real-LLM integration, see specs/005-real-llm-integration/.)

Modified principles:
  - I.   AI Agent Sandboxing          — v2.2.0 MINOR: clarification that LLM API
                                        calls (e.g. from a Verifier that summarises
                                        Docker output via LLM) MUST execute outside
                                        the sandbox container. No change to the
                                        Verifier-only Docker import boundary.
  - V.   LLM Reasoning Reliability    — v2.2.0 MINOR: mock-phase keyword-list trigger
                                        removed (TODO(SPRINT5_KEYWORD_REMOVAL) closed);
                                        replaced with outcome-level invariants for
                                        Security Reviewer (binary verdict, 100%
                                        coverage, interrupt() on HIGH_RISK, audit
                                        trail). Mechanism is now implementation-
                                        agnostic (keyword scan, LLM semantic review,
                                        rule engine, etc. all permitted).

Added principles:
  - VII. LLM Provider Boundary &      — Four sub-clauses:
         Cost Governance                VII.1 LLM Provider Isolation (AST-enforced):
                                              only src/auto_sentinel/llm/** may import
                                              LLM SDKs; v1 pipeline grandfathered.
                                        VII.2 Cost Guard Is Non-Negotiable: every
                                              outbound LLM request passes CostGuard;
                                              budget threshold from env, never
                                              hard-coded.
                                        VII.3 Trace Propagation Is Mandatory: every
                                              LLM call accepts external trace_id and
                                              forwards to LLMTracer.
                                        VII.4 Model-Routing Configuration Is
                                              Declarative: no in-agent hard-coding
                                              of endpoint or model name.

Removed clauses:
  - Principle V mock-phase HIGH_RISK keyword list (DROP TABLE / rm -rf / chmod 777
    / etc.) — superseded by outcome-level invariants. Keyword scanning remains a
    permissible mechanism but is no longer mandated by the constitution.

Templates requiring updates:
  - .specify/templates/plan-template.md  ✅ no structural changes required
  - .specify/templates/spec-template.md  ✅ no structural changes required
  - .specify/templates/tasks-template.md ✅ no structural changes required

Follow-up TODOs (carried forward):
  - TODO(RATIFICATION_APPROVERS): List team members who ratified this constitution
    once the team is assembled.
  - TODO(COMPLIANCE_REVIEW_CADENCE): Confirm quarterly vs. bi-annual review schedule
    once the project reaches production.
  - TODO(MTTR_TARGETS): Define per-service-class MTTR targets (e.g., P1 services
    < 5 min, P2 < 15 min) once the service catalogue is established.
  - TODO(LLM_CONFIDENCE_THRESHOLD): Set the numeric confidence threshold below which
    an agent MUST escalate to human-in-the-loop rather than self-heal automatically.
  - TODO(SPRINT6_V1_RETIREMENT): Remove the v1-pipeline grandfathering exemption from
    Principle VII.1 (and the Principle I Docker grandfathering list) when the v1
    LangGraph pipeline is retired.
-->

# AutoSentinel Constitution

## Core Principles

### I. AI Agent Sandboxing

Every AI agent MUST execute inside an isolated Docker container with a read-only
filesystem except for explicitly declared write paths. Containers MUST run as
non-root users and MUST have CPU, memory, and network egress limits set. Agent
actions that mutate production state (restart, scale, rollback) MUST be declared
in a typed action manifest before the agent is deployed; undeclared actions MUST
be rejected at runtime. Agents MUST NOT share container namespaces with other
agents or with host processes.

In a multi-agent system, only the Verifier Agent is permitted to instantiate
Docker containers via the Docker SDK. All other agents MUST NOT import or invoke
the Docker SDK directly. This constraint MUST be enforced by (a) code review, and
(b) an automated check in CI that fails the build if any module other than the
`verifier` agent module imports `docker` or any submodule thereof, where the
`verifier` agent module is the single Python module designated as the Verifier
Agent's implementation (canonical location: `src/autosentinel/agents/verifier/`).
The exact import-path allowlist MUST be specified in the CI check configuration.
The check MAY be implemented via `ruff` custom rule, `import-linter`, or an
equivalent AST-level tool — `grep` is insufficient.

**Grandfathering clause (v2.1.1)**: Existing v1 LangGraph nodes (Sprint 3 era) that
pre-date this constraint MAY continue to import `docker` until the v1 pipeline is
retired. The CI allowlist MUST list each grandfathered module by full path; new
modules MUST NOT be added to this allowlist without a constitution amendment. The
current grandfathered list is: `autosentinel/nodes/execute_fix.py` (v1 execute_fix
node, retained for benchmark v1/v2 comparison; will be removed when v1 pipeline is
retired in Sprint 6 or later).

**LLM-execution boundary (v2.2.0)**: When an agent (e.g. the Verifier Agent
summarising Docker output, or any agent that consumes container logs) issues an
LLM API call, the LLM call itself MUST execute outside the sandbox container. The
agent's orchestration logic — including Docker SDK usage and any subsequent LLM
request — runs in the host process; only the workload under verification runs
inside the sandbox. Issuing outbound LLM API requests from inside a network-
restricted sandbox is prohibited and would deadlock the pipeline.

**Rationale**: Unbounded agent execution in a distributed environment can cascade
failures faster than any human can intervene. Sandboxing is the hard boundary
that keeps an agent's blast radius predictable and auditable.

### II. Self-Healing First (MTTR Reduction)

The primary success metric for every remediation feature is Mean Time To Recovery
(MTTR). Automated detection-to-remediation pipelines MUST be designed to close
incidents without human intervention for all pre-classified failure modes. Every
self-healing action MUST include a rollback path that is tested in CI. MTTR targets
MUST be defined per service class before a self-healing rule enters production.
Partial self-healing (reducing severity without full recovery) counts as success
and MUST be reported as a distinct metric.

**Rationale**: Reducing MTTR—not simply detecting problems—is the core value
AutoSentinel delivers to operators of distributed microservices.

### III. Test-First (NON-NEGOTIABLE)

Tests MUST be written and confirmed failing before any implementation code is
written (Red → Green → Refactor). Every self-healing scenario MUST have a
corresponding integration test that injects the failure condition and asserts the
expected recovery action and post-recovery state. Agent behaviour tests MUST cover
both the happy path (successful remediation) and the abort path (rollback triggered).
Integration tests MUST run against real containerised dependencies in CI to catch
contract drift between agents and the services they manage.

**Rationale**: An agent whose healing logic was never verified failing is an agent
that may silently do nothing—or the wrong thing—under real incident conditions.

### IV. Observability & Distributed Tracing

Every subsystem MUST emit structured logs (JSON) with a consistent schema:
timestamp, severity, component, correlation ID, trace ID, and event payload.
Distributed traces MUST be propagated across all agent-to-service and
service-to-service calls using W3C Trace Context headers. MTTR dashboards MUST
be the canonical view for incident response; they MUST display detection time,
agent activation time, and recovery time as separate spans. Anomaly detection
signals MUST be enriched with the relevant trace before being handed to an agent,
so the agent reasons on correlated evidence rather than isolated metrics.

**Rationale**: In a distributed system, a log line without a trace ID is an
orphan. Observability is the substrate on which every self-healing decision is
made; degraded observability directly degrades healing quality.

### V. LLM Reasoning Reliability

LLM-generated remediation plans MUST be validated against the typed action
manifest (Principle I) before execution; plans that reference undeclared actions
MUST be rejected. Every LLM call that produces an action plan MUST include a
structured output schema; free-form text responses MUST NOT be parsed as
executable instructions. A numeric confidence score MUST accompany every agent
recommendation; plans below the project-defined threshold MUST escalate to
human-in-the-loop review rather than execute automatically. Prompt templates
that encode remediation logic MUST be versioned and tested like source code.

High-risk remediation categories — defined as any fix that modifies production
configuration, issues database write operations, or touches secrets/credentials —
MUST trigger a LangGraph interrupt() that suspends the pipeline and awaits
explicit human approval before the Verifier Agent is invoked. The high-risk
classification MUST originate from the Security Reviewer Agent and MUST be
recorded in AgentState.

The Security Reviewer Agent MUST emit a binary verdict — `SAFE` or `HIGH_RISK` —
for every fix artifact that reaches it. The internal classification mechanism is
implementation-agnostic: keyword scanning, LLM semantic review, deterministic rule
engines, or any combination thereof are permitted, provided the following outcome-
level invariants hold:

(a) **Coverage**: 100 % of fix artifacts produced by any specialist agent MUST
    pass through the Security Reviewer before reaching the Verifier Agent. No
    bypass path is permitted, including for "obviously safe" fixes.
(b) **Interrupt obligation**: A `HIGH_RISK` verdict MUST cause the LangGraph
    pipeline to issue `interrupt()` and suspend until human approval is recorded
    in `AgentState`. The Verifier Agent MUST NOT be invoked on a `HIGH_RISK` fix
    that has not been approved.
(c) **Auditability**: Every verdict MUST be persisted to the trace stream with
    enough context to reconstruct the decision in post-incident review — at
    minimum: the fix artifact hash, the verdict, the classifier identity (model
    name or rule-engine version), and any intermediate reasoning the classifier
    exposes. A verdict that cannot be replayed from the trace is non-compliant.

**Rationale**: LLM reasoning can hallucinate plausible-sounding but incorrect
remediation steps. Guardrails at the execution boundary, not just at generation
time, are the only reliable way to prevent an LLM mistake from becoming a
production incident.

### VI. Multi-Agent Governance

All specialist agents MUST implement a common BaseAgent interface that exposes a
single `run(state: AgentState) -> AgentState` method, where `AgentState` is a
Pydantic V2 model or a `TypedDict` compatible with LangGraph's state channel
reducer. Returning a bare `dict` is prohibited. Agents MUST NOT expose other
public methods for inter-agent invocation.

Agent communication MUST flow exclusively through LangGraph state channels
(TypedDict fields). Direct Python method calls between agent instances are
prohibited; violations MUST be caught in code review.

Every fix artifact MUST pass through the Security Reviewer Agent before reaching
the Verifier Agent. The Security Reviewer MUST classify each fix as SAFE or
HIGH_RISK (per Principle V). HIGH_RISK fixes MUST NOT proceed without a LangGraph
interrupt approval (see Principle V).

The Supervisor Agent is the sole router. It MUST select specialist agent(s) based
on the Diagnosis Agent's `error_category` output and MUST arbitrate conflicts by
always preferring the lower-blast-radius action, recording its reasoning in
AgentState.

**Rationale**: Without explicit governance, multi-agent systems drift toward tight
coupling — agents call each other directly, bypassing the audit trail that
LangGraph state channels provide. Centralising routing in the Supervisor makes
the decision graph inspectable and testable.

### VII. LLM Provider Boundary & Cost Governance

This principle governs how AutoSentinel agents reach LLM providers. It exists to
preserve provider-agnosticism, enforce cost ceilings, and keep multi-agent traces
correlated end-to-end.

**VII.1 — LLM Provider Isolation (AST-enforced)**

Only modules under `src/auto_sentinel/llm/` (the LLM client abstraction layer) MAY
import an LLM provider SDK (`openai`, `anthropic`, or any equivalent). All six
specialist/orchestrator agent modules (Diagnosis, Supervisor, CodeFixer, InfraSRE,
SecurityReviewer, Verifier) MUST consume LLM functionality exclusively through the
`LLMClient` abstraction; direct SDK imports from agent modules are prohibited.

This constraint MUST be enforced by an automated CI check that walks the AST of
each non-allowlisted module and fails the build on any LLM SDK import. The check
MUST be implemented in `tests/unit/test_llm_sdk_import_boundary.py` using stdlib
`ast.walk()`, in parallel with the existing `test_docker_import_boundary.py`. The
allowlist MUST be specified in the test's configuration; `grep` is insufficient.

**Grandfathering clause (v2.2.0)**: The v1 pipeline modules under
`src/auto_sentinel/nodes/` (e.g. `analyze_error.py`) MAY continue to import
`anthropic` until the v1 pipeline is retired. The grandfathered list MUST be
explicit in the boundary test's allowlist; new modules MUST NOT be added without
a constitution amendment. Removal is tracked as `TODO(SPRINT6_V1_RETIREMENT)`.

**VII.2 — Cost Guard Is Non-Negotiable**

Every outbound LLM request — without exception — MUST pass through `CostGuard.check()`
before the SDK call is issued. The `CostGuard` component MUST:

- Track cumulative spend across all agents within a single pipeline run, and
  optionally across a configurable window (e.g. per-day) for global ceilings.
- Raise a typed `CostGuardError` when a configured threshold is reached; the error
  MUST propagate to the LangGraph orchestrator and abort the pipeline cleanly
  rather than silently truncate output.
- Read budget thresholds from the environment variable `AUTOSENTINEL_LLM_BUDGET_USD`
  (and any companion variables for sub-budgets). Hard-coding budget values in
  source code is prohibited.
- Expose a testing-mode injection point for mock budgets so the cost-guard logic
  itself can be exercised under Test-First (Principle III) without real spend.

This sub-clause is **NON-NEGOTIABLE** — equal in strength to Principle III. A PR
that adds an LLM call path bypassing `CostGuard` is rejected on sight.

**VII.3 — Trace Propagation Is Mandatory**

`LLMClient.complete()` (and any equivalent entry point on the LLM abstraction)
MUST accept an external `trace_id: str | None = None` parameter and MUST forward
it to the `LLMTracer` so every LLM call is correlatable with (a) the originating
LangGraph state at the time of the call, and (b) the upstream trace surfaced on
the LLMOps Dashboard. Agents MUST pass the trace ID from `AgentState` into every
LLM call they issue; dropping the trace ID at any agent boundary is a violation.

**VII.4 — Model-Routing Configuration Is Declarative**

Which LLM model an agent uses MUST be expressed declaratively — in a configuration
module (e.g. `src/auto_sentinel/llm/config.py`) or via environment variables —
never hard-coded inside an agent's `run()` method. Endpoint base URLs (e.g. the
provider gateway) MUST be configurable via environment variable so that switching
providers requires zero code change in agent modules. Agents MUST resolve their
model assignment by name through the configuration layer at construction time.

**Rationale**: Locking provider SDK access to a single layer keeps the codebase
provider-agnostic — switching from one gateway to another is an env-var change,
not a refactor. Cost guarding at the abstraction boundary is the only place where
a single check covers every agent. Trace propagation through the same layer makes
multi-agent LLM behaviour debuggable; without it, the LLMOps Dashboard sees
disconnected fragments instead of one coherent run.

## Agent Execution Requirements

- All inter-agent and agent-to-service communication MUST use TLS 1.2 or higher.
- Sensitive fields in log output (tokens, passwords, PII) MUST be redacted before
  writing.
- Agent container images MUST be rebuilt and rescanned on every dependency update;
  images with critical CVEs MUST NOT be deployed.
- All database queries issued by agents MUST use parameterized statements; no
  string-concatenated SQL is permitted.
- Agent action manifests MUST be stored in version control and reviewed as part of
  the PR that introduces or modifies the agent.
- High-risk remediation requests MUST emit a structured log event with field
  `event: "human_approval_required"` before `LangGraph interrupt()` is issued,
  ensuring the approval request is traceable in the structured log stream even if
  the pipeline is later abandoned or timed out. If the log emission itself fails
  (exception raised by the logging handler), the pipeline MUST still issue
  `interrupt()`, and the failure MUST be re-raised after the interrupt is
  registered. Approval traceability is a soft guarantee; pipeline suspension is a
  hard guarantee.

## Development Workflow

- Every feature MUST start with a specification in `specs/` before any code is
  written.
- PRs MUST pass all CI checks (lint, type check, tests, container build) before
  review is requested.
- At least one peer review is REQUIRED for all changes; changes to agent logic or
  self-healing pipelines REQUIRE two reviewers.
- Complexity deviations from this constitution MUST be documented in the plan's
  Complexity Tracking table with explicit justification; undocumented deviations
  are grounds for PR rejection.
- Each merged PR MUST include a test that covers the primary acceptance scenario
  defined in the feature spec.

## Governance

This constitution supersedes all other development practices and informal
conventions. Any practice not addressed here defaults to the principle that best
serves reliability, observability, and agent safety.

**Amendment procedure**: Amendments MUST be proposed as a PR that updates this
file, increments the version per semantic versioning rules (MAJOR for removals/
redefinitions, MINOR for additions, PATCH for clarifications), and is approved by
at least two project maintainers. The `LAST_AMENDED_DATE` MUST be updated to the
merge date.

**Versioning policy**: MAJOR.MINOR.PATCH following the semantic rules above.
Version history is tracked in git; no separate changelog is required for the
constitution.

**Compliance review**: Compliance with this constitution MUST be verified during
every PR review. A full constitution review MUST be conducted at least once per
quarter to assess whether principles remain current with the project's agent
capabilities and service scale.

**Version**: 2.2.0 | **Ratified**: 2026-04-24 | **Last Amended**: 2026-05-07
