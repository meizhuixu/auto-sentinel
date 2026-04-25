"""AutoSentinel — Core Diagnostic AI Engine."""

from pathlib import Path


class DiagnosticError(Exception):
    """Raised when the pipeline exits via an error state."""


def run_pipeline(log_path: str | Path) -> Path:
    """Run the full diagnostic pipeline on a JSON error log."""
    raise NotImplementedError
