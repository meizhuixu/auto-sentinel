"""InfraSREAgent — LLM-backed fix generator for INFRA and CONFIG categories.

Sprint 5: real LLM call routed by config/model_routing.yaml. SYSTEM_PROMPT
forbids markdown fences; strip_markdown_fence() is a defensive fallback if
the model emits them anyway.
"""

from __future__ import annotations

from autosentinel.agents._parsing import strip_markdown_fence
from autosentinel.agents.base import BaseAgent
from autosentinel.agents.prompts.infra_sre import SYSTEM_PROMPT, USER_TEMPLATE
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient, Message
from autosentinel.models import AgentState


class InfraSREAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def _build_error_context(self, state: AgentState) -> str:
        log = state.get("error_log") or {}
        analysis = state.get("analysis_result") or {}
        return (
            f"service={log.get('service_name', 'unknown')} "
            f"error_type={log.get('error_type', 'unknown')} "
            f"message={log.get('message', '')} "
            f"hypothesis={analysis.get('root_cause_hypothesis', '(none)')}"
        )

    def run(self, state: AgentState) -> AgentState:
        category = state.get("error_category", "INFRA")
        error_context = self._build_error_context(state)

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=USER_TEMPLATE.format(
                    category=category,
                    error_context=error_context,
                ),
            ),
        ]
        response = self._llm_client.complete(
            messages=messages,
            model=self._model_config.model,
            trace_id=state.get("trace_id", ""),
            agent_name="infra_sre",
            max_tokens=self._model_config.max_tokens,
            temperature=self._model_config.temperature,
        )
        artifact = strip_markdown_fence(response.content)

        return {"fix_artifact": artifact, "agent_trace": ["InfraSREAgent"]}
