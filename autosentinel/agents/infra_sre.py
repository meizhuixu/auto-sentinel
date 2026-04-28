"""InfraSREAgent — mock fix generator for INFRA and CONFIG categories."""

from autosentinel.agents.base import BaseAgent
from autosentinel.models import AgentState

_MOCK_FIXES = {
    "INFRA":  'print("Restarting connection pool for upstream dependency...")',
    "CONFIG": 'print("Reloading environment variables from secrets store...")',
}


class InfraSREAgent(BaseAgent):
    def run(self, state: AgentState) -> AgentState:
        # TODO(W2): replace with real LLM call
        category = state.get("error_category", "INFRA")
        artifact = _MOCK_FIXES.get(category, _MOCK_FIXES["INFRA"])
        return {"fix_artifact": artifact, "agent_trace": ["InfraSREAgent"]}
