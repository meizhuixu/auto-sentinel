"""analyze_error node — classifies error via local mock (API-key-free)."""

from autosentinel.models import AnalysisResult, DiagnosticState

# Kept for future real-API integration; not used in mock mode.
DIAGNOSE_PROMPT = (
    "You are a microservice reliability engineer. Analyse the following error log "
    "and use the diagnose_error tool to return a structured diagnosis.\n\n"
    "Service: {service_name}\n"
    "Error type: {error_type}\n"
    "Message: {message}\n"
    "Stack trace: {stack_trace}\n"
    "Timestamp: {timestamp}"
)

DIAGNOSE_TOOL = {
    "name": "diagnose_error",
    "description": "Classify a microservice error and return structured analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "error_category": {
                "type": "string",
                "enum": [
                    "connectivity",
                    "resource_exhaustion",
                    "configuration",
                    "application_logic",
                ],
            },
            "root_cause_hypothesis": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "remediation_steps": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "required": [
            "error_category",
            "root_cause_hypothesis",
            "confidence",
            "remediation_steps",
        ],
    },
}

# Mock rules: keyword tuples → AnalysisResult fields.
# Checked in order; first match wins.
_MOCK_RULES: list[tuple[tuple[str, ...], AnalysisResult]] = [
    (
        ("timeout", "connection", "unreachable", "refused", "dns", "network"),
        AnalysisResult(
            error_category="connectivity",
            root_cause_hypothesis=(
                "The service cannot reach its upstream dependency. "
                "A network partition, misconfigured DNS record, or firewall rule "
                "is preventing TCP connection establishment."
            ),
            confidence=0.91,
            remediation_steps=[
                "Verify DNS resolution for the target host from inside the service pod.",
                "Check security-group / firewall rules between the service and the dependency.",
                "Confirm the dependency is healthy and its port is open.",
                "Increase connection timeout and add retry with exponential back-off.",
            ],
        ),
    ),
    (
        ("oom", "memory", "killed", "heap", "out of memory", "limit"),
        AnalysisResult(
            error_category="resource_exhaustion",
            root_cause_hypothesis=(
                "The process exceeded its configured memory limit and was terminated "
                "by the kernel OOM killer or the container runtime. "
                "Likely caused by a memory leak, an unexpectedly large payload, "
                "or an under-provisioned memory limit."
            ),
            confidence=0.95,
            remediation_steps=[
                "Profile heap allocations to identify the largest consumers.",
                "Review recent deployments for changes that process larger data sets.",
                "Increase the container memory limit as a short-term fix.",
                "Add memory-usage metrics and alert before the limit is reached.",
            ],
        ),
    ),
    (
        ("config", "env", "environment", "secret", "key", "variable", "missing", "not set"),
        AnalysisResult(
            error_category="configuration",
            root_cause_hypothesis=(
                "A required environment variable or secret is absent from the "
                "service's runtime environment. The service cannot start or "
                "complete initialisation without this value."
            ),
            confidence=0.97,
            remediation_steps=[
                "Confirm the variable is declared in the deployment manifest / Helm values.",
                "Verify the secret exists in the secrets store and is mounted correctly.",
                "Check that the CI/CD pipeline injects the variable for this environment.",
                "Add a startup health-check that validates all required config is present.",
            ],
        ),
    ),
]

_MOCK_FIX_SCRIPTS: dict[str, str] = {
    "connectivity": 'print("Restarting connection pool for upstream dependency...")',
    "resource_exhaustion": 'print("Triggering garbage collection and releasing memory buffers...")',
    "configuration": 'print("Reloading environment variables from secrets store...")',
    "application_logic": 'print("Flushing stale state and re-initialising application context...")',
}

_FALLBACK = AnalysisResult(
    error_category="application_logic",
    root_cause_hypothesis=(
        "An unhandled exception or assertion failure occurred inside the service. "
        "The root cause is likely a bug in the application code triggered by an "
        "unexpected input or state transition."
    ),
    confidence=0.72,
    remediation_steps=[
        "Inspect the full stack trace to identify the failing code path.",
        "Reproduce the error locally with the same input payload.",
        "Add a regression test that covers this failure scenario.",
        "Review recent commits to the affected service for unintended side-effects.",
    ],
)


def _mock_classify(error_type: str, message: str) -> AnalysisResult:
    """Return a deterministic AnalysisResult based on keywords in the log."""
    haystack = f"{error_type} {message}".lower()
    for keywords, result in _MOCK_RULES:
        if any(kw in haystack for kw in keywords):
            return result
    return _FALLBACK


def analyze_error(state: DiagnosticState) -> dict:
    """Classify the error in state['error_log'] using local mock data."""
    log = state["error_log"]
    result = _mock_classify(log["error_type"], log["message"])
    return {
        "analysis_result": result,
        "analysis_error": None,
        "fix_script": _MOCK_FIX_SCRIPTS[result["error_category"]],
    }
