"""Contract tests for autosentinel/llm/factory.py — ModelRoutingConfig
validation and factory.build_client_for_agent() startup checks
(data-model.md §4-6).

Today (T010 commit) every test errors on collection because factory.py
does not exist yet. T018 + T019 implement and turn GREEN.

3 cases:
  1. Missing endpoint for a declared model → ValidationError
  2. Missing API key env var at factory build time → ConfigurationError
  3. Valid config back-fills AgentModelConfig.endpoint_alias correctly
"""

import pytest
from pydantic import ValidationError

from autosentinel.llm.errors import ConfigurationError
from autosentinel.llm.factory import (
    AgentModelConfig,
    EndpointConfig,
    ModelRoutingConfig,
    build_client_for_agent,
)


def _valid_config() -> ModelRoutingConfig:
    return ModelRoutingConfig(
        agents={
            "diagnosis": AgentModelConfig(
                model="doubao-seed-2.0-pro",
                temperature=0.2,
                max_tokens=2048,
                endpoint_alias="",  # back-filled by validator
            ),
        },
        endpoints={
            "ark": EndpointConfig(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key_env="ARK_API_KEY",
                models=["doubao-seed-2.0-pro"],
            ),
        },
    )


def test_invalid_model_not_under_any_endpoint_raises():
    """Agent declares a model that no endpoint serves → ValidationError."""
    with pytest.raises(ValidationError):
        ModelRoutingConfig(
            agents={
                "diagnosis": AgentModelConfig(
                    model="ghost-model-9000",
                    temperature=0.2,
                    max_tokens=2048,
                    endpoint_alias="",
                ),
            },
            endpoints={
                "ark": EndpointConfig(
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    api_key_env="ARK_API_KEY",
                    models=["doubao-seed-2.0-pro"],  # does NOT include ghost-model-9000
                ),
            },
        )


def test_valid_config_backfills_endpoint_alias():
    cfg = _valid_config()
    assert cfg.agents["diagnosis"].endpoint_alias == "ark"


def test_missing_api_key_env_var_raises_configuration_error(monkeypatch, tmp_path):
    """When the configured api_key_env name is not set in os.environ, the
    factory must fail-fast with ConfigurationError at build time."""
    # Ensure ARK_API_KEY is NOT in the environment for this test:
    monkeypatch.delenv("ARK_API_KEY", raising=False)

    routing_yaml = tmp_path / "model_routing.yaml"
    routing_yaml.write_text(
        """
agents:
  diagnosis:
    model: doubao-seed-2.0-pro
    temperature: 0.2
    max_tokens: 2048

endpoints:
  ark:
    base_url: https://ark.cn-beijing.volces.com/api/v3
    api_key_env: ARK_API_KEY
    models:
      - doubao-seed-2.0-pro
""".strip()
    )
    monkeypatch.setenv("AUTOSENTINEL_MODEL_ROUTING_PATH", str(routing_yaml))

    with pytest.raises(ConfigurationError):
        build_client_for_agent("diagnosis")
