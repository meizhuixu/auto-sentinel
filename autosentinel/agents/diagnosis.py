"""DiagnosisAgent — LLM-backed error classification (CODE/INFRA/CONFIG/SECURITY).

Sprint 5: real LLM call routed by config/model_routing.yaml.
JSON output: {"category": "<CODE|INFRA|CONFIG|SECURITY>", "reasoning": "..."}
Fail-safe: malformed JSON or unknown category falls back to "CODE" — same
behaviour as the Sprint 4 keyword stub's final 'else' branch, preserving
downstream graph routing (CODE → CodeFixerAgent).
"""

from __future__ import annotations

import json

from autosentinel.agents.base import BaseAgent
from autosentinel.agents.prompts.diagnosis import SYSTEM_PROMPT, USER_TEMPLATE
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient, Message
from autosentinel.models import AgentState


_VALID_CATEGORIES = {"CODE", "INFRA", "CONFIG", "SECURITY"}


class DiagnosisAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def _parse_category(self, content: str) -> str:
        """Extract category from LLM JSON response. Falls back to CODE on
        malformed JSON or invalid category — preserves Sprint 4 routing
        semantics (unknown → CODE → CodeFixerAgent)."""
        try:
            data = json.loads(content)
            category = data.get("category", "")
            if category in _VALID_CATEGORIES:
                return category
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return "CODE"

    def run(self, state: AgentState) -> AgentState:
        log = state["error_log"]

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=USER_TEMPLATE.format(
                    service_name=log.get("service_name", "unknown"),
                    error_type=log.get("error_type", "unknown"),
                    message=log.get("message", ""),
                    stack_trace=log.get("stack_trace") or "(none)",
                ),
            ),
        ]
        response = self._llm_client.complete(
            messages=messages,
            model=self._model_config.model,
            trace_id=state.get("trace_id", ""),
            agent_name="diagnosis",
            max_tokens=self._model_config.max_tokens,
            temperature=self._model_config.temperature,
        )
        category = self._parse_category(response.content)

        return {
            "error_category": category,
            "agent_trace": ["DiagnosisAgent"],
        }
