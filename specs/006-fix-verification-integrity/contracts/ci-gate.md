# Contract: CI Quality Gate

**Feature**: `006-fix-verification-integrity` | **Version**: 1 (Sprint 6)
**Artifact**: `.github/workflows/ci.yml` (new; `scenario-authorship.yml` is a
separate, untouched workflow).

## Triggers

- `pull_request` (all branches, no path filter — the gate is universal)
- `push` to `main`

## Jobs

| Job | Steps | Failure blocks merge |
|-----|-------|----------------------|
| `lint` | checkout → setup-uv (Python 3.11) → `uv sync --extra dev --frozen` → `uv run ruff check .` | yes |
| `typecheck` | same setup → `uv run mypy autosentinel` | yes |
| `test` | same setup → `uv run pytest` | yes |

The AST boundary gates are pytest tests
(`tests/unit/test_docker_import_boundary.py`,
`tests/unit/test_llm_provider_isolation.py`) and therefore run inside the
`test` job — a boundary violation fails CI by construction (Constitution I /
VII.1 enforcement vehicle).

## `test` job environment

- **Service container**: `postgres:16`, ports `5434:5432`,
  `POSTGRES_USER=postgres` / `POSTGRES_PASSWORD=postgres` /
  `POSTGRES_DB=postgres`, `pg_isready` health check — mirrors
  `infra/docker-compose.checkpointer.yml` so local and CI DSNs are identical
  (`postgresql://postgres:postgres@localhost:5434/postgres`).
- **Env**: `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1`.
- **Docker daemon**: required (Verifier sandbox tests); present by default on
  `ubuntu-latest`.

## Anti-silent-skip clause

`requires_checkpointer` (`tests/integration/_pr4_helpers.py`) MUST escalate
skip → **fail** when `AUTOSENTINEL_REQUIRE_CHECKPOINTER=1` and the 5434 probe
fails. Local runs without the variable keep skip behavior. Acceptance: CI logs
show the cross-process checkpointer tests (T029/T036/T044c lineage) in the
executed set, never in the skipped set.

## Toolchain pinning

`ruff>=0.4.0` and `mypy>=1.10.0` live in the `dev` extra of `pyproject.toml`
(re-synced with `uv.lock`, which already carries these pins). CI installs
exclusively via `uv sync --extra dev --frozen` — no `pip install` drift, and
`--frozen` skips re-resolution so the `tracing` extra's local-path source
(`../llmops-dashboard`, absent on CI) is never touched (verified by local
simulation: plain `uv sync --extra dev` fails without the sibling repo,
`--frozen` succeeds).
