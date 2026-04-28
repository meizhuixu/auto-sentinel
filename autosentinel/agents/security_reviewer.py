"""SecurityReviewerAgent — keyword-based security classification of fix_artifact."""

from autosentinel.agents.base import BaseAgent
from autosentinel.models import AgentState

_HIGH_RISK_KEYWORDS = [
    "DROP TABLE", "DROP DATABASE", "TRUNCATE TABLE",
    "rm -rf /", "rm -rf ~", "chmod 777", "mkfs", "dd if=",
]


class SecurityReviewerAgent(BaseAgent):
    def run(self, state: AgentState) -> AgentState:
        # TODO(W2): replace with real LLM call
        artifact = state.get("fix_artifact") or ""
        verdict = "SAFE"
        if any(kw in artifact for kw in _HIGH_RISK_KEYWORDS):
            verdict = "HIGH_RISK"
        return {"security_verdict": verdict, "agent_trace": ["SecurityReviewerAgent"]}
