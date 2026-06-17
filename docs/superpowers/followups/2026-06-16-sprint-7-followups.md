# Sprint 7 — Known Follow-ups for Sprint 8

Adversarial 5-lens review of Sprint 7 (Correctness / Spec compliance / Test quality / Regression risk / Cross-repo).

All 5 lenses returned APPROVE_WITH_NOTES — 0 blockers. Synthesizer
workflow stage hit org monthly spend limit before producing final
recommendation; manual synthesis: **MERGE_WITH_FOLLOWUPS** (no
blockers; 1 important finding deferred + minor).

## Important — address in Sprint 8

### I1. Missing `_assert_nhd_data_present` server-boot pre-flight

Spec at `2026-06-16-sprint-7-nhd-bluespace-design.md` L747-773 +
L923-927 + L953 prescribes this helper verbatim and names it 4 times
across implementation order, risks, test plan, and manual_e2e step 6.
**Not implemented.** Grep confirms zero occurrences in
`backend/app/variable_registry.py` (only orphan reference in
manual_e2e.md L277).

**Consequences:**
- No fast-fail on a Sprint 7 deploy where the 61 GB NHD GDB is missing
  — runner crashes mid-pipeline after lock acquisition, leaving
  partial state.
- manual_e2e.md negative test step 6 cannot be executed as written
  (no MetadataSchemaError raised on rename-aside).
- 2 prescribed registry tests absent.

**Fix:**
- Add `_assert_nhd_data_present(payload)` mirror of
  `_assert_tiger_data_present` (Sprint 6 H2 pattern):
  - Walk `payload["variables"].values()`
  - For any `experiment == "nhd_bluespace"`:
    - Check `{SPACESCANS_DATA_DIR}/data_full/NHD/C4` exists
    - Check `NHDPlus_H_National_Release_2_GDB.gdb` subdir exists
    - Raise `MetadataSchemaError` with the missing path
- Wire into `load_variables()` immediately after
  `_assert_tiger_data_present(payload)` call
- Add 2 unit tests: passes when present, raises when GDB missing

## Minor — could address inline or defer

### I2. Unused `read_table` import in precomputed_static_linkage.py

`src/spacescans/linkage/precomputed_static_linkage.py:26` imports
`read_table` from `spacescans.io.readers` but never uses it (exposure
loading via `get_reader(config.plugin)`). Leftover from earlier
Phase A draft.

**Fix:** Remove line 26 import. No behavioral impact.

### I3. Tile-count unit test gap (d076d4a)

The `nhd_proximity_linkage.py` tile-count fix (`d076d4a` on
`pkg/pypi-only`) is verified end-to-end by the integration tests
but has no unit-level lock. A regression in the tile-count math
would only be caught by the integration test (61 GB GDB required).

**Fix:** Add a unit test in `tests/test_nhd_proximity_linkage.py` that
exercises the bbox→tile-count invariant directly (0.05deg bbox →
exactly 1 tile per axis; 1.0deg → 2 tiles; 1.5deg → 3 tiles; etc.).

### I4. resolve_output_grouping docstring contract

The "episode" branch maps to `group_keys = ["PATID", "geoid"]`. This
produces per-episode rows ONLY because the `demo_conus` adapter
assigns `geoid = episode_id` (`helpers.py:76-77`). For a future
non-demo workload where `geoid` is the real BG geoid, `episode` mode
would collapse to per-(patient, geoid).

Pre-existing project-wide invariant (not Sprint 7 regression) but
worth documenting at the contract level.

**Fix:** Add a docstring note to `resolve_output_grouping` explaining
the demo_conus convention.

## Spend limit note

Sprint 7 final-review synthesizer failed with `You've hit your org's
monthly spend limit · ask your admin to raise it at
claude.ai/admin-settings/usage`. 5 lens reviewers completed
successfully; synthesizer is a single agent call so only the final
recommendation aggregator failed. Manual synthesis from lens outputs
yielded MERGE_WITH_FOLLOWUPS verdict; merge proceeded.

If subsequent sprints hit the same limit at workflow-orchestration
points, options: (a) raise the cap, (b) reduce sprint frequency,
(c) switch to lighter workflows (fewer parallel agents, smaller
scopes).
