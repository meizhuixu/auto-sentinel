"""Constitution VII.4: agent code MUST NOT contain hard-coded model names
or provider endpoint URLs. Everything resolves through config/model_routing.yaml
via factory.build_client_for_agent().

Substring grep over autosentinel/agents/**.py for the prohibited literals.
Today (T007 commit) the test passes trivially — Sprint 4 agents are
mock-bodied, no model literals present. The check becomes load-bearing at
T031-T034 when real-LLM bodies replace the mocks: the implementer must
route the model name via the injected LLMClient, not a string literal.
"""

from pathlib import Path

PROHIBITED_LITERALS = (
    "doubao-",
    "glm-",
    "ark.cn-beijing",
    "open.bigmodel.cn",
)


def test_agents_have_no_hardcoded_model_literals():
    root = Path("autosentinel/agents")
    violations: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in PROHIBITED_LITERALS:
            if needle in text:
                violations.append((str(path), needle))
    assert violations == [], (
        "Hard-coded model names / endpoint URLs found in agent code "
        "(Constitution VII.4 violation): " + repr(violations)
    )
