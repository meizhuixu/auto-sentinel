<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at `specs/006-fix-verification-integrity/plan.md`.
<!-- SPECKIT END -->

## Collaboration Model

**Roles:**
- **Claude Code** (this agent): executes git operations, runs tests,
  writes code, and maintains `[X]` completion status in tasks.md.
- **Developer** (Meizhui): owns design, decisions, commit message wording,
  PR descriptions, and any documentation outside the repo.

**Source of truth:**
- `specs/<sprint>/tasks.md` checkboxes (`[ ]` / `[X]`) are the authoritative
  record of task completion. Claude Code maintains them.
- Sprint progress, commit hashes, and suite status are queried live
  (`git log`, `git status`, `grep` over tasks.md) — never cached in any
  out-of-repo document.

**`[X]` write-back policy:**
- Claude Code decides when to mark a task `[X]`, without waiting for
  per-task approval from the developer.
- Criterion: the task's acceptance condition (e.g. "verify T0XX turns
  GREEN") is genuinely met AND the implementing commit has landed on the
  working branch.
- A task being `[X]` is independent of the surrounding PR's merge status.
  A `[X]` is a task-level fact, not a PR-level fact.
- The `[X]` write-back may piggyback on the implementing commit, or land
  as a separate `chore(sprint<N>): mark TXXX done` commit — whichever
  fits the workflow.

**Hard rules (inherited):**
- Local `git commit` is at Claude Code's discretion following the
  Test-First rhythm — no per-commit reporting or confirmation required.
- `git push`, opening a PR, and merging require the developer's explicit
  confirmation (irreversible / owner action).
- Test-First gate is non-negotiable: failing tests are committed first,
  implementation commits follow.

## Docs Maintenance (PROJECT.md / DEBT.md)

- `docs/PROJECT.md` is the project-context doc + status snapshot. Whenever a
  code change lands as a PR, update its "当前状态（快照）" section in the same
  PR (current sprint/phase, active branch, key outcomes).
- `DEBT.md` is the technical debt register: add an entry inline when new debt
  surfaces while coding; flip `[ ]` → `[X]` in the same commit that lands the
  fix (keep the entry, do not delete it).
- Authoritative progress stays in `git log` + `specs/<sprint>/tasks.md` —
  PROJECT.md is a snapshot / entry point, not the source of truth.

## Shell Execution

- Run shell commands one at a time, each as a separate invocation. Do not
  chain multiple commands together with `&&` (or `;`, `||`).
