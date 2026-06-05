"""T068: the multi-agent pipeline must create ONE parent Langfuse trace per
incident (id == trace_id, tagged project/component) so the per-agent generation
spans nest under a real trace object. Without it, fetch_trace(trace_id) 404s and
the trace carries no project/component tags (the agent clients all attach with
owns_trace=False and never create the parent).

These tests patch the Langfuse-client seam so they stay hermetic (no live
Langfuse, no llmops-dashboard install required).
"""

from unittest.mock import MagicMock, patch

import autosentinel.tracing as tracing

_VALID_TRACE_ID = "a" * 32


def test_noop_when_trace_id_empty():
    with patch.object(tracing, "_langfuse_client") as mk:
        tracing.open_parent_trace("")
        mk.assert_not_called()


def test_noop_when_client_unavailable():
    # llmops-dashboard absent / Langfuse unconfigured -> _langfuse_client None.
    with patch.object(tracing, "_langfuse_client", return_value=None):
        tracing.open_parent_trace(_VALID_TRACE_ID)  # must not raise


def test_creates_parent_trace_when_configured():
    client = MagicMock()
    with patch.object(tracing, "_langfuse_client", return_value=client):
        tracing.open_parent_trace(_VALID_TRACE_ID)
    client.trace.assert_called_once()
    kwargs = client.trace.call_args.kwargs
    assert kwargs["id"] == _VALID_TRACE_ID
    assert "project:auto-sentinel" in kwargs["tags"]
    client.flush.assert_called_once()


def test_never_raises_on_client_error():
    client = MagicMock()
    client.trace.side_effect = RuntimeError("boom")
    with patch.object(tracing, "_langfuse_client", return_value=client):
        tracing.open_parent_trace(_VALID_TRACE_ID)  # swallowed, no raise
