# Summary

<!-- What does this PR change and why? -->

# Test evidence

<!-- Paste the relevant `pytest` summary / suite status. -->

## Sprint 5 benchmark-scenario gate (delete if no scenarios touched)

- [ ] All new or modified scenarios under `benchmarks/scenarios/` were
      human-authored before commit. No AI-generated drafts were committed
      (per spec FR-517).
- [ ] Each scenario yaml has a non-empty `human_labeled_by` and `labeled_at`.
- [ ] Each commit that adds a scenario yaml carries a `Scenario-Authored-By:`
      trailer (enforced by `scripts/check_scenario_authorship.py`).
