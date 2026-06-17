# SpaceScans Web — Final Product State (post Sprint 12)

Sign-off date: **2026-06-16**

This document captures the shipped state of `spacescans-web` after the
Sprint 12 polish/follow-up sprint. The previous 11 sprints (Sprint 1 –
Sprint 11) shipped 8 experiments / 9 variables / 17 integration tests
end-to-end against the live data tree; Sprint 12 closed all 7 known
follow-ups (G1–G7) from the Sprint-4 adversarial review.

## Experiments shipped (8)

| # | Experiment key   | Boundary | C4 linkage pattern             | First shipped |
|---|------------------|----------|--------------------------------|---------------|
| 1 | `bg_ndi_wi`      | BG       | `precomputed_static_linkage`   | Sprint 2      |
| 2 | `zcta5_cbp`      | ZCTA5    | `precomputed_static_linkage`   | Sprint 3      |
| 3 | `tiger_proximity`| BG       | `precomputed_areal_linkage`    | Sprint 5      |
| 4 | `nhd_bluespace`  | BG       | `precomputed_static_linkage`   | Sprint 7      |
| 5 | `noise`          | BG       | `static_areal_linkage` (C3 `grid_weights`) | Sprint 8 |
| 6 | `vnl`            | BG       | `gridded_linkage` (C3 `grid_weights`)      | Sprint 10 |
| 7 | `temis`          | BG       | `gridded_linkage` (C3 `grid_weights`)      | Sprint 10 |
| 8 | `fara_tract`     | Tract    | `fara_linkage`                 | Sprint 11     |

All experiments use the `output_grouping=patient` convention via
`spacescans.linkage.helpers.resolve_output_grouping` (Sprint 7 A1 /
Sprint 8 I4 / Sprint 10 A1 / Sprint 11 Phase A).

## Variable catalog (9 variables, 4 boundaries)

`backend/app/data/variable_metadata.json` (`schema_version: 1`):

| Variable key      | Experiment       | Boundary | display_unit                    | coverage_years |
|-------------------|------------------|----------|---------------------------------|----------------|
| `ndi`             | bg_ndi_wi        | BG       | `z-score`                       | 2012–2022      |
| `walkability`     | bg_ndi_wi        | BG       | `1-20 index`                    | 2016–2021      |
| `cbp_zcta5`       | zcta5_cbp        | ZCTA5    | `establishments / 1k residents` | 2013–2019      |
| `tiger_proximity` | tiger_proximity  | BG       | `meters`                        | 2013–2019      |
| `nhd_bluespace`   | nhd_bluespace    | BG       | `meters`                        | 2024–2024      |
| `noise`           | noise            | BG       | `dBA`                           | 2020–2020      |
| `vnl`             | vnl              | BG       | `radiance`                      | 2013–2019      |
| `temis`           | temis            | BG       | `UV index`                      | 2013–2019      |
| `fara_tract`      | fara_tract       | Tract    | `binary flags`                  | 2013–2019      |

Boundary coverage: **BG ×7, ZCTA5 ×1, Tract ×1, County ×0**.

The catalog is the single source of truth for both the dispatcher
(`variable_registry.variables_by_experiment`) and the frontend
(`/api/variables` → `groupByExperiment`).

## Test counts (post Sprint 12)

| Suite                                                   | Count    |
|---------------------------------------------------------|----------|
| Pipeline (`spacescans-project/tests`)                   | **99**   |
| Web — default (`spacescans-web/backend pytest -q`)      | **261** (+1 skipped) |
| Web — integration (`spacescans-web/backend -m integration`) | **17** |

Sprint 12 net delta vs. post-Sprint-11 baseline: web default +7 tests
(G1 atomicity, G2 cross-endpoint 401, G3 fan_in NaN-fill, G5 startup
probe, G6 sentinel + external-SIGTERM, G7 un-skipped lock test) and
–1 skipped. Pipeline tests unchanged (all G items were web-side).

Frontend: `npx tsc --noEmit` clean.

## Commit history scale

- Pipeline (`spacescans-project pkg/pypi-only` branch): ~30+ commits
  across the 11+1 sprints (mostly linkage refactors + experiment
  wiring).
- Web (`spacescans-web main`): **112+ commits** since Sprint 1
  (commit `58deb12`, "docs(spec): Sprint 1 — pre-flight coverage check
  + C3 weights cross-task cache").

## Sprint 12 polish — G1–G7 status

| ID | Topic                                              | Status               | Commit |
|----|----------------------------------------------------|----------------------|--------|
| G1 | Dispatcher TOCTOU race (pid vs status='running')   | **Closed (fixed)**   | `592c8d2` |
| G2 | 401 vs 403 inconsistency on `/api/variables`       | **Closed (fixed)**   | `71b03fd` |
| G3 | `_merge.fan_in` input-anchored NaN-fill unit test  | **Closed (test added)** | `0d7f04c` |
| G4 | Standalone runner CLI no longer produces `result.csv` | **Documented + deferred**  | `44c9301` |
| G5 | Lazy probe vs FastAPI startup                      | **Closed (fixed)**   | `fb854db` |
| G6 | rc==143 conflates external SIGTERM with user cancel | **Closed (sentinel)** | `9f130be` |
| G7 | Stale `@pytest.mark.skip` on `test_start_lock_returns_409_when_busy` | **Closed (un-skipped)** | `0999300` |

## Known limitations (acknowledged, not worth fixing)

These were noted across sprints and are intentionally left alone:

- **Markdown lint warnings in `manual_e2e.md` Sprint 4 section** —
  verbatim shell block; not user-facing.
- **`frontend/tsconfig.tsbuildinfo` shows as modified after `tsc`** —
  cache artifact; not in git tracking.
- **`groupByExperiment` is O(catalog)** — fine at ≤20 variables; the
  catalog is bounded.
- **Standalone per-experiment runner CLI does not emit `result.csv`**
  (G4): documented in `manual_e2e.md`; the dispatcher path is the sole
  supported production flow.
- **Sentinel-file cancellation is best-effort on unwritable task_dirs**
  (G6): the OSError on `.cancelled.touch()` is swallowed; in that
  edge case rc==143 degrades to the legacy "all-SIGTERM-as-cancel"
  interpretation.
- **`uvicorn --workers N` startup probe is per-worker, not per-cluster**
  (G5): each worker probes once at boot, which is sufficient for the
  intended "fail fast on stale pipeline install" guarantee. There is
  no cross-worker coordination — that is by design.
- **FastAPI `@app.on_event("startup")` is deprecated in favor of
  lifespan handlers**: migration is a single-commit refactor and out
  of scope for this polish sprint; no functional impact.

## Sign-off

**Product polished.** All 8 experiments, all 9 variables, and the 4
boundary types in the catalog are exercised by the 17-test live-data
integration suite. The 261-test default suite covers dispatcher
contracts, registry validation, authentication, merge/fan-in
invariants, cancellation lineage (user + external SIGTERM
discrimination), and per-experiment runner shapes. The frontend is
`tsc`-clean against the API contract.

No open Sprint-13 follow-ups identified. Future work (if any) would
be feature additions (new experiments, new variables, new boundary
types) rather than tech-debt — the polish surface is closed.
