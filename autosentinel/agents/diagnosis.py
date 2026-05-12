"""DiagnosisAgent — classifies error into CODE/INFRA/CONFIG/SECURITY."""

from autosentinel.agents.base import BaseAgent
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient
from autosentinel.models import AgentState

_INFRA_KEYWORDS = (
    "timeout", "connection", "unreachable", "refused", "dns", "network",
    "oom", "memory", "killed", "heap", "out of memory", "limit",
    "cpu", "throttl", "resource",
)
_CONFIG_KEYWORDS = (
    "config", "env", "environment", "secret", "key", "variable", "missing", "not set",
)
_SECURITY_KEYWORDS = (
    "injection", "xss", "auth", "security", "unauthori", "exploit",
    "csrf", "privilege", "tamper",
)


class DiagnosisAgent(BaseAgent):
    def __init__(
        self,
        *,
        llm_client: LLMClient,
        model_config: AgentModelConfig,
    ) -> None:
        self._llm_client = llm_client
        self._model_config = model_config

    def run(self, state: AgentState) -> AgentState:
        # TODO(W2): replace with real LLM call
        log = state["error_log"]
        haystack = f"{log['error_type']} {log['message']}".lower()

        if any(kw in haystack for kw in _INFRA_KEYWORDS):
            category = "INFRA"
        elif any(kw in haystack for kw in _CONFIG_KEYWORDS):
            category = "CONFIG"
        elif any(kw in haystack for kw in _SECURITY_KEYWORDS):
            category = "SECURITY"
        else:
            category = "CODE"

        return {"error_category": category, "agent_trace": ["DiagnosisAgent"]}
