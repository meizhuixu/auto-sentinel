"""Tests for normalize_fix_artifact() — Sprint 6 T002 (contracts/fix-artifact.md).

Pure-function coverage of the Verifier-side deterministic normalization layer,
exhaustive over the data-model.md §1 state transitions:

    verbatim | wrapped (fragment symptoms only) | rejected

Wrapping must preserve statement semantics — asserted by exec()ing the wrapped
code in-process against a MARKER side-effect channel, not just by re-compiling.
"""

from autosentinel.agents._artifact_normalizer import (
    NormalizedArtifact,
    normalize_fix_artifact,
)


def _exec_with_marker(code: str) -> list:
    """Execute normalized code; return the MARKER list mutated by the script."""
    marker: list = []
    exec(compile(code, "<fix>", "exec"), {"MARKER": marker})  # noqa: S102
    return marker


class TestVerbatim:
    def test_complete_script_passes_verbatim(self):
        artifact = 'import json\nprint(json.dumps({"ok": True}))'
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "verbatim"
        assert result.code == artifact
        assert result.reason is None

    def test_script_with_function_and_internal_return_is_verbatim(self):
        artifact = "def fix(d):\n    return d.get('k')\n\nfix({'k': 1})"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "verbatim"
        assert result.code == artifact


class TestWrappedBareReturn:
    """The exact failure class from the real KeyError runs (DEBT.md)."""

    def test_bare_return_fragment_is_wrapped(self):
        artifact = "value = {'a': 1}.get('a')\nreturn"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "wrapped"
        # wrapped form must itself compile as a standalone script
        compile(result.code, "<fix>", "exec")

    def test_wrapped_code_preserves_statement_semantics(self):
        artifact = "MARKER.append(1)\nreturn\nMARKER.append(2)"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "wrapped"
        # the bare return becomes a function return: 1 runs, 2 is skipped
        assert _exec_with_marker(result.code) == [1]

    def test_return_with_value_is_wrapped_and_executes(self):
        artifact = "MARKER.append('ran')\nreturn {'status': 'fixed'}"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "wrapped"
        assert _exec_with_marker(result.code) == ["ran"]


class TestWrappedYield:
    def test_yield_fragment_is_wrapped_and_generator_is_drained(self):
        # wrapping a yield-fragment produces a generator function; the wrapper
        # must drain it so the body actually executes in the sandbox
        artifact = "MARKER.append(1)\nyield\nMARKER.append(2)"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "wrapped"
        assert _exec_with_marker(result.code) == [1, 2]


class TestRejected:
    def test_non_fragment_syntax_error_is_rejected(self):
        artifact = "def broken(:\n    pass"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "rejected"
        assert result.reason is not None and "SyntaxError" in result.reason

    def test_empty_artifact_is_rejected(self):
        result = normalize_fix_artifact("")
        assert result.outcome == "rejected"
        assert result.reason == "empty artifact"

    def test_whitespace_only_artifact_is_rejected(self):
        result = normalize_fix_artifact("   \n\t\n")
        assert result.outcome == "rejected"
        assert result.reason == "empty artifact"

    def test_fragment_that_still_fails_after_wrap_is_rejected(self):
        # first compile error is the bare return (fragment symptom), but the
        # wrapped form still fails: `if True:` with no body
        artifact = "return\nif True:"
        result = normalize_fix_artifact(artifact)
        assert result.outcome == "rejected"
        assert result.reason is not None

    def test_rejected_code_is_empty(self):
        # data-model.md §1: `code` is empty when rejected — nothing runnable
        # must leak toward the sandbox
        result = normalize_fix_artifact("def broken(:")
        assert result.code == ""


class TestResultShape:
    def test_returns_normalized_artifact_type(self):
        result = normalize_fix_artifact('print("x")')
        assert isinstance(result, NormalizedArtifact)

    def test_outcome_is_one_of_the_contract_literals(self):
        for artifact in ['print("x")', "return", "def broken(:"]:
            assert normalize_fix_artifact(artifact).outcome in (
                "verbatim", "wrapped", "rejected",
            )
