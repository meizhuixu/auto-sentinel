# Technical Debt Register

Technical debt items for the Auto Sentinel project. `[ ]` = open, `[X]` = resolved.

When code changes surface a new debt item, Claude Code adds an entry inline. When an item is resolved, mark it `[X]` in the same commit that lands the fix.

---

## Cross-Sprint Debt (design / process layer)

- [ ] **Sprint 5 PR-4**: migrate MemorySaver → PostgresSaver; define interrupt timeout policy.
- [ ] **Sprint 6**: retire the v1 single-agent pipeline (search code for `TODO(SPRINT6_V1_RETIREMENT)`).
- [ ] **Low priority** (ignore during Sprint 5): take `.claude/settings.local.json` out of git tracking.
- [ ] **Check before Sprint 6 kickoff**: `.specify/feature.json` is not auto-bumped by `/specify`. A new feature's first `/plan` run will clobber the previous feature's `plan.md` unless this file is manually updated first. Hit this in Sprint 5 — losing Sprint 4's `plan.md`.
- [ ] **Sprint 6 onboarding**: `uv run pytest` falls back to system Python because pytest lives in the `dev` extras group, which `uv sync` does not install by default. Consider adding `uv sync --extra dev` to `CLAUDE.md` / `README` onboarding steps.

---

## Sprint 5 Pending Anchors (cross-PR items within the active sprint)

- [ ] **PR-3 first action**: `autosentinel/llm/_placeholder_responses.py` hardcodes the Diagnosis placeholder response to `{"category": "CODE"}`. As a result, the production graph always routes to CodeFixer and never reaches InfraSRE / CONFIG / SecurityReviewer paths. **Resolution**: once `ArkLLMClient` ships and `build_client_for_agent()` dispatches on `endpoint_alias` instead of returning the placeholder, strip the **11 `xfail(strict=True)` markers** (4 in `tests/integration/test_multi_agent_graph_routing.py` Group A, 7 in `tests/integration/test_multi_agent_graph_security.py` Group B).

- [ ] **Single PR (own branch) or fold into PR-5** — *raised during PR-4*: the production graph's `build_client_for_agent()` (`autosentinel/llm/factory.py:142-148`) **still hands out `MockLLMClient` + `_placeholder_responses` for ALL 5 agents** — concrete `ArkLLMClient` / `GlmLLMClient` dispatch on `endpoint_alias` was never wired into the production factory (PR-3 only shipped the two client classes + `scripts/run_holdout_eval.py`, which instantiate them directly). Consequence: the production multi-agent graph always routes Diagnosis→CODE→CodeFixer→SAFE; it never reaches InfraSRE / SecurityReviewer HIGH_RISK paths on real input. PR-4's tests sidestep this entirely via the hermetic D2 `agents=` injection seam (no production-factory change, per the agreed plan). **Resolution**: switch `build_client_for_agent()` to concrete dispatch + delete `_placeholder_responses.py`, then strip the **11 `@pytest.mark.xfail(reason=..., strict=True)` markers** (4 in `tests/integration/test_multi_agent_graph_routing.py`, 7 in `tests/integration/test_multi_agent_graph_security.py`). NB: those markers use `xfail(reason=..., strict=True)` form, so the count above (and the line-21 entry's "11") is correct — a bare `grep "xfail(strict=True)"` misses them. This needs real API keys + budget in whatever runs it, so it is deliberately NOT in hermetic PR-4.

- [ ] **PR-5 wrap-up or Sprint 6**: `factory._load_routing_config()` reads `Path("config/model_routing.yaml")` — a path relative to the process CWD. The full test suite happens to pass because the module-level singleton cache is populated when CWD = project root; running a single test file (e.g. `pytest tests/unit/test_run_pipeline.py`) from elsewhere triggers `ConfigurationError: model routing config not found`. **Fix**: use `Path(__file__).resolve().parent.parent.parent / "config/model_routing.yaml"`.
