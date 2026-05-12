"""CodeFixerAgent — mock fix generator for CODE and SECURITY categories."""

from autosentinel.agents.base import BaseAgent
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient
from autosentinel.models import AgentState

_MOCK_FIXES = {
    "CODE":     'print("Flushing stale state and re-initialising application context...")',
    "SECURITY": 'print("Applying security patch to input validation layer...")',
}


class CodeFixerAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def _get_fix_for_security(self) -> str:
        """Overridable in tests to inject HIGH_RISK artifact."""
        return _MOCK_FIXES["SECURITY"]

    def run(self, state: AgentState) -> AgentState:
        # TODO(W2): replace with real LLM call
        category = state.get("error_category", "CODE")
        if category == "SECURITY":
            artifact = self._get_fix_for_security()
        else:
            artifact = _MOCK_FIXES.get(category, _MOCK_FIXES["CODE"])
        return {"fix_artifact": artifact, "agent_trace": ["CodeFixerAgent"]}
