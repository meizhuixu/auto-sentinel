"""SC-004: Only autosentinel/agents/verifier.py may import the docker SDK."""

import ast
from pathlib import Path


_ALLOWED = {
    "autosentinel/agents/verifier.py",
    # v1 legacy node — kept for benchmark v1 pipeline; not an agent module
    "autosentinel/nodes/execute_fix.py",
}


def _imports_docker(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "docker" or a.name.startswith("docker.") for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "docker" or node.module.startswith("docker.")
            ):
                return True
    return False


def test_only_verifier_imports_docker():
    root = Path("autosentinel")
    violations = [
        str(p.relative_to(Path(".")))
        for p in root.rglob("*.py")
        if _imports_docker(p) and str(p.relative_to(Path("."))) not in _ALLOWED
    ]
    assert violations == [], f"Forbidden docker imports in: {violations}"
