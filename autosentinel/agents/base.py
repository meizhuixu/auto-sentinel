"""BaseAgent abstract class for Sprint 4 multi-agent pipeline."""

from abc import ABC, abstractmethod

from autosentinel.models import AgentState


class BaseAgent(ABC):
    @abstractmethod
    def run(self, state: AgentState) -> AgentState:
        """Process state and return updated fields.

        MUST be a pure function of state — no side effects except Docker (VerifierAgent only).
        MUST append self.__class__.__name__ to agent_trace in every return.
        MUST NOT raise exceptions — capture errors in state fields.
        """
        ...
