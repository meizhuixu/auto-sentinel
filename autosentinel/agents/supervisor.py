"""SupervisorAgent — routes error_category to the correct specialist."""

from autosentinel.agents.base import BaseAgent
from autosentinel.models import AgentState

_SPECIALIST_NAMES = {
    "code_fixer": "CodeFixerAgent",
    "infra_sre": "InfraSREAgent",
}


class SupervisorAgent(BaseAgent):
    def get_specialist_key(self, category: str | None) -> str:
        """Return the LangGraph edge key for the given error_category."""
        if category in ("INFRA", "CONFIG"):
            return "infra_sre"
        return "code_fixer"

    def run(self, state: AgentState) -> AgentState:
        # TODO(W2): replace with real LLM call
        category = state.get("error_category") or "UNKNOWN"
        key = self.get_specialist_key(category)
        agent_name = _SPECIALIST_NAMES[key]
        return {
            "routing_decision": f"{category} → {agent_name}",
            "agent_trace": ["SupervisorAgent"],
        }
