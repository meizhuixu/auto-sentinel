# AutoSentinel

🚧 Sprint 4 (Multi-Agent Migration) complete: 6-agent collaborative architecture
(Diagnosis + Supervisor + CodeFixer + InfraSRE + SecurityReviewer + Verifier)
wired through LangGraph 1.x with sequential security gating and Docker isolation.
See `output/benchmark-report.json` for v1 vs v2 5-scenario smoke benchmark.

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

## Benchmark Results (Sprint 4)

5-scenario v1 vs v2 comparison (`output/benchmark-report.json`):

| Pipeline | Resolution Rate | Avg ms |
|----------|----------------|--------|
| v1       | 100%           | ~4 ms  |
| v2       | 100%           | ~4 ms  |

s04 (SECURITY): `was_interrupted=true`, `security_verdict=HIGH_RISK` —
SC-003 human-approval gate confirmed under real LangGraph execution.

## Usage

```bash
# v1 pipeline (Sprint 1–3, LangGraph sequential)
autosentinel path/to/error.json

# v2 pipeline (Sprint 4, multi-agent)
AUTOSENTINEL_MULTI_AGENT=1 autosentinel path/to/error.json

# Run v1/v2 benchmark
python -m autosentinel.benchmark
```

## Development

```bash
# Install
pip install -e ".[dev]"

# Tests + coverage
pytest --cov=autosentinel --cov-branch -q

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
| 5 | Real LLM API integration (W2) | 🔜 Next |
