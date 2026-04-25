"""Unit tests for the analyze_error node."""

from unittest.mock import MagicMock, patch

import pytest

from autosentinel.nodes.analyze_error import analyze_error


def test_analyze_error_happy_path(populated_connectivity_state, mock_tool_use_response):
    mock_response = mock_tool_use_response(error_category="connectivity")
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = analyze_error(populated_connectivity_state)

    assert result["analysis_error"] is None
    assert result["analysis_result"] is not None
    assert result["analysis_result"]["error_category"] == "connectivity"
    assert result["analysis_result"]["confidence"] == pytest.approx(0.92)
    assert len(result["analysis_result"]["remediation_steps"]) >= 1


def test_analyze_error_api_failure(populated_connectivity_state):
    import anthropic as _anthropic
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = _anthropic.APIConnectionError(
            request=MagicMock()
        )
        result = analyze_error(populated_connectivity_state)

    assert result["analysis_result"] is None
    assert result["analysis_error"] is not None
    assert len(result["analysis_error"]) > 0


def test_analyze_error_no_tool_use_block(populated_connectivity_state):
    text_only_block = MagicMock()
    text_only_block.type = "text"
    response = MagicMock()
    response.content = [text_only_block]
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = response
        result = analyze_error(populated_connectivity_state)

    assert result["analysis_result"] is None
    assert result["analysis_error"] is not None
