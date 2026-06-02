"""CI gate: every newly-added benchmark scenario yaml must be introduced by a
commit carrying a `Scenario-Authored-By:` trailer (contracts/benchmark-scenario.md
"Tier 3", spec FR-517 anti-AI-authoring gate).

Usage:
    python scripts/check_scenario_authorship.py [base_ref]

`base_ref` defaults to $GITHUB_BASE_REF then "main". The check:
  1. diff the PR head against the merge base for files ADDED in the range
     (`git diff --name-only --diff-filter=A <merge_base>...HEAD`);
  2. for each added `benchmarks/scenarios/*.yaml`, find the commit that
     introduced it (`git log --diff-filter=A -- <path>`) and assert that
     commit's message contains `Scenario-Authored-By:` (case-sensitive);
  3. exit non-zero with a clear message naming the offending file + commit on
     any miss; exit 0 (no-op) when no scenario yamls were added.
"""

from __future__ import annotations

import os
import subprocess
import sys

_TRAILER = "Scenario-Authored-By:"  # case-sensitive, verbatim


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _resolve_base(base_ref: str) -> str:
    """Resolve a base ref to a name git can use in this checkout.

    CI (actions/checkout) frequently has no local branch `main` — only
    `origin/main`, or the workflow passes a base commit SHA. A bare `main`
    then fails `git merge-base` with exit 128. Try the ref as given, then
    `origin/<ref>`; a SHA verifies as-is on the first try.
    """
    candidates = [base_ref]
    if "/" not in base_ref:
        candidates.append(f"origin/{base_ref}")
    for cand in candidates:
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}"],
                check=True, capture_output=True,
            )
            return cand
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(
        f"scenario-authorship: cannot resolve base ref {base_ref!r} "
        f"(tried {candidates}). Ensure the base branch/SHA is fetched — the "
        f"workflow uses actions/checkout with fetch-depth: 0."
    )


def _added_scenario_yamls(base_ref: str) -> list[str]:
    merge_base = _git("merge-base", _resolve_base(base_ref), "HEAD")
    out = _git("diff", "--name-only", "--diff-filter=A", f"{merge_base}...HEAD")
    paths = []
    for line in out.splitlines():
        line = line.strip()
        if (
            line.startswith("benchmarks/scenarios/")
            and line.endswith(".yaml")
            and "/" not in line[len("benchmarks/scenarios/"):]  # direct child only
        ):
            paths.append(line)
    return paths


def _introducing_commit(path: str) -> str:
    return _git("log", "--diff-filter=A", "--format=%H", "-1", "--", path)


def _commit_message(commit: str) -> str:
    return _git("log", "--format=%B", "-1", commit)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    base_ref = argv[0] if argv else os.environ.get("GITHUB_BASE_REF") or "main"

    added = _added_scenario_yamls(base_ref)
    if not added:
        print("scenario-authorship: no new benchmarks/scenarios/*.yaml added; nothing to check.")
        return 0

    offenders: list[tuple[str, str]] = []
    for path in added:
        commit = _introducing_commit(path)
        if not commit or _TRAILER not in _commit_message(commit):
            offenders.append((path, commit or "<unknown>"))

    if offenders:
        print("scenario-authorship: FAIL — missing 'Scenario-Authored-By:' trailer", file=sys.stderr)
        for path, commit in offenders:
            print(f"  - {path}  (introduced by {commit[:12]})", file=sys.stderr)
        print(
            "\nEvery commit that adds a benchmarks/scenarios/*.yaml MUST include a\n"
            "'Scenario-Authored-By: <human full name>' trailer (spec FR-517).",
            file=sys.stderr,
        )
        return 1

    print(f"scenario-authorship: OK — {len(added)} new scenario yaml(s), all human-authored.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
