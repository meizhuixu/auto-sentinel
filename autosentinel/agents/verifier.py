"""VerifierAgent — sole Docker executor; wraps execute_fix logic for v2 pipeline.

Sprint 6 (006-fix-verification-integrity, contracts/fix-artifact.md consumer
obligations): artifacts pass through deterministic normalization before any
container work — `rejected` short-circuits to an honest failure with no
container launched — and execution is write-to-file + read-only mount instead
of `python -c` (real __main__ semantics, artifact auditable on disk).
"""

import tempfile
import time
from pathlib import Path

import docker
import requests.exceptions

from autosentinel.agents._artifact_normalizer import normalize_fix_artifact
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

        normalized = normalize_fix_artifact(fix_artifact)
        normalization = {
            "outcome": normalized.outcome,
            "reason": normalized.reason,
        }
        if normalized.outcome == "rejected":
            return {
                "execution_result": ExecutionResult(
                    status="failure",
                    return_code=None,
                    stdout="",
                    stderr=normalized.reason or "artifact rejected",
                    duration_ms=0,
                    error=None,
                ),
                "execution_error": None,
                "fix_normalization": normalization,
                "agent_trace": ["VerifierAgent"],
            }

        container = None
        try:
            with tempfile.TemporaryDirectory(prefix="autosentinel-fix-") as workdir:
                (Path(workdir) / "fix.py").write_text(normalized.code)
                client = docker.from_env()
                container = client.containers.run(
                    _IMAGE,
                    ["python", "/workspace/fix.py"],
                    detach=True,
                    mem_limit=_MEM_LIMIT,
                    network_mode="none",
                    volumes={workdir: {"bind": "/workspace", "mode": "ro"}},
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
                        "fix_normalization": normalization,
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
                        "fix_normalization": normalization,
                        "agent_trace": ["VerifierAgent"],
                    }
        except Exception as exc:
            return {
                "execution_result": None,
                "execution_error": str(exc),
                "fix_normalization": normalization,
                "agent_trace": ["VerifierAgent"],
            }
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
