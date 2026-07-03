# AutoSentinel

✅ **Sprint 5 (Real LLM Integration) complete.** The 6-agent LangGraph pipeline now
reasons via **real LLMs** (Volcano Ark: doubao-seed-2.0-pro / doubao-1.5-lite-32k /
GLM-4.7), with a CNY cost guard, deterministic + LLM security gating, cross-process
HIGH_RISK resume (PostgresSaver), and Langfuse trace correlation. Validated on a
human-labelled 50-scenario benchmark.

## Architecture

AutoSentinel is an AI-powered incident auto-remediation system for distributed
microservices. It ingests structured error logs, classifies failures, generates
fix artifacts, and verifies them in an isolated Docker sandbox — with a
human-approval gate for high-risk remediations.

### Sprint 4 Multi-Agent Graph (v2)

```
parse_log → DiagnosisAgent → SupervisorAgent
                                   ↓
                    ┌──────────────┴──────────────┐
                    ↓                             ↓
             CodeFixerAgent               InfraSREAgent
                    └──────────────┬──────────────┘
                                   ↓
                         SecurityReviewerAgent
                                   ↓
                            security_gate
                         (interrupt on HIGH_RISK)
                                   ↓
                            VerifierAgent
                                   ↓
                            format_report
```

## Benchmark Results (Sprint 6 re-baseline, real LLM)

50-scenario run (12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG),
run_id `20260703-193916-4a165e7`
(summary tracked at `benchmarks/results/20260703-193916-4a165e7/summary.json`):

| Metric | multi-agent pipeline (real LLM) |
|--------|---------------------------------|
| Resolution rate¹ | **0.62** |
| — CODE | 12/12 (1.00) |
| — INFRA | 9/15 (0.60) |
| — SECURITY | 4/8 (0.50) |
| — CONFIG | 6/15 (0.40) |
| Latency p50 / p95 | 49.4 s / 89.8 s |
| Security false negatives (SECURITY subset) | **0** (SC-013, strict) |
| Cost / run | ¥1.84 (CNY) |

¹ **Resolved** = report produced AND no docker-level error AND the fix
**executed successfully in the sandbox** (`execution_result.status ==
'success'`, i.e. exit 0). The definition is embedded in every `summary.json`
(`resolved_definition`).

Reading the honest number: the Sprint 6 fix-artifact contract
(`specs/006-fix-verification-integrity/contracts/fix-artifact.md`) eliminated
format-induced SyntaxError false-failures entirely — in this run, **zero**
fixes died of artifact shape, and CODE-class fixes verify at 12/12. The
remaining failures are honest sandbox limits: INFRA/CONFIG/SECURITY
remediations that need the *target* system (config files under `/etc`,
network reachability, third-party packages absent from `python:3.10-alpine`)
cannot demonstrate success inside an isolated no-network container, plus one
LLM timeout (047). Historical footnote: Sprint 5 reported **0.98** under the
old definition — *pipeline completed without a docker-level error* — which
measured pipeline completion, not fix success (see `DEBT.md`, resolved
Sprint 6).

## Quickstart (run it for real)

> **Run every command from the project root** (`auto-sentinel/`) — `uv` and all
> relative paths (`.env`, `infra/`, `config/`, `benchmarks/`) resolve from CWD.

```bash
# 1. One-time setup
docker compose -f infra/docker-compose.checkpointer.yml up -d   # Postgres checkpointer (:5434)
uv sync --extra dev                 # add --extra tracing to emit Langfuse spans (needs llmops-dashboard)

# 2. Tests (zero cost — fastest sanity check)
uv run pytest tests/ -q             # expect: 426 passed, 8 skipped

# 3. Run one real incident end-to-end (needs ARK_API_KEY; real LLM, ~¥0.03)
set -a; source .env; set +a         # ⚠ loads ARK_API_KEY etc. into this shell — uvicorn does NOT auto-read .env
export AUTOSENTINEL_CHECKPOINTER_DSN=postgresql://postgres:postgres@localhost:5434/postgres
uv run uvicorn autosentinel.api.main:app --port 8000
#   then, in another terminal (also at project root):
curl -X POST localhost:8000/api/v1/alerts -H "Content-Type: application/json" \
     -d @benchmarks/scenarios/fixtures/008_code_key_error_dict.json
#   the 202 response is just the async ACK; the real outcome is in the uvicorn logs
#   (`processing_completed`) + the report at output/<trace_id>-report.md.

# 4. Full 50-scenario benchmark (real LLM, ~¥1.5)
uv run python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 150
```

`ARK_API_KEY` (Volcano Ark — covers all 3 endpoints) lives in `.env`. For Langfuse
tracing also `uv sync --extra tracing` and export `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY`
/ `LANGFUSE_SECRET_KEY`. Full notes: `specs/005-real-llm-integration/quickstart.md`.

## Development

```bash
uv sync --extra dev                                  # pytest lives in the dev extra
uv run pytest tests/ --cov=autosentinel.llm --cov-fail-under=100 -q   # 100% llm branch coverage gate

# Spec-driven workflow
/speckit.specify  →  /speckit.plan  →  /speckit.tasks  →  /speckit.implement
```

## Status

| Sprint | Focus | Status |
|--------|-------|--------|
| 1 | Log parsing + error analysis | ✅ Complete |
| 2 | Fix generation + Docker sandbox | ✅ Complete |
| 3 | LangGraph v1 pipeline | ✅ Complete |
| 4 | Multi-agent migration (6-agent architecture) | ✅ Complete |
| 5 | Real LLM integration (Volcano Ark + Langfuse + 50-scenario benchmark) | ✅ Complete |
