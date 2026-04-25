"""parse_log node — reads and validates a JSON error log file."""

from autosentinel.models import DiagnosticState


def parse_log(state: DiagnosticState) -> dict:
    """Read and validate the JSON log file at state['log_path']."""
    raise NotImplementedError
