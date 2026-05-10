# Contract: `LLMClient` (Sprint 5)

**Module**: `autosentinel/llm/protocol.py` (Protocol + value types)
**Concrete implementations**: `ark_client.py`, `glm_client.py`, `mock_client.py`
**AST boundary check**: `tests/unit/test_llm_provider_isolation.py`

---

## Public surface (Protocol)

```python
from typing import Protocol

class LLMClient(Protocol):
    def complete(
        self,
        *,
        messages: list["Message"],
        model: str,
        trace_id: str,
        agent_name: str,
        max_tokens: int,
        temperature: float,
    ) -> "LLMResponse": ...
```

The Protocol has **no other public methods**. Provider concrete classes may
hold private members (httpx connection pool, retry state) but **must not**
expose additional public methods that callers rely on — that would defeat
provider portability.

`Message`, `LLMRequest`, `LLMResponse` schemas: see `data-model.md` §1-3.

---

## Behavioural contract

### Pre-conditions

| Check | When |
|---|---|
| `trace_id` matches `^[0-9a-f]{32}$` | inside `complete()`, before the SDK call. Construct an internal `LLMRequest` (frozen) and let its `field_validator` enforce. |
| Model is registered under the bound endpoint | Already validated at startup by `ModelRoutingConfig._every_agent_model_is_registered` — `complete()` does not re-check. |
| `messages` non-empty | `LLMRequest` validation. |

### Side-effects (in order)

1. Open an `LLMTracer` context manager with `project="auto-sentinel"`,
   `component=agent_name`, `model=model`, `trace_id=trace_id`. **`trace_id`
   is always passed**; the tracer constructor validates it.
2. Issue the SDK call (`self._sdk_client.chat.completions.create(...)`)
   inside that context.
3. On success: call `tracer.set_tokens(prompt=..., completion=...)` with the
   provider's `usage` numbers.
4. Compute `input_cost_usd` and `output_cost_usd` from a per-model price
   table inside the concrete client, call
   `tracer.set_cost_breakdown(input_usd=..., output_usd=...)`.
5. Return an `LLMResponse` (frozen) with `cost_usd = Decimal(input + output)`,
   `latency_ms` measured around the SDK call, `trace_id` copied from input.
6. **After the response is returned**, call
   `cost_guard.accumulate(LLMResponse.cost_usd)`. This is where
   `CostGuardError` may be raised. The response has already been delivered to
   the caller — meaning the caller sees the *successful* result of the call
   that tripped the guard, but the **next** call from anywhere in the process
   raises immediately.

### Retry / timeout

```python
@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, max=8),
    retry=tenacity.retry_if_exception_type((httpx.TimeoutException, httpx.ReadError)),
)
def _do_call(...): ...
```

`httpx.Timeout(30.0)` on the SDK's underlying client. Retries occur **inside**
the `LLMTracer` context (i.e., one tracer span covers all retries; the latency
field captures the total wall-clock including retry waits).

---

## Error types

| Exception | Raised by | Caller obligation |
|---|---|---|
| `CostGuardError` | `cost_guard.accumulate()` after a successful SDK call when cumulative spend would exceed budget on the **next** call. | Let it propagate. LangGraph routes to `cost_exhausted_node` (END). Do **not** catch and retry. |
| `LLMTimeoutError` | concrete client wraps tenacity's `RetryError` after 3 attempts of `httpx.TimeoutException`. | Pipeline-fatal. Surface as the agent's `state["execution_error"]`. |
| `LLMProviderError` | concrete client wraps any non-timeout SDK exception (4xx, 5xx, schema mismatch). | Pipeline-fatal in Sprint 5; log & abort. Sprint 6+ may add a fallback-provider strategy. |
| `ConfigurationError` | `factory.build_client_for_agent()` at startup if `model_routing.yaml` references a missing env var. | Refuse to start the process. |

`ValueError` from a malformed `trace_id` is **not** wrapped — it surfaces from
the `LLMRequest`/`LLMTracer` validators directly. This is intentional: a
missing or malformed `trace_id` is a programmer bug, not a runtime fault.

---

## `MockLLMClient` contract

```python
class MockLLMClient(LLMClient):
    def __init__(self) -> None: ...

    def with_fixture_response(self, response: LLMResponse) -> "MockLLMClient":
        """Next call returns this response (or last-set if multiple calls). Returns self for chaining."""
    def with_error(self, exc: Exception) -> "MockLLMClient":
        """Next call raises this exception (one-shot)."""
    @property
    def call_count(self) -> int: ...
    @property
    def last_request(self) -> LLMRequest | None: ...
```

**Substitution rule**: tests pass `MockLLMClient` to the agent constructor.
**`unittest.mock.patch.object(CodeFixerAgent, ...)` is forbidden** in the test
suite; the existing patch site in `autosentinel/benchmark.py` is removed in
the same PR that introduces `MockLLMClient`.

---

## Provider isolation (AST CI check)

`tests/unit/test_llm_provider_isolation.py` walks every `*.py` under
`autosentinel/`, parses to AST via the stdlib `ast` module, fails the build
if any file outside an explicit allowlist contains an `Import` /
`ImportFrom` whose module name starts with `openai`.

Allowlist (hard-coded):

```python
ALLOWLIST = {
    "autosentinel/llm/ark_client.py",
    "autosentinel/llm/glm_client.py",
    # mock_client.py does NOT need OpenAI SDK; if it ever imports openai, that's a bug.
}
```

The allowlist may **not** be expanded without a constitution amendment
(Constitution VII.1).

---

## Coverage & test surface

| Test file | Cases (minimum) |
|---|---|
| `test_llm_provider_isolation.py` | 1 — fails on any unauthorised `openai` import; passes on the allowlisted files. |
| `test_no_hardcoded_models.py` | 1 — grep agent files for `doubao-`, `glm-`, `ark.cn-beijing`, `open.bigmodel.cn`; any hit fails. |
| `test_llm_protocol.py` | 4 — `LLMRequest` accepts valid trace_id; rejects empty / malformed; `LLMResponse` rejects negative tokens; `Message` is frozen. |
| `test_ark_client.py` | 3 — happy path against a stubbed `httpx.MockTransport`; retry triggers on timeout; raises `LLMProviderError` on 5xx. |
| `test_glm_client.py` | 3 — same as Ark with GLM-specific base_url. |
| `test_mock_client.py` | 3 — fixture response returned; error raised; `call_count` increments. |

**Coverage requirement**: 100 % branch coverage on `autosentinel/llm/`
(Constitution III + V Coverage invariant). Verified by `pytest --cov=autosentinel.llm --cov-fail-under=100`.
