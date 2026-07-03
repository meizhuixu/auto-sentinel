# Contract: Fix Artifact (Producer ⇄ Verifier)

**Feature**: `006-fix-verification-integrity` | **Version**: 1 (Sprint 6)
**Parties**: producers `CodeFixerAgent`, `InfraSREAgent` → channel
`AgentState["fix_artifact"]` → consumer `VerifierAgent`
(SecurityReviewer reads the same field in between; it is a reader, not a party
that may transform the artifact).

## Definition

A **fix artifact** is a complete, standalone-runnable Python script:

1. `compile(artifact, "<fix>", "exec")` succeeds — no bare top-level
   `return` / `yield`, no unclosed blocks.
2. Self-contained: imports everything it uses; references no names from an
   implied enclosing scope.
3. Plain source text: no markdown fences, no explanations (existing
   `strip_markdown_fence()` stays as transport-level defense).
4. Exit semantics: process exit code 0 ⇔ the fix demonstrates success;
   non-zero ⇔ failure. (Sandbox judgment stays deterministic, Constitution I.)

## Producer obligations (best-effort layer)

- Prompts (`agents/prompts/code_fixer.py`, `infra_sre.py`) state the contract
  explicitly (standalone script, exit-code semantics, no fences).
- After fence-stripping, the producer validates with `compile()`. On
  `SyntaxError`: exactly **one** retry, appending the compile error to the
  user prompt. Retry goes through the same `LLMClient.complete()` path
  (CostGuard + trace_id apply; VII.2/VII.3).
- If the retry still fails to compile, the producer emits the artifact as-is
  (the Verifier fallback owns the last line of defense) — it never raises.

## Consumer obligations (deterministic layer)

- `VerifierAgent` calls `normalize_fix_artifact()` (pure, host-side) before
  any container work. Outcomes: `verbatim` → run as-is; `wrapped` (fragment
  symptoms only: `'return' outside function`, `'yield' outside function`) →
  run wrapped form; `rejected` (empty or unfixable SyntaxError) → return
  `ExecutionResult(status="failure")` **without** launching a container.
- Execution: artifact written to a host temp dir as `fix.py`, mounted
  read-only at `/workspace`, run as `["python", "/workspace/fix.py"]` in
  `python:3.10-alpine`, `mem_limit=64m`, `network_mode=none`, 5s wait,
  kill-on-timeout, force-remove — all pre-existing limits preserved.
- The normalization outcome is recorded (trace/agent context) so `wrapped`
  runs are auditable and countable (SC-001 measurement).

## Compatibility

- `AgentState["fix_artifact"]` stays `str | None` — no state-schema change,
  no migration. The contract governs the *content*, not the channel.
- Mock/benchmark fixtures (`expected_resolution_action`) must be
  contract-compliant scripts; scenario ground-truth *labels* are untouched
  (authored data — AI must not regenerate them).

## Breaking-change policy

Any change to the artifact definition or the fragment-symptom list requires a
new version of this contract file and simultaneous updates to both producer
prompts and the normalizer's tests.
