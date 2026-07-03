# Quickstart — Fix Verification Integrity & Pipeline Consolidation

**Feature**: `006-fix-verification-integrity`

## Dev environment (US5 fixes this section's own pitfall)

```bash
uv sync --extra dev          # NOT plain `uv sync` — pytest lives in the dev extra
docker compose -f infra/docker-compose.checkpointer.yml up -d   # :5434 checkpointer
uv run pytest                # full suite; checkpointer tests skip if 5434 is down
```

CI-parity run (checkpointer tests must execute, not skip):

```bash
AUTOSENTINEL_REQUIRE_CHECKPOINTER=1 uv run pytest
```

## Quality gate locally (mirrors `.github/workflows/ci.yml`)

```bash
uv run ruff check .
uv run mypy autosentinel
uv run pytest
```

## Exercising the fix-artifact contract (US1)

```bash
# Pure normalizer cases
uv run pytest tests/unit/test_artifact_normalizer.py -v
# Verifier file-mount execution + honest failure paths
uv run pytest tests/unit/test_verifier_agent.py -v
# Producer compile()-validation + single retry (MockLLMClient, ¥0)
uv run pytest tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py -v
# End-to-end on the fixture that reproduced the bug (requires ARK_API_KEY in .env):
# invoke the multi-agent graph on benchmarks/scenarios/fixtures/008_code_key_error_dict.json
# (e.g. via the README §Quickstart API flow) — the fix must execute in the
# sandbox (fix_normalization outcome recorded), not die of a format SyntaxError
```

## Benchmark (US2)

```bash
# Free smoke run — mock agents, real Verifier/Docker; failing fixes must count unresolved
uv run python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 150 --use-mock

# THE re-baseline run (PR-4 only, costs real CNY, run exactly once, needs developer go-ahead)
uv run python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 150
```

Results land in `benchmarks/results/<run_id>/{results.jsonl,summary.json}`;
`summary.json.pipeline.resolution_rate` + `resolved_definition` are what README
publishes.

## v1 retirement sanity (US4)

```bash
# no FUNCTIONAL references (comments documenting the retirement itself are fine)
grep -rn "AUTOSENTINEL_MULTI_AGENT\|DiagnosticState\|_run_v1" autosentinel scripts tests
# only the sync-impact "closed" note remains
grep -rn "SPRINT6_V1_RETIREMENT" .specify/memory/constitution.md
uv run pytest tests/unit/test_docker_import_boundary.py tests/unit/test_llm_provider_isolation.py -v
```

## Sprint-start guard (US5)

`setup-plan.sh` now refuses to overwrite an existing non-empty `plan.md`
without `--force`; `.specify/feature.json` must point at the new feature
directory before `/speckit.plan` (the speckit-specify workflow persists it).
