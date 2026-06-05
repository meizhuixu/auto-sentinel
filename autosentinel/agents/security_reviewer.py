"""SecurityReviewerAgent — LLM-backed verdict + deterministic deny-list override.

Sprint 5: real LLM call routed by config/model_routing.yaml (reasoning model for security classification).
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

# Constitution Principle V: a fix that touches secrets/credentials MUST be
# HIGH_RISK ("hold for human approval"). LLM semantic review proved unreliable
# for this class (GLM-4.7 SAFEs hardening changes like moving a secret to env or
# upgrading password hashing), so these patterns deterministically force
# HIGH_RISK regardless of the LLM verdict. Matched case-insensitively because
# credential handling appears in mixed case (AWS_SECRET_KEY, bcrypt, hashpw).
_SECRET_CREDENTIAL_KEYWORDS = [
    "secret_key", "secret key", "aws_secret", "api_key", "apikey",
    "private_key", "credential", "password", "passwd",
    "bcrypt", "scrypt", "argon2", "hashpw", "gensalt", "pbkdf2",
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

        # Deterministic overrides trump the LLM verdict (defense-in-depth):
        #  - destructive ops (case-sensitive, prompt-injection-resistant);
        #  - secret/credential handling (case-insensitive, Constitution V).
        artifact_lower = artifact.lower()
        if any(kw in artifact for kw in _HIGH_RISK_KEYWORDS) or any(
            kw in artifact_lower for kw in _SECRET_CREDENTIAL_KEYWORDS
        ):
            final_verdict = "HIGH_RISK"
        else:
            final_verdict = llm_verdict

        return {
            "security_verdict": final_verdict,
            "security_classifier_model": response.model,
            "agent_trace": ["SecurityReviewerAgent"],
        }
