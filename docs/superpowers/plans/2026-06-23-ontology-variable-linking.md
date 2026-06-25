# Ontology ↔ Variable Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link all 9 exposure variables to SPACESCANS ontology nodes via an optional `ontology_id`, adding 5 new "SPACESCANS-local extension" nodes for the concepts the ontology currently lacks.

**Architecture:** Add an optional `ontology_id` string to each variable in `variable_metadata.json` (schema + pydantic model + TS type, no `schema_version` bump). 4 variables point at existing ontology node ids; 5 point at new nodes injected into the generated `frontend/public/ontology/*.json` by a new idempotent `extend_ontology.py` (the OWL source is unavailable, so we patch the generated artifacts directly). Proximity nodes are placed by environmental domain.

**Tech Stack:** Python 3.12 (conda env `/Users/xai/miniconda3/envs/spacescans`), pytest, jsonschema, FastAPI/pydantic v2; Next.js/TypeScript frontend. All paths below are relative to `/Users/xai/Desktop/spacescans-project/spacescans-web`.

**Run tests with:** `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q`
**Typecheck frontend with:** `cd frontend && PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" node_modules/.bin/tsc --noEmit`

---

### Task 1: Optional `ontology_id` field plumbing (schema + model + TS type)

**Files:**
- Modify: `backend/app/data/variable_metadata.schema.json`
- Modify: `backend/app/routers/variables.py`
- Modify: `frontend/src/lib/api.ts`
- Test: `backend/tests/test_variable_registry.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_variable_registry.py`:

```python
def test_schema_allows_optional_ontology_id():
    """The variable_metadata schema must accept an optional ontology_id and
    still validate when it is absent (additionalProperties is false, so this
    fails until ontology_id is declared in the schema)."""
    import json
    import pathlib

    import jsonschema

    schema = json.loads(
        pathlib.Path("app/data/variable_metadata.schema.json").read_text()
    )
    base_var = {
        "label": "L", "description": "D", "boundary": "BG",
        "coverage_years": [2010, 2020], "coverage_region": "CONUS",
        "experiment": "e", "variable_type": "continuous",
        "display_unit": "u", "value_cols": ["v"],
    }
    with_id = {"schema_version": 1,
               "variables": {"x": {**base_var, "ontology_id": "000289"}}}
    without_id = {"schema_version": 1, "variables": {"x": dict(base_var)}}
    jsonschema.validate(with_id, schema)      # must not raise
    jsonschema.validate(without_id, schema)   # must not raise


def test_variable_metadata_model_accepts_optional_ontology_id():
    from app.routers.variables import VariableMetadataModel

    common = dict(
        label="L", description="D", boundary="BG",
        coverage_years=(2010, 2020), coverage_region="CONUS",
        experiment="e", variable_type="continuous",
        display_unit="u", value_cols=["v"],
    )
    assert VariableMetadataModel(**common, ontology_id="000289").ontology_id == "000289"
    assert VariableMetadataModel(**common).ontology_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py::test_schema_allows_optional_ontology_id tests/test_variable_registry.py::test_variable_metadata_model_accepts_optional_ontology_id -q`
Expected: FAIL — schema rejects `ontology_id` (`additionalProperties` false) and `VariableMetadataModel` has no `ontology_id` field.

- [ ] **Step 3: Add `ontology_id` to the JSON schema**

In `backend/app/data/variable_metadata.schema.json`, inside the per-variable `properties` object (the block that already lists `experiment`, `variable_type`, etc.), add this property. Do NOT add it to the `required` array; do NOT change `schema_version`.

```json
"ontology_id": {"type": "string", "minLength": 1},
```

(Place it next to `experiment` for readability — e.g. immediately after the `experiment` property block.)

- [ ] **Step 4: Add `ontology_id` to the pydantic model**

In `backend/app/routers/variables.py`, in `class VariableMetadataModel`, add the field after `experiment: str` (mirror the existing optional pattern used by `temporal`):

```python
    ontology_id: str | None = None
```

- [ ] **Step 5: Add `ontology_id` to the TS interface**

In `frontend/src/lib/api.ts`, in `interface VariableMetadata`, add after the `experiment: string;` line:

```typescript
  /** Linked SPACESCANS ontology node id (see frontend/public/ontology). */
  ontology_id?: string;
```

- [ ] **Step 6: Run tests + typecheck to verify they pass**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -q`
Expected: PASS (new tests green, existing registry tests unaffected).
Run: `cd frontend && PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" node_modules/.bin/tsc --noEmit`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add backend/app/data/variable_metadata.schema.json backend/app/routers/variables.py frontend/src/lib/api.ts backend/tests/test_variable_registry.py
git commit -m "feat(variables): optional ontology_id field (schema + model + type)"
```

---

### Task 2: Idempotent `extend_ontology.py` script + test

**Files:**
- Create: `backend/scripts/extend_ontology.py`
- Test: `backend/tests/test_extend_ontology.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_extend_ontology.py`:

```python
"""Tests for the idempotent ontology extension script."""
import json
from pathlib import Path

import pytest


def _seed(base: Path):
    """Minimal generated-ontology fixture with the 3 parent nodes the
    extension targets. Social (000295) starts as a LEAF (no nodes file)."""
    (base / "nodes").mkdir(parents=True)
    (base / "metadata.json").write_text(json.dumps({
        "000093_2": {"id": "000093_2", "label": "Spatial_and_Contextual_Exposome", "definition": ""},
        "000292": {"id": "000292", "label": "Built_Environment_Exposome", "definition": ""},
        "000094_2": {"id": "000094_2", "label": "Natural_Environment_Exposome", "definition": ""},
        "000295": {"id": "000295", "label": "Social_Environment_Exposome", "definition": ""},
    }))
    (base / "search-index.json").write_text(json.dumps([
        {"id": "000295", "label": "Social_Environment_Exposome", "definition": ""},
    ]))
    (base / "index.json").write_text(json.dumps([]))
    # Exposome root's children: Built/Natural/Social — Social has_children False.
    (base / "nodes" / "000093_2.json").write_text(json.dumps([
        {"id": "000292", "label": "Built_Environment_Exposome", "definition": "", "has_children": True},
        {"id": "000094_2", "label": "Natural_Environment_Exposome", "definition": "", "has_children": True},
        {"id": "000295", "label": "Social_Environment_Exposome", "definition": "", "has_children": False},
    ]))
    (base / "nodes" / "000292.json").write_text(json.dumps([
        {"id": "000294", "label": "Food_Access_Exposome", "definition": "", "has_children": False},
    ]))
    (base / "nodes" / "000094_2.json").write_text(json.dumps([
        {"id": "000289", "label": "Noise", "definition": "", "has_children": False},
    ]))


def test_extend_adds_five_nodes_and_flips_social(tmp_path):
    from scripts.extend_ontology import extend_ontology, NEW_NODES, EXTENSION_MARKER

    _seed(tmp_path)
    extend_ontology(tmp_path)

    meta = json.loads((tmp_path / "metadata.json").read_text())
    search_ids = {it["id"] for it in json.loads((tmp_path / "search-index.json").read_text())}
    for node in NEW_NODES:
        assert node["id"] in meta, node["id"]
        assert meta[node["id"]]["definition"].endswith(EXTENSION_MARKER)
        assert node["id"] in search_ids

    # Social leaf became a parent file with its 2 children.
    social = json.loads((tmp_path / "nodes" / "000295.json").read_text())
    social_ids = {c["id"] for c in social}
    assert social_ids == {
        "SPACESCANS_Neighborhood_Deprivation_Index",
        "SPACESCANS_Community_Organization_Density",
    }
    # Built gained Walkability + Road_Proximity (kept Food_Access).
    built_ids = {c["id"] for c in json.loads((tmp_path / "nodes" / "000292.json").read_text())}
    assert {"SPACESCANS_Walkability", "SPACESCANS_Road_Proximity", "000294"} <= built_ids
    # Natural gained Bluespace (kept Noise).
    nat_ids = {c["id"] for c in json.loads((tmp_path / "nodes" / "000094_2.json").read_text())}
    assert {"SPACESCANS_Bluespace", "000289"} <= nat_ids
    # Social's has_children flipped True in the exposome root's child list.
    root = json.loads((tmp_path / "nodes" / "000093_2.json").read_text())
    social_entry = next(c for c in root if c["id"] == "000295")
    assert social_entry["has_children"] is True


def test_extend_is_idempotent(tmp_path):
    from scripts.extend_ontology import extend_ontology

    _seed(tmp_path)
    extend_ontology(tmp_path)
    first = {p.name: p.read_text() for p in (tmp_path / "nodes").glob("*.json")}
    first["metadata"] = (tmp_path / "metadata.json").read_text()
    first["search"] = (tmp_path / "search-index.json").read_text()

    extend_ontology(tmp_path)  # run again
    # No duplicate children anywhere.
    for f in (tmp_path / "nodes").glob("*.json"):
        ids = [c["id"] for c in json.loads(f.read_text())]
        assert len(ids) == len(set(ids)), f"dupes in {f.name}: {ids}"
    # Byte-identical to first run.
    assert (tmp_path / "metadata.json").read_text() == first["metadata"]
    assert (tmp_path / "search-index.json").read_text() == first["search"]


def test_child_lists_sorted_by_label(tmp_path):
    from scripts.extend_ontology import extend_ontology

    _seed(tmp_path)
    extend_ontology(tmp_path)
    for f in (tmp_path / "nodes").glob("*.json"):
        labels = [c["label"] for c in json.loads(f.read_text())]
        assert labels == sorted(labels), f"{f.name} not sorted: {labels}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_extend_ontology.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.extend_ontology'` (or ImportError).

- [ ] **Step 3: Implement the script**

Create `backend/scripts/extend_ontology.py`:

```python
"""Idempotently inject SPACESCANS-local extension nodes into the GENERATED
ontology JSON (frontend/public/ontology).

WHY this patches generated artifacts instead of the OWL source: the canonical
source `ontology files/SPACEO_20251203.owl` is not present in the repo, so we
cannot regenerate. These 5 concepts are missing from SPACEO and are added here
as clearly-marked local extensions, pending merge into the authoritative
ontology.

IMPORTANT: if `build_ontology.py` is ever re-run from an OWL source, it will
OVERWRITE these nodes. You MUST re-run this script afterwards.
"""
import argparse
import json
from pathlib import Path

EXTENSION_MARKER = " [SPACESCANS-local extension — pending merge into SPACEO]"

# parent ids: 000292 Built_Environment_Exposome, 000094_2 Natural_Environment_
# Exposome, 000295 Social_Environment_Exposome (currently a leaf).
NEW_NODES = [
    {"id": "SPACESCANS_Walkability", "label": "Walkability", "parent": "000292",
     "definition": "EPA National Walkability Index ranking neighborhoods on "
                   "walkability characteristics such as intersection density, "
                   "transit proximity, and employment mix."},
    {"id": "SPACESCANS_Neighborhood_Deprivation_Index",
     "label": "Neighborhood_Deprivation_Index", "parent": "000295",
     "definition": "Composite measure of neighborhood-level socioeconomic "
                   "deprivation derived from US Census ACS variables."},
    {"id": "SPACESCANS_Community_Organization_Density",
     "label": "Community_Organization_Density", "parent": "000295",
     "definition": "Per-capita density of community organization categories "
                   "(religious, civic, business, etc.) from US Census ZIP "
                   "Business Patterns."},
    {"id": "SPACESCANS_Road_Proximity", "label": "Road_Proximity", "parent": "000292",
     "definition": "Distance from a residence to the nearest TIGER/Line "
                   "primary, secondary, and combined primary+secondary roads."},
    {"id": "SPACESCANS_Bluespace", "label": "Bluespace", "parent": "000094_2",
     "definition": "Distance from a residence to the nearest NHD surface-water "
                   "feature (flowline, waterbody, area feature, coastline, and "
                   "combined blue feature)."},
]

# Parent whose has_children must flip True once it gains children, keyed by the
# child-list file in which that parent appears as an entry.
_LEAF_PARENT_TO_FLIP = ("000295", "000093_2.json")


def _load(p: Path):
    return json.loads(p.read_text())


def _dump(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=2))


def extend_ontology(ontology_dir) -> dict:
    base = Path(ontology_dir)
    nodes_dir = base / "nodes"
    metadata = _load(base / "metadata.json")
    search = _load(base / "search-index.json")
    search_ids = {it["id"] for it in search}

    added = 0
    for node in NEW_NODES:
        nid, label, parent = node["id"], node["label"], node["parent"]
        definition = node["definition"] + EXTENSION_MARKER

        metadata[nid] = {"id": nid, "label": label, "definition": definition}

        if nid not in search_ids:
            search.append({"id": nid, "label": label, "definition": definition})
            search_ids.add(nid)

        parent_file = nodes_dir / f"{parent}.json"
        children = _load(parent_file) if parent_file.exists() else []
        existing = next((c for c in children if c["id"] == nid), None)
        if existing is None:
            children.append({"id": nid, "label": label,
                             "definition": definition, "has_children": False})
            added += 1
        else:  # refresh in place (keeps idempotency on label/definition tweaks)
            existing.update({"label": label, "definition": definition,
                             "has_children": False})
        children.sort(key=lambda x: x["label"])
        _dump(parent_file, children)

    # Flip has_children on the former-leaf parent where it appears as a child.
    leaf_id, in_file = _LEAF_PARENT_TO_FLIP
    container = nodes_dir / in_file
    if container.exists():
        items = _load(container)
        for c in items:
            if c["id"] == leaf_id:
                c["has_children"] = True
        _dump(container, items)

    _dump(base / "metadata.json", metadata)
    _dump(base / "search-index.json", search)
    return {"added": added, "total": len(NEW_NODES)}


if __name__ == "__main__":
    default_dir = Path(__file__).resolve().parents[2] / "frontend" / "public" / "ontology"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology-dir", default=str(default_dir))
    args = parser.parse_args()
    result = extend_ontology(args.ontology_dir)
    print(f"extend_ontology: {result['added']} added / {result['total']} total "
          f"-> {args.ontology_dir}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_extend_ontology.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/extend_ontology.py backend/tests/test_extend_ontology.py
git commit -m "feat(ontology): idempotent extend_ontology.py for 5 SPACESCANS nodes"
```

---

### Task 3: Run the script against the real ontology + commit generated JSON

**Files:**
- Modify (via script): `frontend/public/ontology/metadata.json`, `frontend/public/ontology/search-index.json`, `frontend/public/ontology/nodes/000093_2.json`, `frontend/public/ontology/nodes/000292.json`, `frontend/public/ontology/nodes/000094_2.json`
- Create (via script): `frontend/public/ontology/nodes/000295.json`

- [ ] **Step 1: Run the extension script against the real ontology**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python scripts/extend_ontology.py`
Expected output: `extend_ontology: 5 added / 5 total -> .../frontend/public/ontology`

- [ ] **Step 2: Verify the real ontology now contains the 5 nodes correctly**

Run:
```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend/public/ontology && /Users/xai/miniconda3/envs/spacescans/bin/python -c "
import json
si = {it['id'] for it in json.load(open('search-index.json'))}
md = json.load(open('metadata.json'))
for nid in ['SPACESCANS_Walkability','SPACESCANS_Neighborhood_Deprivation_Index','SPACESCANS_Community_Organization_Density','SPACESCANS_Road_Proximity','SPACESCANS_Bluespace']:
    assert nid in si and nid in md, nid
soc = {c['id'] for c in json.load(open('nodes/000295.json'))}
assert len(soc)==2, soc
root = json.load(open('nodes/000093_2.json'))
assert next(c for c in root if c['id']=='000295')['has_children'] is True
print('OK: 5 nodes present, Social has_children flipped')
"
```
Expected: `OK: 5 nodes present, Social has_children flipped`

- [ ] **Step 3: Re-run script to confirm idempotency on real data (git diff should be clean)**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python scripts/extend_ontology.py && cd .. && git diff --stat frontend/public/ontology`
Expected: the second run produces NO further changes beyond step 1 (re-running does not grow the diff; `git diff` after the first run already captured everything, the second run is a no-op).

- [ ] **Step 4: Commit the generated ontology changes**

```bash
git add frontend/public/ontology
git commit -m "feat(ontology): inject 5 SPACESCANS extension nodes into catalog JSON"
```

---

### Task 4: Populate the 9 `ontology_id` values + link-completeness test

**Files:**
- Modify: `backend/app/data/variable_metadata.json`
- Test: `backend/tests/test_variable_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_variable_registry.py`:

```python
def test_every_variable_links_to_an_existing_ontology_node():
    """All 9 variables must carry an ontology_id, and every id must resolve to
    a node in the generated ontology metadata (link integrity)."""
    import json
    import pathlib

    meta = json.loads(
        pathlib.Path("app/data/variable_metadata.json").read_text()
    )["variables"]
    onto = json.loads(
        pathlib.Path("../frontend/public/ontology/metadata.json").read_text()
    )

    expected = {
        "noise": "000289",
        "vnl": "000290",
        "temis": "000288",
        "fara_tract": "000294",
        "walkability": "SPACESCANS_Walkability",
        "ndi": "SPACESCANS_Neighborhood_Deprivation_Index",
        "cbp_zcta5": "SPACESCANS_Community_Organization_Density",
        "tiger_proximity": "SPACESCANS_Road_Proximity",
        "nhd_bluespace": "SPACESCANS_Bluespace",
    }
    for var, want_id in expected.items():
        assert var in meta, f"missing variable {var}"
        assert meta[var].get("ontology_id") == want_id, var
        assert want_id in onto, f"{var} -> {want_id} not in ontology metadata"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py::test_every_variable_links_to_an_existing_ontology_node -q`
Expected: FAIL — no variable has `ontology_id` yet.

- [ ] **Step 3: Add `ontology_id` to each variable**

In `backend/app/data/variable_metadata.json`, for each of the 9 variable objects add an `"ontology_id"` line immediately after that variable's `"experiment": ...,` line, using this mapping:

| variable | ontology_id |
| --- | --- |
| `ndi` | `SPACESCANS_Neighborhood_Deprivation_Index` |
| `walkability` | `SPACESCANS_Walkability` |
| `cbp_zcta5` | `SPACESCANS_Community_Organization_Density` |
| `tiger_proximity` | `SPACESCANS_Road_Proximity` |
| `nhd_bluespace` | `SPACESCANS_Bluespace` |
| `noise` | `000289` |
| `vnl` | `000290` |
| `temis` | `000288` |
| `fara_tract` | `000294` |

Example (the `noise` entry — apply the same single-line insertion to all 9):

```json
      "experiment": "noise",
      "ontology_id": "000289",
      "temporal": "static",
```

- [ ] **Step 4: Run the test + schema validation to verify they pass**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_variable_registry.py -q`
Expected: PASS (link-integrity test green; schema validates the real file because `ontology_id` was made an allowed property in Task 1).

- [ ] **Step 5: Commit**

```bash
git add backend/app/data/variable_metadata.json backend/tests/test_variable_registry.py
git commit -m "feat(variables): link all 9 variables to ontology nodes via ontology_id"
```

---

### Task 5: Document the rebuild hazard + final full verification

**Files:**
- Modify: `backend/scripts/build_ontology.py`

- [ ] **Step 1: Add the rebuild-hazard note to build_ontology.py**

In `backend/scripts/build_ontology.py`, replace the module docstring (line 1) with one that warns about the extension step:

```python
"""Parse OWL file and output split JSON files for the frontend ontology browser.

NOTE: after regenerating from an OWL source, the SPACESCANS-local extension
nodes are wiped. Re-run `python scripts/extend_ontology.py` immediately after
this script to re-inject them (see extend_ontology.py).
"""
```

- [ ] **Step 2: Run the full backend test suite**

Run: `cd backend && /Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q`
Expected: all pass (previous count + the 4 new tests from Tasks 1, 2, 4), 0 failures.

- [ ] **Step 3: Typecheck the frontend**

Run: `cd frontend && PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH" node_modules/.bin/tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/build_ontology.py
git commit -m "docs(ontology): note extend_ontology must re-run after OWL rebuild"
```

---

## Notes for the implementer

- The `scripts.extend_ontology` import in the test works because `backend/` is the pytest rootdir (other tests already import `from scripts.build_ontology import ...`). Run pytest from `backend/`.
- Do NOT bump `schema_version` — `ontology_id` is purely additive and optional; bumping it would trip the frontend `SchemaMismatchBanner`.
- Do NOT run `npm run build` (it can corrupt `.next` while the dev server is running). Verify the frontend with `tsc --noEmit` only.
- Phase 2 (a "View in ontology" deep-link on the variable card → `/catalog?node=<id>`) is intentionally out of scope here.
