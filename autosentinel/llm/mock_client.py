"""Test double for LLMClient (contracts/llm-client.md §"MockLLMClient contract").

Two roles:
1. Injected into agent unit tests via constructor DI (no patch.object).
2. PR-1 placeholder returned by factory.build_client_for_agent() until
   concrete provider clients (T021/T022) are wired in PR-2.

Constitution VII.1: this module does NOT import openai. The provider
isolation AST check (test_llm_provider_isolation.py) would flag it if it did.
"""

from __future__ import annotations

from typing import Optional

from autosentinel.llm.protocol import LLMRequest, LLMResponse, Message


class MockLLMClient:
    """In-memory test double satisfying the LLMClient Protocol.

    - `with_fixture_response(resp)` sets a persistent fixture response;
      every subsequent `complete()` returns it. Returns self for chaining.
    - `with_error(exc)` arms a one-shot exception to raise on the next
      `complete()` call. Returns self for chaining.
    - `call_count` / `last_request` are read-only observability hooks.
    """

    def __init__(self) -> None:
        self._fixture_response: Optional[LLMResponse] = None
        self._next_error: Optional[Exception] = None
        self._call_count: int = 0
        self._last_request: Optional[LLMRequest] = None

    def with_fixture_response(self, response: LLMResponse) -> "MockLLMClient":
        self._fixture_response = response
        return self

    def with_error(self, exc: Exception) -> "MockLLMClient":
        self._next_error = exc
        return self

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def last_request(self) -> Optional[LLMRequest]:
        return self._last_request

    def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        trace_id: str,
        agent_name: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        # Build LLMRequest BEFORE the error check so last_request always
        # mirrors the most recent call regardless of outcome. trace_id
        # validation surfaces here as ValueError (Constitution VII.3).
        req = LLMRequest(
            messages=messages,
            model=model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._call_count += 1
        self._last_request = req

        if self._next_error is not None:
            err = self._next_error
            self._next_error = None  # one-shot
            raise err

        if self._fixture_response is None:
            raise RuntimeError(
                "MockLLMClient.complete() called without with_fixture_response() "
                "or with_error() configured"
            )
        return self._fixture_response
