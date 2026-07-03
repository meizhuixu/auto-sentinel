"""Producer-side fix-artifact contract enforcement — Sprint 6 US1.

contracts/fix-artifact.md producer obligations, shared by CodeFixerAgent and
InfraSREAgent: after fence-stripping, the artifact must compile as a
standalone script; on SyntaxError the producer retries the LLM exactly once
with the compile error appended, then passes the artifact through regardless —
the Verifier's deterministic normalization layer owns the last line of
defense, so this layer never raises over a bad artifact.

The retry goes through the same LLMClient.complete() path as the original
call: CostGuard and trace propagation apply unchanged (Constitution VII.2/3).
"""

from __future__ import annotations

from typing import Optional

from autosentinel.agents._parsing import strip_markdown_fence
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.protocol import LLMClient, Message

RETRY_TEMPLATE = """Your previous response failed to compile as a standalone Python script.

Compile error: {error}

Your previous response was:
{artifact}

Respond again with a COMPLETE standalone Python script. It must compile on its
own: no bare top-level `return` or `yield`, no references to names that are
not defined or imported within the script itself. Executable code only, no
markdown, no explanations."""


def _compile_error(artifact: str) -> Optional[str]:
    try:
        compile(artifact, "<fix>", "exec")
    except SyntaxError as exc:
        return str(exc)
    return None


def complete_script_artifact(
    *,
    llm_client: LLMClient,
    model_config: AgentModelConfig,
    messages: list[Message],
    agent_name: str,
    trace_id: str,
) -> str:
    """Run the fix-generation call with compile()-validation + one retry.

    Returns the final fence-stripped artifact. Best-effort layer only: a
    still-broken artifact after the single retry is returned as-is.
    """

    def _call(msgs: list[Message]) -> str:
        response = llm_client.complete(
            messages=msgs,
            model=model_config.model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
        )
        return strip_markdown_fence(response.content)

    artifact = _call(messages)
    error = _compile_error(artifact)
    if error is None:
        return artifact

    retry_messages = messages + [
        Message(role="assistant", content=artifact),
        Message(role="user", content=RETRY_TEMPLATE.format(error=error, artifact=artifact)),
    ]
    return _call(retry_messages)
