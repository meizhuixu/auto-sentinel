"""Model routing config + LLM client factory (data-model.md §4-6 + tasks T018/T019).

Schema location decision: per data-model.md and per the already-committed
T010 test imports, AgentModelConfig / EndpointConfig / ModelRoutingConfig
all live in this module alongside build_client_for_agent(). No separate
config.py file.

build_client_for_agent() dispatches on each agent's resolved endpoint_alias
to the concrete provider client that lives under autosentinel/llm/ — the
single layer Constitution VII.1 permits to import a provider SDK:
    "ark" → ArkLLMClient   (Volcano-Engine Ark, doubao series)
    "glm" → GlmLLMClient   (GLM-4.7 via the Volcano Ark proxy — same gateway
                            and ARK_API_KEY as "ark"; a distinct alias only so
                            GLM keeps its own price table)
Selection stays fully declarative (Constitution VII.4): the alias, base_url,
and api_key env-var name are all sourced from config/model_routing.yaml; no
model string literal appears here. Agent modules never import openai — they
consume only the returned LLMClient.

The hermetic test / smoke-benchmark mock path does NOT go through this
factory: it injects MockLLMClient instances via build_multi_agent_graph(
agents=...) (the D2 seam), so pytest never reaches a real provider.
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


# Anchored to the repo root via this file's location (factory.py → llm →
# autosentinel → repo root) so tests/tools work from any CWD (Sprint 6 FR-010).
# AUTOSENTINEL_MODEL_ROUTING_PATH env var still takes precedence below.
_DEFAULT_ROUTING_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "model_routing.yaml"
)


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


def _build_concrete_client(
    endpoint_alias: str, *, api_key: str, base_url: str
) -> "LLMClient":
    """Dispatch endpoint_alias → concrete provider client.

    The two concrete clients are imported lazily so that this module (and the
    hermetic test suite that imports it) loads without the provider SDK side
    effects, and so the VII.1 import boundary stays confined to those files.
    """
    if endpoint_alias == "ark":
        from autosentinel.llm.ark_client import ArkLLMClient

        return ArkLLMClient(api_key=api_key, base_url=base_url)
    if endpoint_alias == "glm":
        from autosentinel.llm.glm_client import GlmLLMClient

        return GlmLLMClient(api_key=api_key, base_url=base_url)
    raise ConfigurationError(
        f"no concrete LLM client mapped for endpoint alias {endpoint_alias!r} "
        f"(known: 'ark', 'glm')"
    )


def build_client_for_agent(
    agent_name: str,
) -> tuple["LLMClient", AgentModelConfig]:
    """Build the concrete LLMClient for a production agent + its model config.

    Dispatches on the agent's resolved endpoint_alias (back-filled from
    config/model_routing.yaml's endpoints block) to ArkLLMClient or
    GlmLLMClient. The returned AgentModelConfig carries model / max_tokens /
    temperature, which the agent passes into client.complete() at call time
    per contracts/llm-client.md "Public surface". The (client, config) tuple
    shape is the PR-2 contract and is unchanged here.

    Constitution VII.1 / VII.4: the only inputs are the yaml-sourced alias,
    base_url, and api_key env-var name — no provider SDK import and no model
    literal lives in any agent module. Provider switching is a yaml edit.

    Raises ConfigurationError when:
    - the routing yaml is missing or malformed (via _load_routing_config)
    - agent_name is not declared under `agents:` in the yaml
    - the api_key_env name is not set in os.environ
    - the resolved endpoint_alias has no concrete client mapping
    """
    cfg = _load_routing_config()

    if agent_name not in cfg.agents:
        raise ConfigurationError(
            f"agent {agent_name!r} not found in model routing config "
            f"(known: {sorted(cfg.agents.keys())})"
        )

    agent_cfg = cfg.agents[agent_name]
    endpoint_cfg = cfg.endpoints[agent_cfg.endpoint_alias]
    api_key = os.environ.get(endpoint_cfg.api_key_env)
    if not api_key:
        raise ConfigurationError(
            f"API key env var {endpoint_cfg.api_key_env!r} is not set "
            f"(required for agent {agent_name!r} → endpoint {agent_cfg.endpoint_alias!r})"
        )

    client = _build_concrete_client(
        agent_cfg.endpoint_alias,
        api_key=api_key,
        base_url=str(endpoint_cfg.base_url),
    )
    return client, agent_cfg
