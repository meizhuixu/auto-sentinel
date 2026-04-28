<!--
SYNC IMPACT REPORT
==================
Version change: 2.0.0 → 2.1.0 (MINOR — new Principle VI added; Principles I and V
extended with multi-agent governance constraints)

Modified principles:
  - I.   AI Agent Sandboxing       — extended: Verifier-only Docker access rule added;
                                     CI enforcement requirement specified (AST-level tool,
                                     canonical path as hint only, allowlist in CI config)
  - V.   LLM Reasoning Reliability — extended: LangGraph interrupt() for HIGH_RISK fixes;
                                     mock-phase keyword trigger list (destructive commands
                                     only); keyword list removal required in Sprint 5

Added principles:
  - VI.  Multi-Agent Governance    — BaseAgent interface (AgentState → AgentState);
                                     state-channel-only communication; Security Reviewer
                                     gate; Supervisor as sole router

Added requirements:
  - Agent Execution Requirements: human_approval_required log event obligation;
    interrupt() hard-guarantee semantics; logging-failure fallback

Removed sections: none

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
  - TODO(SPRINT5_KEYWORD_REMOVAL): Remove mock-phase HIGH_RISK keyword list from
    Principle V when real LLM classification is wired in (Sprint 5).
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

During the mock phase (Sprint 4), high-risk classification MUST be triggered by
the presence of any of the following keywords in the fix artifact: `DROP TABLE`,
`DROP DATABASE`, `TRUNCATE TABLE`, `rm -rf /`, `rm -rf ~`, `chmod 777`, `mkfs`,
`dd if=`. This keyword-based trigger is a temporary surrogate and MUST be removed
in Sprint 5 when real LLM classification is wired in.

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
the Verifier Agent. The Security Reviewer MUST classify each fix as SAFE, CAUTION,
or HIGH_RISK. HIGH_RISK fixes MUST NOT proceed without a LangGraph interrupt
approval (see Principle V).

The Supervisor Agent is the sole router. It MUST select specialist agent(s) based
on the Diagnosis Agent's `error_category` output and MUST arbitrate conflicts by
always preferring the lower-blast-radius action, recording its reasoning in
AgentState.

**Rationale**: Without explicit governance, multi-agent systems drift toward tight
coupling — agents call each other directly, bypassing the audit trail that
LangGraph state channels provide. Centralising routing in the Supervisor makes
the decision graph inspectable and testable.

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

**Version**: 2.1.0 | **Ratified**: 2026-04-24 | **Last Amended**: 2026-04-28
