# Quickstart: Core Diagnostic AI Engine

**Branch**: `001-core-diagnostic-engine`

Run the AutoSentinel diagnostic pipeline locally in under 5 minutes.

---

## Prerequisites

- Python 3.10 or higher
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- `pip` or `uv`

---

## 1. Install dependencies

```bash
# With pip
pip install langgraph anthropic

# Or with uv (faster)
uv add langgraph anthropic
```

---

## 2. Set your API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Add this to your `.bashrc` / `.zshrc` to avoid repeating it.

---

## 3. Verify sample log fixtures exist

```bash
ls data/
# Expected:
# crash-connectivity.json
# crash-resource.json
# crash-config.json
```

If the `data/` directory is missing, create it and add at least one fixture:

```bash
mkdir -p data
cat > data/crash-connectivity.json << 'EOF'
{
  "timestamp": "2026-04-24T10:15:00Z",
  "service_name": "payment-service",
  "error_type": "ConnectionTimeout",
  "message": "Database connection timed out after 30s waiting for host db.internal:5432",
  "stack_trace": "Traceback (most recent call last):\n  File 'db.py', line 42, in connect\n    raise ConnectionTimeout('db.internal:5432 unreachable')"
}
EOF
```

---

## 4. Run the diagnostic engine

```bash
python -m autosentinel data/crash-connectivity.json
```

Expected output:
```
[AutoSentinel] Running diagnostic pipeline...
[AutoSentinel] parse_log: OK — service=payment-service error_type=ConnectionTimeout
[AutoSentinel] analyze_error: OK — category=connectivity confidence=0.94
[AutoSentinel] format_report: OK — report written to output/crash-connectivity-report.md
```

---

## 5. View the report

```bash
cat output/crash-connectivity-report.md
```

---

## 6. Run all three sample fixtures

```bash
for f in data/*.json; do python -m autosentinel "$f"; done
ls output/
```

---

## 7. Run the test suite

```bash
# Run all tests
pytest

# Run with branch coverage
pytest --cov=autosentinel --cov-branch --cov-report=term-missing

# Run only unit tests (no LLM calls — fast)
pytest tests/unit/

# Run integration tests (mocked LLM — still no real API calls)
pytest tests/integration/
```

Expected result: all tests pass, 100% branch coverage on `autosentinel/nodes/`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `DiagnosticError: Invalid JSON in data/foo.json` | Malformed fixture | Check JSON syntax with `python -m json.tool data/foo.json` |
| `AuthenticationError` from Anthropic | API key not set or invalid | Verify `echo $ANTHROPIC_API_KEY` is non-empty |
| `FileNotFoundError: data/ directory` | `data/` does not exist | Run step 3 above |
| `ModuleNotFoundError: autosentinel` | Package not installed in editable mode | Run `pip install -e .` from repo root |
