"""VerifierAgent — sole Docker executor; wraps execute_fix logic for v2 pipeline."""

import time

import docker
import requests.exceptions

from autosentinel.agents.base import BaseAgent
from autosentinel.models import AgentState, ExecutionResult

_IMAGE = "python:3.10-alpine"
_TIMEOUT_SECONDS = 5
_MEM_LIMIT = "64m"


class VerifierAgent(BaseAgent):
    def run(self, state: AgentState) -> AgentState:
        fix_artifact = state.get("fix_artifact")

        if fix_artifact is None:
            return {
                "execution_result": ExecutionResult(
                    status="skipped",
                    return_code=None,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    error=None,
                ),
                "execution_error": None,
                "agent_trace": ["VerifierAgent"],
            }

        container = None
        try:
            client = docker.from_env()
            container = client.containers.run(
                _IMAGE,
                ["python", "-c", fix_artifact],
                detach=True,
                mem_limit=_MEM_LIMIT,
                network_mode="none",
            )
            start = time.monotonic()
            try:
                wait_result = container.wait(timeout=_TIMEOUT_SECONDS)
                duration_ms = int((time.monotonic() - start) * 1000)
                stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
                return_code = wait_result["StatusCode"]
                status = "success" if return_code == 0 else "failure"
                return {
                    "execution_result": ExecutionResult(
                        status=status,
                        return_code=return_code,
                        stdout=stdout,
                        stderr=stderr,
                        duration_ms=duration_ms,
                        error=None,
                    ),
                    "execution_error": None,
                    "agent_trace": ["VerifierAgent"],
                }
            except requests.exceptions.ReadTimeout:
                duration_ms = int((time.monotonic() - start) * 1000)
                container.kill()
                return {
                    "execution_result": ExecutionResult(
                        status="timeout",
                        return_code=None,
                        stdout="",
                        stderr="",
                        duration_ms=duration_ms,
                        error=None,
                    ),
                    "execution_error": None,
                    "agent_trace": ["VerifierAgent"],
                }
        except Exception as exc:
            return {
                "execution_result": None,
                "execution_error": str(exc),
                "agent_trace": ["VerifierAgent"],
            }
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
