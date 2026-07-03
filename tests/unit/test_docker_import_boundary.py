"""SC-004: Only autosentinel/agents/verifier.py may import the docker SDK.

Sprint 6 (006-fix-verification-integrity US4): the v1 grandfathering entry
(autosentinel/nodes/execute_fix.py, Constitution v2.1.1 clause) is removed —
the v1 pipeline is retired and the Verifier is the single Docker importer.
Expanding this allowlist requires a constitution amendment.
"""

import ast
from pathlib import Path


_ALLOWED = {
    "autosentinel/agents/verifier.py",
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
