"""SecurityReviewerAgent — LLM-backed verdict + deterministic deny-list override.

Sprint 5: real LLM call (GLM-4.7 via factory).
Deny-list override (Defense-in-Depth): even if the LLM returns SAFE/CAUTION,
any artifact containing a HIGH_RISK keyword is forced to HIGH_RISK. The
keyword list is hard-coded (not learned) — prompt-injection-resistant.
"""

from __future__ import annotations

import json

from autosentinel.agents.base import BaseAgent
from autosentinel.agents.prompts.security_reviewer import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
)
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient, Message
from autosentinel.models import AgentState


_HIGH_RISK_KEYWORDS = [
    "DROP TABLE", "DROP DATABASE", "TRUNCATE TABLE",
    "rm -rf /", "rm -rf ~", "chmod 777", "mkfs", "dd if=",
]

_VALID_VERDICTS = {"SAFE", "HIGH_RISK", "CAUTION"}


class SecurityReviewerAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def _parse_verdict(self, content: str) -> str:
        """Extract verdict from LLM JSON response. Falls back to CAUTION
        on malformed JSON or missing/invalid verdict field — fail-safe."""
        try:
            data = json.loads(content)
            verdict = data.get("verdict", "")
            if verdict in _VALID_VERDICTS:
                return verdict
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        return "CAUTION"

    def run(self, state: AgentState) -> AgentState:
        artifact = state.get("fix_artifact") or ""

        # LLM call
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=USER_TEMPLATE.format(fix_artifact=artifact)),
        ]
        response = self._llm_client.complete(
            messages=messages,
            model=self._model_config.model,
            trace_id=state.get("trace_id", ""),
            agent_name="security_reviewer",
            max_tokens=self._model_config.max_tokens,
            temperature=self._model_config.temperature,
        )
        llm_verdict = self._parse_verdict(response.content)

        # Deny-list override: HIGH_RISK keywords trump LLM verdict
        if any(kw in artifact for kw in _HIGH_RISK_KEYWORDS):
            final_verdict = "HIGH_RISK"
        else:
            final_verdict = llm_verdict

        return {
            "security_verdict": final_verdict,
            "security_classifier_model": response.model,
            "agent_trace": ["SecurityReviewerAgent"],
        }
