"""T065: close the remaining branch/line coverage gaps in autosentinel/llm/ so
the Constitution III 100%-coverage gate passes. These exercise error and
defensive branches the contract tests did not reach — notably the C0
concrete-dispatch paths in factory.py and the optional-tracer / generic-SDK-error
branches in the ark/glm clients.
"""

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

import autosentinel.llm.cost_guard as cost_guard_mod
from autosentinel.llm import factory
from autosentinel.llm.ark_client import ArkLLMClient
from autosentinel.llm.errors import ConfigurationError, LLMProviderError
from autosentinel.llm.glm_client import GlmLLMClient
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse, Message

VALID_TRACE_ID = "0" * 32


def _ok_handler(model: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "x", "object": "chat.completion", "created": 1,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })
    return handler


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _kwargs(model: str, agent: str) -> dict:
    return {
        "messages": [Message(role="user", content="hi")],
        "model": model, "trace_id": VALID_TRACE_ID, "agent_name": agent,
        "max_tokens": 256, "temperature": 0.0,
    }


# --- factory.py ---

class TestFactoryGaps:
    def _write_cfg(self, tmp_path, body: str, monkeypatch) -> Path:
        p = tmp_path / "routing.yaml"
        p.write_text(body)
        monkeypatch.setenv("AUTOSENTINEL_MODEL_ROUTING_PATH", str(p))
        return p

    def test_duplicate_model_under_two_endpoints_raises(self, tmp_path, monkeypatch):
        self._write_cfg(tmp_path, """
agents:
  diagnosis: {model: m1, temperature: 0.0, max_tokens: 16}
endpoints:
  ark: {base_url: "https://a.example/v1", api_key_env: ARK_API_KEY, models: [m1]}
  glm: {base_url: "https://b.example/v1", api_key_env: GLM_API_KEY, models: [m1]}
""".strip(), monkeypatch)
        with pytest.raises(ConfigurationError):
            factory.build_client_for_agent("diagnosis")

    def test_missing_config_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTOSENTINEL_MODEL_ROUTING_PATH", str(tmp_path / "nope.yaml"))
        with pytest.raises(ConfigurationError, match="not found"):
            factory.build_client_for_agent("diagnosis")

    def test_malformed_config_raises(self, tmp_path, monkeypatch):
        # valid yaml, invalid schema (endpoints missing) -> ValidationError path
        self._write_cfg(tmp_path, "agents: {}\n", monkeypatch)
        with pytest.raises(ConfigurationError, match="invalid model routing config"):
            factory.build_client_for_agent("diagnosis")

    def test_unknown_agent_raises(self, tmp_path, monkeypatch):
        self._write_cfg(tmp_path, """
agents:
  diagnosis: {model: m1, temperature: 0.0, max_tokens: 16}
endpoints:
  ark: {base_url: "https://a.example/v1", api_key_env: ARK_API_KEY, models: [m1]}
""".strip(), monkeypatch)
        monkeypatch.setenv("ARK_API_KEY", "k")
        with pytest.raises(ConfigurationError, match="not found in model routing"):
            factory.build_client_for_agent("nonexistent_agent")

    def test_unknown_endpoint_alias_has_no_concrete_client(self):
        with pytest.raises(ConfigurationError, match="no concrete LLM client"):
            factory._build_concrete_client("azure", api_key="k", base_url="https://x")


# --- ark_client.py ---

class TestArkClientGaps:
    def test_generic_api_error_raises_provider_error(self, monkeypatch):
        from unittest.mock import patch
        client = ArkLLMClient(api_key="k", base_url="https://a/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(_connect_error_handler)))
        with patch("autosentinel.llm.ark_client.LLMTracer"):
            with pytest.raises(LLMProviderError):
                client.complete(**_kwargs("doubao-seed-2.0-pro", "diagnosis"))

    def test_tracer_none_skips_enrichment(self, monkeypatch):
        # LLMTracer unavailable -> nullcontext -> tracer is None -> the
        # set_tokens / set_cost_breakdown branches are skipped.
        from unittest.mock import patch
        client = ArkLLMClient(api_key="k", base_url="https://a/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(_ok_handler("doubao-seed-2.0-pro"))))
        with patch("autosentinel.llm.ark_client.LLMTracer", None):
            resp = client.complete(**_kwargs("doubao-seed-2.0-pro", "diagnosis"))
        assert resp.content == "ok"


# --- glm_client.py ---

class _BareTracer:
    """Context manager whose entered object lacks set_tokens/set_cost_breakdown,
    forcing the hasattr branches to the False side."""

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return object()

    def __exit__(self, *args):
        return False


class TestGlmClientGaps:
    def test_tracer_none_skips_enrichment(self):
        # LLMTracer unavailable -> nullcontext -> tracer is None -> the
        # set_tokens / set_cost_breakdown branches are skipped. Mirrors
        # ArkLLMClient: SecurityReviewer (GLM-4.7) must run in benchmark /
        # script contexts where llmops_dashboard is not installed.
        from unittest.mock import patch
        client = GlmLLMClient(api_key="k", base_url="https://b/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(_ok_handler("glm-4.7"))))
        with patch("autosentinel.llm.glm_client.LLMTracer", None):
            resp = client.complete(**_kwargs("glm-4.7", "security_reviewer"))
        assert resp.content == "ok"

    def test_generic_api_error_raises_provider_error(self):
        from unittest.mock import patch
        client = GlmLLMClient(api_key="k", base_url="https://b/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(_connect_error_handler)))
        with patch("autosentinel.llm.glm_client.LLMTracer"):
            with pytest.raises(LLMProviderError):
                client.complete(**_kwargs("glm-4.7", "security_reviewer"))

    def test_tracer_without_enrichment_attrs_is_tolerated(self):
        from unittest.mock import patch
        client = GlmLLMClient(api_key="k", base_url="https://b/v1",
                              http_client=httpx.Client(transport=httpx.MockTransport(_ok_handler("glm-4.7"))))
        with patch("autosentinel.llm.glm_client.LLMTracer", _BareTracer):
            resp = client.complete(**_kwargs("glm-4.7", "security_reviewer"))
        assert resp.content == "ok"


# --- mock_client.py ---

def test_mock_client_complete_without_config_raises():
    with pytest.raises(RuntimeError, match="without with_fixture_response"):
        MockLLMClient().complete(
            messages=[Message(role="user", content="hi")],
            model="m", trace_id=VALID_TRACE_ID, agent_name="a",
            max_tokens=16, temperature=0.0,
        )


# --- protocol.py ---

def test_llm_response_rejects_malformed_trace_id():
    with pytest.raises(ValueError, match="trace_id"):
        LLMResponse(content="x", model="m", prompt_tokens=0, completion_tokens=0,
                    cost=Decimal("0"), latency_ms=0, trace_id="not-hex")


# --- cost_guard.py ---

def test_get_cost_guard_double_checked_locking_inner_recheck(monkeypatch):
    """Cover the double-checked-locking inner re-check: another caller wins the
    race and populates the singleton while we wait on the lock."""
    cost_guard_mod._singleton = None
    winner = cost_guard_mod.CostGuard(budget_limit=Decimal("1"))

    class _RacingLock:
        def __enter__(self):
            cost_guard_mod._singleton = winner  # the "other thread" got here first
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(cost_guard_mod, "_singleton_lock", _RacingLock())
    try:
        assert cost_guard_mod.get_cost_guard() is winner
    finally:
        cost_guard_mod._singleton = None
