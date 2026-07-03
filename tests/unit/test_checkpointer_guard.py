"""Anti-silent-skip guard for checkpointer tests — Sprint 6 T016 (contracts/ci-gate.md).

The `requires_checkpointer` mark must never let CI go green by skipping: with
AUTOSENTINEL_REQUIRE_CHECKPOINTER=1 an unreachable :5434 DB means the tests
RUN (and fail loudly on connection errors) instead of skipping. Local runs
without the variable keep today's skip behavior.

The decision is a pure function so this policy is unit-testable without a
database.
"""

import pytest

from tests.integration._pr4_helpers import (
    checkpointer_required,
    should_skip_checkpointer_tests,
)


class TestSkipDecision:
    def test_unavailable_and_not_required_skips(self):
        # local dev without the container: skip (today's behavior)
        assert should_skip_checkpointer_tests(available=False, required=False) is True

    def test_unavailable_but_required_does_not_skip(self):
        # CI: never skip — the tests run and fail loudly on connect errors
        assert should_skip_checkpointer_tests(available=False, required=True) is False

    def test_available_never_skips(self):
        assert should_skip_checkpointer_tests(available=True, required=False) is False
        assert should_skip_checkpointer_tests(available=True, required=True) is False


class TestRequiredEnvParsing:
    def test_required_when_env_is_1(self, monkeypatch):
        monkeypatch.setenv("AUTOSENTINEL_REQUIRE_CHECKPOINTER", "1")
        assert checkpointer_required() is True

    def test_not_required_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("AUTOSENTINEL_REQUIRE_CHECKPOINTER", raising=False)
        assert checkpointer_required() is False

    def test_not_required_when_env_is_0(self, monkeypatch):
        monkeypatch.setenv("AUTOSENTINEL_REQUIRE_CHECKPOINTER", "0")
        assert checkpointer_required() is False


class TestMarkerWiring:
    def test_marker_is_skipif_built_from_the_decision(self):
        # the module-level mark must be a skipif whose condition came from
        # should_skip_checkpointer_tests (probe + env at import time)
        from tests.integration import _pr4_helpers

        mark = _pr4_helpers.requires_checkpointer
        assert mark.name == "skipif"
        expected = should_skip_checkpointer_tests(
            available=_pr4_helpers.checkpointer_available(),
            required=checkpointer_required(),
        )
        assert mark.args[0] == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
