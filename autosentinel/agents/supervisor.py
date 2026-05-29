"""SupervisorAgent — LLM-backed routing to specialist agents.

Sprint 5 T039: real LLM call routed by config/model_routing.yaml.
JSON output: {"specialist": "code_fixer"|"infra_sre", "rationale": "..."}
Fail-safe: malformed JSON or invalid specialist falls back to
("code_fixer", "LLM 解析失败,fallback 到 code_fixer") — same
routing-progress guarantee as DiagnosisAgent's CODE-fallback.

Output writes two AgentState fields:
  - state["specialist"]      — short key consumed by graph router
  - state["routing_decision"] — LLM rationale (free text) for the report

Constitution VII.4: this module names no provider model literally; the
concrete model is resolved at construction time through the injected
AgentModelConfig.
"""

from __future__ import annotations

import json

from autosentinel.agents.base import BaseAgent
from autosentinel.agents.prompts.supervisor import SYSTEM_PROMPT, USER_TEMPLATE
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient, Message
from autosentinel.models import AgentState


_VALID_SPECIALISTS = {"code_fixer", "infra_sre"}
_FALLBACK_SPECIALIST = "code_fixer"
_FALLBACK_RATIONALE = "LLM 解析失败,fallback 到 code_fixer"


class SupervisorAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def get_specialist_key(self, category: str | None) -> str:
        """Deterministic category→specialist map used as graph-router fallback
        when state["specialist"] is absent (e.g. Supervisor node bypassed)."""
        if category in ("INFRA", "CONFIG"):
            return "infra_sre"
        return "code_fixer"

    def _parse_routing(self, content: str) -> tuple[str, str]:
        """Extract (specialist, rationale) from LLM JSON. Returns the fallback
        pair on malformed JSON / unknown specialist / empty rationale."""
        try:
            data = json.loads(content)
            specialist = data.get("specialist", "")
            rationale = data.get("rationale", "")
            if (
                specialist in _VALID_SPECIALISTS
                and isinstance(rationale, str)
                and rationale
            ):
                return specialist, rationale
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return _FALLBACK_SPECIALIST, _FALLBACK_RATIONALE

    def _format_context(self, state: AgentState) -> str:
        """Stringify whatever incident context is in state. Accepts either
        the production shape (error_log: ErrorLog TypedDict) or the
        held-out-test shape (analysis_result: raw error_log string)."""
        parts: list[str] = []
        log = state.get("error_log")
        if log:
            parts.append(f"service: {log.get('service_name', 'unknown')}")
            parts.append(f"error_type: {log.get('error_type', 'unknown')}")
            parts.append(f"message: {log.get('message', '')}")
            stack = log.get("stack_trace")
            if stack:
                parts.append(f"stack_trace: {stack}")
        analysis = state.get("analysis_result")
        if analysis is not None:
            if isinstance(analysis, str):
                parts.append(f"analysis: {analysis}")
            elif isinstance(analysis, dict):
                cat = analysis.get("error_category")
                if cat:
                    parts.append(f"analysis_category: {cat}")
                hyp = analysis.get("root_cause_hypothesis")
                if hyp:
                    parts.append(f"root_cause: {hyp}")
        return "\n".join(parts) if parts else "(no context available)"

    def run(self, state: AgentState) -> AgentState:
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=USER_TEMPLATE.format(context=self._format_context(state)),
            ),
        ]
        response = self._llm_client.complete(
            messages=messages,
            model=self._model_config.model,
            trace_id=state.get("trace_id", ""),
            agent_name="supervisor",
            max_tokens=self._model_config.max_tokens,
            temperature=self._model_config.temperature,
        )
        specialist, rationale = self._parse_routing(response.content)

        return {
            "specialist": specialist,
            "routing_decision": rationale,
            "agent_trace": ["SupervisorAgent"],
        }
