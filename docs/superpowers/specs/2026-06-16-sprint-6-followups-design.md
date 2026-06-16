# Sprint 6 Spec — Sprint 5 Follow-ups (H1-H6)

**Date:** 2026-06-16
**Status:** Approved by user 2026-06-16 (Sprint 5 cleanup only).
**Goal:** Close the 6 IMPORTANT findings from Sprint 5's adversarial cross-lens final review (blocker was fixed inline at 3eabacb). No new experiments, no new variables. Pure tech-debt cleanup so subsequent sprints build on a stable foundation.

## Background

Sprint 5 shipped the `tiger_proximity` runner end-to-end: pipeline-side
`linkage_pattern: tiger_proximity` + the C3-tiled `tl_{year}_{cnty}_roads.zip`
ingest, web-side runner mirror, dispatcher fan-out across three
experiments, registry-driven variables UI surfacing the new variable,
plus a Phase A (`pkg/pypi-only`) coordinated bump moving the pipeline
toward a real PyPI install posture. The post-T8 adversarial multi-lens
review surfaced one blocker — fixed in-sprint at commit `3eabacb`
(dispatcher slot reseeding after Sprint 4's slot-status race) — plus 6
IMPORTANT findings that did not gate Sprint 5 ship but compound risk
if carried into Sprint 7's continued experiment buildout.

The findings live in
`spacescans-web/docs/superpowers/followups/2026-06-16-sprint-5-followups.md`:

- **H1.** `backend/requirements.txt` has no `spacescans-pipeline` pin;
  the web's runtime contract with the editable install is
  documentation-only.
- **H2.** Server-boot pre-flight for TIGER C4 tiles is missing —
  `variable_registry.load_variables` validates schema + experiment
  whitelist but does not assert the on-disk
  `data_full/TIGER/C4/tiger{year}_roads/` subdirs exist for declared
  `coverage_years`. Tile-miss surfaces only mid-run.
- **H3.** Sprint 5's B4-fix (`ae6ca7c`) attributed cache-hit lines in
  `tiger_proximity.py` to `step.name`, but cache-check-fail /
  cache-write / cache-write-fail in the same file plus ALL four cache
  lines in `bg_ndi_wi.py` and `zcta5_cbp.py` still emit `source="runner"`.
- **H4.** `test_three_experiment_dispatch_preserves_metadata_order`
  monkeypatches `variables_by_experiment` with a hand-rolled dict that
  already matches the real metadata file's order — redundant and hides
  regressions in the real registry path.
- **H5.** Four linkage modules dereference `config.time.output_grouping`
  unconditionally; with `time=None` they raise AttributeError instead
  of a clear ValueError. The followups doc names two files; research
  found the same shape in two more (`static_areal_linkage.py`,
  `yearly_areal_bg_vintage_linkage.py`).
- **H6.** `tests/test_pipeline_smoke.py:159-160` overrides `PYTHONPATH`
  to the worktree's `src/`. With Phase A's editable install resolving
  to the same path, the override is now a no-op on single-checkout dev
  boxes but remains load-bearing on worktree-based dev.

These six findings are the full scope of Sprint 6.

## Goal

Resolve H1-H6 without adding new behaviour. The Sprint 6 diff is a
sequence of small, independent fixups with regression tests; the
system's user-visible surface area is unchanged except for a new
startup-time `MetadataSchemaError` on missing TIGER tiles (H2) and a
clearer `ValueError` on missing time-block (H5) — both replace
later-firing AttributeError / FileNotFoundError surfaces.

## Scope

### In scope (Sprint 6)

- **H1.** Add `spacescans-pipeline>=0.2` to `backend/requirements.txt`.
  Coordinated with the Phase A version bump in pipeline `pyproject.toml`
  (`0.1.0` → `0.2.0`) in the same PR.
- **H2.** Add `_assert_tiger_data_present(payload)` to
  `variable_registry`, called from `load_variables` after the
  experiment-whitelist loop and before the cache write. Expands each
  `tiger_proximity` variable's `coverage_years[min, max]` to the
  inclusive year range; asserts
  `{SPACESCANS_DATA_DIR}/data_full/TIGER/C4/tiger{year}_roads/` exists
  per year. Raises `MetadataSchemaError` on miss.
- **H3.** Back-port `source=step.name` to all four cache-related
  `_append_log` calls (hit + check-fail + write + write-fail) in all
  three C3-aware runners. SIGTERM-cancel log line stays as
  `source="runner"` (lifecycle event, not a step event).
- **H4.** Delete the monkeypatch block at
  `test_task_manager_dispatch.py:269-276`; test exercises the real
  registry path against the on-disk `variable_metadata.json`.
- **H5.** Add `resolve_output_grouping(config) -> str` helper to
  `src/spacescans/linkage/helpers.py`; replace the four if/elif/else
  blocks at `precomputed_areal_linkage.py:118`, `yearly_areal_linkage.py:50`,
  `static_areal_linkage.py:46`, and `yearly_areal_bg_vintage_linkage.py:143`
  with calls to the helper. Pipeline repo change first; web absorbs
  via editable install.
- **H6.** Rewrite `tests/test_pipeline_smoke.py:159-160` as a
  conditional override: inject `PYTHONPATH` only when
  `Path(spacescans.__file__).resolve()` differs from the worktree's
  `src/spacescans/__init__.py`.

### Out of scope (deferred)

- New experiments — `nhd_bluespace`, `vnl`, `temis`, `fara_tract`,
  `noise`. Sprint 8+.
- G1-G7 from Sprint 4's adversarial backlog. Could roll into Sprint 7
  cleanup; Sprint 6 is strictly Sprint-5-finding scope to keep the
  cleanup auditable.
- Frontend test framework (jest / vitest).
- Per-variable shapefile coverage. Still bbox-based.
- LRU cap on C3 cache directory.
- A metadata editor UI.
- Multi-experiment parallel spawn. Sequential remains the contract.

## H1 — spacescans-pipeline version pin

### Today's state

`backend/requirements.txt` is 15 lines and has no `spacescans-pipeline`
entry. The pipeline's distribution name (per
`/Users/xai/Desktop/spacescans-project/pyproject.toml:6`) is
`spacescans-pipeline`; the import name is `spacescans`. The followups
doc's shorthand "`spacescans>=X.Y`" is the IMPORT name; pip would
resolve a different unrelated package or fail to resolve. The correct
pin uses the distribution name.

The pipeline's current version is `0.1.0` (`pyproject.toml:7`).
Sprint 4's F3 probe message already references the target —
"Install/upgrade spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension
contract)" at `variable_registry.py:52`. Pinning `>=0.2` today against
the unbumped `0.1.0` would fail resolution.

### Design decisions

- **Pin name: `spacescans-pipeline`** (distribution, not import). Pip
  resolves by distribution name.
- **Bump in lockstep:** `pyproject.toml` version bumps to `0.2.0` in
  the same PR as the requirements add. Sprint 4's F3 probe already
  asserts the `output_grouping` field that `>=0.2` is meant to encode;
  the bump makes the probe's message accurate against the on-disk
  install.
- **Deployment path:** the web's deployment is `pip install -e ..` +
  `pip install -r backend/requirements.txt`. The pin IS load-bearing
  — pip refuses if the editable install's declared version is too old.

### Code change

`pyproject.toml` line 7 (pipeline repo):

```toml
- version = "0.1.0"
+ version = "0.2.0"
```

`backend/requirements.txt`, append:

```
spacescans-pipeline>=0.2
```

### Test plan

- **New unit test** `test_requirements_pin_resolves` in
  `backend/tests/test_install_posture.py`: `pip install --dry-run -r
  backend/requirements.txt` in a temp venv; expect rc=0.
- **New unit test** `test_pipeline_version_matches_pin`: parse
  `importlib.metadata.version("spacescans-pipeline")` and assert
  `packaging.version.Version(...) >= Version("0.2")`. Locks the
  lockstep — bumping the pin without bumping the pipeline fires this.

## H2 — TIGER C4 server-boot pre-flight

### Today's state

`backend/app/variable_registry.py:72-101` (`load_variables`):

1. Calls `_assert_pipeline_version_compatible()` (line 73).
2. Reads + jsonschema-validates `variable_metadata.json`.
3. Asserts each `experiment` is in the runner whitelist (lines 92-97).
4. Writes the `_CACHE` entry (line 99).

No on-disk TIGER C4 check. A missing year subdir surfaces deep inside
`tiger_proximity.run` mid-task, after the user has selected variables
and POSTed `/api/tasks/{id}/start`.

Verified TIGER subdir naming on disk: `tiger{year}_roads` (NOT
`tl_{year}_roads`). `coverage_years` per
`variable_metadata.schema.json:30-34` is a 2-element array
(`minItems: 2, maxItems: 2`) with inclusive `[min, max]` range
semantics — confirmed by `configs/c3/tiger_roads_demo.yaml:15`
expanding `[2013, 2019]` into the seven-year list.

### Design decisions

- **Range expansion: `range(lo, hi + 1)`.** The schema's 2-element
  constraint is `[min, max]` inclusive; iterating the array directly
  (per a literal reading of the followups doc) would check only the
  endpoints, leaving 2014-2018 unverified.
- **Exception type: `MetadataSchemaError`** (consistent with the rest
  of `variable_registry`; lines 51, 57, 86, 94 already raise it for
  registry-level violations).
- **Test-env handling: short-circuit when the TIGER root is absent.**
  Unit tests under `backend/tests/` call `load_variables` directly
  without going through `create_app`; the test default
  `SPACESCANS_DATA_DIR=/nonexistent` would fail every registry test.
  Production startup runs `validate_pipeline_settings` first which
  raises if the data dir is missing — so the short-circuit only fires
  in tests, where the absent-data signal is already encoded by the
  absent root. The gate is on the TIGER subtree (not the data root)
  so a partial install still triggers per-year errors.

### Code change

`backend/app/variable_registry.py`, new private helper:

```python
def _assert_tiger_data_present(payload: dict) -> None:
    """Pre-flight: TIGER C4 tile subdirs exist for each coverage_year.

    Raises MetadataSchemaError if a declared tiger_proximity variable's
    coverage_years range names a year with no on-disk
    {DATA_ROOT}/data_full/TIGER/C4/tiger{year}_roads/ subdir.
    """
    from app.config import settings
    root = settings.SPACESCANS_DATA_DIR / "data_full" / "TIGER" / "C4"
    if not root.exists():
        return  # test default or non-TIGER deployment
    for key, m in payload["variables"].items():
        if m.get("experiment") != "tiger_proximity":
            continue
        yr_lo, yr_hi = m["coverage_years"]
        for year in range(yr_lo, yr_hi + 1):
            subdir = root / f"tiger{year}_roads"
            if not subdir.exists():
                raise MetadataSchemaError(
                    f"tiger_proximity variable '{key}' coverage_year "
                    f"{year} missing data: {subdir}"
                )
```

Invoke from `load_variables` between the experiment-whitelist loop
(line 97) and the `_CACHE` write (line 99).

### Test plan

- **New unit test** `test_tiger_preflight_passes_when_all_years_present`:
  `tmp_path` with `tiger2013_roads` through `tiger2019_roads` subdirs;
  monkeypatch `settings.SPACESCANS_DATA_DIR`; expect no raise.
- **New unit test** `test_tiger_preflight_raises_on_missing_year`:
  same fixture but `rmtree(tiger2017_roads)`; expect `MetadataSchemaError`
  with `"2017"` and `tiger2017_roads` in the message.
- **New unit test** `test_tiger_preflight_skips_when_root_missing`:
  `tmp_path` with no `data_full/TIGER/` tree; expect no raise.

## H3 — Cache-hit log source unify across 3 runners

### Today's state

11 cache-related `_append_log` lines still emit `source="runner"`:

| File | Line | Event |
|------|------|-------|
| `tiger_proximity.py` | 303 | cache-hit (already `step.name` from B4-fix; not touched) |
| `tiger_proximity.py` | 322 | cache-check-failed |
| `tiger_proximity.py` | 386 | cache-write |
| `tiger_proximity.py` | 389 | cache-write-failed |
| `bg_ndi_wi.py` | 474 | cache-hit |
| `bg_ndi_wi.py` | 493 | cache-check-failed |
| `bg_ndi_wi.py` | 563 | cache-write |
| `bg_ndi_wi.py` | 566 | cache-write-failed |
| `zcta5_cbp.py` | 295 | cache-hit |
| `zcta5_cbp.py` | 314 | cache-check-failed |
| `zcta5_cbp.py` | 379 | cache-write |
| `zcta5_cbp.py` | 382 | cache-write-failed |

All 12 lines sit inside `if step.is_c3:` guarded blocks
(`bg_ndi_wi.py:467` + `:549`; `zcta5_cbp.py:288` + `:365`;
`tiger_proximity.py:296` + `:373`) — `step.name` is unambiguously in
scope.

The SIGTERM-cancel `_append_log` lines (`bg_ndi_wi.py:339`,
`zcta5_cbp.py:183`, `tiger_proximity.py:187`) are NOT cache events;
they fire inside `_install_cancel_handler` where `step` is not in
scope. They stay as `source="runner"`.

### Design decision

**Convention: `step.name` for ALL FOUR cache events, all three
runners.** B4-fix's reasoning (UI step-filter visibility for the
`c3_bg` / `c3_zcta5` / `c3_tiger_roads` step buckets) applies equally
to cache-write and cache-check-failure events. "Runner" was the
undifferentiated original; B4-fix only addressed the most user-visible
regression (cache-hit attribution observed in T4) and left the rest
for a sweep-fix sprint.

### Code change

Eleven mechanical replacements:

```python
# tiger_proximity.py:322, :386, :389
- _append_log(task_dir, "warning", "runner", f"...")
+ _append_log(task_dir, "warning", step.name, f"...")

# bg_ndi_wi.py:474, :493, :563, :566 — same pattern
# zcta5_cbp.py:295, :314, :379, :382 — same pattern
```

### Test plan

- **New parametrized unit test** `test_cache_log_source_consistency`
  in `backend/tests/test_runner_logging.py`: parametrize over the
  three runners and four events. Use a synthetic step + tmp_path;
  force each path (touch a cache file for hit; chmod 000 the cache
  dir for check-fail; pass an unwritable root for write-fail). Assert
  `log.jsonl` entries have `source == step.name` for every cache-event
  line.

## H4 — Remove redundant monkeypatch

### Today's state

`backend/tests/test_task_manager_dispatch.py:269-276`:

```python
monkeypatch.setattr(
    dispatcher.variable_registry,
    "variables_by_experiment",
    lambda selected: {
        "bg_ndi_wi": ["ndi", "walkability"],
        "zcta5_cbp": ["cbp_zcta5"],
        "tiger_proximity": ["tiger_proximity"],
    },
)
```

The lambda's return value EXACTLY matches what
`variable_registry.variables_by_experiment(["tiger_proximity",
"cbp_zcta5", "ndi", "walkability"])` produces from the real
`variable_metadata.json` — the file has keys in order `ndi`,
`walkability`, `cbp_zcta5`, `tiger_proximity`, and the registry
iterates `payload["variables"].items()` in OrderedDict insertion
order (`load_variables` uses `object_pairs_hook=OrderedDict` at line
79).

The monkeypatch is therefore redundant AND hides regressions in the
real registry path.

### Design decision

**Full removal.** The followups doc lists both removal and
clarifying-comment options. Removal eliminates redundancy and the
regression-hiding risk at zero coverage cost — the companion test
`test_variable_registry.py::test_variables_by_experiment_preserves_file_order`
already covers the registry side independently. The two tests then
form a paired invariant: the registry test locks file-order semantics,
the dispatch test locks registry-to-cmd preservation.

### Code change

`backend/tests/test_task_manager_dispatch.py:269-276` — delete the
seven-line block. Existing assertions at lines 282-289 (cmd ordering +
completed-list contents) stay.

### Test plan

- Run the modified test — must continue to pass on the real metadata
  path.
- No new tests added; this is pure deletion.

## H5 — `config.time` None guard via helper

### Today's state

`src/spacescans/models/config.py:189` declares
`time: TimeConfig | None = None`. Four linkage modules dispatch on
`config.time.output_grouping` without a None guard:

| File | Line | Branch output |
|------|------|---------------|
| `precomputed_areal_linkage.py` | 118 | `(select_keys, group_keys)` tuple |
| `yearly_areal_linkage.py` | 50 | `group_by_keys: list[str]` |
| `static_areal_linkage.py` | 46 | `group_by_episode: bool` |
| `yearly_areal_bg_vintage_linkage.py` | 143 | `group_by_keys: list[str]` |

Each is `if config.time.output_grouping == "patient": ... elif ==
"episode": ... else: raise ValueError(...)`. With `config.time is None`,
AttributeError fires before reaching the explicit ValueError.

Other `config.time` dereferences in the same files DO guard
(`acag_linkage.py:39`, `gridded_linkage.py:26`,
`precomputed_areal_linkage.py:42`, `tiger_proximity_linkage.py:137`,
`proximity_linkage.py:32-33` all use
`config.time.X if config.time else <default>`). The four
`output_grouping` dispatch sites are the last unguarded `config.time`
accesses in the linkage layer.

The followups doc names only the first two files. Sprint 6 fixes all
four — the other two have the same crash surface and would be a fifth
and sixth drift point if left.

### Design decisions

- **Helper-based centralization** in `linkage/helpers.py`, not inline
  guards. The four sites have IDENTICAL predicates (`output_grouping in
  {"patient", "episode"}`) and DIVERGENT outputs (list / tuple / bool).
  Consolidating the predicate eliminates a four-way drift hazard;
  leaving site-specific shapes untouched keeps the helper narrow.
- **Helper returns the validated literal**, not the dispatched
  per-site output. Per-pattern outputs are too structurally different
  to unify (list vs bool vs tuple); unifying them would require a sum
  type per pattern. Each call site owns its mapping in 4 lines.
- **Scope: all four files.** The followups doc undercounts. Partial
  fix leaves the same crash live in two siblings — and the cost of
  two extra mechanical call-site rewrites in the same PR is trivial.

### Code change

`src/spacescans/linkage/helpers.py`, new function:

```python
def resolve_output_grouping(config: DatasetConfig) -> str:
    """Return the validated output_grouping literal.

    Raises ValueError when config.time is None or when output_grouping
    holds an unsupported value. Used by linkage patterns that branch
    per-episode vs per-patient.
    """
    if config.time is None:
        raise ValueError(
            "linkage pattern requires a time block with output_grouping"
        )
    grouping = config.time.output_grouping
    if grouping not in ("patient", "episode"):
        raise ValueError(f"unsupported output_grouping: {grouping!r}")
    return grouping
```

Four call-site rewrites — pattern at `precomputed_areal_linkage.py:118`
(the other three follow identically):

```python
# before
if config.time.output_grouping == "patient":
    select_keys, group_keys = ...
elif config.time.output_grouping == "episode":
    select_keys, group_keys = ...
else:
    raise ValueError(...)

# after
grouping = resolve_output_grouping(config)
if grouping == "patient":
    select_keys, group_keys = ...
else:  # "episode" — helper already rejected other values
    select_keys, group_keys = ...
```

Phase A note: this is a pipeline-repo change. The web absorbs it via
the editable install — no `backend/` touch required. The H1 pin bump
to `>=0.2` is the same wheel that ships this helper, so the changes
are atomic from the web's perspective.

### Test plan

- **New unit test** `tests/test_linkage_helpers.py
  ::test_resolve_output_grouping_raises_on_none_time`: `DatasetConfig`
  with `time=None`; expect `ValueError` with substring `"time block"`.
- **New unit test** `test_resolve_output_grouping_raises_on_invalid`:
  `time=TimeConfig(output_grouping="weekly")`; expect `ValueError`
  with `"weekly"`.
- **New unit test** `test_resolve_output_grouping_returns_literal`:
  parametrize over `"patient"` / `"episode"`; assert helper returns
  the literal unchanged.
- Existing per-pattern integration tests continue to exercise both
  branches; no fixture changes required.

## H6 — `PYTHONPATH` override cleanup

### Today's state

`tests/test_pipeline_smoke.py:159-160`:

```python
worktree_src = str(Path(__file__).resolve().parents[1] / "src")
env = {**os.environ, "PYTHONPATH": worktree_src + os.pathsep + os.environ.get("PYTHONPATH", "")}
```

Added during Sprint 5 as a developer affordance — letting the smoke
test run against the worktree's `src/` even when the editable install
resolved elsewhere.

Verified that on a single-checkout dev box, the editable install's
resolved path matches the worktree's `src/` exactly — the override
is currently a no-op there.

BUT: Sprint 5's `output_grouping` dispatch code is on `pkg/pypi-only`
only; `git show main:src/spacescans/linkage/precomputed_areal_linkage.py`
has zero `output_grouping` references. The override IS load-bearing
for anyone whose editable install was last reinstalled against a
main-branch checkout.

The followups doc gates cleanup: "remove the PYTHONPATH override...
once Sprint 5 has been stable in production for a release cycle (or
move to a test-helper that conditionally sets it only when the test
is run from a worktree differing from the editable install's path)."

### Design decision

**Conditional rewrite, not full deletion or leave-as-is.** Full
deletion is unsafe today — Phase A is not yet merged to main, so any
worktree-based dev (which the Sprint 6 plan reintroduces via
`using-git-worktrees`) would silently run the smoke test against the
wrong tree. Leave-as-is keeps a perma-no-op affordance with no signal
to future maintainers. Conditional rewrite is mechanically small, makes
the conditional explicit, and preserves worktree safety.

**Inline in `test_pipeline_smoke.py`**, not a shared `conftest.py`
fixture. Only one call site today; promote to fixture when a second
test needs the same shape.

### Code change

`tests/test_pipeline_smoke.py:159-160`:

```python
# after
import spacescans as _ss_pkg
worktree_init = Path(__file__).resolve().parents[1] / "src" / "spacescans" / "__init__.py"
installed_init = Path(_ss_pkg.__file__).resolve()
if worktree_init.resolve() != installed_init:
    # worktree differs from editable install — inject worktree onto PYTHONPATH
    worktree_src = str(Path(__file__).resolve().parents[1] / "src")
    env = {**os.environ, "PYTHONPATH": worktree_src + os.pathsep + os.environ.get("PYTHONPATH", "")}
else:
    env = os.environ.copy()
```

The `import spacescans as _ss_pkg` hoists to file-top imports.

### Test plan

- **Smoke test still green** on single-checkout dev box — the else
  branch fires, subprocess inherits a clean env. Existing assertions
  unchanged.
- **Manual worktree verification** (documented in PR, not a pytest):
  on a worktree at `pkg/pypi-only` whose editable install points to
  main, `pytest tests/test_pipeline_smoke.py` must inject the
  worktree's `src/` onto `PYTHONPATH`.
- **New unit test** `test_pythonpath_helper_no_ops_when_paths_match`:
  monkeypatch `spacescans.__file__` to the worktree's expected init;
  re-run the path-comparison block in isolation; assert env equals
  `os.environ`.

## Implementation order

**H6 → H4 → H3 → H1 → H2 → H5.** Mechanical first, cross-repo last:

- **H6** (PYTHONPATH conditional): single file, no cross-repo
  coupling. Cleans the test-env surface first.
- **H4** (monkeypatch removal): single file, pure deletion.
  Incidentally validates H6 — if smoke env broke registry imports,
  H4's test would catch it.
- **H3** (cache log source unify): 11 mechanical line edits across
  three runners. Self-contained in `backend/`.
- **H1** (requirements pin): cross-repo (pipeline `pyproject.toml`
  bump + web `requirements.txt` add). Atomic in one PR. Lands before
  H2 + H5 because both depend on the new wheel being installable.
- **H2** (TIGER pre-flight): single file (`variable_registry.py`),
  three new tests. Builds on H1's pin.
- **H5** (output_grouping helper): cross-repo. Lands last because
  it's the largest diff and benefits from H1's lockstep version bump
  already being merged so the web's editable install picks it up
  cleanly.

Each step is committable in isolation — if a step blocks, the
preceding steps remain mergeable.

## Test impact

| Step | New tests | Test fixups | Total delta |
|------|-----------|-------------|-------------|
| H1   | +2 (install posture + version match) | 0 | +2 |
| H2   | +3 (preflight pass/miss/skip) | 0 | +3 |
| H3   | +1 (parametrized cache log source) | 0 | +1 |
| H4   | 0 | +1 (monkeypatch removed) | +1 |
| H5   | +3 (helper unit tests, pipeline repo) | 0 | +3 |
| H6   | +1 (helper no-op branch) | 0 | +1 |

Net: ~10 new tests, ~1 test fixup. Sprint 5 ended at ~150 tests;
Sprint 6 ends ~160. No tests deleted.

## Risks

- **H1 wheel-publish absence** — `>=0.2` is enforced against the
  editable install's declared version. If a future deployment pivots
  to wheel-only without bumping the pipeline `version` field again,
  the pin tightens automatically — no risk, just deferred enforcement.
- **H2 test-env short-circuit** — the `if not root.exists(): return`
  guard skips preflight in tests. Mitigation: H2's unit suite covers
  all three paths (full present, partial missing, root absent) with
  monkeypatched `SPACESCANS_DATA_DIR`. The short-circuit is opt-in
  for tests, not a silent prod escape.
- **H3 step-name visibility under non-C3 step** — all 12 lines are
  guarded by `if step.is_c3:` so `step.name` is guaranteed to be the
  C3 step. Risk only materializes if a future refactor moves a cache
  call outside the guard; the new `test_cache_log_source_consistency`
  test would catch that.
- **H4 metadata-file order coupling** — removing the monkeypatch
  means the test now depends on `variable_metadata.json` keeping its
  current key order. `test_variables_by_experiment_preserves_file_order`
  already asserts that order, so a metadata reorder fires the right
  test first.
- **H5 helper centralization scope creep** — the helper currently
  returns only the validated literal. Adding more behaviour (per-site
  shapes) would re-introduce the cross-pattern coupling the helper is
  meant to avoid. Mitigation: the helper's docstring + unit tests pin
  the narrow contract.
- **H6 worktree drift** — if `spacescans.__file__` resolves to a
  non-canonical path (symlinks, namespace packages), the
  `Path(...).resolve()` comparison could spuriously trip. Mitigation:
  both sides call `.resolve()`; the fallback (always inject) is the
  safe direction.

## Explicitly out of scope (deferred)

- G1-G7 (Sprint 4 adversarial review backlog) — could roll into a
  Sprint 7 cleanup.
- The 5 remaining experiments (`nhd_bluespace`, `vnl`, `temis`,
  `fara_tract`, `noise`). Sprint 8+.
- Multi-experiment parallel spawn. Sequential remains the contract.
- Per-variable shapefile coverage. Bbox-based CONUS envelope continues.
- Frontend test framework (jest / vitest).
- LRU cap on the C3 cache directory.
- A metadata editor UI.
- The global `geoid` → `episode_id` rename in the upstream pipeline.
- A real PyPI publish flow for `spacescans-pipeline` — Sprint 7+
  Phase B concern.
- Restructuring `merge_results(...)` signatures (Sprint 4 deferred
  the same).
