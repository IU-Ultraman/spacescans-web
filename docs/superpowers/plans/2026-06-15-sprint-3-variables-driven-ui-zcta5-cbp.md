# Sprint 3: Variables-driven UI + ZCTA5×CBP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Variables wizard step to be metadata-driven, and introduce ZCTA5×CBP (community organization density) as the pilot 2nd experiment that proves the registry-driven UI generalizes across boundary types.

**Architecture:** Source-controlled `variable_metadata.json` (+ JSON Schema validator) becomes the single source of truth. A new `variable_registry` module loads + validates it at startup. The Variables wizard step fetches via `/api/variables`. `task_manager.start_task()` groups selected variables by their `experiment` field and spawns one subprocess per experiment sequentially (host-level `.run_lock` constraint). Each experiment runner emits a per-experiment partial CSV; `task_manager` final-merges all partials on `(pid, episode_id)` → `result.csv`. The `zcta5_cbp.py` experiment clones `bg_ndi_wi.py`'s shape and inherits Sprint 2's `output_grouping=episode` dispatch via the `yearly_areal` linkage pattern with 0 pipeline changes.

**Tech Stack:** Python (FastAPI, pandas, DuckDB via spacescans-pipeline), TypeScript/React 18/Next.js (App Router), pytest, pyreadr (.Rda reader), JSON Schema (draft-2020-12), Sprint 2 episode-dimension contract.

**Spec:** `docs/superpowers/specs/2026-06-15-sprint-3-variables-driven-ui-zcta5-cbp-design.md` (1718 lines, committed 3ac4d2c)

**Base branch:** `main` (Sprint 2 already merged at d030798)

**Worktree:** `/Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3`, branch `feat/sprint-3-variables-driven-ui-zcta5-cbp`

**Backend env:** `/Users/xai/miniconda3/envs/spacescans/bin/python`
**Frontend env:** `~/.nvm/versions/node/v20.20.2/bin` (with `node_modules` symlink to main worktree)

**Baseline:** 75 backend tests pass, 6 integration tests pass, tsc clean (post-Sprint 2 main)

---

## Task list

| # | Task | Summary |
|---|---|---|
| T0 | Pre-flight checks | pyreadr import, YAML template, ZCTA5 weight parquet, Sprint 2 baseline — captured as a dated report |
| T1 | Move + schema-wrap `variable_metadata.json` | git mv into package tree; add `schema_version:1` envelope, `cbp_zcta5` entry, JSON Schema file |
| T2 | `variable_registry.py` | mtime-cached load + validate + query helpers (get_variable, variables_by_experiment, list_experiments) |
| T3 | `GET /api/variables` | Pydantic-validated catalog endpoint with 401 / 503 / 500 error mapping |
| T4 | `compute_coverage` rewire | Source per-variable metadata via registry; add `boundary` + `display_unit` response fields |
| T5 | Extract `_merge.py` | Lift `(pid, episode_id)` join + match_pct from `bg_ndi_wi.merge_results` into shared `write_partial` / `fan_in` |
| T6 | `_BOUNDARY` constant | Lift hardcoded `"BG"` cache-key literal into a module-level constant so per-runner caches namespace cleanly |
| T7 | `zcta5_cbp.py` runner | Clone-trim of `bg_ndi_wi.py`; one C3 + one C4 step; `_BOUNDARY="ZCTA5"`; merges via shared `_merge.write_partial` |
| T8 | Atomic `_write_status` | flock-protected read-modify-write with per-experiment-key deep merge + derived flat fields |
| T9 | `dispatcher.py` + multi-experiment `start_task` | Supervisor subprocess sequentially Popens runners; partial-failure → skipped + `fan_in` on completed prefix |
| T10 | Frontend lib: catalog | `api.listVariables`, `VarCoverage` extension, `variable-grouping.ts`, `useVariableCatalog` hook |
| T11 | UI primitives | Chip/Pill, ErrorCard, LoadingCard, SchemaMismatchBanner |
| T12 | VariablesStep rewrite | Catalog-driven, boundary-grouped, lifts inline label into `VariableCard`; coverage-panel boundary string |
| T13 | ReviewStep refactor | Drop `/ontology/metadata.json` fetch; group selected variables by experiment via shared hook |
| T14 | Integration tests | e2e ZCTA5×CBP single-experiment + multi-experiment dispatch; regress Sprint 2 multi-episode |
| T15 | Final verification | Append manual_e2e Sprint 3 walkthrough; run full pytest + tsc + lint; PR-ready cleanup |

---

### Task T0: Pre-flight: pyreadr + YAML template + ZCTA5 weight parquet checks

**Files:**
- Create: `spacescans-web/docs/superpowers/preflight/2026-06-15-sprint-3-preflight.md`
- Modify: (none)
- Test: (none — this is a documentation/verification task; no pytest)

**Goal:** Before any Sprint 3 code lands, prove the four external preconditions (pyreadr import, YAML template file, ZCTA5 weight parquet, Sprint 2 baseline green) hold on this dev host, and pin the evidence in a dated preflight report.

**Context:** Sprint 3 introduces a second experiment runner (`zcta5_cbp`) that reads a `.Rda` exposure file via `spacescans._extras.require('rda', 'pyreadr')` and renders `configs/c4/zcta5_cbp_demo.yaml` from a template, joining onto the cached ZCTA5×25m weight parquet at `output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet`. Risks R1 and R2 in the spec (lines 1598-1599) call out exactly these two artifacts as likely failure modes if a fresh dev or deploy host is missing them. Phase A (lines 1684-1700) and Phase B step 1 (lines 1704-1707) make the preflight a hard gate. This task is the gate: no Sprint 3 PR opens until the report is committed and all four checks are green. The Sprint 3 worktree itself (`spacescans-web/.worktrees/feat-sprint-3`) does not yet exist — Task T1 creates it — so all commands here run from the main `spacescans-web` checkout on branch `pkg/pypi-only` (or whatever the current branch is) and write the report there.

- [ ] **Step 1: Write the failing test(s)**

There is no pytest in this task. The "failing test" is the four shell checks below. Capture each one's stdout verbatim into the report. Run them in order; the first failure aborts the task and we fix the underlying environment before re-running.

```bash
# Check 1: pyreadr importable in the pipeline env
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import pyreadr, spacescans._extras as e; e.require('rda', 'pyreadr'); print('pyreadr', pyreadr.__version__)"

# Check 2: zcta5_cbp_demo.yaml template exists and parses
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import yaml, pathlib; p = pathlib.Path('/Users/xai/Desktop/spacescans-project/configs/c4/zcta5_cbp_demo.yaml'); assert p.exists(), p; d = yaml.safe_load(p.read_text()); print('top-level keys:', sorted(d.keys()))"

# Check 3: ZCTA5×25m weight parquet present, readable, non-empty
/Users/xai/miniconda3/envs/spacescans/bin/python -c \
  "import pandas as pd, pathlib; p = pathlib.Path('/Users/xai/Desktop/spacescans-project/output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet'); assert p.exists(), p; df = pd.read_parquet(p); print('rows', len(df), 'cols', list(df.columns)[:6], 'size_bytes', p.stat().st_size)"

# Check 4: Sprint 2 baseline green (75 passed, 1 skipped, 5 deselected)
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend && \
  /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

- [ ] **Step 2: Run the test to confirm RED**

This step is what makes the preflight worth committing: we *expect* all four to pass on the controller's dev host today (the parquet was last seen May 26 16:40 per spec R2; pyreadr is declared under `[rda]` extras). If any of the four FAILS, the failure mode itself is the RED signal — record it in the report under "Issues found" and remediate before continuing:

| Check | Likely failure | Fix |
|---|---|---|
| 1 (pyreadr) | `ModuleNotFoundError: pyreadr` or `ExtraNotInstalled('rda')` | `cd /Users/xai/Desktop/spacescans-project && /Users/xai/miniconda3/envs/spacescans/bin/pip install -e '.[rda]'` |
| 2 (yaml template) | `FileNotFoundError` | locate template in upstream `spacescans-pipeline`; copy or symlink into `configs/c4/` |
| 3 (parquet) | `FileNotFoundError` | regenerate per `spacescans-pipeline/README.md`: run `configs/c3/zcta5_us_demo.yaml` once to repopulate cache |
| 4 (baseline) | not "75 passed" | stop — Sprint 2 regression; do NOT proceed with Sprint 3 until baseline is restored |

Expected on a clean host: all four green; no RED outcome. If RED appears, fix and re-run before Step 3.

- [ ] **Step 3: Implement the minimal code to pass the test**

The "implementation" is the report file. Create `spacescans-web/docs/superpowers/preflight/2026-06-15-sprint-3-preflight.md` with the exact captured output:

```markdown
# Sprint 3 Pre-flight Report

**Date:** 2026-06-15
**Host:** <hostname from `hostname -s`>
**Operator:** <git user.email>
**Branch:** <current branch name>
**Spec:** `docs/superpowers/specs/2026-06-15-sprint-3-variables-driven-ui-zcta5-cbp-design.md`
**Risks gated:** R1 (pyreadr), R2 (ZCTA5 weight parquet cache)

## Check 1 — pyreadr extras installed (R1)

Command:
    /Users/xai/miniconda3/envs/spacescans/bin/python -c \
      "import pyreadr, spacescans._extras as e; e.require('rda', 'pyreadr'); print('pyreadr', pyreadr.__version__)"

Output:
    pyreadr <version>

Status: PASS

## Check 2 — zcta5_cbp_demo.yaml template present

Path: `/Users/xai/Desktop/spacescans-project/configs/c4/zcta5_cbp_demo.yaml`
Top-level keys (from `yaml.safe_load`): <list captured>

Status: PASS

## Check 3 — ZCTA5×25m weight parquet present (R2)

Path: `/Users/xai/Desktop/spacescans-project/output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet`
Rows: <captured>
First 6 columns: <captured>
Size (bytes): <captured>
Last modified: <`stat -f '%Sm' <path>` output>

Status: PASS

## Check 4 — Sprint 2 backend baseline green

Command:
    cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend && \
      /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q

Result: 75 passed, 1 skipped, 5 deselected (Sprint 2 close-out baseline)

Status: PASS

## Decision

All four preconditions hold. Sprint 3 implementation may proceed at Task T1
(worktree creation).

## Issues found

(none)
```

Fill `<...>` placeholders with the literal stdout from Step 1. The report MUST contain real captured values — do not commit a template with `<version>` left in.

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
# Confirm the report file exists, is non-trivial, and contains all four PASS markers
test -f /Users/xai/Desktop/spacescans-project/spacescans-web/docs/superpowers/preflight/2026-06-15-sprint-3-preflight.md && \
  echo "exists" && \
  grep -c "^Status: PASS" /Users/xai/Desktop/spacescans-project/spacescans-web/docs/superpowers/preflight/2026-06-15-sprint-3-preflight.md
```

Expected: `exists` followed by `4`.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 75 passed, 1 skipped, 5 deselected. This task adds zero tests; the Sprint 3 backend baseline going into Task T1 is **75 passed**.

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web
git add docs/superpowers/preflight/2026-06-15-sprint-3-preflight.md
git commit -m "docs(sprint-3): pre-flight report — pyreadr, yaml template, ZCTA5 parquet, baseline green"
```

**Notes:**
- This task is intentionally a docs-only commit; no code or tests change, so the backend test count is unchanged (75). Subsequent Sprint 3 tasks use 75 as their starting baseline.
- The report lives under `docs/superpowers/preflight/` (new directory — `mkdir -p` is implicit via `git add` of a file inside it). Future sprints can reuse the same directory.
- If Check 1 fails because `spacescans._extras.require` itself is missing (older pipeline checkout), that is R8 territory (editable-install drift), not R1 — record it as a separate issue and escalate before installing pyreadr blindly.
- The template path in Check 2 is the upstream `spacescans-pipeline` checkout's `configs/c4/`, not anything under `spacescans-web/`. Sprint 3 reads it via `subprocess` + the pipeline CLI; we do not copy or vendor it into `spacescans-web/`.
- Do NOT proceed to Task T1 if any check is still RED after one remediation attempt — escalate instead.

---

### Task T1: Move variable_metadata.json + add schema_version + add JSON Schema file

**Files:**
- Create: `spacescans-web/backend/app/data/variable_metadata.json` (moved via `git mv` from `backend/data/variable_metadata.json`, then edited)
- Create: `spacescans-web/backend/app/data/variable_metadata.schema.json`
- Create: `spacescans-web/backend/tests/test_variable_metadata_file.py`
- Modify: `spacescans-web/backend/.gitignore` (remove line 6: `app/data/variable_metadata.json`)

**Goal:** Move `variable_metadata.json` into the package tree, wrap it in a versioned envelope (`schema_version: 1` + `variables: {...}`), add a `cbp_zcta5` entry with 10 `r_*` value columns, ship a JSON Schema draft-2020-12 file, and prove via pytest that the data file validates against the schema.

**Context:** Sprint 1 placed `variable_metadata.json` at `backend/data/variable_metadata.json` and listed it in `backend/.gitignore` line 6 (a leftover from when the file was treated as a per-deployment override). Sprint 3 promotes it to a source-controlled, schema-validated registry living inside the Python package at `backend/app/data/`. Existing entries (`ndi`, `walkability`) currently sit at the JSON document's top level — they must be nested under a new `variables` key alongside `schema_version: 1`. The third entry, `cbp_zcta5`, is the ZCTA5×CBP variable Sprint 3 introduces (10 per-capita organization-density columns from Census ZIP Business Patterns). The schema file pins keys to `^[a-z][a-z0-9_]*$`, restricts `boundary` to `{BG, ZCTA5, Tract, County}`, and locks `schema_version` to `const 1`. The registry loader (Task T2) will consume both files; this task only stages the data and the schema, plus a one-shot validation test that does not depend on the loader.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_variable_metadata_file.py`:

```python
"""Sprint 3 T1: variable_metadata.json + schema co-locate and validate.

This test is intentionally loader-free — it only checks the on-disk artefacts
so a schema bug shows up before the registry loader (T2) is wired in.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

BACKEND = Path(__file__).resolve().parent.parent
DATA_PATH = BACKEND / "app" / "data" / "variable_metadata.json"
SCHEMA_PATH = BACKEND / "app" / "data" / "variable_metadata.schema.json"


@pytest.fixture(scope="module")
def metadata() -> dict:
    return json.loads(DATA_PATH.read_text())


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_metadata_file_exists_at_new_path():
    assert DATA_PATH.is_file(), f"expected {DATA_PATH} to exist after git mv"


def test_schema_file_exists():
    assert SCHEMA_PATH.is_file(), f"expected {SCHEMA_PATH} to exist"


def test_old_metadata_path_is_gone():
    old = BACKEND / "data" / "variable_metadata.json"
    assert not old.exists(), (
        f"{old} should have been removed by git mv; stale copy would "
        "shadow the package-tree file"
    )


def test_schema_version_is_one(metadata):
    assert metadata["schema_version"] == 1


def test_variables_envelope_present(metadata):
    assert "variables" in metadata
    assert isinstance(metadata["variables"], dict)
    assert set(metadata["variables"].keys()) >= {"ndi", "walkability", "cbp_zcta5"}


def test_cbp_zcta5_entry_shape(metadata):
    entry = metadata["variables"]["cbp_zcta5"]
    assert entry["boundary"] == "ZCTA5"
    assert entry["experiment"] == "zcta5_cbp"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["coverage_region"] == "CONUS"
    assert entry["variable_type"] == "continuous"
    assert entry["value_cols"] == [
        "r_religious", "r_civic", "r_business", "r_political",
        "r_professional", "r_labor", "r_bowling", "r_recreational",
        "r_golf", "r_sports",
    ]


def test_metadata_validates_against_schema(metadata, schema):
    # Draft 2020-12 — jsonschema picks the validator from $schema
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator_cls(schema).validate(metadata)


def test_schema_rejects_unknown_top_level_key(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {"schema_version": 1, "variables": {"ndi": {}}, "unexpected": True}
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)


def test_schema_rejects_wrong_schema_version(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {"schema_version": 2, "variables": {}}
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)


def test_schema_rejects_bad_variable_key(schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    bad = {
        "schema_version": 1,
        "variables": {
            "BadKey": {
                "label": "x", "description": "x", "boundary": "BG",
                "coverage_years": [2000, 2001], "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi", "variable_type": "continuous",
                "display_unit": "u", "value_cols": ["c"],
            }
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        validator_cls(schema).validate(bad)
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_metadata_file.py -v
```

Expected: `test_metadata_file_exists_at_new_path` and `test_schema_file_exists` FAIL with `AssertionError` (the new paths don't exist yet); the rest error out at fixture collection because `DATA_PATH.read_text()` raises `FileNotFoundError`.

- [ ] **Step 3: Implement the minimal code to pass the test**

3a. Move the existing file into the package tree (preserves history):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
mkdir -p app/data
git mv data/variable_metadata.json app/data/variable_metadata.json
# If backend/data/ is now empty:
rmdir data 2>/dev/null || true
```

3b. Rewrite `backend/app/data/variable_metadata.json` to the v1 envelope. Replace the file's full contents with:

```json
{
  "schema_version": 1,
  "variables": {
    "ndi": {
      "label": "Neighborhood Deprivation Index (NDI)",
      "description": "Composite measure of neighborhood-level socioeconomic deprivation from US Census ACS variables.",
      "boundary": "BG",
      "coverage_years": [2012, 2022],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "z-score",
      "value_cols": ["ndi"]
    },
    "walkability": {
      "label": "EPA Walkability Index",
      "description": "EPA National Walkability Index ranking neighborhoods on walkability characteristics (intersection density, transit proximity, employment mix).",
      "boundary": "BG",
      "coverage_years": [2016, 2021],
      "coverage_region": "CONUS",
      "experiment": "bg_ndi_wi",
      "variable_type": "continuous",
      "display_unit": "1-20 index",
      "value_cols": ["NatWalkInd"]
    },
    "cbp_zcta5": {
      "label": "Community Organization Density (ZBP)",
      "description": "Per-capita density of 10 community organization categories (religious, civic, business, political, professional, labor, bowling, recreational, golf, sports) at the ZIP Code Tabulation Area level from Census Zip Business Patterns.",
      "boundary": "ZCTA5",
      "coverage_years": [2013, 2019],
      "coverage_region": "CONUS",
      "experiment": "zcta5_cbp",
      "variable_type": "continuous",
      "display_unit": "establishments / 1k residents",
      "value_cols": [
        "r_religious", "r_civic", "r_business", "r_political",
        "r_professional", "r_labor", "r_bowling", "r_recreational",
        "r_golf", "r_sports"
      ]
    }
  }
}
```

3c. Create `backend/app/data/variable_metadata.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "spacescans.org/variable_metadata.schema.json",
  "title": "spacescans-web variable metadata",
  "type": "object",
  "required": ["schema_version", "variables"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"type": "integer", "const": 1},
    "variables": {
      "type": "object",
      "minProperties": 1,
      "patternProperties": {
        "^[a-z][a-z0-9_]*$": {
          "type": "object",
          "required": [
            "label", "description", "boundary",
            "coverage_years", "coverage_region",
            "experiment", "variable_type",
            "display_unit", "value_cols"
          ],
          "additionalProperties": false,
          "properties": {
            "label": {"type": "string", "minLength": 1, "maxLength": 80},
            "description": {"type": "string", "minLength": 1, "maxLength": 400},
            "boundary": {
              "type": "string",
              "enum": ["BG", "ZCTA5", "Tract", "County"]
            },
            "coverage_years": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1900, "maximum": 2100},
              "minItems": 2, "maxItems": 2
            },
            "coverage_region": {
              "type": "string",
              "enum": ["CONUS", "US", "AK_HI"]
            },
            "experiment": {
              "type": "string",
              "pattern": "^[a-z][a-z0-9_]*$"
            },
            "variable_type": {
              "type": "string",
              "enum": ["categorical", "continuous"]
            },
            "display_unit": {
              "type": "string",
              "pattern": "^[\\x20-\\x7E]+$",
              "maxLength": 50
            },
            "value_cols": {
              "type": "array",
              "items": {"type": "string", "minLength": 1},
              "minItems": 1
            }
          }
        }
      },
      "additionalProperties": false
    }
  }
}
```

3d. Remove the now-obsolete `.gitignore` entry. Open `backend/.gitignore` and delete line 6, which reads:

```
app/data/variable_metadata.json
```

(If line 6 is instead `data/variable_metadata.json`, delete that — the goal is no path-based ignore covers the registry JSON.)

3e. Confirm `jsonschema` is importable in the env (it is a transitive dep of `fastapi`/`openapi-schema-validator`, but pin it if missing):

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -c "import jsonschema; print(jsonschema.__version__)"
```

If the import fails, add `jsonschema>=4.21` to `backend/requirements.txt` and `pip install -r backend/requirements.txt` before re-running tests.

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_variable_metadata_file.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 84 passed (Sprint 2 baseline 75 + 9 new from this task), plus whatever skips/deselects the suite already reports.

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
git add backend/app/data/variable_metadata.json \
        backend/app/data/variable_metadata.schema.json \
        backend/.gitignore \
        backend/tests/test_variable_metadata_file.py
# git mv already staged the deletion of backend/data/variable_metadata.json
git status --short
git commit -m "feat(metadata): move variable_metadata into package, add schema_version + JSON Schema + cbp_zcta5 (Sprint 3 T1)"
```

**Notes:**
- The `git mv` in Step 3a is the migration mechanism called out in spec lines 1561–1567; do not delete-and-recreate or history is lost.
- The schema is intentionally strict (`additionalProperties: false`, `const: 1`). Task T2's loader will reuse the same schema file via `jsonschema.validators.validator_for`, so any tightening here propagates automatically.
- If `backend/.gitignore` line 6 has already drifted (e.g. blank line, different pattern), grep for `variable_metadata.json` in the file and remove every matching line — the invariant is "no gitignore rule hides the new path." Confirm with `git check-ignore -v backend/app/data/variable_metadata.json` (must print nothing).
- Do not wire the registry loader yet; T2 owns that. This task's contract ends at "files exist on disk and validate."
- `package_data` / `MANIFEST.in` updates (so the JSON ships with the wheel) are out of scope for T1 and tracked under the packaging task later in Sprint 3 — flag if installed-wheel tests start failing in T2.

---

### Task T2: variable_registry.py: load/validate/cache + query helpers

**Files:**
- Create: `spacescans-web/backend/app/variable_registry.py`
- Modify: (none)
- Test: `spacescans-web/backend/tests/test_variable_registry.py`

**Goal:** Land the registry module — mtime-cached load with `jsonschema.validate`, `schema_version` gating, experiment whitelist via `_discover_experiments`, and the query helpers (`get_variable`, `variables_by_experiment`, `list_experiments`) — so downstream tasks (`/api/variables`, dispatch loop, coverage refactor) have a single source of truth.

**Context:** Sprint 3 Task T1 just landed `backend/app/data/variable_metadata.json` (3 entries: `ndi`, `walkability`, `cbp_zcta5`) and `backend/app/data/variable_metadata.schema.json` (JSON Schema draft-2020-12, `schema_version: const 1`). Today's loader is a private mtime-keyed cache inside `task_manager.py` (Sprint 1's `_VARIABLE_METADATA_CACHE`); Sprint 3 lifts it into its own module so the FastAPI route, the dispatch loop, and the coverage endpoint can all share it. The experiment whitelist is enforced at load time so unknown experiment values fail-fast at server startup instead of at runner-spawn time. File-order of `variables` in the JSON is a contract — `variables_by_experiment` must preserve it (used downstream to order subprocess dispatch). The spec's reference implementation is `specs/2026-06-15-sprint-3-variables-driven-ui-zcta5-cbp-design.md:518-616`; copy it verbatim modulo formatting.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_variable_registry.py`:

```python
"""Sprint 3 T2: variable_registry — load, validate, cache, query helpers."""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_registry_cache():
    """Force fresh load each test so mtime / payload state does not leak."""
    from app import variable_registry as vr
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None
    yield
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None


def test_load_variables_passes_schema_validation():
    from app import variable_registry as vr
    payload = vr.load_variables()
    assert payload["schema_version"] == 1
    assert set(payload["variables"].keys()) >= {"ndi", "walkability", "cbp_zcta5"}


def test_get_variable_returns_metadata_dict():
    from app import variable_registry as vr
    m = vr.get_variable("ndi")
    assert m["experiment"] == "bg_ndi_wi"
    assert m["boundary"] == "BG"
    assert m["value_cols"] == ["ndi"]


def test_get_variable_unknown_key_raises_keyerror():
    from app import variable_registry as vr
    with pytest.raises(KeyError):
        vr.get_variable("does_not_exist")


def test_missing_required_field_rejected(tmp_path, monkeypatch):
    """A variable lacking a required field must fail jsonschema validation."""
    from app import variable_registry as vr

    bad = {
        "schema_version": 1,
        "variables": {
            "ndi": {
                # missing "label"
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }
    bad_path = tmp_path / "variable_metadata.json"
    bad_path.write_text(json.dumps(bad))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_path)

    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        vr.load_variables(force=True)


def test_unknown_experiment_rejected(tmp_path, monkeypatch):
    """Variable referencing an experiment with no module in app/experiments/ must fail."""
    from app import variable_registry as vr

    bad = {
        "schema_version": 1,
        "variables": {
            "ndi": {
                "label": "NDI",
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "ghost_runner",  # no such module
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }
    bad_path = tmp_path / "variable_metadata.json"
    bad_path.write_text(json.dumps(bad))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_path)

    with pytest.raises(vr.MetadataSchemaError, match="unknown experiment"):
        vr.load_variables(force=True)


def test_schema_version_mismatch_rejected(tmp_path, monkeypatch):
    """schema_version not in supported set raises MetadataSchemaError."""
    from app import variable_registry as vr

    bad_payload = tmp_path / "variable_metadata.json"
    bad_schema = tmp_path / "variable_metadata.schema.json"
    bad_payload.write_text(json.dumps({
        "schema_version": 2,
        "variables": {
            "ndi": {
                "label": "NDI",
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }))
    # Permissive schema so jsonschema.validate passes and the version gate fires.
    bad_schema.write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["schema_version", "variables"],
    }))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_payload)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", bad_schema)

    with pytest.raises(vr.MetadataSchemaError, match="unsupported schema_version"):
        vr.load_variables(force=True)


def test_mtime_cache_reloads_on_file_change(tmp_path, monkeypatch):
    """Touching the metadata file (new mtime) must trigger a reload."""
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"

    def write(label_for_ndi: str) -> None:
        payload_path.write_text(json.dumps({
            "schema_version": 1,
            "variables": {
                "ndi": {
                    "label": label_for_ndi,
                    "description": "x",
                    "boundary": "BG",
                    "coverage_years": [2012, 2022],
                    "coverage_region": "CONUS",
                    "experiment": "bg_ndi_wi",
                    "variable_type": "continuous",
                    "display_unit": "z-score",
                    "value_cols": ["ndi"],
                }
            },
        }))

    write("first")
    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)

    first = vr.load_variables(force=True)
    assert first["variables"]["ndi"]["label"] == "first"

    # Ensure new mtime is distinct (filesystem mtime resolution >= 1s on some FSes).
    time.sleep(1.1)
    write("second")
    second = vr.load_variables()  # no force — relies on mtime cache invalidation
    assert second["variables"]["ndi"]["label"] == "second"


def test_variables_by_experiment_preserves_file_order(tmp_path, monkeypatch):
    """Reordering the JSON file inverts the OrderedDict iteration order."""
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"

    def variable(label: str, experiment: str, boundary: str) -> dict:
        return {
            "label": label, "description": "x",
            "boundary": boundary, "coverage_years": [2012, 2022],
            "coverage_region": "CONUS", "experiment": experiment,
            "variable_type": "continuous", "display_unit": "u",
            "value_cols": ["c"],
        }

    p = tmp_path / "variable_metadata.json"
    monkeypatch.setattr(vr, "_METADATA_PATH", p)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)

    # bg_ndi_wi first in file → first in dispatch
    p.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "ndi": variable("NDI", "bg_ndi_wi", "BG"),
            "cbp_zcta5": variable("CBP", "zcta5_cbp", "ZCTA5"),
        },
    }))
    grouped = vr.variables_by_experiment(["ndi", "cbp_zcta5"])
    assert isinstance(grouped, OrderedDict)
    assert list(grouped.keys()) == ["bg_ndi_wi", "zcta5_cbp"]

    # Invert order — must invert dispatch
    time.sleep(1.1)
    p.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "cbp_zcta5": variable("CBP", "zcta5_cbp", "ZCTA5"),
            "ndi": variable("NDI", "bg_ndi_wi", "BG"),
        },
    }))
    grouped = vr.variables_by_experiment(["ndi", "cbp_zcta5"])
    assert list(grouped.keys()) == ["zcta5_cbp", "bg_ndi_wi"]


def test_list_experiments_dedupes_in_file_order():
    from app import variable_registry as vr
    exps = vr.list_experiments()
    # ndi + walkability both map to bg_ndi_wi; cbp_zcta5 → zcta5_cbp.
    # bg_ndi_wi appears first because ndi is the first key in the JSON file.
    assert exps == ["bg_ndi_wi", "zcta5_cbp"]
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.variable_registry'` on every test (the module does not exist yet).

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `spacescans-web/backend/app/variable_registry.py`:

```python
"""Single source of truth for variable definitions.

Loads backend/app/data/variable_metadata.json, validates against
variable_metadata.schema.json on every reload, and exposes typed
query helpers used by the API layer, the dispatch loop, and the
coverage endpoint.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import jsonschema

_DATA_DIR = Path(__file__).parent / "data"
_METADATA_PATH = _DATA_DIR / "variable_metadata.json"
_SCHEMA_PATH = _DATA_DIR / "variable_metadata.schema.json"
_SUPPORTED_SCHEMA_VERSIONS = {1}

_CACHE: dict[str, Any] = {"mtime": None, "payload": None}


class MetadataSchemaError(RuntimeError):
    """Raised when variable_metadata.json fails registry-level validation
    (schema_version gate or experiment whitelist). jsonschema.ValidationError
    propagates as-is for raw schema violations."""


def _discover_experiments() -> set[str]:
    exp_dir = Path(__file__).parent / "experiments"
    return {
        p.stem for p in exp_dir.glob("*.py")
        if p.stem not in {"__init__", "_merge"}
    }


def load_variables(*, force: bool = False) -> dict[str, Any]:
    mtime = _METADATA_PATH.stat().st_mtime
    if not force and _CACHE["mtime"] == mtime and _CACHE["payload"]:
        return _CACHE["payload"]

    with _METADATA_PATH.open() as f:
        payload = json.load(f, object_pairs_hook=OrderedDict)
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    jsonschema.validate(payload, schema)

    if payload["schema_version"] not in _SUPPORTED_SCHEMA_VERSIONS:
        raise MetadataSchemaError(
            f"unsupported schema_version: {payload['schema_version']} "
            f"(supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)})"
        )

    known_experiments = _discover_experiments()
    for key, m in payload["variables"].items():
        if m["experiment"] not in known_experiments:
            raise MetadataSchemaError(
                f"variable {key!r} references unknown experiment "
                f"{m['experiment']!r} (known: {sorted(known_experiments)})"
            )

    _CACHE["mtime"] = mtime
    _CACHE["payload"] = payload
    return payload


def get_variable(key: str) -> dict[str, Any]:
    payload = load_variables()
    try:
        return payload["variables"][key]
    except KeyError:
        raise KeyError(key)


def variables_by_experiment(keys: list[str]) -> "OrderedDict[str, list[str]]":
    """Group variable keys by their experiment, preserving metadata file order."""
    payload = load_variables()
    out: OrderedDict[str, list[str]] = OrderedDict()
    for var_key, m in payload["variables"].items():
        if var_key not in keys:
            continue
        out.setdefault(m["experiment"], []).append(var_key)
    return out


def list_experiments() -> list[str]:
    payload = load_variables()
    seen: list[str] = []
    for m in payload["variables"].values():
        if m["experiment"] not in seen:
            seen.append(m["experiment"])
    return seen
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 93 passed (75 Sprint-2 baseline + 9 from T1 + 9 from T2).

- [ ] **Step 6: Commit**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
git add backend/app/variable_registry.py backend/tests/test_variable_registry.py
git commit -m "feat(registry): variable_registry with mtime cache, schema gate, experiment whitelist"
```

**Notes:**
- `_CACHE` is module-global; the autouse fixture resets it between tests so monkeypatched `_METADATA_PATH`/`_SCHEMA_PATH` from one test do not bleed into the next.
- `_discover_experiments()` is called inside `load_variables()` (not at import) so the whitelist refreshes when new experiment modules land — important because T7 (`zcta5_cbp.py`) adds one mid-sprint.
- The mtime test uses `time.sleep(1.1)` to dodge 1-second mtime resolution on some FS (macOS HFS+, older ext4). Slow but reliable; do not shorten.
- `OrderedDict` is load-bearing: Python 3.7+ dict preserves insertion order, but the spec calls out `OrderedDict` explicitly and the dispatch-order test (T13/integration) depends on this — keep the type as written.

---

### Task T3: GET /api/variables endpoint + router wiring + Pydantic models

**Files:**
- Create: `spacescans-web/backend/app/routers/variables.py`
- Modify: `spacescans-web/backend/app/main.py` (add `app.include_router(variables.router)` next to the existing `app.include_router(tasks.router)` call)
- Test: `spacescans-web/backend/tests/test_api_variables.py`

**Goal:** Expose the variable catalog as `GET /api/variables` returning a Pydantic-validated `VariableCatalogResponse` with proper auth (401), missing-file (503), and schema-invalid (500) error semantics.

**Context:** Sprint 3 spec B8 (lines 104-105) introduces a new endpoint that surfaces the variable registry built in T1 (`backend/app/variable_registry.py`, exposing `load_variables()` and `MetadataSchemaError`). T2 already extracted `require_user` so it can be imported as a dependency by sibling routers. This task wires those two pieces into a real FastAPI router mounted at `/api/variables`, keeping the existing `/api/tasks` router untouched. The endpoint code block in the spec (lines 946-998) is the source of truth for shape; contract notes (lines 999-1018) define the error mapping. The frontend (B10) will consume this as `api.listVariables()` in a later task.

- [ ] **Step 1: Write the failing test(s)**

Create `backend/tests/test_api_variables.py`:

```python
"""Sprint 3 T3: GET /api/variables endpoint contract.

Covers four cases from spec contract notes (lines 999-1018):
- unauthenticated → 401
- happy path → 200 with schema_version + 3-entry catalog
- registry FileNotFoundError → 503 metadata_unavailable
- registry MetadataSchemaError → 500 metadata_schema_invalid
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import variable_registry


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


def _fake_catalog():
    return {
        "schema_version": 1,
        "variables": {
            "ndi": {
                "label": "Neighborhood Deprivation Index",
                "description": "Census-tract NDI (Messer 2006).",
                "boundary": "BG",
                "coverage_years": (2010, 2022),
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            },
            "NatWalkInd": {
                "label": "National Walkability Index",
                "description": "EPA SLD walkability score.",
                "boundary": "BG",
                "coverage_years": (2021, 2021),
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "index",
                "value_cols": ["NatWalkInd"],
            },
            "cbp_zcta5": {
                "label": "County Business Patterns (ZCTA5)",
                "description": "10 sector ratios from CBP at ZCTA5.",
                "boundary": "ZCTA5",
                "coverage_years": (2017, 2022),
                "coverage_region": "CONUS",
                "experiment": "zcta5_cbp",
                "variable_type": "continuous",
                "display_unit": "ratio",
                "value_cols": [f"r_{i}" for i in range(10)],
            },
        },
    }


def test_unauthenticated_returns_401(client):
    r = client.get("/api/variables")
    assert r.status_code == 401


def test_authenticated_returns_catalog(client, auth_headers):
    with patch.object(variable_registry, "load_variables", return_value=_fake_catalog()):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == 1
    assert set(body["variables"].keys()) == {"ndi", "NatWalkInd", "cbp_zcta5"}
    assert body["variables"]["cbp_zcta5"]["boundary"] == "ZCTA5"
    assert body["variables"]["cbp_zcta5"]["value_cols"] == [f"r_{i}" for i in range(10)]


def test_metadata_file_missing_returns_503(client, auth_headers):
    with patch.object(
        variable_registry, "load_variables",
        side_effect=FileNotFoundError("variable_metadata.json not found"),
    ):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "metadata_unavailable"
    assert "variable_metadata.json" in r.json()["detail"]["message"]


def test_metadata_schema_invalid_returns_500(client, auth_headers):
    with patch.object(
        variable_registry, "load_variables",
        side_effect=variable_registry.MetadataSchemaError("unknown experiment 'bogus'"),
    ):
        r = client.get("/api/variables", headers=auth_headers)
    assert r.status_code == 500
    assert r.json()["detail"]["error"] == "metadata_schema_invalid"
    assert "bogus" in r.json()["detail"]["message"]
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_api_variables.py -v
```

Expected: 4 FAIL — `404 Not Found` on every test because the `/api/variables` route does not exist yet.

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `backend/app/routers/variables.py`:

```python
"""GET /api/variables — variable catalog endpoint (Sprint 3 B8)."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import variable_registry
from app.routers.tasks import require_user

router = APIRouter(prefix="/api/variables", tags=["variables"])


class VariableMetadataModel(BaseModel):
    label: str
    description: str
    boundary: Literal["BG", "ZCTA5", "Tract", "County"]
    coverage_years: tuple[int, int]
    coverage_region: Literal["CONUS", "US", "AK_HI"]
    experiment: str
    variable_type: Literal["categorical", "continuous"]
    display_unit: str
    value_cols: list[str]


class VariableCatalogResponse(BaseModel):
    schema_version: int
    variables: dict[str, VariableMetadataModel]


@router.get(
    "",
    response_model=VariableCatalogResponse,
    include_in_schema=True,
)
def list_variables(_user=Depends(require_user)) -> VariableCatalogResponse:
    try:
        payload = variable_registry.load_variables()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail={"error": "metadata_unavailable", "message": str(e)},
        )
    except variable_registry.MetadataSchemaError as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "metadata_schema_invalid", "message": str(e)},
        )
    return payload
```

In `backend/app/main.py` find the existing `app.include_router(tasks.router)` line and add:

```python
from app.routers import tasks, variables  # was: from app.routers import tasks

app.include_router(tasks.router)
app.include_router(variables.router)
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_api_variables.py -v
```

Expected: 4 PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 97 passed (Sprint 2 baseline 75 + T1's 9 + T2's 9 + T3's 4).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/variables.py backend/app/main.py backend/tests/test_api_variables.py
git commit -m "feat(api): GET /api/variables endpoint with Pydantic catalog model (Sprint 3 B8)"
```

**Notes:**
- The `_user=Depends(require_user)` parameter is intentionally underscored — the dep exists purely to trigger the 401 branch when auth is absent.
- `response_model=VariableCatalogResponse` does Pydantic coercion of the registry's plain-dict payload, so `load_variables()` returning a `dict` (not a model instance) is fine.
- `coverage_years` is typed as `tuple[int, int]`; Pydantic v2 coerces `[2010, 2022]` → `(2010, 2022)` and serializes back to a JSON array, so wire format remains `[y0, y1]`.
- Do NOT add an `__init__.py` change inside `backend/app/routers/` — both `tasks.py` and `variables.py` are imported by name from `app.main`.
- Depends on T2 (`require_user` must already be importable from `app.routers.tasks`).

---

### Task T4: compute_coverage: registry-driven + boundary/display_unit response fields

**Files:**
- Create: `spacescans-web/backend/tests/test_coverage_metadata.py`
- Modify: `spacescans-web/backend/app/task_manager.py:39-145` (`compute_coverage`)
- Test: `spacescans-web/backend/tests/test_coverage_metadata.py`

**Goal:** Rewire `compute_coverage` to read variable metadata via `variable_registry.get_variable(key)` and add `boundary` + `display_unit` to each per-variable response dict, without changing CONUS filtering or the unknown-key error shape.

**Context:** `backend/app/task_manager.py` today owns its own metadata cache (`_load_variable_metadata` + `_VARIABLE_METADATA_CACHE`, lines 17-36) and `compute_coverage` (lines 39-145) reads from it via `metadata[var]` to pull `coverage_years` / `coverage_region`. Sprint 3 Task T2 introduced `backend/app/variable_registry.py`, and the canonical store moved to `backend/app/data/variable_metadata.json` (wrapped as `{schema_version: 1, variables: {...}}`). T4 retires the inline cache path inside `compute_coverage` only: every per-variable lookup goes through `variable_registry.get_variable(var)`, raising `KeyError(var)` on unknown keys (preserving today's error shape). The CONUS bbox (`-125..-66`, `24..50`) and warning-emission logic stay byte-for-byte identical. The per-variable response dict gains two fields read straight from registry metadata: `boundary` and `display_unit`.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_coverage_metadata.py`:

```python
"""Sprint 3 T4: compute_coverage gains boundary + display_unit, is registry-driven."""
import importlib
import json
from pathlib import Path

import pytest


_REGISTRY_FIXTURE = {
    "schema_version": 1,
    "variables": {
        "ndi": {
            "label": "Neighborhood Deprivation Index",
            "description": "NDI composite.",
            "boundary": "BG",
            "coverage_years": [2012, 2022],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
            "variable_type": "continuous",
            "display_unit": "z-score",
            "value_cols": ["ndi"],
        },
        "cbp_zcta5": {
            "label": "Community Organization Density (ZBP)",
            "description": "CBP per-capita densities at ZCTA5.",
            "boundary": "ZCTA5",
            "coverage_years": [2013, 2019],
            "coverage_region": "CONUS",
            "experiment": "zcta5_cbp",
            "variable_type": "continuous",
            "display_unit": "establishments / 1k residents",
            "value_cols": [
                "r_religious", "r_civic", "r_business", "r_political",
                "r_professional", "r_labor", "r_bowling", "r_recreational",
                "r_golf", "r_sports",
            ],
        },
    },
}


def _seed(monkeypatch, tmp_path, csv_body: str) -> str:
    """Boot a task dir with input.csv + registry JSON pointing app.config at tmp_path."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))

    import app.config
    importlib.reload(app.config)
    import app.variable_registry as vr
    importlib.reload(vr)

    reg_path = tmp_path / "variable_metadata.json"
    reg_path.write_text(json.dumps(_REGISTRY_FIXTURE))
    monkeypatch.setattr(vr, "_METADATA_PATH", reg_path)
    monkeypatch.setattr(vr, "_CACHE", {"mtime": None, "payload": None})
    monkeypatch.setattr(vr, "_SCHEMA_PATH", reg_path)
    monkeypatch.setattr("jsonschema.validate", lambda payload, schema: None)
    monkeypatch.setattr(vr, "_discover_experiments",
                        lambda: {"bg_ndi_wi", "zcta5_cbp"})

    import app.task_manager
    importlib.reload(app.task_manager)

    task_dir = app.config.settings.TASKS_DIR / "task-cov-meta-01"
    task_dir.mkdir(parents=True)
    (task_dir / "input.csv").write_text(csv_body)
    return "cov-meta-01"


def test_compute_coverage_response_includes_boundary_and_display_unit(monkeypatch, tmp_path):
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    v = out["variables"]["ndi"]
    assert v["boundary"] == "BG"
    assert v["display_unit"] == "z-score"
    assert v["coverage_years"] == [2012, 2022]
    assert v["coverage_pct"] == 100.0


def test_compute_coverage_cbp_zcta5_returns_boundary_zcta5(monkeypatch, tmp_path):
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2015-06-01,2015-12-31,-93.0,45.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["cbp_zcta5"])
    v = out["variables"]["cbp_zcta5"]
    assert v["boundary"] == "ZCTA5"
    assert v["display_unit"] == "establishments / 1k residents"


def test_compute_coverage_conus_filter_unchanged(monkeypatch, tmp_path):
    """CONUS bbox (-125..-66, 24..50) still rejects an Alaska coordinate."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P_AK,2017-01-01,2017-12-31,-149.9,61.2\n"
        "P_TX,2017-01-01,2017-12-31,-95.0,30.0\n"
    )
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["variables"]["ndi"]["patients_in_region"] == 1
    assert out["variables"]["ndi"]["coverage_pct"] == 50.0


def test_compute_coverage_unknown_variable_still_raises_keyerror(monkeypatch, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93,45\n"
    task_id = _seed(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    with pytest.raises(KeyError) as excinfo:
        compute_coverage(task_id, ["pm25"])
    assert "pm25" in str(excinfo.value)
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_coverage_metadata.py -v
```

Expected: tests FAIL with `KeyError: 'boundary'` (response dict doesn't yet include the new fields) and `FileNotFoundError` (loader still reads `app.config.settings.DATA_DIR / "variable_metadata.json"`, not the patched registry).

- [ ] **Step 3: Implement the minimal code to pass the test**

Edit `spacescans-web/backend/app/task_manager.py`. Replace the body of `compute_coverage` (lines 39-145) so it sources metadata via the registry:

```python
def compute_coverage(task_id: str, variable_keys: list[str]) -> dict:
    """Compute per-variable cohort coverage statistics for a task's input.csv."""
    import pandas as pd  # noqa: PLC0415
    from app import variable_registry  # noqa: PLC0415

    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_csv = task_dir / "input.csv"
    if not input_csv.exists():
        raise FileNotFoundError("No input uploaded")

    resolved: dict[str, dict] = {}
    unknown: list[str] = []
    for var in variable_keys:
        try:
            resolved[var] = variable_registry.get_variable(var)
        except KeyError:
            unknown.append(var)
    if unknown:
        raise KeyError(", ".join(unknown))

    df = pd.read_csv(
        input_csv,
        parse_dates=["startDate", "endDate"],
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )
    n_total = len(df)

    if n_total == 0:
        return {
            "row_count": 0,
            "variables": {
                var: {
                    "coverage_years": list(resolved[var]["coverage_years"]),
                    "patients_in_time_window": 0,
                    "patients_in_region": 0,
                    "patients_covered": 0,
                    "coverage_pct": 0.0,
                    "warnings": ["Cohort is empty — no patients to evaluate"],
                    "boundary": resolved[var]["boundary"],
                    "display_unit": resolved[var]["display_unit"],
                }
                for var in variable_keys
            },
        }

    out_vars: dict[str, dict] = {}
    for var in variable_keys:
        m = resolved[var]
        y0, y1 = m["coverage_years"]
        cov_start = pd.Timestamp(f"{y0}-01-01")
        cov_end = pd.Timestamp(f"{y1}-12-31")
        in_time = (df["startDate"] <= cov_end) & (df["endDate"] >= cov_start)
        if m.get("coverage_region") == "CONUS":
            in_region = (
                df["longitude"].between(-125, -66)
                & df["latitude"].between(24, 50)
            )
        else:
            in_region = pd.Series(True, index=df.index)
        covered = in_time & in_region

        warnings: list[str] = []
        time_out_pct = (~in_time).sum() / n_total * 100
        if time_out_pct > 5:
            warnings.append(
                f"{time_out_pct:.0f}% of patients have episodes entirely outside "
                f"{y0}-{y1}"
            )
        region_out_pct = (~in_region).sum() / n_total * 100
        if region_out_pct > 5:
            warnings.append(
                f"{region_out_pct:.0f}% of patients fall outside the "
                f"{m['coverage_region']} coverage region"
            )

        out_vars[var] = {
            "coverage_years": [y0, y1],
            "patients_in_time_window": int(in_time.sum()),
            "patients_in_region": int(in_region.sum()),
            "patients_covered": int(covered.sum()),
            "coverage_pct": round(100 * covered.sum() / n_total, 2),
            "warnings": warnings,
            "boundary": m["boundary"],
            "display_unit": m["display_unit"],
        }

    return {"row_count": n_total, "variables": out_vars}
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_coverage_metadata.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 101 passed (75 + 9 + 9 + 4 + 4).

- [ ] **Step 6: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_coverage_metadata.py
git commit -m "feat(coverage): drive compute_coverage from variable_registry; add boundary + display_unit to response"
```

**Notes:**
- The inline `_load_variable_metadata` + module cache stay live for other call sites in `task_manager.py`. T4 is a surgical swap inside `compute_coverage` only.
- `KeyError` raising semantics are preserved (`args[0]` is the comma-joined unknown-key list) so `app/routers/tasks.py`'s `400 unknown variable` mapping needs no change.
- Depends on T2 (`variable_registry` module + `MetadataSchemaError`); does not depend on T3.

---

### Task T5: experiments/_merge.py: extract write_partial + fan_in from bg_ndi_wi.merge_results

**Files:**
- Create: `spacescans-web/backend/app/experiments/_merge.py`
- Modify: `spacescans-web/backend/app/experiments/bg_ndi_wi.py:228-270` (replace `merge_results` body with a 3-line call into `write_partial`)
- Test: `spacescans-web/backend/tests/test_merge_partial.py`

**Goal:** Extract the (pid, episode_id) join, value-col selection, and match_pct logging from `bg_ndi_wi.merge_results` into a shared `experiments/_merge.py` module exposing `write_partial(...) -> Path` and `fan_in(...) -> Path`, sourcing `value_cols` from `variable_registry.get_variable(key)` so the same merge code serves bg_ndi_wi, zcta5_cbp, and future runners.

**Context:** Sprint 2 left the (pid, episode_id) join inlined inside `backend/app/experiments/bg_ndi_wi.py:228-270` — that block reads each variable's per-step parquet, renames `{PATID -> pid, geoid -> episode_id}`, coerces `episode_id` to int, outer-joins across variables, emits a `match_pct` warning to `logs.jsonl` if < 90%, and writes `task_dir/output/result.csv`. Sprint 3 (B5) calls for two runners each emitting a per-experiment partial CSV, then a separate fan-in step. The extraction MUST preserve the Sprint 2 join byte-for-byte (Risk R6); the only new behaviour is that `value_cols` now comes from `variable_registry.get_variable(key)["value_cols"]` instead of "all parquet columns minus join keys".

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_merge_partial.py`:

```python
"""Sprint 3 T5: experiments/_merge.py — write_partial + fan_in."""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


def _write_input_csv(task_dir: Path, n: int = 10) -> None:
    (task_dir).mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(n)],
        "startDate": ["2017-01-01"] * n,
        "endDate": ["2017-12-31"] * n,
        "longitude": [-93.0] * n,
        "latitude": [45.0] * n,
    })
    df.to_csv(task_dir / "input.csv", index=False)


def _write_variable_parquet(out_dir: Path, name: str, n: int, value_cols: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"PATID": [f"PID{i:07d}" for i in range(n)],
            "geoid": list(range(n))}
    for c in value_cols:
        data[c] = [float(i) for i in range(n)]
    pd.DataFrame(data).to_parquet(out_dir / f"{name}.parquet", index=False)


def test_write_partial_synthetic_10x10_match_pct_100(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-a"
    _write_input_csv(task_dir, n=10)
    _write_variable_parquet(task_dir / "output", "ndi", n=10, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    assert out == task_dir / "output" / "result_bg_ndi_wi.csv"
    df = pd.read_csv(out)
    assert set(df.columns) >= {"pid", "episode_id", "ndi"}
    assert len(df) == 10
    logs = task_dir / "logs.jsonl"
    if logs.exists():
        events = [json.loads(line) for line in logs.read_text().splitlines() if line.strip()]
        assert not any(e.get("event") == "merge_partial_low_match_pct" for e in events)


def test_write_partial_renames_patid_to_pid_and_geoid_to_episode_id(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-b"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(task_dir / "output", "ndi", n=5, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    df = pd.read_csv(out)
    assert "pid" in df.columns and "PATID" not in df.columns
    assert "episode_id" in df.columns and "geoid" not in df.columns
    assert pd.api.types.is_integer_dtype(df["episode_id"])


def test_write_partial_emits_low_match_pct_warning(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-c"
    _write_input_csv(task_dir, n=10)
    _write_variable_parquet(task_dir / "output", "ndi", n=5, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    events = [json.loads(line) for line in (task_dir / "logs.jsonl").read_text().splitlines() if line.strip()]
    low = [e for e in events if e.get("event") == "merge_partial_low_match_pct"]
    assert len(low) == 1
    assert low[0]["experiment_key"] == "bg_ndi_wi"
    assert low[0]["match_pct"] == 50.0


def test_write_partial_value_cols_sourced_from_registry(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-d"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(task_dir / "output", "cbp_multi", n=5,
                            value_cols=["r_total", "r_food", "r_unused"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["r_total", "r_food"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="zcta5_cbp",
            variables=["cbp_multi"],
            parquet_map={"cbp_multi": "cbp_multi.parquet"},
        )

    df = pd.read_csv(out)
    assert "r_total" in df.columns and "r_food" in df.columns
    assert "r_unused" not in df.columns


def test_fan_in_left_joins_two_partials_no_row_duplication(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-e"
    _write_input_csv(task_dir, n=5)
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(5)],
        "episode_id": list(range(5)),
        "ndi": [0.1 * i for i in range(5)],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(5)],
        "episode_id": list(range(5)),
        "r_total": [float(i) for i in range(5)],
    }).to_csv(out_dir / "result_zcta5_cbp.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi", "zcta5_cbp"])
    df = pd.read_csv(out)
    assert out == task_dir / "output" / "result.csv"
    assert len(df) == 5
    assert {"pid", "episode_id", "ndi", "r_total"}.issubset(df.columns)


def test_fan_in_suffix_handling_on_column_collision(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-f"
    _write_input_csv(task_dir, n=3)
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(3)],
        "episode_id": list(range(3)),
        "score": [1.0, 2.0, 3.0],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(3)],
        "episode_id": list(range(3)),
        "score": [10.0, 20.0, 30.0],
    }).to_csv(out_dir / "result_zcta5_cbp.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi", "zcta5_cbp"])
    df = pd.read_csv(out)
    assert "score" in df.columns
    assert "score_zcta5_cbp_dup" in df.columns
    assert df["score"].tolist() == [1.0, 2.0, 3.0]
    assert df["score_zcta5_cbp_dup"].tolist() == [10.0, 20.0, 30.0]


def test_bg_ndi_wi_merge_results_delegates_to_write_partial(tmp_path):
    from app.experiments import bg_ndi_wi as mod

    task_dir = tmp_path / "task-t5-g"
    _write_input_csv(task_dir, n=4)
    _write_variable_parquet(task_dir / "output", "ndi", n=4, value_cols=["ndi"])
    _write_variable_parquet(task_dir / "output", "natwalkind", n=4, value_cols=["NatWalkInd"])

    with patch("app.variable_registry.get_variable",
               side_effect=lambda k: {"ndi": {"value_cols": ["ndi"]},
                                      "natwalkind": {"value_cols": ["NatWalkInd"]}}[k]):
        mod.merge_results(task_dir=task_dir, variables=["ndi", "natwalkind"])

    assert (task_dir / "output" / "result_bg_ndi_wi.csv").exists()
    df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    assert {"pid", "episode_id", "ndi", "NatWalkInd"}.issubset(df.columns)
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_merge_partial.py -v
```

Expected: all 7 tests FAIL with `ModuleNotFoundError: No module named 'app.experiments._merge'`.

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `spacescans-web/backend/app/experiments/_merge.py`:

```python
"""Shared per-experiment merge utilities. Extracted from bg_ndi_wi.merge_results."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from app import variable_registry


def _emit_log_warning(task_dir: Path, **fields) -> None:
    log_path = task_dir / "logs.jsonl"
    record = {"ts": time.time(), "level": "warning", **fields}
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def write_partial(
    task_dir: Path,
    experiment_key: str,
    variables: list[str],
    parquet_map: dict[str, str],
) -> Path:
    """Per-runner merge step. Returns path to result_<experiment_key>.csv."""
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_{experiment_key}.csv"

    input_df = pd.read_csv(task_dir / "input.csv", dtype=str)
    input_df["episode_id"] = list(range(len(input_df)))
    input_df["episode_id"] = input_df["episode_id"].astype(int)
    if "pid" not in input_df.columns:
        input_df = input_df.rename(columns={"PATID": "pid"})
    input_keys = input_df[["pid", "episode_id"]]

    merged: pd.DataFrame | None = None
    for var_key in variables:
        parquet_path = out_dir / parquet_map[var_key]
        df = pd.read_parquet(parquet_path)

        df = df.rename(columns={"PATID": "pid", "geoid": "episode_id"})
        df["episode_id"] = df["episode_id"].astype(int)

        meta = variable_registry.get_variable(var_key)
        value_cols = [c for c in meta["value_cols"] if c in df.columns]
        df = df[["pid", "episode_id"] + value_cols]

        if merged is None:
            merged = df
        else:
            new_cols = [c for c in df.columns
                        if c in ("pid", "episode_id") or c not in merged.columns]
            df = df[new_cols]
            merged = merged.merge(df, on=["pid", "episode_id"], how="outer")

    if merged is None:
        merged = input_keys.copy()

    joined = input_keys.merge(merged, on=["pid", "episode_id"], how="left")
    value_only = joined.drop(columns=["pid", "episode_id"])
    if value_only.shape[1] == 0:
        match_pct = 100.0
        matched = len(input_keys)
    else:
        matched = int(value_only.notna().any(axis=1).sum())
        match_pct = round(100.0 * matched / max(len(input_keys), 1), 2)

    if match_pct < 90.0:
        _emit_log_warning(
            task_dir,
            experiment_key=experiment_key,
            event="merge_partial_low_match_pct",
            match_pct=match_pct,
            cohort_n=len(input_keys),
            matched_n=int(matched),
        )

    merged.to_csv(out_path, index=False)
    return out_path


def fan_in(task_dir: Path, experiment_keys: list[str]) -> Path:
    """Left-join each result_<key>.csv on (pid, episode_id) → result.csv."""
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    if "pid" not in df.columns:
        df = df.rename(columns={"PATID": "pid"})
    df["episode_id"] = list(range(len(df)))
    df["episode_id"] = df["episode_id"].astype(int)

    for exp_key in experiment_keys:
        partial = pd.read_csv(
            task_dir / "output" / f"result_{exp_key}.csv",
            dtype=str,
        )
        partial["episode_id"] = partial["episode_id"].astype(int)
        df = df.merge(
            partial,
            on=["pid", "episode_id"],
            how="left",
            suffixes=("", f"_{exp_key}_dup"),
        )

    out_path = task_dir / "output" / "result.csv"
    df.to_csv(out_path, index=False)
    return out_path
```

Then replace `merge_results` body inside `bg_ndi_wi.py`:

```python
def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Sprint 3: delegates to the shared _merge.write_partial."""
    from app.experiments import _merge
    parquet_map = {v: f"{_VARIABLE_TO_STEP[v].name}.parquet" for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="bg_ndi_wi",
        variables=variables,
        parquet_map=parquet_map,
    )
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_merge_partial.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 108 passed (75 + 9 + 9 + 4 + 4 + 7). The Sprint 2 regression `test_e2e_multi_episode_cohort` must still pass (Risk R6).

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/_merge.py \
        backend/app/experiments/bg_ndi_wi.py \
        backend/tests/test_merge_partial.py
git commit -m "refactor(experiments): extract write_partial + fan_in into _merge.py"
```

**Notes:** Depends on T2. Sprint 2's old file was `result.csv`; Sprint 3 renames per-runner output to `result_bg_ndi_wi.csv` and produces unified `result.csv` only after `fan_in` runs in T9. Adjust any Sprint 2 test that asserts on the old path. `cohort_n` denominator uses input.csv row count, matching Sprint 2 semantics. `fan_in`'s `suffixes=("", f"_{exp_key}_dup")` keeps the first occurrence un-suffixed.

---

### Task T6: bg_ndi_wi: lift BG cache-key literal into _BOUNDARY constant

**Files:**
- Create: (none)
- Modify: `spacescans-web/backend/app/experiments/bg_ndi_wi.py:294-304` (`_cache_key`) plus a new module-level `_BOUNDARY` constant near the top of the file
- Test: `spacescans-web/backend/tests/test_bg_ndi_wi.py` (append two cases)

**Goal:** Replace the hardcoded `"BG"` string inside `_cache_key` with a module-level `_BOUNDARY = "BG"` constant so each per-boundary runner (Sprint 3 adds `zcta5_cbp.py` with `_BOUNDARY = "ZCTA5"`) parameterises its own cache namespace via a single named symbol, while keeping byte-for-byte parity with the existing BG cache.

**Context:** `bg_ndi_wi.py`'s `_cache_key(input_parquet, step, user_config)` currently hardcodes `boundary = "BG"` and emits `f"{sha[:8]}__{boundary}__b{buf}m__r{raster}m"`. Spec B15 and C3 Cache Extension require the literal to become a per-runner module constant so the upcoming `zcta5_cbp.py` can declare `_BOUNDARY = "ZCTA5"`. The function signature is unchanged; this is a pure refactor — existing BG cache entries on disk must keep hitting.

- [ ] **Step 1: Write the failing test(s)**

Append to `spacescans-web/backend/tests/test_bg_ndi_wi.py`:

```python
def test_boundary_constant_is_BG():
    """Sprint 3 B15: the per-runner boundary literal must be a module constant."""
    from app.experiments import bg_ndi_wi
    assert bg_ndi_wi._BOUNDARY == "BG"


def test_cache_key_byte_identical_after_boundary_refactor(tmp_path):
    """Refactoring 'BG' into _BOUNDARY must NOT change the emitted key bytes."""
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP, _hash_input_parquet

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}

    sha8 = _hash_input_parquet(p)[:8]
    expected = f"{sha8}__BG__b270m__r25m"
    assert _cache_key(p, _C3_STEP, cfg) == expected
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_bg_ndi_wi.py -v -k "boundary_constant or byte_identical"
```

Expected: `test_boundary_constant_is_BG` FAILS with `AttributeError: module 'app.experiments.bg_ndi_wi' has no attribute '_BOUNDARY'`.

- [ ] **Step 3: Implement the minimal code to pass the test**

In `bg_ndi_wi.py`, add the module-level constant just below `_C3_STEP`:

```python
_C3_STEP = PipelineStep(name="c3_bg", template_relpath="c3/bg_us_demo.yaml", is_c3=True)

# Sprint 3 B15: per-runner boundary tag baked into the C3 cache key.
_BOUNDARY = "BG"
```

Then replace the `boundary = "BG"` line inside `_cache_key`:

```python
def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Build a deterministic, human-readable cache key.

    Format: ``<sha8>__<boundary>__b<buffer>m__r<raster>m``
    """
    sha = _hash_input_parquet(input_parquet)
    boundary = _BOUNDARY
    buf = user_config["buffer"]["size"]
    raster = user_config["buffer"]["raster_res_m"]
    return f"{sha[:8]}__{boundary}__b{buf}m__r{raster}m"
```

Leave the `boundary="BG"` literal in `_write_cache_meta(...)` alone for now — sidecar metadata is a separate concern.

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_bg_ndi_wi.py -v -k "cache_key"
```

Expected: all `cache_key*` tests pass (including the new 2).

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 110 passed (75 + 9 + 9 + 4 + 4 + 7 + 2).

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "refactor(bg_ndi_wi): lift 'BG' cache-key literal into _BOUNDARY constant"
```

**Notes:** Pure refactor — no behaviour change for existing BG caches. The `boundary="BG"` literal at `_write_cache_meta` is intentionally untouched; revisit when Sprint 3 introduces a second runner. T7 will mirror this pattern with `_BOUNDARY = "ZCTA5"`.

---

### Task T7: experiments/zcta5_cbp.py: new ZCTA5xCBP runner (clone-trim of bg_ndi_wi)

**Files:**
- Create: `spacescans-web/backend/app/experiments/zcta5_cbp.py`
- Test: `spacescans-web/backend/tests/test_zcta5_cbp.py`

**Goal:** Add a second experiment runner that drives the ZCTA5×CBP pipeline (`c3/zcta5_us_demo.yaml` + `c4/zcta5_cbp_demo.yaml`), wired to the shared `_merge.write_partial` so it emits `output/result_zcta5_cbp.csv`, with cache keys disambiguated by the literal `ZCTA5` boundary.

**Context:** The existing `backend/app/experiments/bg_ndi_wi.py` is a single-experiment orchestrator. Sprint 3 introduces a second experiment for ZCTA5×CBP that reuses 95% of that machinery. The CBP step's upstream template hardcodes `raster_res_m=25`, so this runner MUST NOT inject `buffer.raster_res_m` at C3-render time. T5 already extracted shared merge logic into `app.experiments._merge.write_partial`. T6 established the `_BOUNDARY` pattern — this task supplies `"ZCTA5"` instead of `"BG"`. The CBP parquet is one-parquet-many-columns: a single `c4_zcta5_cbp.parquet` carries all 10 `r_*` columns for the only `cbp_zcta5` variable key.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_zcta5_cbp.py`:

```python
"""Sprint 3 T7: ZCTA5xCBP runner — clone-trim of bg_ndi_wi."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from app.experiments import zcta5_cbp


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_T7"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({
        "variables": ["cbp_zcta5"],
        "buffer": {"size": 1000, "raster_res_m": 25},
    }))
    return d


def test_plan_is_c3_then_c4(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = zcta5_cbp.plan(config)
    assert [s.name for s in steps] == ["c3_zcta5", "c4_zcta5_cbp"]
    assert steps[0].is_c3 is True
    assert steps[1].is_c3 is False


def test_plan_rejects_unknown_variable(task_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        zcta5_cbp.plan({"variables": ["ndi"]})  # ndi belongs to bg_ndi_wi


def test_csv_to_parquet_adds_episode_id(task_dir: Path) -> None:
    src = task_dir / "input.csv"
    dst = task_dir / "input.parquet"
    zcta5_cbp.csv_to_parquet(src, dst)
    df = pd.read_parquet(dst)
    assert "episode_id" in df.columns
    assert df["episode_id"].tolist() == [0, 1, 2]


def test_render_yaml_injects_output_grouping_episode(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    templates = tmp_path / "configs"
    (templates / "c3").mkdir(parents=True)
    (templates / "c4").mkdir(parents=True)
    (templates / "c3" / "zcta5_us_demo.yaml").write_text(yaml.safe_dump({
        "name": "c3_zcta5_us_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270,
                   "raster_res_m": 25},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    (templates / "c4" / "zcta5_cbp_demo.yaml").write_text(yaml.safe_dump({
        "name": "c4_zcta5_cbp_demo",
        "buffer": {"patient_file": "PLACEHOLDER", "buffer_m": 270},
        "time": {"years": [2017]},
        "output": {"path": "PLACEHOLDER"},
    }))
    import app.config as cfgmod
    monkeypatch.setattr(cfgmod.settings, "SPACESCANS_CONFIG_TEMPLATES_DIR",
                        templates, raising=False)

    cfg = {"buffer": {"size": 1500, "raster_res_m": 25}}
    c3_path = zcta5_cbp.render_yaml(zcta5_cbp._C3_STEP, task_dir, cfg)
    rendered = yaml.safe_load(c3_path.read_text())
    assert rendered["time"]["output_grouping"] == "episode"
    assert rendered["buffer"]["raster_res_m"] == 25
    assert rendered["buffer"]["buffer_m"] == 1500


def test_cache_key_contains_zcta5_boundary(task_dir: Path) -> None:
    zcta5_cbp.csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
    key = zcta5_cbp._cache_key(
        task_dir / "input.parquet",
        zcta5_cbp._C3_STEP,
        {"buffer": {"size": 1500, "raster_res_m": 25}},
    )
    parts = key.split("__")
    assert parts[1] == "ZCTA5"
    assert parts[2] == "b1500m"
    assert parts[3] == "r25m"


def test_merge_results_emits_result_zcta5_cbp_csv(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """zcta5_cbp.merge_results mirrors bg_ndi_wi.merge_results — both
    are thin wrappers around _merge.write_partial (see T5)."""
    out_dir = task_dir / "output"
    out_dir.mkdir()
    r_cols = ["r_religious", "r_civic", "r_business", "r_political",
              "r_professional", "r_labor", "r_bowling", "r_recreational",
              "r_golf", "r_sports"]
    parquet_df = pd.DataFrame({
        "PATID": ["p1", "p1", "p2"],
        "geoid": [0, 1, 2],
        **{c: [0.1, 0.2, 0.3] for c in r_cols},
    })
    parquet_df.to_parquet(out_dir / "c4_zcta5_cbp.parquet", index=False)

    with monkeypatch.context() as m:
        m.setattr("app.variable_registry.get_variable",
                  lambda k: {"value_cols": r_cols})
        out = zcta5_cbp.merge_results(task_dir, variables=["cbp_zcta5"])
    assert out == out_dir / "result_zcta5_cbp.csv"
    assert out.exists()


def test_cli_accepts_variables_comma_list(
    task_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0
    monkeypatch.setattr(zcta5_cbp, "run", fake_run)

    rc = zcta5_cbp._cli_main(
        ["zcta5_cbp", "run", str(task_dir), "--variables", "cbp_zcta5"]
    )
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["cbp_zcta5"]
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_zcta5_cbp.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.experiments.zcta5_cbp'`.

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `spacescans-web/backend/app/experiments/zcta5_cbp.py` as a structural clone of `bg_ndi_wi.py`. Key differences from `bg_ndi_wi.py`: `_BOUNDARY = "ZCTA5"`, a single `_C3_STEP` keyed off `c3/zcta5_us_demo.yaml`, a one-entry `_VARIABLE_TO_STEP` for `cbp_zcta5`, a `_PARQUET_MAP` for the C4 output, `render_yaml` that does NOT inject `buffer.raster_res_m` (template default honoured — the CBP step hardcodes raster_res_m=25), a thin `merge_results` wrapper delegating to `_merge.write_partial`, and a `run(task_dir, variables=None)` that mirrors `bg_ndi_wi.run` with an optional override.

```python
"""Single-experiment orchestrator: ZCTA5 boundaries × CBP density.

Spawned by app.dispatcher as:
    python -m app.experiments.zcta5_cbp run <task_dir> [--variables cbp_zcta5]
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

import app.config
from app.experiments import _merge
from app.experiments.bg_ndi_wi import (
    PipelineStep,
    parse_step_progress,
    run_pipeline_step,
    _append_log,
    _is_valid_cached_parquet,
)

_log = logging.getLogger(__name__)

_BOUNDARY = "ZCTA5"

_C3_STEP = PipelineStep(
    name="c3_zcta5",
    template_relpath="c3/zcta5_us_demo.yaml",
    is_c3=True,
)

_VARIABLE_TO_STEP = {
    "cbp_zcta5": PipelineStep(
        name="c4_zcta5_cbp",
        template_relpath="c4/zcta5_cbp_demo.yaml",
        is_c3=False,
    ),
}

_PARQUET_MAP = {"cbp_zcta5": "c4_zcta5_cbp.parquet"}


def plan(config: dict) -> list[PipelineStep]:
    """Compute the ordered pipeline steps for a task.

    One C3 step (ZCTA5 boundary) then one C4 step per selected variable.
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    steps: list[PipelineStep] = [_C3_STEP]
    for v in ("cbp_zcta5",):
        if v in variables:
            steps.append(_VARIABLE_TO_STEP[v])
    return steps


_FIPS_STR_COLS = ("state_fips", "county_fips", "tract_geoid", "bg_geoid", "zcta5")


def csv_to_parquet(src: Path, dst: Path) -> None:
    """Convert uploaded CSV to parquet with explicit dtype handling.

    Mirrors bg_ndi_wi.csv_to_parquet but extends the FIPS string set with
    `zcta5` so ZCTA5 codes retain leading zeros for downstream geo joins.
    Adds a deterministic ``episode_id = range(len(df))`` column.
    """
    header = pd.read_csv(src, nrows=0).columns.tolist()
    fips_dtypes = {c: str for c in _FIPS_STR_COLS if c in header}
    df = pd.read_csv(src, dtype=fips_dtypes)
    df["startDate"] = pd.to_datetime(df["startDate"], format="%Y-%m-%d", errors="raise")
    df["endDate"] = pd.to_datetime(df["endDate"], format="%Y-%m-%d", errors="raise")
    if "episode_id" in df.columns:
        _log.warning(
            "input.csv carried an episode_id column; overwriting with "
            "deterministic row-index ids."
        )
    df["episode_id"] = range(len(df))
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dst, index=False)


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read a pipeline YAML template, inject task-specific fields, write to task dir.

    Unlike bg_ndi_wi.render_yaml, this runner does NOT overwrite
    ``buffer.raster_res_m`` — the c4/zcta5_cbp_demo.yaml template hardcodes
    raster_res_m=25 to match the ZCTA5×25m weight parquet at
    output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet,
    and overriding it would break that join. We still inject
    ``time.output_grouping='episode'`` so the pipeline emits one row per
    (PATID, episode_id) for the merge step to join on.
    """
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    # NOTE: intentionally NO `cfg["buffer"]["raster_res_m"] = ...` here.
    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def _write_status(task_dir: Path, **fields) -> None:
    """Delegates to the atomic _write_status introduced in T8."""
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **fields)


def _hash_input_parquet(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Build a deterministic cache key namespaced by ``_BOUNDARY``.

    Format mirrors bg_ndi_wi._cache_key: ``<sha8>__ZCTA5__b<buffer>m__r<raster>m``.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    raster = user_config["buffer"]["raster_res_m"]
    return f"{sha[:8]}__{_BOUNDARY}__b{buf}m__r{raster}m"


def _write_cache_meta(path: Path, **fields) -> None:
    fields.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(fields, indent=2))


def _count_input_rows(input_csv: Path) -> int:
    with open(input_csv) as f:
        next(f, None)
        return sum(1 for _ in f)


def _install_cancel_handler(task_dir: Path) -> None:
    def _handler(_signum, _frame):
        _write_status(task_dir, status="cancelled",
                      message="Task cancelled by user")
        _append_log(task_dir, "info", "runner",
                    "received SIGTERM — task cancelled")
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, _handler)


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to the shared _merge.write_partial (matches bg_ndi_wi T5 wrapper)."""
    parquet_map = {v: _PARQUET_MAP[v] for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="zcta5_cbp",
        variables=variables,
        parquet_map=parquet_map,
    )


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Main entry point. Mirrors bg_ndi_wi.run with an override `variables`.

    Acquires .run_lock (fcntl) for the lifetime of this process. The
    `variables` override (when provided by the dispatcher) replaces the
    config-file variable list so a multi-experiment dispatch routes only
    this runner's variables here.
    """
    _install_cancel_handler(task_dir)
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _write_status(task_dir, status="error",
                      message="another task acquired the run lock first; retry shortly")
        os.close(lock_fd)
        return 1

    try:
        config = json.loads((task_dir / "config.json").read_text())
        if variables is not None:
            config = {**config, "variables": list(variables)}
        steps = plan(config)
        total_steps = len(steps)

        _write_status(
            task_dir,
            status="running",
            progress=0.0,
            message="Preparing input data",
            started_at=datetime.now(timezone.utc).isoformat(),
            pid=os.getpid(),
            current_step="csv_to_parquet",
            total_steps=total_steps,
            steps=[s.name for s in steps],
        )

        try:
            csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"csv_to_parquet failed: {exc!r}")
            _write_status(task_dir, status="error",
                          message=f"input conversion failed: {exc}")
            return 1

        for idx, step in enumerate(steps):
            _write_status(
                task_dir,
                current_step=step.name,
                message=f"Running {step.name} ({idx+1}/{total_steps})",
                progress=idx / total_steps,
            )
            out_parquet = task_dir / "output" / f"{step.name}.parquet"

            cache_path: Path | None = None
            if step.is_c3:
                try:
                    cache_key = _cache_key(task_dir / "input.parquet", step, config)
                    cache_path = app.config.settings.C3_CACHE_DIR / f"{cache_key}.parquet"
                    if _is_valid_cached_parquet(cache_path):
                        out_parquet.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(cache_path, out_parquet)
                        _append_log(task_dir, "info", "runner",
                                    f"cache hit: {cache_key} — skipping pipeline run")
                        _write_status(
                            task_dir,
                            current_step=step.name,
                            progress=(idx + 1) / total_steps,
                            message=f"Reused cached {step.name}",
                        )
                        continue
                except Exception as exc:
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
                    cache_path = None

            try:
                yaml_path = render_yaml(step, task_dir, config)
            except Exception as exc:
                _append_log(task_dir, "error", "runner",
                            f"render_yaml({step.name}) failed: {exc!r}")
                _write_status(task_dir, status="error",
                              message=f"render failed at {step.name}")
                return 1

            def _on_step_progress(frac: float, idx=idx, step=step) -> None:
                _write_status(
                    task_dir,
                    progress=(idx + frac) / total_steps,
                    message=f"Running {step.name} ({idx+1}/{total_steps}) — {int(frac*100)}%",
                )

            step_start = time.time()
            rc = run_pipeline_step(yaml_path, task_dir, step_name=step.name,
                                   on_progress=_on_step_progress)
            if rc != 0:
                _write_status(task_dir, status="error",
                              message=f"step {step.name} failed with exit code {rc}")
                return rc
            if not out_parquet.exists():
                _write_status(task_dir, status="error",
                              message=f"step {step.name} produced no output parquet")
                return 1

            if step.is_c3 and cache_path is not None:
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(out_parquet, cache_path)
                    _write_cache_meta(
                        cache_path.with_suffix(".meta.json"),
                        sha_full=_hash_input_parquet(task_dir / "input.parquet"),
                        boundary=_BOUNDARY,
                        buffer_m=config["buffer"]["size"],
                        raster_res_m=config["buffer"]["raster_res_m"],
                        input_row_count=_count_input_rows(task_dir / "input.csv"),
                        wall_clock_seconds=int(time.time() - step_start),
                        file_size_bytes=out_parquet.stat().st_size,
                    )
                    _append_log(task_dir, "info", "runner",
                                f"cache write: {cache_path.name}")
                except OSError as exc:
                    _append_log(task_dir, "warning", "runner",
                                f"cache write failed: {exc!r} — continuing")

        _write_status(task_dir, current_step="merge",
                      message="Merging variable outputs",
                      progress=(total_steps - 0.1) / total_steps)
        try:
            merge_results(task_dir, variables=config["variables"])
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"merge_results failed: {exc!r}")
            _write_status(task_dir, status="error", message=f"merge failed: {exc}")
            return 1

        _write_status(task_dir, status="finished", progress=1.0,
                      message=f"Completed {total_steps} pipeline steps")
        return 0
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _cli_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="zcta5_cbp")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("task_dir", type=Path)
    p_run.add_argument("--variables", type=str, default=None,
                       help="comma-separated subset (overrides config.json)")
    args = parser.parse_args(argv[1:])
    if args.cmd != "run":
        parser.error(f"unknown command: {args.cmd}")
    variables = (
        [v.strip() for v in args.variables.split(",") if v.strip()]
        if args.variables else None
    )
    return run(args.task_dir, variables=variables)


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv))
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_zcta5_cbp.py -v
```

Expected: 7 PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 117 passed (110 + 7).

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/zcta5_cbp.py backend/tests/test_zcta5_cbp.py
git commit -m "feat(experiments): ZCTA5xCBP runner cloned-and-trimmed from bg_ndi_wi"
```

**Notes:** Depends on T5 (`_merge.write_partial`) and T6 (`_BOUNDARY` pattern). The C4 template at `/Users/xai/Desktop/spacescans-project/spacescans-pipeline/configs/c4/zcta5_cbp_demo.yaml` is touched only during e2e runs (T14). `run()` is structurally identical to `bg_ndi_wi.run()` except for: (1) `variables` override param for CLI flag; (2) `_BOUNDARY="ZCTA5"`; (3) no `raster_res_m` override; (4) merge dispatches to shared `_merge.write_partial`.

---

### Task T8: status.json: atomic merge writer + experiments map schema extension

**Files:**
- Create: `spacescans-web/backend/tests/test_status_writer.py`
- Modify: `spacescans-web/backend/app/task_manager.py:390-394` (replace `_read_status` and add `_write_status`)
- Test: `spacescans-web/backend/tests/test_status_writer.py`

**Goal:** Upgrade `_write_status` into a flock-protected read-modify-write helper that deep-merges the `experiments` sub-key per-key, atomically replaces `status.json`, and re-derives the legacy flat `steps[]`/`current_step`/`total_steps`/`progress` fields by concatenating across experiments in dispatch (insertion) order.

**Context:** `task_manager.py` owns `_read_status(task_dir)` (lines 390-394) and `recover_orphaned_tasks` writes status.json via raw `write_text` (lines 386-388). Runners (`bg_ndi_wi.py`) and the orchestrator both call `status_path.write_text(json.dumps(...))` directly, which races whenever two writers touch the file. Sprint 3 dispatches multiple runners sequentially (T9), so the supervisor + active runner pair becomes two concurrent writers; the spec mandates `fcntl.flock` + `os.replace` atomic rename plus a deep merge of the new top-level `experiments` map.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_status_writer.py`:

```python
"""Sprint 3 T8: _write_status atomic merge writer + experiments map."""
import json
import multiprocessing as mp
from pathlib import Path

import pytest


@pytest.fixture
def task_dir(tmp_path):
    d = tmp_path / "task-abc"
    d.mkdir()
    return d


def test_write_status_creates_file_with_experiments_initialiser(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={})
    data = json.loads((task_dir / "status.json").read_text())
    assert data["status"] == "running"
    assert data["experiments"] == {}
    assert data["steps"] == []
    assert data["total_steps"] == 0
    assert data["current_step"] is None
    assert data["progress"] == 0.0


def test_write_status_experiments_amend_preserves_sibling_keys(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_bg", "c4_ndi"], "current_step": None},
        "zcta5_cbp": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"], "current_step": None},
    })
    _write_status(task_dir, experiments={
        "bg_ndi_wi": {"status": "running", "progress": 0.5,
                      "current_step": "c4_ndi"},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["experiments"]["bg_ndi_wi"]["status"] == "running"
    assert data["experiments"]["bg_ndi_wi"]["progress"] == 0.5
    assert data["experiments"]["bg_ndi_wi"]["steps"] == ["c3_bg", "c4_ndi"]
    assert data["experiments"]["zcta5_cbp"]["status"] == "pending"


def test_write_status_flat_steps_concatenated_in_insertion_order(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
                      "current_step": None},
        "zcta5_cbp": {"status": "pending", "progress": 0.0,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"],
                      "current_step": None},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["steps"] == ["c3_bg", "c4_ndi", "c4_walkability",
                             "c3_zcta5", "c4_zcta5_cbp"]
    assert data["total_steps"] == 5


def test_write_status_aggregated_progress(task_dir):
    from app.task_manager import _write_status
    # 3*1.0 + 2*0.5 = 4 completed / 5 total = 0.80
    _write_status(task_dir, status="running", experiments={
        "bg_ndi_wi": {"status": "finished", "progress": 1.0,
                      "steps": ["c3_bg", "c4_ndi", "c4_walkability"],
                      "current_step": None},
        "zcta5_cbp": {"status": "running", "progress": 0.5,
                      "steps": ["c3_zcta5", "c4_zcta5_cbp"],
                      "current_step": "c4_zcta5_cbp"},
    })
    data = json.loads((task_dir / "status.json").read_text())
    assert data["progress"] == pytest.approx(0.80, abs=1e-6)
    assert data["current_step"] == "c4_zcta5_cbp"


def test_write_status_top_level_keys_overwrite(task_dir):
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", pid=123, started_at="2026-06-15T10:00:00Z")
    _write_status(task_dir, status="finished")
    data = json.loads((task_dir / "status.json").read_text())
    assert data["status"] == "finished"
    assert data["pid"] == 123
    assert data["started_at"] == "2026-06-15T10:00:00Z"


def _hammer(args):
    task_dir_str, exp_key, n = args
    import importlib
    import app.task_manager as tm
    importlib.reload(tm)
    for i in range(n):
        tm._write_status(Path(task_dir_str), experiments={
            exp_key: {"status": "running", "progress": i / n,
                      "steps": [f"{exp_key}_s1", f"{exp_key}_s2"],
                      "current_step": f"{exp_key}_s1"},
        })


def test_write_status_two_concurrent_writers_do_not_corrupt(task_dir):
    """fcntl.flock + os.replace must keep the file parseable under contention."""
    from app.task_manager import _write_status
    _write_status(task_dir, status="running", experiments={})
    with mp.get_context("spawn").Pool(2) as pool:
        pool.map(_hammer, [(str(task_dir), "bg_ndi_wi", 50),
                           (str(task_dir), "zcta5_cbp", 50)])
    raw = (task_dir / "status.json").read_text()
    data = json.loads(raw)
    assert set(data["experiments"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert not (task_dir / "status.json.tmp").exists()
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_status_writer.py -v
```

Expected: All 6 tests fail with `AttributeError: module 'app.task_manager' has no attribute '_write_status'`.

- [ ] **Step 3: Implement the minimal code to pass the test**

Edit `spacescans-web/backend/app/task_manager.py`. Replace the final `_read_status` block (lines 390-394) with:

```python
def _read_status(task_dir: Path) -> dict:
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return {"status": "not_started", "progress": 0.0, "message": "",
                "steps": [], "current_step": None, "total_steps": 0,
                "experiments": {}}
    return json.loads(status_path.read_text())


def _derive_flat_fields(experiments: dict) -> dict:
    """Compute legacy flat steps[]/current_step/total_steps/progress from
    the experiments map, preserving insertion (dispatch) order.

    Aggregated progress = sum(completed sub-steps) / total_steps.
    """
    flat_steps: list[str] = []
    completed = 0.0
    current_step = None
    for exp_key, exp in experiments.items():
        steps = list(exp.get("steps") or [])
        flat_steps.extend(steps)
        completed += float(exp.get("progress") or 0.0) * len(steps)
        if exp.get("status") == "running" and exp.get("current_step"):
            current_step = exp["current_step"]
    total = len(flat_steps)
    progress = (completed / total) if total else 0.0
    return {"steps": flat_steps, "current_step": current_step,
            "total_steps": total, "progress": round(progress, 6)}


def _write_status(task_dir: Path, **kwargs) -> dict:
    """Atomic read-modify-write of status.json with experiments-aware merge."""
    task_dir.mkdir(parents=True, exist_ok=True)
    lock_path = task_dir / ".status_lock"
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)

    import time as _time
    deadline = _time.monotonic() + 5.0
    while True:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if _time.monotonic() >= deadline:
                os.close(lock_fd)
                raise TimeoutError(
                    f"_write_status: could not acquire {lock_path} within 5s"
                )
            _time.sleep(0.01)

    try:
        status_path = task_dir / "status.json"
        if status_path.exists():
            current = json.loads(status_path.read_text())
        else:
            current = {}

        incoming_experiments = kwargs.pop("experiments", None)
        if incoming_experiments is not None:
            merged_experiments = dict(current.get("experiments") or {})
            for exp_key, exp_payload in incoming_experiments.items():
                existing_slot = dict(merged_experiments.get(exp_key) or {})
                existing_slot.update(exp_payload)
                merged_experiments[exp_key] = existing_slot
            current["experiments"] = merged_experiments
        elif "experiments" not in current:
            current["experiments"] = {}

        current.update(kwargs)

        current.update(_derive_flat_fields(current["experiments"]))

        tmp_path = task_dir / "status.json.tmp"
        tmp_path.write_text(json.dumps(current, indent=2))
        os.replace(str(tmp_path), str(status_path))
        return current
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_status_writer.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 123 passed (117 + 6).

- [ ] **Step 6: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_status_writer.py
git commit -m "feat(task_manager): atomic _write_status with experiments map deep-merge (Sprint 3 T8)"
```

**Notes:**
- `fcntl` is already imported in `task_manager.py`.
- The `.status_lock` lives inside the task directory so per-task contention does not block sibling tasks.
- `os.replace` is atomic only when source and destination are on the same filesystem — both live inside `task_dir`, so this holds.
- T9 (sequential dispatch loop) will be the first caller to write the `experiments={}` initialiser.

---

### Task T9: dispatcher.py supervisor + task_manager.start_task multi-experiment dispatch

**Files:**
- Create: `spacescans-web/backend/app/dispatcher.py`
- Modify: `spacescans-web/backend/app/task_manager.py` (replace `start_task` body; amend `stop_task`)
- Test: `spacescans-web/backend/tests/test_task_manager_dispatch.py`

**Goal:** Move the per-experiment runner loop out of the request thread into a Popen'd `app.dispatcher` supervisor subprocess that sequentially spawns each runner, marks remaining experiments as `skipped_due_to_prior_failure` on the first failure, and always calls `_merge.fan_in` on whatever completed — while `start_task` returns the supervisor pid synchronously.

**Context:** Sprint 2's `task_manager.start_task` `Popen`s a single runner and returns its pid immediately so the FastAPI request thread does not block. Sprint 3 introduces a multi-experiment world (T2 added `variables_by_experiment`, T5 created `_merge.fan_in`, T7 created the `zcta5_cbp` runner, T8 created the atomic `_write_status`). Spec section "Dispatch shape" mandates a two-process layout: the request handler `start_task` Popens `python -m app.dispatcher run <task_id>` with `start_new_session=True`, and the supervisor itself runs the sequential loop. The legacy `experiment` field on `POST /api/tasks/{id}/config` must still be accepted by the schema and recorded in `logs.jsonl`, but it is ignored for dispatch. Risk R5 requires partial-failure semantics: when a runner returns non-zero, mark remaining as `"skipped_due_to_prior_failure"` and still call `fan_in` on `completed`.

- [ ] **Step 1: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_task_manager_dispatch.py`:

```python
"""Sprint 3 T9: dispatcher supervisor + multi-experiment dispatch."""
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def task_dir_with_config(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task-xyz"
    task_dir.mkdir()
    (task_dir / "config.json").write_text(json.dumps({
        "variables": ["ndi", "cbp_density"],
        "buffer": {"size": 270, "raster_res_m": 25},
        "experiment": "auto",
    }))
    (task_dir / "output").mkdir()
    return task_dir


class _FakePopen:
    instances: list["_FakePopen"] = []

    def __init__(self, cmd, *, returncode: int = 0, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self._rc = returncode
        self.pid = 9000 + len(_FakePopen.instances)
        _FakePopen.instances.append(self)

    def wait(self, timeout=None):
        return self._rc


def test_dispatch_sequential_order_matches_registry(task_dir_with_config, monkeypatch):
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 2
    assert "app.experiments.bg_ndi_wi" in _FakePopen.instances[0].cmd
    assert "app.experiments.zcta5_cbp" in _FakePopen.instances[1].cmd
    assert result["completed"] == ["bg_ndi_wi", "zcta5_cbp"]
    fan_in.assert_called_once_with(task_dir_with_config, ["bg_ndi_wi", "zcta5_cbp"])


def test_dispatch_initialises_experiments_map(task_dir_with_config, monkeypatch):
    from app import dispatcher

    _FakePopen.instances = []
    captured_writes = []

    monkeypatch.setattr(dispatcher, "_write_status",
                        lambda task_dir, **kwargs: captured_writes.append(kwargs))
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    assert captured_writes
    first = captured_writes[0]
    assert first["status"] == "running"
    assert set(first["experiments"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert first["experiments"]["bg_ndi_wi"]["status"] == "pending"


def test_dispatch_partial_failure_marks_remaining(task_dir_with_config, monkeypatch):
    """First runner fails → second is marked skipped; fan_in NOT called (no completed)."""
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})

    def popen_with_first_fail(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(2 if idx == 0 else 0), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_with_first_fail)
    marked = []
    monkeypatch.setattr(dispatcher, "_mark_experiment",
                        lambda task_dir, key, status: marked.append((key, status)))
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 1
    assert ("zcta5_cbp", "skipped_due_to_prior_failure") in marked
    fan_in.assert_not_called()
    assert result["failed"] == ["bg_ndi_wi", "zcta5_cbp"]


def test_dispatch_partial_failure_after_success_calls_fan_in(task_dir_with_config, monkeypatch):
    """Runner 1 succeeds, runner 2 fails → fan_in called on [bg_ndi_wi]."""
    from app import dispatcher

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})

    def popen_with_second_fail(cmd, **kw):
        idx = len(_FakePopen.instances)
        return _FakePopen(cmd, returncode=(0 if idx == 0 else 2), **kw)

    monkeypatch.setattr(dispatcher.subprocess, "Popen", popen_with_second_fail)
    monkeypatch.setattr(dispatcher, "_mark_experiment", lambda *a, **kw: None)
    fan_in = MagicMock()
    monkeypatch.setattr("app.experiments._merge.fan_in", fan_in)

    result = dispatcher.dispatch(str(task_dir_with_config))

    fan_in.assert_called_once_with(task_dir_with_config, ["bg_ndi_wi"])
    assert result["completed"] == ["bg_ndi_wi"]
    assert result["failed"] == ["zcta5_cbp"]


def test_start_task_popens_dispatcher_and_returns_pid(task_dir_with_config, monkeypatch):
    from app import task_manager

    captured = {}

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        captured["kwargs"] = kw
        return _FakePopen(cmd, returncode=0, **kw)

    monkeypatch.setattr(task_manager.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(task_manager, "_task_dir",
                        lambda task_id: task_dir_with_config)

    out = task_manager.start_task(task_dir_with_config.name)

    assert "app.dispatcher" in captured["cmd"]
    assert "run" in captured["cmd"]
    assert captured["kwargs"].get("start_new_session") is True
    assert isinstance(out["pid"], int)


def test_legacy_experiment_field_logged_but_ignored(task_dir_with_config, monkeypatch):
    """experiment='bg_ndi_wi' must not prevent dispatch of cbp_zcta5.

    Asserts the audit record lands in the per-task logs.jsonl (spec R10),
    NOT in stdlib's caplog — the spec contract is the on-disk audit trail.
    """
    from app import dispatcher

    cfg = json.loads((task_dir_with_config / "config.json").read_text())
    cfg["experiment"] = "bg_ndi_wi"
    (task_dir_with_config / "config.json").write_text(json.dumps(cfg))

    _FakePopen.instances = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda cmd, **kw: _FakePopen(cmd, returncode=0, **kw))
    monkeypatch.setattr(dispatcher.variable_registry, "variables_by_experiment",
                        lambda selected: {"bg_ndi_wi": ["ndi"], "zcta5_cbp": ["cbp_density"]})
    monkeypatch.setattr("app.experiments._merge.fan_in", MagicMock())

    dispatcher.dispatch(str(task_dir_with_config))

    assert len(_FakePopen.instances) == 2
    log_lines = (task_dir_with_config / "logs.jsonl").read_text().splitlines()
    audit = [
        json.loads(line) for line in log_lines if line.strip()
        and json.loads(line).get("event") == "config_saved"
    ]
    assert len(audit) == 1, f"expected exactly one config_saved audit entry; got {audit}"
    assert audit[0]["experiment_field_received"] == "bg_ndi_wi"
    assert set(audit[0]["dispatch_plan"].keys()) == {"bg_ndi_wi", "zcta5_cbp"}
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_task_manager_dispatch.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.dispatcher'`.

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `spacescans-web/backend/app/dispatcher.py`:

```python
"""Sprint 3 T9: Supervisor subprocess that sequentially dispatches per-experiment runners.

Spawned by task_manager.start_task as: python -m app.dispatcher run <task_id>
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import app.config
from app import variable_registry

_log = logging.getLogger(__name__)


def _task_dir(task_id: str) -> Path:
    return app.config.settings.TASKS_DIR / f"task-{task_id}"


def _write_status(task_dir: Path, **kwargs) -> None:
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **kwargs)


def _mark_experiment(task_dir: Path, exp_key: str, status: str) -> None:
    _write_status(task_dir, experiments={exp_key: {"status": status}})


def dispatch(task_id_or_dir: str) -> dict:
    task_dir = Path(task_id_or_dir)
    if not task_dir.is_absolute():
        task_dir = _task_dir(task_id_or_dir)

    config = json.loads((task_dir / "config.json").read_text())
    selected = config.get("variables", [])
    legacy_exp_field = config.get("experiment")
    by_exp = variable_registry.variables_by_experiment(selected)

    # Audit-log the legacy `experiment` field receipt into the per-task
    # logs.jsonl (NOT stdlib logging) so spec R10 is structurally provable
    # from the task directory's audit stream.
    _audit_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": "info",
        "source": "dispatcher",
        "event": "config_saved",
        "experiment_field_received": legacy_exp_field,
        "dispatch_plan": {k: list(v) for k, v in by_exp.items()},
    }
    with open(task_dir / "logs.jsonl", "a") as _f:
        _f.write(json.dumps(_audit_entry) + "\n")

    if not by_exp:
        _write_status(task_dir, status="error", progress=0.0,
                      message="no variables selected")
        return {"task_id": task_dir.name, "failed": []}

    _write_status(
        task_dir,
        status="running",
        progress=0.0,
        message="Dispatching experiments",
        experiments={
            exp_key: {"status": "pending", "variables": list(vars_),
                      "started_at": None}
            for exp_key, vars_ in by_exp.items()
        },
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    completed: list[str] = []
    exp_keys = list(by_exp.keys())
    for i, exp_key in enumerate(exp_keys):
        exp_vars = by_exp[exp_key]
        cmd = [
            str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
            "-m", f"app.experiments.{exp_key}",
            "run", str(task_dir),
            "--variables", ",".join(exp_vars),
        ]
        _write_status(task_dir, experiments={exp_key: {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }})
        proc = subprocess.Popen(
            cmd,
            cwd=str(app.config.settings.BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Record the runner pid into the experiments map so stop_task (and
        # any external supervisor) can walk it to send SIGTERM directly.
        _write_status(task_dir, experiments={exp_key: {"pid": proc.pid}})
        rc = proc.wait()
        if rc != 0:
            _mark_experiment(task_dir, exp_key, "error")
            for skipped in exp_keys[i + 1:]:
                _mark_experiment(task_dir, skipped, "skipped_due_to_prior_failure")
            break
        _mark_experiment(task_dir, exp_key, "finished")
        completed.append(exp_key)

    failed = [k for k in exp_keys if k not in completed]

    if completed:
        from app.experiments import _merge
        _merge.fan_in(task_dir, completed)

    if not completed:
        _write_status(task_dir, status="error", progress=0.0,
                      message=f"All experiments failed (first failure: {failed[0]})")
        return {"task_id": task_dir.name, "failed": failed}
    if failed:
        _write_status(
            task_dir,
            status="partial",
            progress=round(len(completed) / len(exp_keys), 2),
            message=f"{len(completed)}/{len(exp_keys)} experiments completed",
        )
        return {"task_id": task_dir.name, "completed": completed, "failed": failed}

    _write_status(task_dir, status="finished", progress=1.0,
                  message=f"Completed {len(completed)} experiments")
    return {"task_id": task_dir.name, "completed": completed}


def _main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[1] != "run":
        print("usage: python -m app.dispatcher run <task_id>", file=sys.stderr)
        return 2
    try:
        dispatch(argv[2])
    except Exception:
        _log.exception("dispatcher crashed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
```

Modify `spacescans-web/backend/app/task_manager.py`. Replace `start_task` body with:

```python
def start_task(task_id: str) -> dict:
    """Sprint 3: Popen the supervisor and return its pid synchronously."""
    task_dir = _task_dir(task_id)
    if not (task_dir / "config.json").exists():
        raise FileNotFoundError(f"config.json missing for task {task_id}")

    cmd = [
        sys.executable,
        "-m", "app.dispatcher",
        "run", task_id,
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(app.config.settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _write_status(task_dir, pid=proc.pid)
    return {"pid": proc.pid, "task_id": task_id}
```

Amend `stop_task` inside `task_manager.py` to walk the experiments map and SIGTERM running runner pids in addition to the supervisor. Replace the existing stop_task body with:

```python
def stop_task(task_id: str) -> dict:
    """Sprint 3: SIGTERM the supervisor AND any per-experiment runner pids
    recorded under status.experiments[<exp_key>].pid by dispatcher.dispatch.

    The supervisor uses start_new_session=True, so SIGTERM to its pid
    normally takes down its child runners via the process group as well —
    but the dispatcher also Popens each runner with start_new_session=True,
    which puts each runner in its OWN session. We therefore walk the
    experiments map and SIGTERM each runner pid explicitly to avoid orphans.
    """
    import os
    import signal
    task_dir = _task_dir(task_id)
    status_path = task_dir / "status.json"
    if not status_path.exists():
        return {"status": "no-op", "reason": "no status.json"}
    status = json.loads(status_path.read_text())

    pids: list[int] = []
    sup_pid = status.get("pid")
    if isinstance(sup_pid, int):
        pids.append(sup_pid)
    for exp in (status.get("experiments") or {}).values():
        exp_pid = exp.get("pid")
        if isinstance(exp_pid, int) and exp.get("status") == "running":
            pids.append(exp_pid)

    sent: list[int] = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            sent.append(pid)
        except ProcessLookupError:
            continue
    return {"status": "stopping", "signalled_pids": sent}
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_task_manager_dispatch.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 129 passed (123 + 6). Existing `test_task_manager.py` tests that asserted the old single-runner Popen shape may need updates to assert the new dispatcher Popen shape (`"app.dispatcher" in cmd`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/dispatcher.py backend/app/task_manager.py backend/tests/test_task_manager_dispatch.py
git commit -m "feat(dispatcher): supervisor subprocess + sequential multi-experiment dispatch"
```

**Notes:**
- The dispatcher imports `app.experiments._merge` lazily inside `dispatch()` so test monkeypatches against `"app.experiments._merge.fan_in"` resolve correctly.
- `start_task` uses `sys.executable` for the supervisor (FastAPI worker's interpreter); the supervisor then shells out to `SPACESCANS_PIPELINE_PYTHON` for each runner.
- Depends on T5 (`_merge.fan_in`), T7 (`zcta5_cbp` runner), T8 (`_write_status`).

---

### Task T10: frontend/src/lib: api.listVariables + VarCoverage extension + variable-grouping helpers + use-variable-catalog hook

**Files:**
- Create: `spacescans-web/frontend/src/lib/variable-grouping.ts`
- Create: `spacescans-web/frontend/src/lib/use-variable-catalog.ts`
- Modify: `spacescans-web/frontend/src/lib/api.ts` (VarCoverage interface :96-103, api.saveConfig literal :161, append VariableMetadata/VariableCatalog + listVariables)
- Test: `spacescans-web/frontend/scripts/check-variable-grouping.mjs`

**Goal:** Add the typed catalog fetcher (`api.listVariables`), extend `VarCoverage` with `boundary` + `display_unit`, swap the `saveConfig` `experiment: "bg_ndi_wi"` literal for `"auto"`, and ship two pure helpers (`variable-grouping.ts`, `use-variable-catalog.ts`) that the Sprint 3 Variables and Review steps consume.

**Context:** `frontend/src/lib/api.ts` is the single typed wrapper around the FastAPI backend. Sprint 1 added `VarCoverage`; Sprint 3 backend T4 already extended that endpoint to also surface `boundary` and `display_unit`, so the TS interface is the last piece blocking the wizard refactor. The Variables step today hardcodes a `V1_VARIABLES` array — Sprint 3 deletes that in favor of `api.listVariables()` returning `VariableCatalog`. `variable-grouping.ts` is a pure helper module; `use-variable-catalog.ts` is a tiny React hook with a module-level cache so `VariablesStep` and `ReviewStep` share one fetch per page lifetime.

- [ ] **Step 1: Write the failing test(s)**

Create `frontend/scripts/check-variable-grouping.mjs`:

```javascript
// Sprint 3 T10 smoke: exercises variable-grouping helpers via the tsc-emitted JS output.
import assert from 'node:assert/strict';
import {
  groupByBoundary,
  groupByExperiment,
  BOUNDARY_ORDER,
  BOUNDARY_LABEL,
} from '../.next-check/lib/variable-grouping.js';

const catalog = {
  schema_version: 1,
  variables: {
    bg_ndi: {
      label: 'NDI', description: '', boundary: 'BG',
      coverage_years: [2013, 2020], coverage_region: 'CONUS',
      experiment: 'bg_ndi_wi', variable_type: 'continuous',
      display_unit: 'z-score', value_cols: ['ndi'],
    },
    bg_wi: {
      label: 'Walk Index', description: '', boundary: 'BG',
      coverage_years: [2014, 2019], coverage_region: 'CONUS',
      experiment: 'bg_ndi_wi', variable_type: 'continuous',
      display_unit: 'index', value_cols: ['wi'],
    },
    zcta5_cbp_food: {
      label: 'Food Retail Density', description: '', boundary: 'ZCTA5',
      coverage_years: [2013, 2020], coverage_region: 'CONUS',
      experiment: 'zcta5_cbp', variable_type: 'continuous',
      display_unit: 'per 1k', value_cols: ['food'],
    },
  },
};

const grouped = groupByBoundary(catalog.variables);
assert.deepEqual(Object.keys(grouped), ['BG', 'ZCTA5']);
assert.equal(grouped.BG.length, 2);
assert.equal(grouped.BG[0][0], 'bg_ndi');
assert.equal(grouped.ZCTA5[0][0], 'zcta5_cbp_food');
assert.equal(grouped.Tract, undefined);

const byExp = groupByExperiment(['zcta5_cbp_food', 'bg_ndi', 'bg_wi'], catalog);
assert.deepEqual(Object.keys(byExp), ['bg_ndi_wi', 'zcta5_cbp']);
assert.deepEqual(byExp.bg_ndi_wi, ['bg_ndi', 'bg_wi']);

assert.deepEqual([...BOUNDARY_ORDER], ['BG', 'ZCTA5', 'Tract', 'County']);
assert.equal(BOUNDARY_LABEL.BG, 'Block Group');

console.log('variable-grouping smoke OK');
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
node scripts/check-variable-grouping.mjs 2>&1 | head -3
```

Expected: tsc errors / script errors with `ERR_MODULE_NOT_FOUND`.

- [ ] **Step 3: Implement the minimal code to pass the test**

Edit `frontend/src/lib/api.ts`. Replace `VarCoverage`:

```typescript
export interface VarCoverage {
  coverage_years: [number, number];
  patients_in_time_window: number;
  patients_in_region: number;
  patients_covered: number;
  coverage_pct: number;
  warnings: string[];
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
  display_unit: string;
}

export interface VariableMetadata {
  label: string;
  description: string;
  boundary: 'BG' | 'ZCTA5' | 'Tract' | 'County';
  coverage_years: [number, number];
  coverage_region: 'CONUS' | 'US' | 'AK_HI';
  experiment: string;
  variable_type: 'categorical' | 'continuous';
  display_unit: string;
  value_cols: string[];
}

export interface VariableCatalog {
  schema_version: number;
  variables: Record<string, VariableMetadata>;
}
```

Modify the existing `export const api = { ... }` object literal in `frontend/src/lib/api.ts` (located after the type exports). The change is two-fold: (1) flip the `saveConfig` body's literal `experiment: "bg_ndi_wi"` to the post-Sprint-3 sentinel `experiment: "auto"` (Risk R10 — backend dispatcher ignores this field but the schema still accepts it); (2) append a new `listVariables` entry just before the closing brace.

Before (current Sprint 2 shape):

```typescript
export const api = {
  // ...auth + tasks above are unchanged...

  saveConfig: (id: string, config: Record<string, unknown>) =>
    request<Task>(`/api/tasks/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ experiment: "bg_ndi_wi", ...config }),
    }),

  startTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/start`, { method: "POST" }),

  // ...stopTask, getCoverage, getStatus, getLogs, downloadResults unchanged...

  downloadResults: (id: string) => `${API_BASE}/api/tasks/${id}/results`,
};
```

After:

```typescript
export const api = {
  // ...auth + tasks above are unchanged...

  saveConfig: (id: string, config: Record<string, unknown>) =>
    request<Task>(`/api/tasks/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ experiment: "auto", ...config }),
    }),

  startTask: (id: string) =>
    request<Task>(`/api/tasks/${id}/start`, { method: "POST" }),

  // ...stopTask, getCoverage, getStatus, getLogs, downloadResults unchanged...

  downloadResults: (id: string) => `${API_BASE}/api/tasks/${id}/results`,

  listVariables: () => request<VariableCatalog>("/api/variables"),
};
```

Create `frontend/src/lib/variable-grouping.ts`:

```typescript
import type { VariableCatalog, VariableMetadata } from './api';

export const BOUNDARY_ORDER = ['BG', 'ZCTA5', 'Tract', 'County'] as const;
export type BoundaryKey = typeof BOUNDARY_ORDER[number];

export const BOUNDARY_LABEL: Record<BoundaryKey, string> = {
  BG: 'Block Group',
  ZCTA5: 'ZIP Code Tabulation Area',
  Tract: 'Census Tract',
  County: 'County',
};

export function groupByBoundary(
  variables: Record<string, VariableMetadata>,
): Partial<Record<BoundaryKey, [string, VariableMetadata][]>> {
  const out: Partial<Record<BoundaryKey, [string, VariableMetadata][]>> = {};
  for (const b of BOUNDARY_ORDER) {
    const entries = Object.entries(variables).filter(([, m]) => m.boundary === b);
    if (entries.length > 0) out[b] = entries;
  }
  return out;
}

export function groupByExperiment(
  selectedKeys: string[],
  catalog: VariableCatalog,
): Record<string, string[]> {
  const selected = new Set(selectedKeys);
  const out: Record<string, string[]> = {};
  for (const [key, meta] of Object.entries(catalog.variables)) {
    if (!selected.has(key)) continue;
    (out[meta.experiment] ??= []).push(key);
  }
  return out;
}
```

Create `frontend/src/lib/use-variable-catalog.ts`:

```typescript
import { useEffect, useState } from 'react';
import { api, type VariableCatalog } from './api';

let cached: VariableCatalog | null = null;
let inflight: Promise<VariableCatalog> | null = null;

function load(): Promise<VariableCatalog> {
  if (cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = api.listVariables().then((c) => {
      cached = c;
      inflight = null;
      return c;
    });
  }
  return inflight;
}

export function useVariableCatalog(): {
  catalog: VariableCatalog | null;
  error: string | null;
} {
  const [catalog, setCatalog] = useState<VariableCatalog | null>(cached);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (catalog) return;
    let cancelled = false;
    load()
      .then((c) => !cancelled && setCatalog(c))
      .catch((e) => !cancelled && setError(String(e)));
    return () => { cancelled = true; };
  }, [catalog]);

  return { catalog, error };
}

export function __resetVariableCatalogCache(): void {
  cached = null;
  inflight = null;
}
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
node_modules/.bin/tsc --outDir .next-check --module nodenext --moduleResolution nodenext --target es2022 --skipLibCheck src/lib/variable-grouping.ts src/lib/api.ts
node scripts/check-variable-grouping.mjs
```

Expected: tsc emits zero errors; `variable-grouping smoke OK` prints.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
cd ../backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: tsc clean; backend pytest baseline unchanged at 129 (no new backend tests in T10).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts \
        frontend/src/lib/variable-grouping.ts \
        frontend/src/lib/use-variable-catalog.ts \
        frontend/scripts/check-variable-grouping.mjs
git commit -m "feat(frontend/lib): api.listVariables + variable-grouping + use-variable-catalog hook"
```

**Notes:**
- The `saveConfig` literal swap to `"auto"` is intentionally minimal — the field stays in the body for one release; Sprint 4 drops it entirely.
- `groupByBoundary` returns a `Partial<...>` — only boundaries with entries appear.
- The module-level cache in `use-variable-catalog.ts` is page-lifetime only — no mtime invalidation yet.
- Depends on T3 (backend `/api/variables` endpoint); consumed by T12, T13.

---

### Task T11: Frontend UI primitives: Chip/Pill, ErrorCard, LoadingCard, SchemaMismatchBanner

**Files:**
- Create: `spacescans-web/frontend/src/components/ui/chip.tsx`
- Create: `spacescans-web/frontend/src/components/wizard/error-card.tsx`
- Create: `spacescans-web/frontend/src/components/wizard/loading-card.tsx`
- Create: `spacescans-web/frontend/src/components/wizard/schema-mismatch-banner.tsx`
- Modify: (none)
- Test: (none — purely presentational; verified by tsc + manual visual check)

**Goal:** Land the four new presentational primitives so downstream tasks (T12 `variable-card.tsx`, T12/T13 wizard step refactors) can import them without circular blockers.

**Context:** The Sprint 3 spec inventories four NEW components. `Chip` is a thin rounded-full badge with `variant: 'default' | 'outline'`; `Pill` is a re-export alias. `ErrorCard` and `LoadingCard` are wrappers around `<Card>` with a `message` prop. `SchemaMismatchBanner` takes `expected` + `actual` numeric props plus an `onRefresh` handler. All follow the existing convention: named function component, `cn()` helper from `@/lib/utils`, shadcn primitives imported from `@/components/ui/*`. No state, no effects, no fetches.

- [ ] **Step 1: Write the failing test(s)**

This task has no unit-test layer. The failing-state check is `tsc --noEmit` against import sites. To exercise the failure deterministically, append a temporary scratch consumer at `frontend/src/components/wizard/__t11_smoke.tsx`:

```tsx
import { Chip, Pill } from "@/components/ui/chip";
import { ErrorCard } from "@/components/wizard/error-card";
import { LoadingCard } from "@/components/wizard/loading-card";
import { SchemaMismatchBanner } from "@/components/wizard/schema-mismatch-banner";

export function __T11Smoke() {
  return (
    <>
      <Chip>2017–2021</Chip>
      <Chip variant="outline">BG</Chip>
      <Pill>NDI</Pill>
      <ErrorCard message="boom" />
      <LoadingCard message="loading…" />
      <SchemaMismatchBanner expected={42} actual={41} onRefresh={() => {}} />
    </>
  );
}
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
npx tsc --noEmit
```

Expected: 4 errors of the form `Cannot find module '@/components/ui/chip'` etc.

- [ ] **Step 3: Implement the minimal code to pass the test**

Create `frontend/src/components/ui/chip.tsx`:

```tsx
import * as React from "react";

import { cn } from "@/lib/utils";

type ChipVariant = "default" | "outline";

interface ChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: ChipVariant;
}

function Chip({ className, variant = "default", ...props }: ChipProps) {
  return (
    <span
      data-slot="chip"
      data-variant={variant}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        variant === "default" && "bg-muted text-muted-foreground",
        variant === "outline" && "border border-border text-foreground",
        className,
      )}
      {...props}
    />
  );
}

const Pill = Chip;

export { Chip, Pill };
export type { ChipProps, ChipVariant };
```

Create `frontend/src/components/wizard/error-card.tsx`:

```tsx
import * as React from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ErrorCardProps {
  message: string;
  title?: string;
  className?: string;
}

function ErrorCard({ message, title = "Something went wrong", className }: ErrorCardProps) {
  return (
    <Card
      data-slot="error-card"
      className={cn("border-destructive/40 bg-destructive/5", className)}
      role="alert"
    >
      <CardHeader>
        <CardTitle className="text-destructive">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-destructive">{message}</CardContent>
    </Card>
  );
}

export { ErrorCard };
export type { ErrorCardProps };
```

Create `frontend/src/components/wizard/loading-card.tsx`:

```tsx
import * as React from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface LoadingCardProps {
  message?: string;
  className?: string;
}

function LoadingCard({ message = "Loading…", className }: LoadingCardProps) {
  return (
    <Card data-slot="loading-card" className={cn("", className)} aria-busy="true">
      <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
        <span
          className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
          aria-hidden="true"
        />
        <span>{message}</span>
      </CardContent>
    </Card>
  );
}

export { LoadingCard };
export type { LoadingCardProps };
```

Create `frontend/src/components/wizard/schema-mismatch-banner.tsx`:

```tsx
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SchemaMismatchBannerProps {
  expected: number;
  actual: number;
  onRefresh: () => void;
  className?: string;
}

function SchemaMismatchBanner({
  expected, actual, onRefresh, className,
}: SchemaMismatchBannerProps) {
  return (
    <Card
      data-slot="schema-mismatch-banner"
      className={cn("border-destructive/40 bg-destructive/5", className)}
      role="alert"
    >
      <CardHeader>
        <CardTitle className="text-destructive">Catalog out of date</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3 text-sm text-destructive">
        <span>
          UI knows schema_version {expected}; server reported {actual}. Please refresh.
        </span>
        <Button variant="outline" size="sm" onClick={onRefresh}>Refresh</Button>
      </CardContent>
    </Card>
  );
}

export { SchemaMismatchBanner };
export type { SchemaMismatchBannerProps };
```

- [ ] **Step 4: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
npx tsc --noEmit
```

Expected: PASS — no errors.

- [ ] **Step 5: Manual visual verification + drop the smoke file**

Mount the four components in a scratch page or import ad-hoc into `frontend/src/app/dashboard/page.tsx` for a moment. Confirm visuals. Then delete the scratch smoke file:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
rm src/components/wizard/__t11_smoke.tsx
npx tsc --noEmit
```

Expected: still PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/chip.tsx \
        frontend/src/components/wizard/error-card.tsx \
        frontend/src/components/wizard/loading-card.tsx \
        frontend/src/components/wizard/schema-mismatch-banner.tsx
git commit -m "feat(ui): chip/pill, error-card, loading-card, schema-mismatch-banner primitives"
```

**Notes:**
- `Pill = Chip` alias — keeping it a separate symbol means future divergence costs one edit.
- `SchemaMismatchBanner` exposes `onRefresh` as a required callback so T12's wiring is forced to be explicit.
- `ErrorCard` and `SchemaMismatchBanner` use `role="alert"`; `LoadingCard` uses `aria-busy="true"`.
- Depends on T10 only for shared types.

---

### Task T12: Frontend: VariableCard extraction + VariablesStep rewrite + VariableCoveragePanel update

**Files:**
- Create: `spacescans-web/frontend/src/components/wizard/variable-card.tsx`
- Modify: `spacescans-web/frontend/src/components/wizard/variables-step.tsx` (full rewrite — replaces the hardcoded `V1_VARIABLES` array and the inline `<label>` block)
- Modify: `spacescans-web/frontend/src/components/wizard/variable-coverage-panel.tsx` (body string at :73-75 — swap `coverage region` for `{boundary} on CONUS`)
- Test: (none — UI changes; verified via manual visual check + tsc)

**Goal:** Replace the hardcoded `V1_VARIABLES` array in `VariablesStep` with a catalog-driven, boundary-grouped UI that mounts a new `VariableCard` per variable and surfaces the registry's `display_unit` / `coverage_years` / `boundary` as chips, while updating `VariableCoveragePanel`'s body string to render the boundary.

**Context:** T10 introduced `useVariableCatalog()`, `groupByBoundary`, `BOUNDARY_ORDER`, `BOUNDARY_LABEL`. T11 introduced `Chip`, `ErrorCard`, `LoadingCard`, `SchemaMismatchBanner`. `api.listVariables()` returns `{schema_version, variables}`. This task wires all of those into the wizard's Step-3 UI.

- [ ] **Step 1: Write the failing test(s)**

No automated test. Write a one-line grep guard for Step 5:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
grep -nE '^const V1_VARIABLES' src/components/wizard/variables-step.tsx
grep -n 'coverage region' src/components/wizard/variable-coverage-panel.tsx
```

- [ ] **Step 2: Run the guards to confirm RED**

Expected: first grep matches `const V1_VARIABLES = [`; second matches `… + coverage region`.

- [ ] **Step 3: Implement the minimal code to pass**

(a) Create `frontend/src/components/wizard/variable-card.tsx`:

```tsx
"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import type { VariableMetadata } from "@/lib/api";
import { VariableCoveragePanel } from "./variable-coverage-panel";

interface VariableCardProps {
  varKey: string;
  meta: VariableMetadata;
  checked: boolean;
  onToggle: () => void;
  taskId: string;
}

export function VariableCard({
  varKey, meta, checked, onToggle, taskId,
}: VariableCardProps) {
  return (
    <label className="flex items-start gap-3 rounded-md border border-border p-3 hover:bg-muted/30 cursor-pointer">
      <Checkbox checked={checked} onCheckedChange={onToggle} className="mt-0.5" />
      <div className="flex-1">
        <div className="font-medium">{meta.label}</div>
        <div className="text-sm text-muted-foreground">{meta.description}</div>
        <div className="flex gap-1 mt-1">
          <Chip>{meta.display_unit}</Chip>
          <Chip>{meta.coverage_years[0]}–{meta.coverage_years[1]}</Chip>
          <Chip variant="outline">{meta.boundary}</Chip>
        </div>
        {checked && (
          <VariableCoveragePanel taskId={taskId} variableKey={varKey} />
        )}
      </div>
    </label>
  );
}
```

(b) Rewrite `frontend/src/components/wizard/variables-step.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import {
  BOUNDARY_ORDER, BOUNDARY_LABEL, groupByBoundary,
} from "@/lib/variable-grouping";
import { ErrorCard } from "./error-card";
import { LoadingCard } from "./loading-card";
import { SchemaMismatchBanner } from "./schema-mismatch-banner";
import { VariableCard } from "./variable-card";

const EXPECTED_VARIABLE_SCHEMA_VERSION = 1;

interface VariablesStepProps {
  taskId: string;
  onComplete: (selectedVariables: string[]) => void;
  onBack: () => void;
  initialSelection?: string[];
}

export function VariablesStep({
  taskId, onComplete, onBack, initialSelection = [],
}: VariablesStepProps) {
  const { catalog, error: loadError } = useVariableCatalog();
  const [selected, setSelected] = useState<string[]>(initialSelection);

  useEffect(() => {
    if (!catalog) return;
    const known = new Set(Object.keys(catalog.variables));
    setSelected((prev) => prev.filter((k) => known.has(k)));
  }, [catalog]);

  const grouped = useMemo(
    () => (catalog ? groupByBoundary(catalog.variables) : null),
    [catalog],
  );

  if (loadError) return <ErrorCard message={loadError} />;
  if (!catalog || !grouped) {
    return <LoadingCard message="Loading variable catalog..." />;
  }
  if (catalog.schema_version !== EXPECTED_VARIABLE_SCHEMA_VERSION) {
    return (
      <SchemaMismatchBanner
        expected={EXPECTED_VARIABLE_SCHEMA_VERSION}
        actual={catalog.schema_version}
        onRefresh={() => window.location.reload()}
      />
    );
  }

  const toggleSelection = (key: string) =>
    setSelected((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );

  const canContinue = selected.length >= 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Select Variables</CardTitle>
        <CardDescription>
          Choose one or more exposures to compute for your cohort. Variables
          are grouped by spatial boundary.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {BOUNDARY_ORDER.map((boundary) => {
          const entries = grouped[boundary];
          if (!entries || entries.length === 0) return null;
          return (
            <section key={boundary} className="space-y-3">
              <h3 className="text-sm font-medium text-muted-foreground">
                {BOUNDARY_LABEL[boundary]}
              </h3>
              <div className="space-y-3">
                {entries.map(([key, meta]) => (
                  <VariableCard
                    key={key}
                    varKey={key}
                    meta={meta}
                    checked={selected.includes(key)}
                    onToggle={() => toggleSelection(key)}
                    taskId={taskId}
                  />
                ))}
              </div>
            </section>
          );
        })}

        <div className="flex justify-between pt-4">
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="size-4" /> Back
          </Button>
          <Button
            onClick={() => onComplete(selected)}
            disabled={!canContinue}
            size="lg"
          >
            Next <ArrowRight className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
```

(c) In `frontend/src/components/wizard/variable-coverage-panel.tsx`, replace the body line:

Old: `{data.coverage_years[1]} + coverage region`
New: `{data.coverage_years[1]} + {data.boundary} on CONUS`

- [ ] **Step 4: Re-run the guards to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
grep -nE '^const V1_VARIABLES' src/components/wizard/variables-step.tsx && echo "STILL HARDCODED" || echo "REMOVED"
grep -n 'coverage region' src/components/wizard/variable-coverage-panel.tsx && echo "OLD STRING PRESENT" || echo "STRING UPDATED"
grep -n '{data.boundary} on CONUS' src/components/wizard/variable-coverage-panel.tsx
```

Expected: first prints `REMOVED`; second prints `STRING UPDATED`; third matches.

- [ ] **Step 5: Typecheck + manual visual check**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
npx tsc --noEmit
npm run dev
```

Open browser, upload demo CSV, advance to Variables step. Confirm:
1. Header reads `Select Variables`.
2. `Block Group` section above NDI + Walkability cards.
3. `ZIP Code Tabulation Area` section above CBP card.
4. Each card shows label, description, three chips.
5. Checking a card mounts coverage panel ending with `+ BG on CONUS` or `+ ZCTA5 on CONUS`.

Backend pytest unchanged (no backend code touched).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/wizard/variable-card.tsx \
        frontend/src/components/wizard/variables-step.tsx \
        frontend/src/components/wizard/variable-coverage-panel.tsx
git commit -m "feat(wizard): catalog-driven VariablesStep with boundary sections + VariableCard"
```

**Notes:**
- `useVariableCatalog` is module-level cached (T10) — navigating Back/Next does NOT re-fetch `/api/variables`.
- `BOUNDARY_ORDER` includes `Tract` and `County` even though Sprint 3 has no entries for them — the `if (!entries...)` guard keeps those sections from rendering as empty placeholders.
- Tone thresholds in `variable-coverage-panel.tsx` (95/60) are intentionally NOT changed; Sprint 4 aligns them with backend's 5% threshold.

---

### Task T13: Frontend: ReviewStep refactor (drop /ontology fetch; group by experiment)

**Files:**
- Create: (none)
- Modify: `spacescans-web/frontend/src/components/wizard/review-step.tsx` (lines 67-81 deletion + Selected Variables SummarySection at lines 172-187)
- Test: (none — manual visual check)

**Goal:** Replace the legacy `/ontology/metadata.json` fetch in `ReviewStep` with the shared `useVariableCatalog()` hook and group the Selected Variables summary by experiment using `groupByExperiment`.

**Context:** `ReviewStep` is the last wizard pane before task launch. It currently fetches a legacy `/ontology/metadata.json` payload on mount just to translate selected variable IDs into human labels via `getLabel(id)`. T12 introduced `useVariableCatalog()` and `groupByExperiment`, both consumed by `VariablesStep`. T13 wires `ReviewStep` onto the same catalog so the wizard no longer makes a second network call and so the "Selected Variables" SummarySection renders one block per experiment.

- [ ] **Step 1: Write the failing test(s)**

No pytest/Jest test here — the verification is structural. Define grep guards on `frontend/src/components/wizard/review-step.tsx` (mirroring T12's pattern) that prove the legacy fetch + label resolution were removed and the new hook + helper were wired. The "test" is the trio of `grep` invocations below; in RED the first two must match and the third must NOT; in GREEN the inverse.

Guards (run these from the worktree root):

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
grep -n "/ontology/metadata.json"   frontend/src/components/wizard/review-step.tsx  # legacy fetch URL
grep -n "getLabel"                  frontend/src/components/wizard/review-step.tsx  # legacy label-resolver
grep -n "useVariableCatalog"        frontend/src/components/wizard/review-step.tsx  # new hook (post-refactor)
```

- [ ] **Step 2: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
grep -n "/ontology/metadata.json"   frontend/src/components/wizard/review-step.tsx && echo "RED guard 1 OK (legacy fetch still present)"
grep -n "getLabel"                  frontend/src/components/wizard/review-step.tsx && echo "RED guard 2 OK (legacy resolver still present)"
grep -n "useVariableCatalog"        frontend/src/components/wizard/review-step.tsx || echo "RED guard 3 OK (new hook not yet wired)"
```

Expected RED:
- guard 1 prints the matching line AND `RED guard 1 OK ...`
- guard 2 prints the matching line AND `RED guard 2 OK ...`
- guard 3 prints `RED guard 3 OK (new hook not yet wired)` (no match)

- [ ] **Step 3: Implement the minimal code to pass the test**

Edit `spacescans-web/frontend/src/components/wizard/review-step.tsx`.

(a) Update imports: remove `useEffect` from `react` (only `useState` is still needed), add hook + helper + pill imports:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Pill } from "@/components/ui/chip";
import { api, ApiError } from "@/lib/api";
import { useVariableCatalog } from "@/lib/use-variable-catalog";
import { groupByExperiment } from "@/lib/variable-grouping";
import { cn } from "@/lib/utils";
import {
  ArrowLeft, ChevronDown, Clock, FileSpreadsheet, Loader2, Play,
  Settings, Shapes, Tags,
} from "lucide-react";
import type { DataSummary } from "./upload-step";
import type { BufferConfig } from "./buffer-step";
```

(b) Delete the legacy fetch + label-resolution block:

```tsx
  const [memoryLimit, setMemoryLimit] = useState("8");
  const [metadata, setMetadata] = useState<...>({});

  useEffect(() => {
    fetch("/ontology/metadata.json")
      .then((r) => r.json())
      .then(setMetadata)
      .catch(() => {});
  }, []);

  const getLabel = (id: string) => {
    const meta = metadata[id];
    return meta ? meta.label.replace(/_/g, " ") : id;
  };
```

Replace with:

```tsx
  const [memoryLimit, setMemoryLimit] = useState("8");
  const { catalog } = useVariableCatalog();
```

(c) Replace the Selected Variables SummarySection body with experiment-grouped output:

```tsx
        <SummarySection
          icon={<Tags className="size-4" />}
          title={`Selected Variables (${selectedVariables.length})`}
        >
          {catalog ? (
            <div className="space-y-3">
              {Object.entries(
                groupByExperiment(selectedVariables, catalog),
              ).map(([expKey, varKeys]) => (
                <div key={expKey}>
                  <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1.5">
                    {expKey}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {varKeys.map((k) => (
                      <Pill key={k}>
                        {catalog.variables[k]?.label ?? k}
                      </Pill>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {selectedVariables.map((id) => (
                <Pill key={id}>{id}</Pill>
              ))}
            </div>
          )}
        </SummarySection>
```

- [ ] **Step 4: Run the test to confirm GREEN**

Re-run the grep guards from Step 1 in the inverse direction:

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
grep -n "/ontology/metadata.json"   frontend/src/components/wizard/review-step.tsx && echo "GREEN guard 1 FAIL (legacy fetch still present)" || echo "GREEN guard 1 OK"
grep -n "getLabel"                  frontend/src/components/wizard/review-step.tsx && echo "GREEN guard 2 FAIL (legacy resolver still present)" || echo "GREEN guard 2 OK"
grep -n "useVariableCatalog"        frontend/src/components/wizard/review-step.tsx && echo "GREEN guard 3 OK (new hook wired)" || echo "GREEN guard 3 FAIL"
cd frontend && npx tsc --noEmit
```

Expected: three `GREEN guard N OK` prints and zero TypeScript errors.

- [ ] **Step 5: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
npx tsc --noEmit
grep -n "ontology/metadata.json\|useEffect\|getLabel" src/components/wizard/review-step.tsx || echo "OK: legacy refs removed"
```

Manual visual check:

```bash
npm run dev
```

Upload demo CSV → buffer → on VariablesStep tick **NDI (BG)** and **CBP density (ZCTA5)** → Next. On Review pane the Selected Variables section must show **two** stacked blocks (`bg_ndi_wi` and `zcta5_cbp`) with corresponding Pill chips. DevTools Network: no request to `/ontology/metadata.json`.

Backend pytest unchanged at 129.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/wizard/review-step.tsx
git commit -m "refactor(review-step): drop /ontology fetch; group selected variables by experiment via useVariableCatalog"
```

**Notes:** Depends on T12 (`useVariableCatalog`, `groupByExperiment`, `Pill`). The `catalog ? ... : ...` fallback is defensive. `estimateRuntime()` untouched (per-experiment refinement deferred). Legacy `/ontology/metadata.json` static asset is left in place; removing it is out of scope.

---

### Task T14: Integration tests: e2e_zcta5_cbp_cohort + e2e_multi_experiment_cohort

**Files:**
- Create: `spacescans-web/backend/tests/fixtures/patients_5.csv` (shared fixture used by both new tests)
- Create: `spacescans-web/backend/tests/test_e2e_zcta5_cbp_cohort.py`
- Create: `spacescans-web/backend/tests/test_e2e_multi_experiment.py`
- Test: both new files plus regression re-run of `test_bg_ndi_wi_integration.py::test_e2e_multi_episode_cohort`

**Goal:** Lock the end-to-end behaviour of Sprint 3's two dispatch paths — single-experiment ZCTA5×CBP and multi-experiment (BG + ZCTA5) fan-out / fan-in — and re-prove that the `_merge.py` extraction did not regress Sprint 2's per-episode join.

**Context:** Sprint 2 wrote `test_bg_ndi_wi_integration.py` as the canonical e2e integration shape: module-level `pytest.mark.skipif` keyed off `_integration_available()` (which checks `SPACESCANS_DATA_DIR`, the pipeline CLI, and `data_full/BG_FL/C3/tiger2010_bg10_states`); a fixture that drops `input.csv` + `config.json` into a `tmp_path` task dir; and `subprocess.run` against `python -m app.experiments.<key> run <task_dir>`. Sprint 3 promotes that into two new files: one driving a single `zcta5_cbp` runner via `task_manager.start_task`, and one driving both `bg_ndi_wi` + `zcta5_cbp` through `task_manager.start_task` so the metadata-ordered sequential dispatch path is exercised end-to-end. The `cbp_zcta5` variable's exposure file is a `.Rda` that requires `pyreadr` (Risk R1).

**Input schema convention (resolves T7 ↔ input.csv divergence):** the canonical task input schema used by `task_manager.create_task` and `csv_to_parquet` is `pid,startDate,endDate,longitude,latitude`. T7's unit test used the abbreviated `long,lat` column names to exercise `csv_to_parquet` directly with a synthetic minimal CSV; that was an in-test convenience and does NOT change the on-disk input.csv contract. Both T14 fixtures (and the production upload path) MUST use the full `longitude,latitude` names. If T7's `csv_to_parquet` does not already accept both spellings, extend it via a one-line rename so the production schema is honoured.

- [ ] **Step 1: Create the shared CSV fixture**

Create `spacescans-web/backend/tests/fixtures/patients_5.csv` (5 rows of Florida demo cohort patients spanning the ZCTA5×CBP exposure file's year coverage — 2017 — and ZCTA5 boundaries present in `data_full/`):

```csv
pid,startDate,endDate,longitude,latitude
p1,2017-01-01,2017-12-31,-82.5158,27.9506
p2,2017-02-15,2017-11-30,-81.3792,28.5383
p3,2017-03-01,2018-02-28,-80.1918,25.7617
p4,2017-06-01,2018-05-31,-84.2807,30.4383
p5,2017-09-15,2018-09-14,-82.4572,27.9659
```

The fixture lives under `backend/tests/fixtures/` so both new tests reference it by `Path(__file__).parent / "fixtures" / "patients_5.csv"`. The directory may not exist yet — create it as part of this step. Commit the fixture in the same commit as the two test files.

- [ ] **Step 2: Write the failing test(s)**

Create `spacescans-web/backend/tests/test_e2e_zcta5_cbp_cohort.py`:

```python
"""Sprint 3 e2e: single-experiment ZCTA5×CBP via task_manager.start_task."""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_R_STAR_COLUMNS = [
    "r_religious", "r_civic", "r_business", "r_political", "r_professional",
    "r_labor", "r_bowling", "r_recreational", "r_golf", "r_sports",
]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_zcta5_cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-zcta5-cbp")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["cbp_zcta5"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_zcta5_cbp_cohort(task_with_zcta5_cohort):
    task_id, task_dir = task_with_zcta5_cohort

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 180.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 180s; last status={status}")

    assert status["status"] == "finished"
    experiments = status.get("experiments", {})
    assert "zcta5_cbp" in experiments
    assert experiments["zcta5_cbp"]["status"] == "finished"

    assert (task_dir / "output" / "result_zcta5_cbp.csv").exists()
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()

    input_df = pd.read_csv(task_dir / "input.csv")
    df = pd.read_csv(result_csv)

    assert len(df) == len(input_df)
    missing = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing, f"missing r_* columns: {missing}"
```

Create `spacescans-web/backend/tests/test_e2e_multi_experiment.py`:

```python
"""Sprint 3 e2e: multi-experiment dispatch (bg_ndi_wi + zcta5_cbp)."""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config


_R_STAR_COLUMNS = [
    "r_religious", "r_civic", "r_business", "r_political", "r_professional",
    "r_labor", "r_bowling", "r_recreational", "r_golf", "r_sports",
]


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    if not (app.config.settings.SPACESCANS_DATA_DIR
            / "data_full/BG_FL/C3/tiger2010_bg10_states").exists():
        return False
    try:
        import pyreadr  # noqa: F401
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / pipeline CLI / pyreadr not configured",
)


@pytest.fixture
def task_with_multi_experiment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_tm)

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-multi-experiment")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": ["ndi", "walkability", "cbp_zcta5"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    })
    return meta["id"], task_dir


@pytest.mark.integration
def test_e2e_multi_experiment_cohort(task_with_multi_experiment):
    task_id, task_dir = task_with_multi_experiment

    from app.task_manager import start_task
    start_task(task_id)

    deadline = time.monotonic() + 240.0
    while time.monotonic() < deadline:
        status = json.loads((task_dir / "status.json").read_text())
        if status.get("status") in ("finished", "error", "partial", "cancelled"):
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"task did not terminate within 240s; last status={status}")

    assert status["status"] == "finished"

    experiments = status.get("experiments", {})
    assert set(experiments.keys()) == {"bg_ndi_wi", "zcta5_cbp"}
    assert experiments["bg_ndi_wi"]["status"] == "finished"
    assert experiments["zcta5_cbp"]["status"] == "finished"

    bg_start = experiments["bg_ndi_wi"]["started_at"]
    zc_start = experiments["zcta5_cbp"]["started_at"]
    assert bg_start <= zc_start, (
        f"expected bg_ndi_wi to start before zcta5_cbp; bg={bg_start} zc={zc_start}"
    )

    assert (task_dir / "output" / "result_bg_ndi_wi.csv").exists()
    assert (task_dir / "output" / "result_zcta5_cbp.csv").exists()
    result_csv = task_dir / "output" / "result.csv"
    assert result_csv.exists()

    df = pd.read_csv(result_csv)

    assert "ndi" in df.columns
    assert "NatWalkInd" in df.columns

    missing = [c for c in _R_STAR_COLUMNS if c not in df.columns]
    assert not missing, f"missing r_* columns after fan_in: {missing}"

    bg_df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    zc_df = pd.read_csv(task_dir / "output" / "result_zcta5_cbp.csv")
    assert len(df) == len(bg_df) == len(zc_df)
```

- [ ] **Step 3: Run the test to confirm RED**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest backend/tests/test_e2e_zcta5_cbp_cohort.py backend/tests/test_e2e_multi_experiment.py -v -m integration
```

Expected on integration host: tests FAIL or ERROR if something in T2-T13 is wired wrong. On a non-integration host: both SKIPPED.

- [ ] **Step 4: Implement the minimal code to pass the test**

No production code changes — T14 is pure test wiring. If a test fails, the failure points at T2/T5/T7/T8/T9; fix there.

Regression check:

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    backend/tests/test_bg_ndi_wi_integration.py::test_e2e_multi_episode_cohort \
    -v -m integration
```

Expected: PASS unchanged (Risk R6).

- [ ] **Step 5: Run the test to confirm GREEN**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest \
    backend/tests/test_e2e_zcta5_cbp_cohort.py \
    backend/tests/test_e2e_multi_experiment.py \
    backend/tests/test_bg_ndi_wi_integration.py::test_e2e_multi_episode_cohort \
    -v -m integration
```

Expected: 3 PASSED on integration host; 3 SKIPPED on non-integration host.

- [ ] **Step 6: Run the full suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 129 passed (Sprint 3 backend baseline carries forward; the 2 new integration tests are skipped/deselected by default).

- [ ] **Step 7: Commit**

```bash
git add backend/tests/fixtures/patients_5.csv \
        backend/tests/test_e2e_zcta5_cbp_cohort.py \
        backend/tests/test_e2e_multi_experiment.py
git commit -m "test(integration): e2e ZCTA5×CBP + multi-experiment dispatch (Sprint 3 T14)"
```

**Notes:**
- Both tests inherit the Sprint 2 skip-gate pattern plus a `pyreadr` probe.
- These tests drive `task_manager.start_task` (the dispatcher), not the runner module directly.
- `experiment: "auto"` is the post-Sprint-3 sentinel (Risk R10).
- Do NOT edit `test_bg_ndi_wi_integration.py`. The regression re-run is by invocation, not modification.

---

### Task T15: Manual e2e Sprint 3 section + final verification + PR-ready cleanup

**Files:**
- Modify: `spacescans-web/backend/tests/manual_e2e.md` (append Sprint 3 section)

**Goal:** Append the Sprint 3 walk-through to `backend/tests/manual_e2e.md`, run the full backend pytest + frontend tsc/lint as the green-light gate, confirm no legacy `backend/data/variable_metadata.json` remains, and emit the Sprint 3 wrap-up note.

**Context:** This is the final Sprint 3 task — by the time it runs, T1-T14 have already landed registry + schema + `/api/variables`, `_merge.py` extraction, `zcta5_cbp` runner, the dispatcher multi-experiment loop, and the frontend variables-step refactor. `backend/tests/manual_e2e.md` currently ends with the Sprint 2 multi-episode walk-through. Sprint 1's legacy metadata file was moved (git mv) to `backend/app/data/variable_metadata.json` in T1; the `.gitignore` entry was removed in the same commit. All Sprint 3 work lives on branch `feat/sprint-3-variables-driven-ui-zcta5-cbp`.

- [ ] **Step 1: Run the full backend pytest suite (green-light gate)**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: 129 passed (Sprint 2 baseline 75 + T1's 9 + T2's 9 + T3's 4 + T4's 4 + T5's 7 + T6's 2 + T7's 7 + T8's 6 + T9's 6), plus the usual skipped/deselected counts.

- [ ] **Step 2: Run integration tests (opt-in)**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v
```

Expected: 8/8 pass (5 Sprint 1 + 1 Sprint 2 multi-episode + 1 Sprint 3 ZCTA5×CBP + 1 Sprint 3 multi-experiment). Wall-clock ≈ 3-4 min.

- [ ] **Step 3: Frontend typecheck + lint**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
node_modules/.bin/next lint
```

Expected: zero TypeScript errors; zero ESLint errors.

- [ ] **Step 4: Confirm no legacy variable_metadata.json remains**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
test ! -f backend/data/variable_metadata.json && echo "OK: legacy path absent"
test -f backend/app/data/variable_metadata.json && echo "OK: new path present"
grep -n "variable_metadata.json" backend/.gitignore && echo "FAIL: stale .gitignore entry" || echo "OK: .gitignore clean"
```

Expected: three `OK:` prints.

- [ ] **Step 5: Append Sprint 3 section to `backend/tests/manual_e2e.md`**

Append the following block to the end of `backend/tests/manual_e2e.md`:

```markdown
## Sprint 3 — Variables-driven UI + ZCTA5×CBP

Pre-flight:
- `backend/app/data/variable_metadata.json` exists with `schema_version: 1` and 3 entries (`ndi`, `walkability`, `cbp_zcta5`).
- `backend/app/data/variable_metadata.schema.json` exists.
- `pyreadr` is importable in the spacescans env (Sprint 3 Risk R1).
- The ZCTA5 buffer parquet exists at `output/python_v2/270m/ZCTA5_US/C3/buffer270mZCTA525m_demo100k.parquet` (Sprint 3 Risk R2).
- The pipeline config exists at `spacescans-pipeline/configs/c4/zcta5_cbp_demo.yaml`.
- Legacy `backend/data/variable_metadata.json` does NOT exist.

Walk-through:

1. **3-card variables-step render.** Reach the Variables step. Confirm 3 cards rendered, grouped by boundary:
   - "Block Group" section: NDI, EPA Walkability Index.
   - "ZIP Code Tabulation Area" section: Community Organization Density (ZBP).
   Each card shows: label, description, unit chip, year-range chip, boundary chip.

2. **Coverage panel mount.** Tick any single card. The coverage panel mounts inline and issues `GET /api/tasks/<id>/coverage?variables=<key>`. The response now includes the `boundary` chip.

3. **schema_version=2 mismatch banner.** Temporarily edit `backend/app/data/variable_metadata.json` and set `"schema_version": 2`. Refresh the wizard. Expected: top-of-step banner reads "Catalog out of date" with a Refresh button; the cards do NOT render. Revert the file.

4. **Multi-experiment run with `experiments` map progression.** Tick all 3 cards → Review → Run. On the task page, poll `/api/tasks/<id>/status`:
   - First snapshot: `status.experiments == {"bg_ndi_wi": "running", "zcta5_cbp": "pending"}`.
   - Mid-run snapshot: `status.experiments == {"bg_ndi_wi": "finished", "zcta5_cbp": "running"}`.
   - Final snapshot: both `"finished"`; `status.status == "finished"`.

5. **result.csv column set.** Download `result.csv`. Required columns:
   - Keys: `pid`, `episode_id`.
   - BG: `ndi`, `NatWalkInd`.
   - ZCTA5: `r_religious`, `r_civic`, `r_business`, `r_political`, `r_professional`, `r_labor`, `r_bowling`, `r_recreational`, `r_golf`, `r_sports`.
   Row count equals the BG row count from Sprint 2; ZCTA5 columns left-join cleanly.

To force a fresh run after Sprint 3 deployment (cache keys changed):

    rm -rf backend/data/c3_cache/
```

- [ ] **Step 6: Commit the manual_e2e append**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3
git add backend/tests/manual_e2e.md
git commit -m "docs(tests): manual_e2e Sprint 3 variables-driven UI + multi-experiment walk-through"
```

- [ ] **Step 7: Sprint 3 branch summary**

```bash
git log --oneline main..HEAD
git diff --stat main..HEAD | tail -3
```

Expected: ~15 commits on `feat/sprint-3-variables-driven-ui-zcta5-cbp` (T0..T15).

- [ ] **Step 8: Hand off to finishing-a-development-branch**

The Sprint 3 implementation is complete. Decide merge / PR / keep / discard via:

```
Use the superpowers:finishing-a-development-branch skill.
```

Report: status / final test counts (129 default + 8 integration + tsc zero / lint zero) / commit SHAs / any concerns / readiness for merge into `main`.

**Notes:** Docs + verification only — no production code changes. Steps 1-4 are the green-light gate; if Step 1 or Step 3 fails, stop and route the failure back to the owning task (T1-T14) rather than papering over it here. Step 4's `.gitignore` check guards against the Sprint 1 → Sprint 3 file-move regression.

---

## Final verification

Run from `spacescans-web/.worktrees/feat-sprint-3/` after Task T15 commits:

### Backend
```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```
Expected: **129 passed**, 1 skipped, 8 deselected.

### Integration suite (opt-in)
```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v
```
Expected: **8/8 passed** (5 Sprint 1 + 1 Sprint 2 + 2 new Sprint 3).

### Frontend typecheck + lint
```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/.worktrees/feat-sprint-3/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
node_modules/.bin/next lint
```
Expected: zero errors from both.

### Manual e2e walkthrough checkpoint
Run through `backend/tests/manual_e2e.md` — the Sprint 1 + Sprint 2 + Sprint 3 sections in sequence. Confirm:
- 3-card variables-step render with BG / ZCTA5 sections
- Coverage panel mounts with `+ BG on CONUS` / `+ ZCTA5 on CONUS`
- schema_version=2 → mismatch banner (revert after)
- Multi-experiment run finishes with both experiments `finished` in `status.experiments`
- `result.csv` carries `ndi` + `NatWalkInd` + 10 `r_*` columns, one row per `(pid, episode_id)`

### Decide branch finish
Once the above checkpoints are all green, invoke:

```
Use the superpowers:finishing-a-development-branch skill.
```

The skill will guide the user through merge vs. PR vs. cleanup decisions and ensure the Sprint 3 work lands cleanly on `main`.
