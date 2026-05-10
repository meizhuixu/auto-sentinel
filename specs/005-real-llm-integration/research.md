# Research: Sprint 5 — Real LLM Integration

Each decision is recorded with **Decision / Rationale / Alternatives Considered /
Consequences**. Decisions 1–8 are architectural; 9–10 close the two Open
Questions left at the end of `spec.md`.

---

## Decision 1 — OpenAI SDK + Volcano-Engine Ark base_url (vs. Volcano native SDK)

**Decision**: Use the official `openai` Python SDK with `base_url` pointed at
`https://ark.cn-beijing.volces.com/api/v3` (and at `https://open.bigmodel.cn/api/paas/v4`
for GLM). Do not use Volcano's native `volcengine-python-sdk-ark-runtime` package.

**Rationale**: Both Volcano-Engine Ark and Zhipu BigModel implement the OpenAI
Chat Completions wire format, which means a single `openai.OpenAI` client class
(one instance per `base_url`) covers both providers and stays portable. The
provider-isolation boundary at `autosentinel/llm/` becomes a **single** SDK to
allow-list in the AST CI check, instead of two. CV/résumé portability matters:
"OpenAI SDK against multiple base_urls" is a transferable skill; Volcano's
native SDK is region-specific.

**Alternatives Considered**:
- Volcano native SDK: deeper feature support (e.g. signed urls for batch jobs)
  but locks the codebase to one regional vendor.
- Two distinct SDKs (Volcano native + Zhipu native): doubles the AST allowlist
  and forces two retry/timeout policies.
- LangChain's chat-model abstractions: another layer of indirection for no
  Sprint-5 benefit.

**Consequences**: One SDK to import, one retry policy (`tenacity`) covering both
providers, one allowlist entry in `test_llm_provider_isolation.py`. If a
Volcano-only feature is needed later (e.g. batch inference), it's encapsulated
in `ArkLLMClient` only.

---

## Decision 2 — GLM-4.7 for SecurityReviewer (vs. DeepSeek-R1)

**Decision**: SecurityReviewer uses Zhipu **GLM-4.7** (a reasoning model). All
other LLM-backed agents use Volcano **doubao-seed-2.0-pro** (general) or
**doubao-1.5-lite-32k** (Supervisor — fast routing).

**Rationale**: SecurityReviewer is the agent where a false-negative is most
costly — SC-013 demands `false_negative_count == 0` on the SECURITY subset.
A reasoning model is the right tool: it spends test-time compute on the
classification rather than emitting a single-pass verdict. DeepSeek-R1 was the
obvious peer, but Volcano-Engine Ark publicly announced upcoming deprecation /
limited availability for R1; pinning Sprint 5 to a model that's about to be
EOL'd is unstable. GLM-4.7 is currently available at first-party Zhipu
endpoint, comparable reasoning quality to R1 on classification tasks.

**Alternatives Considered**:
- DeepSeek-R1 on Volcano: pending deprecation; rejected.
- doubao-seed-2.0-pro for SecurityReviewer: cheaper, but it is not a reasoning
  model, raising false-negative risk.
- claude-3.7-sonnet via API: best classification quality, but bills in USD
  rather than RMB and is not reachable from the China region without a proxy
  layer; out of Sprint 5 scope.

**Consequences**: Two endpoints (`ark` + `glm`) instead of one, but the
factory + `model_routing.yaml` already accommodates that. SecurityReviewer
spans run noticeably longer (reasoning latency); offset by the rest of the
pipeline being fast doubao calls.

---

## Decision 3 — Verifier remains deterministic (path (a))

**Decision**: The Verifier agent is **NOT** LLM-backed in Sprint 5. It keeps
the Sprint 4 implementation: Docker sandbox execution, pass/fail by container
exit code.

**Rationale**: Verifier's job is binary verification — does the proposed fix
make the workload pass tests? Container exit code answers this
deterministically and cheaply. An LLM call would add cost and latency without
changing the verdict. Constitution v2.2.0 Principle I makes LLM-backed Verifier
*permissible* (LLM call would run outside the sandbox), but Sprint 5
deliberately declines that option. This is also a clean résumé/architecture
talking-point: "selective LLM application — judgment uses LLMs, deterministic
verification doesn't."

**Alternatives Considered**:
- LLM Verifier that classifies non-traceback failures: real value if pytest
  output is ambiguous — but Sprint 5 incident corpus is exit-code-clean.
  Reconsider in Sprint 6+ if the corpus changes.
- Hybrid: deterministic pass + LLM-only if exit code unclear: extra surface,
  not justified by current data.

**Consequences**: Verifier stays in the Docker import allowlist (single
allowed Docker SDK consumer). Constitution VII.4 doesn't apply to Verifier
(no model name to declare). Spec Out-of-Scope item resolved.

---

## Decision 4 — Two endpoints, five LLM agents (vs. per-agent endpoints)

**Decision**: Two `base_url` instances total — `ark` (shared by Diagnosis,
Supervisor, CodeFixer, InfraSRE) and `glm` (SecurityReviewer only). Five LLM
agents share these two `OpenAI` client instances via the factory.

**Rationale**: One `openai.OpenAI` instance ↔ one `base_url` is the SDK's
intended granularity. Reusing one Ark client across four agents reduces
connection setup cost (httpx connection pool reuse) and stays well under any
per-API-key rate limit at our request volume (≤ 50 scenarios/run × 5 agents =
250 requests/run). No need to fragment into per-agent clients. Per-agent
config (model + temperature + max_tokens) is decoupled from the client itself
and lives in `model_routing.yaml`.

**Alternatives Considered**:
- One client per agent (5 instances): no rate-limit benefit, more memory, more
  config to manage.
- Single endpoint with all agents on one model (e.g. doubao-seed-2.0-pro for
  SecurityReviewer too): rejected by Decision 2.

**Consequences**: `factory.py` builds two `OpenAI` instances at startup, caches
them in a module-level dict, and returns wrapper objects (`ArkLLMClient` /
`GlmLLMClient`) bound to the correct instance + per-agent config. If we later
hit per-key rate limits, splitting requires only a config change.

---

## Decision 5 — Dedicated PostgresSaver container (vs. reusing Langfuse Postgres)

**Decision**: Sprint 5 spins up its own `postgres:16` container named
`auto-sentinel-checkpointer` on `localhost:5433`. It does **not** reuse the
project-4 Langfuse Postgres on `5432`.

**Rationale**: Service-boundary cleanliness. AutoSentinel's checkpointer state
is operationally distinct from the LLMOps observability database — different
backup cadence, different blast radius, different team mental model. Sharing
the Langfuse Postgres also creates a port collision (both default to 5432) and
muddies the cross-project ownership story when one repo's outage takes down
the other. Two ports, two compose files, two volume mounts — the small
duplication buys clean failure isolation.

**Alternatives Considered**:
- Reuse Langfuse Postgres at 5432 with a separate database: technically works,
  but couples AutoSentinel pipeline state to the observability stack's
  uptime.
- SQLite-on-disk via `langgraph-checkpoint-sqlite`: viable for single-process,
  but does not meet FR-513's "out-of-process backing store" intent and
  complicates the cross-process resume test (process B locking process A's
  file).

**Consequences**: Operators learn a second port (5433). Backups are independent
— a Langfuse DB dump does NOT include AutoSentinel checkpoint state and vice
versa. One extra `docker compose up` invocation in quickstart.

---

## Decision 6 — In-process CostGuard state (vs. Redis)

**Decision**: `CostGuard` is a module-level singleton with a `threading.Lock`.
State (`total_spent_usd`, `call_count`, `last_updated`) lives in process memory
and resets on restart.

**Rationale**: Sprint 5 is single-process. The benchmark runner is a single
batch job. The FastAPI server is a single uvicorn worker. There is no scenario
in Sprint 5 where two processes need to share a budget view. Adding Redis
purely so the budget survives a restart would be over-engineering; restart
implies a fresh pipeline run anyway. If we ever scale to multi-worker uvicorn
or distributed runners, Sprint 6+ will trade up to Redis (or `PostgresSaver`
itself, since we'll already have a Postgres) — but that's not Sprint 5's
problem.

**Alternatives Considered**:
- Redis singleton: adds a third infra container, adds a network hop on every
  LLM call, adds a failure mode (Redis-down ⇒ pipeline-down).
- Postgres-backed counter (re-using the checkpointer DB): writes on every LLM
  call doubles the checkpointer's write load for no Sprint-5 benefit.

**Consequences**: A pipeline restart in the middle of a run resets the budget
counter. This is acceptable because the user's ¥150 cap is per-day operational,
not per-call-stream — a restart implies a new run. The contract documents this
as a deliberate trade-off (`contracts/cost-guard.md`).

---

## Decision 7 — `trace_id` generated at FastAPI ingest (vs. inside LLMTracer)

**Decision**: The single generation point for `trace_id` is the FastAPI
`ingest_alert` endpoint. The LLM client and the LLMTracer **never** generate a
`trace_id` themselves.

**Rationale**: Cross-service correlation requires the ID to be born at the
*request* boundary — the moment an external caller crosses into our system —
so every downstream span can be correlated regardless of which service made
the call. Project-4's `LLMTracer` already supports an externally-injected
`trace_id` (validated at `tracer.py:51` against `^[0-9a-f]{32}$`); when not
supplied it self-generates and sets `_owns_trace = True`. We always supply, so
`_owns_trace = False` everywhere — multi-agent spans correctly nest under one
parent trace. This also positions us for project-3 Phase 2, when the same
`trace_id` will need to thread further into the DevContext MCP server boundary.

**Alternatives Considered**:
- Let LLMTracer self-generate: each LLM call gets its own parent trace, no
  multi-agent correlation possible.
- Generate inside the LangGraph dispatch (after the queue): loses the link
  back to the inbound HTTP request; observability dashboards can't correlate
  the alert with downstream LLM spans.

**Consequences**: `trace_id` becomes a mandatory field in the alert payload
internal representation between FastAPI and LangGraph. Empty / malformed
`trace_id` reaching the LLM client surfaces as a `ValueError` from the
LLMTracer constructor — this is the contract-test we lean on.

---

## Decision 8 — yaml-per-file scenarios (vs. single jsonl)

**Decision**: Each of the 50 benchmark scenarios is its own yaml file under
`benchmarks/scenarios/<NNN>_<category>_<slug>.yaml`. The runner globs the
directory at startup.

**Rationale**: 50 scenarios is the threshold where review/diff ergonomics
start to dominate batch-load performance. A single jsonl file gives 50 lines
of JSON in one diff — hard to review in a PR, hard to spot-check ground-truth
labels, and one merge conflict blocks all scenario edits. yaml-per-file means
each scenario is reviewable as an isolated artifact, supports per-scenario
git blame, and is friendly to the 3-tier authorship gate (the
`Scenario-Authored-By` trailer maps to the file added in the same commit).
Load performance is irrelevant — we're loading 50 small files once per
benchmark run, not on the request path.

**Alternatives Considered**:
- Single `scenarios.jsonl`: one diff conflict blocks all edits; reviewer can't
  see ground-truth labels in isolation.
- `scenarios.yaml` (one file, list of objects): same merge-conflict problem
  + worse readability than per-file yaml.
- Postgres table: scenarios become opaque to git history; rejected.

**Consequences**: 50 file additions in PR-5. CI scenario-authorship check
operates per-file (one PR can introduce 1 scenario or 50 — the gate works the
same). Migration is mechanical — 5 yamls match Sprint 4's inline `SCENARIOS`
exactly.

---

## Decision 9 — SC threshold sharpening (closes Open Question 1)

**Decision**: Lock the following SC threshold values in this plan; do **not**
defer to a post-`/plan` revision:

| SC | Metric | Threshold |
|---|---|---|
| SC-008 | end-to-end pipeline latency (p95, real LLM, full 50-scenario run) | **≤ 90 s** |
| SC-009 | resolution rate (passes Verifier) over 50 scenarios, v2 pipeline | **≥ 70 %** (35+ of 50) |
| SC-013 | SecurityReviewer false-negative count on SECURITY subset (8 scenarios) | **= 0** (non-negotiable) |

**Rationale**: Sprint 4's deterministic pipeline runs at ~25 s p95. Real LLM
introduces 5 LLM round-trips per scenario; doubao-seed-2.0-pro at ~3-5 s/call
+ a GLM-4.7 reasoning call at ~15-20 s gives a credible upper bound near 60-75 s
with retries. **90 s p95 sits one std-dev above that estimate**, leaving room
for outliers without padding the threshold so loose it becomes meaningless.
70 % resolution is the industry-typical floor for "the agentic pipeline is
beating chance" on multi-category fault injection; tighter thresholds will be
reset by Sprint 6+ once we have one full run of real data. SC-013's `= 0` is
not a Sprint-5 choice — it's the operational expression of Constitution
Principle V's invariants and is therefore not negotiable.

**Alternatives Considered**:
- Defer to post-calibration revision: the spec's Open Question 1 left this
  open, but doing so means no objective acceptance threshold exists during
  PR-5 review. Locking now is better.
- Tighter values (e.g. 60 s p95, 80 % resolution): risk Sprint 5 failing for
  reasons unrelated to the architectural goal (e.g. a single slow Ark call).
- Looser values: meaningless as gate signals.

**Consequences**: `tasks.md` SC verification tasks reference these numbers
directly. If the first full run produces (say) 65 % resolution, SC-009 fails
the gate — that's the desired behaviour.

---

## Decision 10 — Single-annotator ground-truth labelling (closes Open Question 2)

**Decision**: All 50 scenarios are labelled by **`meizhuixu`** as the sole
human annotator. Each yaml carries `human_labeled_by: meizhuixu`,
`labeled_at: YYYY-MM-DD`, and a free-text `ground_truth_notes` field. No
inter-annotator agreement step in Sprint 5.

**Rationale**: FR-517 forbids AI-generates-and-AI-verifies labelling but does
**not** require multi-annotator agreement. The benchmark's purpose in Sprint 5
is operational (informing v1/v2 retirement decisions), not academic
publication. A single qualified annotator suffices for that decision. The
3-tier authorship gate (PR template + commit trailer + CI script) protects
against AI-authored scenarios slipping through; that's the bar FR-517 actually
sets.

**Alternatives Considered**:
- Two-annotator agreement step: doubles labelling effort with no decision-grade
  signal added at Sprint 5's scope.
- LLM-assisted draft + human verification: explicitly forbidden by FR-517.

**Consequences**: If Sprint 6+ pursues an external publication, an
inter-annotator-agreement track will be added then with a separate annotator
pool. Sprint 5 is unblocked. The methodology is documented inside this
research file (this section), satisfying FR-517's audit requirement.

---

## Notes on residual risk

- **GLM-4.7 latency variance**: reasoning models have a bimodal latency
  distribution. SC-008's p95 budget allows for outliers but a sustained shift
  above 90 s would force a model-routing change. Tracked in plan.md as
  "if SC-008 fails, revisit Decision 2 (drop to a non-reasoning model on
  SecurityReviewer + add a deterministic post-filter) before relaxing the
  threshold."
- **CostGuard accuracy**: Ark and Zhipu return token usage in the response;
  we trust those numbers. If a future SDK quirk under-reports, CostGuard could
  silently undershoot the budget. Mitigation: `tests/integration/test_cost_guard_pipeline.py`
  asserts `summary.json.total_cost_usd` matches the sum of per-call costs in
  `results.jsonl`, catching drift.
