# Quickstart: Event Gateway (Sprint 2)

## Prerequisites

- Python 3.10+
- Sprint 1 already installed: `pip install -e ".[dev]"` was run from repo root
- No external services required (queue is in-memory)

## Install Sprint 2 Dependencies

```bash
pip install -e ".[dev]"
```

New packages added by Sprint 2: `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27`

## Start the API Server

```bash
uvicorn autosentinel.api.main:app --reload --port 8000
```

Server starts on `http://localhost:8000`. You should see structured JSON log output in the terminal as alerts are processed.

## Submit a Test Alert

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "payment-service",
    "error_type": "ConnectionTimeout",
    "message": "Database connection timed out after 30s waiting for host db.internal:5432",
    "timestamp": "2026-04-24T10:15:00Z"
  }'
```

Expected response (immediate, < 50ms):
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "accepted",
  "message": "Alert accepted for processing"
}
```

Within a second or two, a diagnostic report appears at `output/{job_id}-report.md`.

## Submit Using an Existing Fixture

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d @data/crash-connectivity.json
```

## Run Tests

```bash
pytest --cov=autosentinel --cov-branch --cov-fail-under=100
```

All tests run without a running server — `TestClient` manages the app lifecycle internally.

## Inspect Structured Logs

Log output is newline-delimited JSON to stdout. Example lifecycle trace for one alert:

```json
{"timestamp":"2026-04-25T10:00:01Z","severity":"INFO","component":"event_gateway","correlation_id":"abc-123","trace_id":"abc-123","event":"alert_received","event_payload":{"service_name":"payment-service","error_type":"ConnectionTimeout"}}
{"timestamp":"2026-04-25T10:00:01Z","severity":"INFO","component":"event_gateway","correlation_id":"abc-123","trace_id":"abc-123","event":"alert_queued","event_payload":{"service_name":"payment-service","queue_depth":1}}
{"timestamp":"2026-04-25T10:00:01Z","severity":"INFO","component":"event_gateway","correlation_id":"abc-123","trace_id":"abc-123","event":"processing_started","event_payload":{"service_name":"payment-service","log_path":"data/incoming/abc-123.json"}}
{"timestamp":"2026-04-25T10:00:02Z","severity":"INFO","component":"event_gateway","correlation_id":"abc-123","trace_id":"abc-123","event":"processing_completed","event_payload":{"service_name":"payment-service","report_path":"output/abc-123-report.md","duration_ms":342}}
```

## Project Layout After Sprint 2

```text
autosentinel/
├── __init__.py          # run_pipeline() — unchanged from Sprint 1
├── __main__.py          # CLI — unchanged from Sprint 1
├── models.py            # TypedDicts — unchanged from Sprint 1
├── graph.py             # LangGraph — unchanged from Sprint 1
├── nodes/               # parse_log, analyze_error, format_report — unchanged
└── api/
    ├── __init__.py
    ├── main.py          # FastAPI app + lifespan + /api/v1/alerts router
    ├── models.py        # AlertPayload, AlertJobResponse Pydantic models
    ├── queue.py         # asyncio.Queue singleton + worker coroutine
    └── logging.py       # JSONFormatter + get_logger()

data/
├── crash-*.json         # Sprint 1 fixtures
└── incoming/            # Runtime alert files (gitignored)

output/                  # Generated reports (gitignored)

tests/
├── conftest.py          # Shared fixtures (extended for Sprint 2)
├── unit/                # Sprint 1 unit tests (unchanged)
└── integration/
    ├── test_pipeline.py # Sprint 1 integration tests (unchanged)
    └── test_api.py      # Sprint 2: route + background processing tests
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: fastapi` | Dependencies not reinstalled | `pip install -e ".[dev]"` |
| Port 8000 already in use | Another process | `uvicorn ... --port 8001` |
| Report not appearing after POST | Worker not started | Ensure app started with `lifespan`; check logs for `processing_started` |
| `422` on valid payload | Timestamp or field format | Check all required fields are non-empty strings |
