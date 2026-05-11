"""Model routing config + LLM client factory (data-model.md §4-6 + tasks T018/T019).

Schema location decision: per data-model.md and per the already-committed
T010 test imports, AgentModelConfig / EndpointConfig / ModelRoutingConfig
all live in this module alongside build_client_for_agent(). No separate
config.py file.

T019 status: PR-1 placeholder. Validates routing config + env vars at call
time, then returns a MockLLMClient. Concrete-client dispatch (ArkLLMClient
vs GlmLLMClient based on endpoint_alias) is wired in PR-2 once T021/T022
land. The intermediate behaviour is sufficient for the foundational tests:
T010's missing-env-var case raises ConfigurationError before reaching the
late MockLLMClient import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator

from autosentinel.llm.errors import ConfigurationError

if TYPE_CHECKING:
    from autosentinel.llm.protocol import LLMClient


# ──────────────────────────────────────────────────────────────────────────
# Schemas (data-model.md §4-6)
# ──────────────────────────────────────────────────────────────────────────


class AgentModelConfig(BaseModel):
    """Per-agent reflection of model_routing.yaml's agents.<name> block.
    `endpoint_alias` is back-filled by ModelRoutingConfig._every_agent_model_is_registered."""

    model: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=32_768)
    endpoint_alias: str = ""


class EndpointConfig(BaseModel):
    base_url: HttpUrl
    api_key_env: str = Field(min_length=1)
    models: list[str] = Field(min_length=1)


class ModelRoutingConfig(BaseModel):
    agents: dict[str, AgentModelConfig]
    endpoints: dict[str, EndpointConfig]

    @model_validator(mode="after")
    def _every_agent_model_is_registered(self) -> "ModelRoutingConfig":
        """Cross-validation: each agent's model must appear under exactly one
        endpoint. Back-fills AgentModelConfig.endpoint_alias as a side-effect."""
        all_models: dict[str, str] = {}
        for alias, ep in self.endpoints.items():
            for m in ep.models:
                if m in all_models:
                    raise ValueError(
                        f"model {m!r} declared under multiple endpoints "
                        f"({all_models[m]!r} and {alias!r})"
                    )
                all_models[m] = alias
        for agent_name, cfg in self.agents.items():
            if cfg.model not in all_models:
                raise ValueError(
                    f"agent {agent_name!r} uses model {cfg.model!r} "
                    f"not declared under any endpoint"
                )
            cfg.endpoint_alias = all_models[cfg.model]
        return self


# ──────────────────────────────────────────────────────────────────────────
# Loader + factory (T019)
# ──────────────────────────────────────────────────────────────────────────


_DEFAULT_ROUTING_PATH = Path("config/model_routing.yaml")


def _load_routing_config() -> ModelRoutingConfig:
    path = Path(
        os.environ.get("AUTOSENTINEL_MODEL_ROUTING_PATH", str(_DEFAULT_ROUTING_PATH))
    )
    if not path.exists():
        raise ConfigurationError(f"model routing config not found at {path}")
    with path.open() as f:
        data = yaml.safe_load(f)
    try:
        return ModelRoutingConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigurationError(
            f"invalid model routing config at {path}: {e}"
        ) from e


def build_client_for_agent(agent_name: str) -> "LLMClient":
    """PR-1 placeholder. Validates config + env vars; returns MockLLMClient.

    Concrete dispatch (ArkLLMClient | GlmLLMClient based on endpoint_alias)
    will be wired in PR-2 after T021/T022 land. Until then, callers get a
    placeholder client that satisfies the LLMClient Protocol but has no
    real provider behaviour.

    Raises ConfigurationError when:
    - the routing yaml is missing or malformed (via _load_routing_config)
    - agent_name is not declared under `agents:` in the yaml
    - the api_key_env name is not set in os.environ
    """
    cfg = _load_routing_config()

    if agent_name not in cfg.agents:
        raise ConfigurationError(
            f"agent {agent_name!r} not found in model routing config "
            f"(known: {sorted(cfg.agents.keys())})"
        )

    agent_cfg = cfg.agents[agent_name]
    endpoint_cfg = cfg.endpoints[agent_cfg.endpoint_alias]
    if not os.environ.get(endpoint_cfg.api_key_env):
        raise ConfigurationError(
            f"API key env var {endpoint_cfg.api_key_env!r} is not set "
            f"(required for agent {agent_name!r} → endpoint {agent_cfg.endpoint_alias!r})"
        )

    # PR-1 placeholder; concrete dispatch wired in PR-2.
    from autosentinel.llm.mock_client import MockLLMClient  # late import — module
    return MockLLMClient()                                  # may not exist until T020
