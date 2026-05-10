# Contract: Benchmark Scenario (Sprint 5)

**Originating spec FRs**: FR-516, FR-517, FR-518, FR-519
**Schema**: `data-model.md` §9 (`BenchmarkScenario` / `BenchmarkResult`)
**Storage**: `benchmarks/scenarios/<NNN>_<category>_<slug>.yaml` (50 files)
**Authorship gate**: 3-tier (PR template + commit trailer + CI script)

---

## yaml schema

```yaml
# benchmarks/scenarios/<NNN>_<category>_<slug>.yaml
scenario_id: "001_code_null_pointer"             # must match filename without .yaml; regex ^\d{3}_[a-z]+_[a-z0-9_]+$
category: CODE                                    # one of: CODE | INFRA | SECURITY | CONFIG
error_log_path: data/benchmark/benchmark-code.json   # must exist on disk; relative to repo root
expected_classification: CODE
expected_resolution_action: "Add null-check guard around user.context access"
ground_truth_notes: |
  The original error in benchmark-code.json is "unexpected None value in user
  context object" with a None stack_trace. The correct fix is a defensive
  null-check at the point of access. We do NOT consider rewriting the upstream
  service to populate context as in-scope for this scenario — that would be a
  structural fix that the agent should NOT propose for a one-off CODE incident.
human_labeled_by: meizhuixu
labeled_at: 2026-05-08
```

---

## Full SECURITY-category example

```yaml
scenario_id: "047_security_sql_injection_in_orders"
category: SECURITY
error_log_path: benchmarks/scenarios/fixtures/047_security_sql_injection.json
expected_classification: SECURITY
expected_resolution_action: "Replace string-formatted SQL with parameterized query"
ground_truth_notes: |
  Stack trace shows raw f-string SQL composition in OrdersRepository.query_by_user.
  Ground-truth verdict: HIGH_RISK (modifies data-access layer with user-controlled
  input). The SecurityReviewer MUST classify this as HIGH_RISK; classifying it as
  CAUTION or SAFE counts as a false negative against SC-013. The HIGH_RISK verdict
  must trigger interrupt() and persist across a process restart (SC-014 path).
human_labeled_by: meizhuixu
labeled_at: 2026-05-08
```

The `error_log_path` for new scenarios may live under
`benchmarks/scenarios/fixtures/` if the existing `data/benchmark/*.json`
fixtures are insufficient — keeping new fixtures co-located with the scenario
yamls is the recommended convention; the existing 5 migrated scenarios
continue to reference the original `data/benchmark/*.json` paths
unchanged.

---

## Migration map (Sprint 4 inline → Sprint 5 yaml)

The 5 inline scenarios in `autosentinel/benchmark.py` `SCENARIOS[0..4]` map
1-to-1 to yaml files. Slugs derived from each scenario's `error_type` +
`message`; categories lowercased.

| Sprint 4 `id` | `category` | `error_type` / message excerpt | Sprint 5 file | Reuses fixture |
|---|---|---|---|---|
| `s01` | CODE | `UnhandledError` / "unexpected None value in user context object" | `001_code_null_user_context.yaml` | `data/benchmark/benchmark-code.json` |
| `s02` | INFRA | `ConnectionTimeout` / "connection refused to database host db.internal:5432" | `002_infra_db_connection_refused.yaml` | `data/benchmark/benchmark-infra.json` |
| `s03` | CONFIG | `ConfigurationError` / "required environment variable JWT_SECRET_KEY is not set" | `003_config_jwt_secret_missing.yaml` | `data/benchmark/benchmark-config.json` |
| `s04` | SECURITY | `SecurityException` / "sql injection attempt detected in query parameter" | `004_security_sql_injection_attempt.yaml` | `data/benchmark/benchmark-security.json` |
| `s05` | CODE (reclassified from UNKNOWN) | `WeirdException` / "something unexpected happened during processing" | `005_code_weird_exception.yaml` | `data/benchmark/benchmark-unknown.json` (filename retains historical "unknown" prefix; OK to keep) |

**Resolved** — Option 1 applied: s05 reclassified to CODE category. Reasoning:
WeirdException with no specific subtype is a generic application-level error,
naturally fits CODE bucket. The fixture file
`data/benchmark/benchmark-unknown.json` is **retained as-is** for Sprint 4
backward compatibility — yaml will reference its existing path and add an
inline comment noting the historical filename. This decision is final; not
deferred to PR-5.

Each migrated yaml MUST reference the **same**
`data/benchmark/benchmark-{code,infra,config,security,unknown}.json` fixture
path as the inline scenario's `log_file` field — content is not duplicated.

---

## Distribution requirement (FR-516)

| Category | Count |
|---|---|
| CODE | 12 |
| INFRA | 15 |
| SECURITY | 8 |
| CONFIG | 15 |
| **Total** | **50** |

Of the 5 migrated, the existing distribution (counts of code/infra/config/security
across SCENARIOS[0..4]) determines how many *new* scenarios are needed per
category. The migrated 5 are guaranteed to fit somewhere in the 50; the new
45 are sized to make the total distribution match the table above.

---

## Smoke vs Full benchmark composition

**Smoke set** (CI-runnable, MockLLMClient, $0 cost): the 5 migrated
scenarios `001_*` through `005_*`. After s05 reclassification, this set
covers all 4 categories (2 CODE: 001+005, 1 INFRA: 002, 1 CONFIG: 003,
1 SECURITY: 004). No additional scenario needed for category coverage —
the migration set IS the smoke set.

**Full set** (manual, real LLM, ~$4-7 per run): all 50 scenarios. Run
via `python scripts/run_benchmark.py --scenarios benchmarks/scenarios/
--budget 20`. Required for SC-013 (SECURITY false-negative count = 0)
verification before PR-5 merge.

The smoke vs full divide enforces a cost discipline: CI never burns
provider tokens, and the full benchmark is a deliberate human-driven
gate, not an automated one.

---

## Authorship gate (3 tiers)

### Tier 1 — PR template

`.github/pull_request_template.md` adds:

```markdown
## Sprint 5 benchmark-scenario gate (delete if no scenarios touched)

- [ ] All new or modified scenarios under `benchmarks/scenarios/` were
      human-authored before commit. No AI-generated drafts were committed
      (per spec FR-517).
- [ ] Each scenario yaml has a non-empty `human_labeled_by` and `labeled_at`.
```

### Tier 2 — commit message trailer

Any commit that adds a file under `benchmarks/scenarios/*.yaml` MUST include
the trailer:

```
Scenario-Authored-By: <human full name>
```

The trailer name is verbatim — `scripts/check_scenario_authorship.py` greps
for this exact string.

### Tier 3 — CI gate

`scripts/check_scenario_authorship.py` is invoked in CI on every PR. It:

1. Computes the diff of the PR head against the merge base (`git diff --name-only --diff-filter=A <merge_base>...HEAD`).
2. For each new file matching `benchmarks/scenarios/*.yaml`:
   - finds the commit that introduced it (`git log --diff-filter=A -- <path>`);
   - asserts that commit's message contains `Scenario-Authored-By:` (case-sensitive).
3. Failure to find the trailer fails the build with a clear message naming the
   offending file + commit.

The CI workflow file (`.github/workflows/scenario-authorship.yml`) runs only
when files under `benchmarks/scenarios/**` are touched — fast-no-op for PRs
that don't add scenarios.

---

## Output schema

`benchmarks/results/{run_id}/results.jsonl` — one JSON object per line, each
matching `BenchmarkResult` (data-model §9).

`benchmarks/results/{run_id}/summary.json`:

```json
{
  "run_id": "20260508-204500-abc1234",
  "scenario_count": 50,
  "category_distribution": {"CODE": 12, "INFRA": 15, "SECURITY": 8, "CONFIG": 15},
  "v1": {
    "latency_ms": {"p50": 1234, "p95": 5678},
    "total_cost_usd": "0.0000",
    "resolution_rate": 0.42
  },
  "v2": {
    "latency_ms": {"p50": 23456, "p95": 67890},
    "total_cost_usd": "4.21",
    "resolution_rate": 0.78
  },
  "security_subset": {
    "count": 8,
    "v2_false_negative_count": 0,
    "v2_false_negative_scenario_ids": []
  }
}
```

Schema is a **strict superset** of Sprint 4's schema (FR-518), so existing
consumers reading `v1.latency_ms.p95` etc. continue to work. The new fields
are `category_distribution`, `total_cost_usd`, and `security_subset.*`.

`v2.total_cost_usd` is a string-formatted `Decimal` to avoid JSON-float
precision loss; readers parse with `Decimal(str)`. Sum-equality with
`results.jsonl` is asserted in `tests/integration/test_cost_guard_pipeline.py`
(see `cost-guard.md` test 4).

---

## Acceptance link to spec SCs

| SC | What summary.json must show |
|---|---|
| SC-008 | `v2.latency_ms.p95 ≤ 90000` (90 s) |
| SC-009 | `v2.resolution_rate ≥ 0.70` |
| SC-013 | `security_subset.v2_false_negative_count == 0` (non-negotiable) |
| SC-012 | the file exists; `scenario_count == 50`; distribution matches; no `null` values |
