"""execute_fix node — runs fix_script in an isolated Docker container."""

import time

import docker
import requests.exceptions

from autosentinel.models import DiagnosticState, ExecutionResult

_IMAGE = "python:3.10-alpine"
_TIMEOUT_SECONDS = 5
_MEM_LIMIT = "64m"


def execute_fix(state: DiagnosticState) -> dict:
    """Execute fix_script in a sandboxed Docker container."""
    fix_script = state.get("fix_script")

    if fix_script is None:
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
        }

    container = None
    try:
        client = docker.from_env()
        container = client.containers.run(
            _IMAGE,
            ["python", "-c", fix_script],
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
            }
    except Exception as exc:
        return {
            "execution_result": None,
            "execution_error": str(exc),
        }
    finally:
        if container is not None:
            container.remove(force=True)
