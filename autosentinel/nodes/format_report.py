"""format_report node — renders markdown report and writes to output/."""

from autosentinel.models import DiagnosticState


def format_report(state: DiagnosticState) -> dict:
    """Format analysis into a markdown report and write to output/."""
    raise NotImplementedError
