# Sprint 1: Pre-flight Coverage Check + C3 Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two independent improvements to spacescans-web v1: (a) per-variable cohort-coverage statistics surfaced in the Variables wizard step before the user starts a 4-7 min run, and (b) a server-side cache for C3 boundary-overlap weight tables so repeat tasks on the same cohort + buffer skip recomputation.

**Architecture:** Phase A (#2 pre-flight) lands a `variable_metadata.json` catalog + `/api/tasks/{id}/coverage` endpoint + a frontend `VariableCoveragePanel` rendered inline beneath each checked variable. Phase B (#5 cache) layers SHA256-keyed `c3_cache/` lookup into `bg_ndi_wi.run()` — hit copies a cached parquet, miss runs the pipeline and writes back. The two phases share no files and can be implemented in either order.

**Tech Stack:** FastAPI · pandas · pyarrow · Next.js 14 · shadcn/ui · subprocess + sha256 (stdlib) · pytest.

---

## Pre-implementation: confirm environment

The implementer must verify these once before starting:

```bash
test -d /Users/xai/Desktop/spacescans-project/spacescans-web
test -x /Users/xai/miniconda3/envs/spacescans/bin/python
test -d /Users/xai/Desktop/spacescans-project/data_full
test -f /Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env && grep -q SPACESCANS_DATA_DIR /Users/xai/Desktop/spacescans-project/spacescans-web/backend/.env
# Frontend node:
test -x /Users/xai/.nvm/versions/node/v20.20.2/bin/node
```

If anything fails, STOP and ask the controller to fix the environment first.

Conventions used throughout the plan:

- All `cd` commands assume the spacescans-web worktree root unless noted.
- Python: `/Users/xai/miniconda3/envs/spacescans/bin/python` (alias `PY`).
- Frontend tsc: `node_modules/.bin/tsc --noEmit` from `frontend/` with `~/.nvm/versions/node/v20.20.2/bin` on PATH.
- TDD discipline: write the failing test first, run it to confirm RED, implement, run it to confirm GREEN, commit.

---

## File Structure

### Phase A — #2 Pre-flight

New:
- `backend/data/variable_metadata.json` — variable catalog (NOT tracked; created on first deploy)
- `backend/tests/test_coverage.py` — unit tests for the coverage endpoint and helper
- `frontend/src/components/wizard/variable-coverage-panel.tsx` — inline coverage display

Modified:
- `backend/app/task_manager.py` — add `compute_coverage()` + `_load_variable_metadata()`
- `backend/app/routers/tasks.py` — add `GET /{task_id}/coverage`
- `backend/.gitignore` — add `data/variable_metadata.json` (it's environment data, not code)
- `frontend/src/lib/api.ts` — add `getCoverage` method
- `frontend/src/components/wizard/variables-step.tsx` — render `VariableCoveragePanel` per checked variable

### Phase B — #5 C3 cache

New:
- `backend/data/c3_cache/` — directory (created lazily on first miss)

Modified:
- `backend/app/config.py` — add `C3_CACHE_DIR` setting
- `backend/app/experiments/bg_ndi_wi.py` — add `_hash_input_parquet`, `_cache_key`, `_is_valid_cached_parquet`; wire cache check/write into `run()`
- `backend/.gitignore` — add `data/c3_cache/`
- `backend/tests/test_bg_ndi_wi.py` — append cache unit tests
- `backend/tests/test_bg_ndi_wi_integration.py` — append `test_e2e_cache_second_run_faster`

---

## Task 1: variable_metadata.json catalog + loader helper

**Files:**
- Create: `backend/data/variable_metadata.json`
- Modify: `backend/app/task_manager.py` (add `_load_variable_metadata`)
- Modify: `backend/.gitignore`
- Test: `backend/tests/test_coverage.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_coverage.py`:

```python
import importlib
import json
from pathlib import Path
import pytest


def test_load_variable_metadata_reads_ndi_and_walkability(monkeypatch, tmp_path):
    """The loader returns the canonical 2-entry catalog for Sprint 1."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {
            "label": "Neighborhood Deprivation Index",
            "boundary": "BG",
            "coverage_years": [2012, 2022],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
        "walkability": {
            "label": "EPA Walkability Index",
            "boundary": "BG",
            "coverage_years": [2016, 2021],
            "coverage_region": "CONUS",
            "experiment": "bg_ndi_wi",
        },
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    meta = app.task_manager._load_variable_metadata()
    assert "ndi" in meta
    assert meta["ndi"]["coverage_years"] == [2012, 2022]
    assert meta["walkability"]["coverage_years"] == [2016, 2021]


def test_load_variable_metadata_caches_until_mtime_changes(monkeypatch, tmp_path):
    """Loader uses mtime-based cache invalidation."""
    data_dir = tmp_path
    (data_dir / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"coverage_years": [2012, 2022], "coverage_region": "CONUS", "label": "X", "boundary": "BG", "experiment": "bg_ndi_wi"},
    }))
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("DB_PATH", str(data_dir / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(data_dir / "tasks"))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    first = app.task_manager._load_variable_metadata()
    second = app.task_manager._load_variable_metadata()
    assert first is second  # same object — cached
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v
```

Expected: 2 tests FAIL with `AttributeError: module 'app.task_manager' has no attribute '_load_variable_metadata'`.

- [ ] **Step 3: Implement the loader**

Add to `backend/app/task_manager.py` (top-level, before existing functions; just under the existing `import` block):

```python
# Module-level cache for variable_metadata.json (mtime-invalidated).
_VARIABLE_METADATA_CACHE: dict | None = None
_VARIABLE_METADATA_MTIME: float | None = None


def _load_variable_metadata() -> dict:
    """Read and cache backend/data/variable_metadata.json.

    Cache is invalidated whenever the file's mtime changes so dev edits
    are picked up without restarting the server.
    """
    global _VARIABLE_METADATA_CACHE, _VARIABLE_METADATA_MTIME
    path = app.config.settings.DATA_DIR / "variable_metadata.json"
    if not path.exists():
        raise FileNotFoundError(f"variable_metadata.json missing at {path}")
    mtime = path.stat().st_mtime
    if _VARIABLE_METADATA_CACHE is None or mtime != _VARIABLE_METADATA_MTIME:
        _VARIABLE_METADATA_CACHE = json.loads(path.read_text())
        _VARIABLE_METADATA_MTIME = mtime
    return _VARIABLE_METADATA_CACHE
```

- [ ] **Step 4: Run tests to verify PASS**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Create the canonical metadata file**

Create `backend/data/variable_metadata.json`:

```json
{
  "ndi": {
    "label": "Neighborhood Deprivation Index",
    "boundary": "BG",
    "coverage_years": [2012, 2022],
    "coverage_region": "CONUS",
    "experiment": "bg_ndi_wi"
  },
  "walkability": {
    "label": "EPA Walkability Index",
    "boundary": "BG",
    "coverage_years": [2016, 2021],
    "coverage_region": "CONUS",
    "experiment": "bg_ndi_wi"
  }
}
```

- [ ] **Step 6: Add to .gitignore**

Append to `backend/.gitignore`:

```
data/variable_metadata.json
```

(Reasoning: this is environment data, not code. Future Sprint 3 may move it into `backend/app/` if it needs to be source-controlled.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_coverage.py backend/.gitignore
git commit -m "feat(coverage): _load_variable_metadata with mtime-invalidated cache"
```

Note: `data/variable_metadata.json` is intentionally NOT committed (gitignored).

---

## Task 2: compute_coverage() helper

**Files:**
- Modify: `backend/app/task_manager.py` (add `compute_coverage`)
- Test: `backend/tests/test_coverage.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_coverage.py`:

```python
def _seed_task_with_csv(monkeypatch, tmp_path, rows_csv: str) -> str:
    """Helper: create a task dir with an input.csv and return its task_id."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "NDI", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
        "walkability": {"label": "WI", "boundary": "BG", "coverage_years": [2016, 2021],
                        "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)

    task_dir = app.config.settings.TASKS_DIR / "task-cov-test-01"
    task_dir.mkdir(parents=True)
    (task_dir / "input.csv").write_text(rows_csv)
    return "cov-test-01"


def test_compute_coverage_basic_ndi(monkeypatch, tmp_path):
    """100% covered: cohort in 2017, all coords in CONUS."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
        "P2,2017-06-01,2018-06-01,-95.0,30.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["row_count"] == 2
    assert out["variables"]["ndi"]["coverage_pct"] == 100.0
    assert out["variables"]["ndi"]["patients_covered"] == 2


def test_compute_coverage_time_window_filter(monkeypatch, tmp_path):
    """Walkability covers 2016-2021. Patients in 2014 fall outside."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2014-01-01,2014-12-31,-93.0,45.0\n"
        "P2,2018-01-01,2018-06-01,-93.0,45.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["walkability"])
    assert out["variables"]["walkability"]["patients_in_time_window"] == 1
    assert out["variables"]["walkability"]["coverage_pct"] == 50.0


def test_compute_coverage_region_filter_conus(monkeypatch, tmp_path):
    """CONUS box rejects an Alaska longitude."""
    csv = (
        "pid,startDate,endDate,longitude,latitude\n"
        "P_AK,2017-01-01,2017-12-31,-149.9,61.2\n"
        "P_TX,2017-01-01,2017-12-31,-95.0,30.0\n"
    )
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["ndi"])
    assert out["variables"]["ndi"]["patients_in_region"] == 1
    assert out["variables"]["ndi"]["coverage_pct"] == 50.0


def test_compute_coverage_unknown_variable_raises(monkeypatch, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93,45\n"
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    with pytest.raises(KeyError):
        compute_coverage(task_id, ["pm25"])


def test_compute_coverage_no_input_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "x", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    import app.config
    importlib.reload(app.config)
    import app.task_manager
    importlib.reload(app.task_manager)
    # Create task dir but no input.csv
    (app.config.settings.TASKS_DIR / "task-cov-test-02").mkdir(parents=True)
    from app.task_manager import compute_coverage
    with pytest.raises(FileNotFoundError):
        compute_coverage("cov-test-02", ["ndi"])


def test_compute_coverage_emits_warning_on_low_time_coverage(monkeypatch, tmp_path):
    """When >5% of patients are outside the time window, append a human-readable warning."""
    rows = ["pid,startDate,endDate,longitude,latitude"]
    for i in range(100):
        # 10 patients in 2014 (out of WI 2016-2021), 90 in 2018
        year = 2014 if i < 10 else 2018
        rows.append(f"P{i},{year}-01-01,{year}-12-31,-93.0,45.0")
    csv = "\n".join(rows) + "\n"
    task_id = _seed_task_with_csv(monkeypatch, tmp_path, csv)
    from app.task_manager import compute_coverage
    out = compute_coverage(task_id, ["walkability"])
    assert out["variables"]["walkability"]["coverage_pct"] == 90.0
    assert len(out["variables"]["walkability"]["warnings"]) >= 1
    assert "2016-2021" in out["variables"]["walkability"]["warnings"][0]
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v
```

Expected: 6 new tests FAIL with `ImportError` on `compute_coverage`.

- [ ] **Step 3: Implement compute_coverage**

Add to `backend/app/task_manager.py` (below `_load_variable_metadata`):

```python
def compute_coverage(task_id: str, variable_keys: list[str]) -> dict:
    """Compute per-variable cohort coverage statistics for a task's input.csv.

    Returns
    -------
    dict
        Shape:
            {
              "row_count": int,
              "variables": {
                  var_key: {
                      "coverage_years": [int, int],
                      "patients_in_time_window": int,
                      "patients_in_region": int,
                      "patients_covered": int,
                      "coverage_pct": float (2 dp),
                      "warnings": list[str],
                  },
                  ...
              }
            }

    Raises
    ------
    FileNotFoundError
        If the task's input.csv is missing.
    KeyError
        If any requested variable is not in variable_metadata.json (the
        exception args[0] is a comma-separated list of unknown keys).
    """
    import pandas as pd  # noqa: PLC0415  — local import to keep cold-import light

    task_dir = app.config.settings.TASKS_DIR / f"task-{task_id}"
    input_csv = task_dir / "input.csv"
    if not input_csv.exists():
        raise FileNotFoundError("No input uploaded")

    metadata = _load_variable_metadata()
    unknown = [v for v in variable_keys if v not in metadata]
    if unknown:
        raise KeyError(", ".join(unknown))

    df = pd.read_csv(
        input_csv,
        parse_dates=["startDate", "endDate"],
        dtype={"state_fips": "string", "county_fips": "string",
               "tract_geoid": "string", "bg_geoid": "string"},
    )
    n_total = len(df)

    out_vars: dict[str, dict] = {}
    for var in variable_keys:
        m = metadata[var]
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
        }

    return {"row_count": n_total, "variables": out_vars}
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v
```

Expected: all 8 tests PASS (2 from Task 1 + 6 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/task_manager.py backend/tests/test_coverage.py
git commit -m "feat(coverage): compute_coverage helper with time-window + CONUS-region filter"
```

---

## Task 3: GET /coverage router endpoint

**Files:**
- Modify: `backend/app/routers/tasks.py`
- Test: `backend/tests/test_coverage.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_coverage.py`:

```python
def _make_authed_client(monkeypatch, tmp_path):
    """Boot a TestClient with the variable_metadata fixture + a signed-in user."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "tasks"))
    (tmp_path / "variable_metadata.json").write_text(json.dumps({
        "ndi": {"label": "NDI", "boundary": "BG", "coverage_years": [2012, 2022],
                "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
        "walkability": {"label": "WI", "boundary": "BG", "coverage_years": [2016, 2021],
                        "coverage_region": "CONUS", "experiment": "bg_ndi_wi"},
    }))
    for mod_name in [
        "app.config", "app.database", "app.auth", "app.routers.auth",
        "app.task_manager", "app.routers.tasks", "app.main",
    ]:
        mod = importlib.import_module(mod_name)
        importlib.reload(mod)

    from app.main import create_app
    from app.database import init_db
    from fastapi.testclient import TestClient

    init_db()
    client = TestClient(create_app())
    resp = client.post("/api/auth/signup", json={
        "email": "c@c.com", "password": "pw123", "first_name": "C", "last_name": "U"
    })
    token = resp.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_coverage_endpoint_basic(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 1
    assert body["variables"]["ndi"]["coverage_pct"] == 100.0


def test_coverage_endpoint_unknown_variable(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=pm25", headers=auth)
    assert resp.status_code == 400
    assert "unknown variable" in resp.json()["detail"].lower()


def test_coverage_endpoint_multi_variables(monkeypatch, tmp_path):
    import io
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi,walkability", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert "ndi" in body["variables"]
    assert "walkability" in body["variables"]


def test_coverage_endpoint_no_input(monkeypatch, tmp_path):
    client, auth = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "cov"}, headers=auth).json()["id"]
    # No upload — task exists but no input.csv
    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth)
    assert resp.status_code == 400
    assert "no input" in resp.json()["detail"].lower()


def test_coverage_endpoint_ownership_403(monkeypatch, tmp_path):
    import io
    client, auth_a = _make_authed_client(monkeypatch, tmp_path)
    task_id = client.post("/api/tasks", json={"task_name": "A's task"}, headers=auth_a).json()["id"]
    csv = b"pid,startDate,endDate,longitude,latitude\nP1,2017-01-01,2017-12-31,-93.0,45.0\n"
    client.post(f"/api/tasks/{task_id}/upload", headers=auth_a,
                files={"file": ("in.csv", io.BytesIO(csv), "text/csv")})

    # User B
    resp_b = client.post("/api/auth/signup", json={
        "email": "b@b.com", "password": "pw123", "first_name": "B", "last_name": "U"
    })
    token_b = resp_b.json()["access_token"]
    auth_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get(f"/api/tasks/{task_id}/coverage?variables=ndi", headers=auth_b)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v -k "endpoint"
```

Expected: 5 endpoint tests FAIL with 404 Not Found.

- [ ] **Step 3: Add the router endpoint**

Edit `backend/app/routers/tasks.py`. Find the `Query` import; if `Query` is not imported, change:

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
```

to:

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
```

Add this endpoint after the existing `/start` / `/stop` / `/status` / `/logs` / `/results` routes:

```python
@router.get("/{task_id}/coverage")
def get_coverage(
    task_id: str,
    variables: str = Query(..., description="Comma-separated variable keys"),
    user: dict = Depends(get_current_user),
):
    """Per-variable cohort coverage statistics for a task's input.csv."""
    _verify_ownership(task_id, user)
    var_keys = [v.strip() for v in variables.split(",") if v.strip()]
    if not var_keys:
        raise HTTPException(status_code=400, detail="variables query is required")
    try:
        return task_manager.compute_coverage(task_id, var_keys)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"unknown variable(s): {exc.args[0]}")
```

- [ ] **Step 4: Tests pass**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_coverage.py -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Run the full backend suite to check no regressions**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: prior count + 8 new = ~50 passed, 1 skipped, 4 deselected.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/tasks.py backend/tests/test_coverage.py
git commit -m "feat(api): GET /api/tasks/{id}/coverage endpoint for pre-flight variable check"
```

---

## Task 4: Frontend api.ts getCoverage

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Read existing api.ts structure**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
sed -n '50,130p' src/lib/api.ts
```

Locate the existing exported `api` object with its `createTask`, `listTasks`, etc. methods.

- [ ] **Step 2: Add the VarCoverage / CoverageResponse interfaces**

Add near the existing `LogEntry` / `Task` interfaces (top of `api.ts` exported types):

```ts
export interface VarCoverage {
  coverage_years: [number, number];
  patients_in_time_window: number;
  patients_in_region: number;
  patients_covered: number;
  coverage_pct: number;
  warnings: string[];
}

export interface CoverageResponse {
  row_count: number;
  variables: Record<string, VarCoverage>;
}
```

- [ ] **Step 3: Add getCoverage method**

In the existing `api` object literal, add (place it alphabetically near `getStatus` / `getLogs`):

```ts
  getCoverage: (taskId: string, variables: string[]) =>
    fetchJson<CoverageResponse>(
      `${API_BASE}/api/tasks/${taskId}/coverage?variables=${variables.join(",")}`,
      { headers: { ...authHeader() } },
    ),
```

If `fetchJson` is not the helper name used in the file, find the existing pattern (e.g. `apiFetch` or inline `fetch`) and match it. The other methods in the same object are the reference.

- [ ] **Step 4: Typecheck**

```bash
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
node_modules/.bin/tsc --noEmit
```

Expected: zero errors, zero output.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/tsconfig.tsbuildinfo
git commit -m "feat(api): frontend api.getCoverage method + VarCoverage types"
```

---

## Task 5: VariableCoveragePanel component + variables-step integration

**Files:**
- Create: `frontend/src/components/wizard/variable-coverage-panel.tsx`
- Modify: `frontend/src/components/wizard/variables-step.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/wizard/variable-coverage-panel.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { api, type VarCoverage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";

interface VariableCoveragePanelProps {
  taskId: string;
  variableKey: string;
}

export function VariableCoveragePanel({
  taskId,
  variableKey,
}: VariableCoveragePanelProps) {
  const [data, setData] = useState<VarCoverage | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getCoverage(taskId, [variableKey])
      .then((resp) => {
        if (cancelled) return;
        setRowCount(resp.row_count);
        setData(resp.variables[variableKey] ?? null);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, variableKey]);

  if (error) return null; // fail silently — don't obstruct Run
  if (!data || rowCount === null) {
    return (
      <div className="mt-2 text-xs text-muted-foreground">
        Checking coverage...
      </div>
    );
  }

  const tone =
    data.coverage_pct >= 95
      ? "ok"
      : data.coverage_pct >= 60
        ? "warn"
        : "bad";
  const Icon =
    tone === "ok" ? CheckCircle2 : tone === "warn" ? AlertTriangle : AlertCircle;

  return (
    <div
      className={cn(
        "mt-2 rounded-md border p-2 text-xs",
        tone === "ok" &&
          "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400",
        tone === "warn" &&
          "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-400",
        tone === "bad" &&
          "border-red-500/30 bg-red-500/5 text-red-700 dark:text-red-400",
      )}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <Icon className="size-3.5" />
        {data.coverage_pct}% of your cohort covered
      </div>
      <div className="mt-0.5 text-muted-foreground">
        {data.patients_covered.toLocaleString()} /{" "}
        {rowCount.toLocaleString()} within {data.coverage_years[0]}-
        {data.coverage_years[1]} + coverage region
      </div>
      {data.warnings.map((w, i) => (
        <div key={i} className="mt-1">
          {w}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Wire into variables-step.tsx**

Read the current shape of `variables-step.tsx` to find where each variable checkbox renders:

```bash
sed -n '1,80p' src/components/wizard/variables-step.tsx
```

The component renders a list of variables (each a label + checkbox). Identify the props the parent passes — specifically whether `taskId` is already available.

If `taskId` is NOT already a prop of `VariablesStep`, add it:

```tsx
interface VariablesStepProps {
  taskId: string;          // ★ NEW
  selectedVariables: string[];
  // ... existing props
}
```

And update the parent page (`frontend/src/app/dashboard/task/new/page.tsx`) to pass `taskId` to `VariablesStep`. The parent already manages `taskId` for `BufferStep` and `ReviewStep`, so passing it to `VariablesStep` is one new line.

Inside the variable-rendering loop (where each checkbox + label renders), import and add `VariableCoveragePanel`:

```tsx
import { VariableCoveragePanel } from "./variable-coverage-panel";

// ... inside the V1_VARIABLES.map((v) => ... ) block, AFTER the existing
// <Checkbox> + <div>{v.label}</div> + <div>{v.description}</div>:

{selectedVariables.includes(v.id) && (
  <VariableCoveragePanel taskId={taskId} variableKey={v.id} />
)}
```

- [ ] **Step 3: Typecheck**

```bash
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
node_modules/.bin/tsc --noEmit
```

Expected: zero errors. If you get errors about `taskId` not being passed, update the parent page (`new/page.tsx`).

- [ ] **Step 4: Manual smoke (optional but recommended)**

```bash
# Backend already running per earlier setup; restart if needed:
#   cd backend; /Users/xai/miniconda3/envs/spacescans/bin/uvicorn app.main:app --reload --port 8000

# Frontend:
cd frontend
npm run dev
```

In a browser: sign in, start a new task, upload `data_full/demo_patients_conus_fast_100000.csv` (or a smaller sample), reach the Variables step. Check NDI — expect a green/yellow panel below it. Check Walkability — expect a separate panel.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/wizard/variable-coverage-panel.tsx \
        frontend/src/components/wizard/variables-step.tsx \
        frontend/src/app/dashboard/task/new/page.tsx \
        frontend/tsconfig.tsbuildinfo
git commit -m "feat(wizard): VariableCoveragePanel inline coverage check on Variables step"
```

(If `new/page.tsx` was not modified because `taskId` was already a prop, omit it from the `git add`.)

---

## Task 6: C3 cache helpers (hash + key + validate)

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py` (add helpers)
- Modify: `backend/app/config.py` (add `C3_CACHE_DIR`)
- Modify: `backend/.gitignore` (add `data/c3_cache/`)
- Test: `backend/tests/test_bg_ndi_wi.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
def test_hash_input_parquet_is_deterministic(tmp_path):
    """Same bytes → same hash; one byte change → different hash."""
    from app.experiments.bg_ndi_wi import _hash_input_parquet

    p = tmp_path / "in.parquet"
    p.write_bytes(b"hello world" * 1000)
    h1 = _hash_input_parquet(p)
    h2 = _hash_input_parquet(p)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest

    p.write_bytes(b"hello WORLD" * 1000)  # one byte case change
    h3 = _hash_input_parquet(p)
    assert h3 != h1


def test_cache_key_stable_same_inputs(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    k1 = _cache_key(p, _C3_STEP, cfg)
    k2 = _cache_key(p, _C3_STEP, cfg)
    assert k1 == k2


def test_cache_key_changes_on_input(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    cfg = {"buffer": {"size": 270, "raster_res_m": 25}}
    k1 = _cache_key(p, _C3_STEP, cfg)
    p.write_bytes(b"\x01" * 4096)
    k2 = _cache_key(p, _C3_STEP, cfg)
    assert k1 != k2


def test_cache_key_changes_on_buffer(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k1 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    k2 = _cache_key(p, _C3_STEP, {"buffer": {"size": 500, "raster_res_m": 25}})
    assert k1 != k2


def test_cache_key_changes_on_raster(tmp_path):
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k1 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    k2 = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 50}})
    assert k1 != k2


def test_cache_key_format_human_readable(tmp_path):
    """Sanity-check the filename grammar so devs can identify cache entries."""
    from app.experiments.bg_ndi_wi import _cache_key, _C3_STEP

    p = tmp_path / "in.parquet"
    p.write_bytes(b"\x00" * 4096)
    k = _cache_key(p, _C3_STEP, {"buffer": {"size": 270, "raster_res_m": 25}})
    assert "__BG__" in k
    assert "__b270m__" in k
    assert "__r25m" in k


def test_is_valid_cached_parquet_rejects_short_file(tmp_path):
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    p = tmp_path / "fake.parquet"
    p.write_bytes(b"too short")
    assert not _is_valid_cached_parquet(p)


def test_is_valid_cached_parquet_rejects_missing(tmp_path):
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    assert not _is_valid_cached_parquet(tmp_path / "does-not-exist.parquet")


def test_is_valid_cached_parquet_accepts_real_parquet(tmp_path):
    import pandas as pd
    from app.experiments.bg_ndi_wi import _is_valid_cached_parquet

    p = tmp_path / "real.parquet"
    pd.DataFrame({"a": [1, 2, 3]}).to_parquet(p, index=False)
    assert _is_valid_cached_parquet(p)
```

- [ ] **Step 2: Run failing tests**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "hash_input_parquet or cache_key or is_valid_cached_parquet"
```

Expected: 9 FAIL with `ImportError`.

- [ ] **Step 3: Add the helpers**

Edit `backend/app/experiments/bg_ndi_wi.py`. Add near the other helpers (above `_install_cancel_handler` is a good place). Use `import hashlib` at the top of the file:

```python
import hashlib
```

(Likely needs to be added — check existing imports.)

Then add:

```python
def _hash_input_parquet(path: Path) -> str:
    """Return the SHA256 hex digest of a parquet file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):  # 1 MB chunks
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Build a deterministic, human-readable cache key.

    Format: ``<sha8>__<boundary>__b<buffer>m__r<raster>m``
    Example: ``a8f3c2b1__BG__b270m__r25m``
    """
    sha = _hash_input_parquet(input_parquet)
    boundary = "BG"  # Sprint 1: only BG. Sprint 3 will derive from step.
    buf = user_config["buffer"]["size"]
    raster = user_config["buffer"]["raster_res_m"]
    return f"{sha[:8]}__{boundary}__b{buf}m__r{raster}m"


def _is_valid_cached_parquet(path: Path) -> bool:
    """Cheap sanity check before trusting a cached file.

    Rejects missing files, files under 100 bytes (typical truncated /
    in-progress writes), and files whose parquet header is unreadable.
    """
    if not path.exists():
        return False
    if path.stat().st_size < 100:
        return False
    try:
        import pandas as pd
        pd.read_parquet(path, columns=[])  # header read; ignores data
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Add `C3_CACHE_DIR` to config**

Edit `backend/app/config.py`. Inside the `Settings` class, add a line:

```python
    C3_CACHE_DIR: Path = DATA_DIR / "c3_cache"
```

(Place it right after `TASKS_DIR`.)

- [ ] **Step 5: Add to .gitignore**

Append to `backend/.gitignore`:

```
data/c3_cache/
```

- [ ] **Step 6: Run tests to verify PASS**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "hash_input_parquet or cache_key or is_valid_cached_parquet"
```

Expected: 9 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/app/config.py backend/.gitignore backend/tests/test_bg_ndi_wi.py
git commit -m "feat(cache): C3 cache helpers — hash, key, validator + C3_CACHE_DIR setting"
```

---

## Task 7: Wire cache check/write into run()

**Files:**
- Modify: `backend/app/experiments/bg_ndi_wi.py` (modify `run()` body)
- Test: `backend/tests/test_bg_ndi_wi.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_bg_ndi_wi.py`:

```python
def test_cache_miss_creates_artifact_and_meta(fake_template_dir, fake_cli_settings, tmp_path):
    """First run with no cache → cache dir gets <key>.parquet + <key>.meta.json."""
    import app.config

    task_dir = tmp_path / "task-cache-01"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    from app.experiments.bg_ndi_wi import run
    rc = run(task_dir)
    assert rc == 0

    cache_dir = app.config.settings.C3_CACHE_DIR
    parquets = list(cache_dir.glob("*.parquet"))
    metas = list(cache_dir.glob("*.meta.json"))
    assert len(parquets) == 1
    assert len(metas) == 1
    # filename grammar
    assert "__BG__b270m__r25m" in parquets[0].name


def test_cache_hit_skips_subprocess(fake_template_dir, fake_cli_settings, tmp_path, monkeypatch):
    """Second run with same inputs → Popen called 0 times for c3_bg."""
    import app.config

    # Run 1: populates cache.
    task_dir = tmp_path / "task-cache-A"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    from app.experiments.bg_ndi_wi import run
    assert run(task_dir) == 0

    # Run 2: byte-identical input + same config. Should hit cache for c3_bg.
    task_dir_2 = tmp_path / "task-cache-B"
    task_dir_2.mkdir()
    shutil.copy(task_dir / "input.csv", task_dir_2 / "input.csv")
    shutil.copy(task_dir / "config.json", task_dir_2 / "config.json")

    # Monkeypatch run_pipeline_step to count invocations BY STEP NAME.
    from app.experiments import bg_ndi_wi
    calls: list[str] = []
    real_run_step = bg_ndi_wi.run_pipeline_step

    def counting_run_step(yaml_path, task_dir, step_name, on_progress=None):
        calls.append(step_name)
        return real_run_step(yaml_path, task_dir, step_name, on_progress)

    monkeypatch.setattr(bg_ndi_wi, "run_pipeline_step", counting_run_step)
    assert run(task_dir_2) == 0

    # c3_bg should be a cache hit (not in calls); c4_ndi must still run.
    assert "c3_bg" not in calls, f"c3_bg should have hit cache; calls={calls}"
    assert "c4_ndi" in calls


def test_cache_corrupted_falls_through(fake_template_dir, fake_cli_settings, tmp_path):
    """Pre-existing 10-byte fake cache entry → ignored, fresh run, cache overwritten."""
    import app.config

    task_dir = tmp_path / "task-cache-C"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    # Pre-populate the cache with a corrupted file at the EXACT key the run will compute.
    # Easiest: do one real run first to learn the key, then truncate the file.
    from app.experiments.bg_ndi_wi import run
    run(task_dir)  # populates cache
    cache_dir = app.config.settings.C3_CACHE_DIR
    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) == 1
    parquets[0].write_bytes(b"truncated!")  # corrupt it

    # Now run again — should detect corruption and rebuild.
    task_dir_2 = tmp_path / "task-cache-D"
    task_dir_2.mkdir()
    shutil.copy(task_dir / "input.csv", task_dir_2 / "input.csv")
    shutil.copy(task_dir / "config.json", task_dir_2 / "config.json")
    assert run(task_dir_2) == 0
    # Cache should be rewritten with valid content.
    assert parquets[0].stat().st_size > 100


def test_cache_write_failure_does_not_break_task(
    fake_template_dir, fake_cli_settings, tmp_path, monkeypatch
):
    """shutil.copy raising OSError on cache write → task still finishes."""
    import shutil as real_shutil
    from app.experiments import bg_ndi_wi

    task_dir = tmp_path / "task-cache-E"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(
        "pid,startDate,endDate,longitude,latitude\n"
        "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
    )
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))

    # Sabotage cache writes only — keep other copies working.
    real_copy = real_shutil.copy

    def failing_copy(src, dst, *a, **kw):
        # Identify cache-write copies by destination containing /c3_cache/.
        if "c3_cache" in str(dst):
            raise OSError(28, "No space left on device")
        return real_copy(src, dst, *a, **kw)

    monkeypatch.setattr(bg_ndi_wi.shutil, "copy", failing_copy)

    rc = bg_ndi_wi.run(task_dir)
    assert rc == 0  # task still finishes
    status = json.loads((task_dir / "status.json").read_text())
    assert status["status"] == "finished"
```

NOTE: these tests use the existing `fake_template_dir` and `fake_cli_settings` fixtures already in `test_bg_ndi_wi.py` (from Task 6 of the v1 plan). Reuse them; do not redefine.

- [ ] **Step 2: Run failing tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v -k "test_cache_miss_creates or test_cache_hit_skips or test_cache_corrupted_falls or test_cache_write_failure"
```

Expected: 4 FAIL — cache files won't appear because `run()` doesn't write the cache yet.

- [ ] **Step 3: Wire cache logic into run()**

Edit `backend/app/experiments/bg_ndi_wi.py`. Locate the existing `for idx, step in enumerate(steps):` loop inside `run()`. Modify it as follows. Find the existing block:

```python
        for idx, step in enumerate(steps):
            _write_status(
                task_dir,
                current_step=step.name,
                message=f"Running {step.name} ({idx+1}/{total_steps})",
                progress=idx / total_steps,
            )
            try:
                yaml_path = render_yaml(step, task_dir, config)
            except Exception as exc:
                _append_log(task_dir, "error", "runner", f"render_yaml({step.name}) failed: {exc!r}")
                _write_status(task_dir, status="error", message=f"render failed at {step.name}")
                return 1

            def _on_step_progress(frac: float, idx=idx, step=step) -> None:
                _write_status(
                    task_dir,
                    progress=(idx + frac) / total_steps,
                    message=f"Running {step.name} ({idx+1}/{total_steps}) — {int(frac*100)}%",
                )

            rc = run_pipeline_step(yaml_path, task_dir, step_name=step.name,
                                   on_progress=_on_step_progress)
            if rc != 0:
                _write_status(task_dir, status="error",
                              message=f"step {step.name} failed with exit code {rc}")
                return rc

            out_parquet = task_dir / "output" / f"{step.name}.parquet"
            if not out_parquet.exists():
                _write_status(task_dir, status="error",
                              message=f"step {step.name} produced no output parquet")
                return 1
```

Replace it with:

```python
        for idx, step in enumerate(steps):
            _write_status(
                task_dir,
                current_step=step.name,
                message=f"Running {step.name} ({idx+1}/{total_steps})",
                progress=idx / total_steps,
            )

            out_parquet = task_dir / "output" / f"{step.name}.parquet"

            # C3 cache check
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
                        continue  # skip subprocess entirely
                except Exception as exc:
                    _append_log(task_dir, "warning", "runner",
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
                    cache_path = None  # disable write-back too

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

            # C3 cache write-back on success
            if step.is_c3 and cache_path is not None:
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(out_parquet, cache_path)
                    _write_cache_meta(
                        cache_path.with_suffix(".meta.json"),
                        sha_full=_hash_input_parquet(task_dir / "input.parquet"),
                        boundary="BG",
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
```

Also add at the top of `bg_ndi_wi.py` (under the existing imports):

```python
import shutil
import time
```

(Both may already be imported — check before adding.)

And add the helper functions near the other module-level helpers:

```python
def _write_cache_meta(path: Path, **fields) -> None:
    """Write a JSON sidecar describing a cache entry."""
    fields.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(fields, indent=2))


def _count_input_rows(input_csv: Path) -> int:
    """Cheap row count — used only for the meta sidecar."""
    with open(input_csv) as f:
        next(f, None)  # header
        return sum(1 for _ in f)
```

- [ ] **Step 4: Run tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest tests/test_bg_ndi_wi.py -v
```

Expected: all bg_ndi_wi tests PASS (existing + 9 from Task 6 + 4 new = 32+ tests in this file).

- [ ] **Step 5: Run the full backend suite**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: ~58 passed, 1 skipped, 4 deselected (no regressions, +13 new from coverage and cache).

- [ ] **Step 6: Commit**

```bash
git add backend/app/experiments/bg_ndi_wi.py backend/tests/test_bg_ndi_wi.py
git commit -m "feat(cache): C3 cache check + write-back wired into bg_ndi_wi.run()"
```

---

## Task 8: Integration test — sequential runs prove cache speedup

**Files:**
- Modify: `backend/tests/test_bg_ndi_wi_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bg_ndi_wi_integration.py`:

```python
@pytest.mark.integration
def test_e2e_cache_second_run_faster(task_with_5_patients, tmp_path):
    """Run the same 5-patient cohort twice; the second run hits the c3_bg cache
    and finishes in a small fraction of the first run's wall-clock."""
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_with_5_patients),
    ]

    # First run: full pipeline.
    t1_start = time.monotonic()
    proc1 = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    t1 = time.monotonic() - t1_start
    assert proc1.returncode == 0

    # Second task with byte-identical input.csv + config.
    task_dir_2 = tmp_path / "task-int-cache-02"
    task_dir_2.mkdir()
    (task_dir_2 / "output").mkdir()
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir_2 / "input.csv",
    )
    (task_dir_2 / "config.json").write_text(json.dumps({
        "experiment": "bg_ndi_wi",
        "variables": ["ndi", "walkability"],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    cmd2 = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir_2),
    ]
    t2_start = time.monotonic()
    proc2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
    t2 = time.monotonic() - t2_start
    assert proc2.returncode == 0

    # Second run should be MUCH faster (C3 step skipped).
    # The 5-patient C3 takes ~13-15s on this fixture; cache hit copies a file (<100ms).
    # Conservatively assert t2 < 0.3 * t1.
    assert t2 < 0.3 * t1, (
        f"expected second run to be < 30% of first; got t1={t1:.2f}s t2={t2:.2f}s"
    )

    # Cache directory exists with one entry.
    cache_dir = app.config.settings.C3_CACHE_DIR
    parquets = list(cache_dir.glob("*.parquet"))
    assert len(parquets) >= 1
```

- [ ] **Step 2: Confirm the integration env is set up**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
test -f .env && grep -q SPACESCANS_DATA_DIR .env && echo "env OK"
test -d /Users/xai/Desktop/spacescans-project/data_full && echo "data_full OK"
```

- [ ] **Step 3: Clean any prior cache to ensure a clean first run**

```bash
rm -rf data/c3_cache/
```

- [ ] **Step 4: Run the integration test**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v tests/test_bg_ndi_wi_integration.py::test_e2e_cache_second_run_faster
```

Expected: PASS. Run 1 ~15-20s, Run 2 ~2-5s.

If the `t2 < 0.3 * t1` assertion fails because hardware is slow enough that even 30% of t1 is < 2s, raise the threshold to `0.5 * t1` and re-run. The intent is "noticeably faster" not "exactly N times faster".

- [ ] **Step 5: Run the default suite to confirm no regressions**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: all unit tests pass; integration tests deselected.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_bg_ndi_wi_integration.py
git commit -m "test(integration): C3 cache makes second run on same cohort much faster"
```

---

## Task 9: Final verification + manual smoke

**Files:**
- Modify: `backend/tests/manual_e2e.md` (append cache + coverage steps)

- [ ] **Step 1: Run the full backend suite**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/backend
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -q
```

Expected: ~58 passed, 1 skipped, 4 deselected, 0 failed.

- [ ] **Step 2: Run integration tests**

```bash
/Users/xai/miniconda3/envs/spacescans/bin/python -m pytest -m integration -v
```

Expected: 5 integration tests pass (4 from v1 + 1 new cache test).

- [ ] **Step 3: Typecheck the frontend**

```bash
cd /Users/xai/Desktop/spacescans-project/spacescans-web/frontend
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"
node_modules/.bin/tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 4: Append to manual_e2e.md**

Open `backend/tests/manual_e2e.md` and append a new section after the existing "Pass criteria":

```markdown
## Sprint 1 additions (Pre-flight + Cache)

### Pre-flight coverage check

On the Variables step, after checking NDI:
- Expect a colored panel below: green if ≥95% covered, yellow 60-95%, red <60%.
- The panel reads: "X% of your cohort covered" with breakdown by time and region.
- Try a cohort with patients in 2010 (outside NDI 2012-2022) — expect a warning line.

### C3 cache speedup

After completing one task with NDI + Walkability:
1. Note the wall-clock for c3_bg step in the LogViewer (timestamp diff between
   "spawning c3_bg" and "step c3_bg exit code 0").
2. Create a NEW task, upload the same CSV, select the same variables and buffer.
3. Start the task. The c3_bg step should appear, log "cache hit", and complete
   in under a second (you'll see the step list flicker by quickly).
4. result.csv should still be produced.

To force a cache rebuild:
```
rm -rf backend/data/c3_cache/
```
```

- [ ] **Step 5: Final commit**

```bash
git add backend/tests/manual_e2e.md
git commit -m "docs(tests): manual_e2e Sprint 1 sections — coverage panel + cache speedup"
```

- [ ] **Step 6: Hand off to finishing-a-development-branch**

The Sprint 1 implementation is complete. Decide merge / PR / keep / discard via:

```
Use the superpowers:finishing-a-development-branch skill.
```

---

## Spec coverage map

| Spec section | Implemented by |
|---|---|
| Goal | All tasks collectively |
| Scope > In scope > coverage endpoint | Tasks 1, 2, 3 |
| Scope > In scope > variable_metadata.json | Task 1 |
| Scope > In scope > VariableCoveragePanel | Tasks 4, 5 |
| Scope > In scope > c3_cache directory | Task 6 (helpers), Task 7 (wiring) |
| Scope > In scope > sidecar .meta.json | Task 7 (_write_cache_meta) |
| Scope > In scope > unit + integration tests | Tasks 1-8 (each has tests) |
| Scope > Out of scope (LRU, metrics, C4 cache, remote, shapefile region, schema versioning, multi-tenancy) | Deliberately not implemented |
| Architecture > #2 flow | Tasks 1-5 |
| Architecture > #5 flow | Tasks 6-8 |
| Data Flow > Pre-flight 7 steps | Tasks 1-5 |
| Data Flow > Cache 4 steps | Tasks 6-7 |
| Backend Modules > variable_metadata.json | Task 1 Step 5 |
| Backend Modules > compute_coverage | Task 2 |
| Backend Modules > /coverage router | Task 3 |
| Backend Modules > _hash_input_parquet, _cache_key, _is_valid_cached_parquet | Task 6 |
| Backend Modules > C3_CACHE_DIR setting | Task 6 |
| Backend Modules > cache check/write in run() | Task 7 |
| Frontend Changes > VariableCoveragePanel | Task 5 |
| Frontend Changes > api.ts getCoverage | Task 4 |
| Frontend Changes > variables-step.tsx integration | Task 5 |
| Error Handling > Pre-flight failure matrix #1-#6 | Task 2 (FileNotFoundError, KeyError), Task 3 (HTTPException mapping), Task 5 (silent fail in UI) |
| Error Handling > Cache failure matrix #1-#8 | Task 6 (validation), Task 7 (corrupt fall-through, write-failure, hash-failure, concurrent race) |
| Testing > Unit tests | Tasks 1-3 (coverage) + Task 6 (cache helpers) + Task 7 (cache wiring) |
| Testing > Integration test | Task 8 |
| Testing > Manual smoke | Task 9 |
| Implementation Estimate (~540 new, ~90 modified) | Roughly tracked by per-task LOC |

All spec requirements have at least one implementing task. No gaps.
