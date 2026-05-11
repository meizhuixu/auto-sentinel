"""Constitution VII.1: only autosentinel/llm/{ark_client,glm_client}.py
may import the OpenAI SDK.

Mirrors the AST-boundary pattern in test_docker_import_boundary.py. The
allowlist is hard-coded; expanding it requires a constitution amendment.

Today (T006 commit) the test passes trivially — no openai imports exist
anywhere yet. The boundary becomes load-bearing once T021 lands the first
`import openai` inside ark_client.py: if T021 forgets to be inside an
allowlisted file, this test catches it.
"""

import ast
from pathlib import Path


_ALLOWED = {
    "autosentinel/llm/ark_client.py",
    "autosentinel/llm/glm_client.py",
    # mock_client.py does NOT need OpenAI SDK; if it ever imports openai,
    # that's a bug — and this test will flag it.
}


def _imports_openai(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "openai" or a.name.startswith("openai.") for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "openai" or node.module.startswith("openai.")
            ):
                return True
    return False


def test_only_allowlisted_files_import_openai():
    root = Path("autosentinel")
    violations = [
        str(p.relative_to(Path(".")))
        for p in root.rglob("*.py")
        if _imports_openai(p) and str(p.relative_to(Path("."))) not in _ALLOWED
    ]
    assert violations == [], f"Forbidden openai imports in: {violations}"
