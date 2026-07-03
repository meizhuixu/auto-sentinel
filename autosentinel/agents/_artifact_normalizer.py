"""Deterministic fix-artifact normalization — Sprint 6 US1.

The Verifier-side guarantee layer of contracts/fix-artifact.md: producers are
*asked* (prompt + compile()-validated retry) to emit complete runnable
scripts, but LLM output has no hard guarantee. This pure function pins SC-001
(zero format-induced sandbox failures) regardless of what the producers emit.

Kept separate from VerifierAgent so it is unit-testable without Docker and the
Verifier stays the thin, sole-Docker-executor module (Constitution I).
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Literal, Optional

_FRAGMENT_SYMPTOMS = (
    "'return' outside function",
    "'yield' outside function",
)

# The wrapper calls the fix body and drains it when the wrap turned the body
# into a generator function (a yield-fragment's statements only execute on
# iteration). send/throw discriminates generators from ordinary iterables.
_WRAPPER_TEMPLATE = """\
def __autosentinel_fix__():
{body}

_autosentinel_result = __autosentinel_fix__()
if hasattr(_autosentinel_result, "send") and hasattr(_autosentinel_result, "throw"):
    for _ in _autosentinel_result:
        pass
"""


@dataclass(frozen=True)
class NormalizedArtifact:
    """Outcome of normalization (data-model.md §1).

    code    — what the sandbox will execute ('' when rejected)
    outcome — verbatim | wrapped | rejected
    reason  — populated iff rejected
    """

    code: str
    outcome: Literal["verbatim", "wrapped", "rejected"]
    reason: Optional[str] = None


def _compile_error(artifact: str) -> Optional[SyntaxError]:
    try:
        compile(artifact, "<fix>", "exec")
    except SyntaxError as exc:
        return exc
    return None


def normalize_fix_artifact(artifact: str) -> NormalizedArtifact:
    """Classify + normalize a fix artifact for sandbox execution.

    Exhaustive transitions:
      empty/whitespace          -> rejected("empty artifact")
      compiles                  -> verbatim
      fragment SyntaxError      -> wrap in a function; recompile
                                   -> wrapped | rejected
      any other SyntaxError     -> rejected(error text)
    """
    if not artifact.strip():
        return NormalizedArtifact(code="", outcome="rejected", reason="empty artifact")

    error = _compile_error(artifact)
    if error is None:
        return NormalizedArtifact(code=artifact, outcome="verbatim")

    if not any(symptom in str(error) for symptom in _FRAGMENT_SYMPTOMS):
        return NormalizedArtifact(
            code="", outcome="rejected", reason=f"SyntaxError: {error}"
        )

    wrapped = _WRAPPER_TEMPLATE.format(body=textwrap.indent(artifact, "    "))
    wrap_error = _compile_error(wrapped)
    if wrap_error is not None:
        return NormalizedArtifact(
            code="", outcome="rejected", reason=f"SyntaxError: {wrap_error}"
        )
    return NormalizedArtifact(code=wrapped, outcome="wrapped")
