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

## Benchmark Results (Sprint 5, real LLM)

50-scenario v1 vs v2 run (12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG):

| Metric | v2 (multi-agent, real LLM) |
|--------|----------------------------|
| Resolution rate¹ | 0.98 |
| Latency p50 / p95 | ~39 s / ~90 s |
| Security false negatives (SECURITY subset) | **0** (SC-013, strict) |
| Cost / run | ~¥1.5 (CNY) |

¹ "Resolution" currently means *pipeline completed without a Docker-level error*,
not *the generated fix passes the sandbox*. See `DEBT.md` (fix-artifact ↔ Verifier
execution-format mismatch) — this is a known gap being tracked.

## Quickstart (run it for real)

> **Run every command from the project root** (`auto-sentinel/`) — `uv` and all
> relative paths (`.env`, `infra/`, `config/`, `benchmarks/`) resolve from CWD.

```bash
# 1. One-time setup
docker compose -f infra/docker-compose.checkpointer.yml up -d   # Postgres checkpointer (:5434)
uv sync --extra dev                 # add --extra tracing to emit Langfuse spans (needs llmops-dashboard)

# 2. Tests (zero cost — fastest sanity check)
uv run pytest tests/ -q             # expect: 415 passed, 8 skipped

# 3. Run one real incident end-to-end (needs ARK_API_KEY; real LLM, ~¥0.03)
set -a; source .env; set +a         # ⚠ loads ARK_API_KEY etc. into this shell — uvicorn does NOT auto-read .env
export AUTOSENTINEL_MULTI_AGENT=1
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
