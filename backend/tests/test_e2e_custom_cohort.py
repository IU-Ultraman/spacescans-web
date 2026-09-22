"""e2e: a user-uploaded custom exposome through task_manager.start_task.

Proves the whole path for combination 1 of the custom-exposome design: the
library accepts a CSV of real Florida tract values, the config endpoint's
resolution snapshots it into config.json, the dispatcher routes the custom_*
key to app.experiments.custom, the shipped TRACT C3 runs (or is reused from
cache), static_areal reads the uploaded CSV with no plugin, and the per-episode
grouping survives into result_custom.csv.

Asserting on result_custom.csv rather than result.csv is deliberate: result.csv
is a LEFT JOIN onto the cohort keys, so it always has one row per cohort row and
every declared column. An empty linkage satisfies a row-count check — that is
exactly how an empty FAQSD join once passed as green.
"""
import json
import shutil
import time
from pathlib import Path

import pandas as pd
import pytest

import app.config

_VALUE_COLS = ["greenness", "heat_index"]
# The fixture's values, by construction. An area-weighted average over any mix
# of tracts has to land inside these bands; anything outside means the join
# matched the wrong rows rather than simply matching none.
_GREENNESS_RANGE = (0.300, 0.400)
_HEAT_RANGE = (80.0, 85.0)


def _integration_available() -> bool:
    if not app.config.settings.SPACESCANS_DATA_DIR.exists():
        return False
    if not app.config.settings.SPACESCANS_PIPELINE_CLI.exists():
        return False
    tract_c3 = app.config.settings.SPACESCANS_DATA_DIR / "TRACT" / "C3"
    return tract_c3.is_dir() and any(tract_c3.glob("tl_2010_*_tract10"))


pytestmark = pytest.mark.skipif(
    not _integration_available(),
    reason="SPACESCANS_DATA_DIR / Tract C3 / pipeline CLI not configured",
)


@pytest.fixture
def task_with_custom_exposome(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TASKS_DIR", str(tmp_path / "data" / "tasks"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "data" / "test.db"))

    import importlib
    import app.config as _config
    import app.custom_exposomes as _lib
    import app.task_manager as _tm
    importlib.reload(_config)
    importlib.reload(_lib)
    importlib.reload(_tm)

    fixture = Path(__file__).parent / "fixtures" / "custom_fl_tracts.csv"
    manifest = _lib.create(
        1,
        content=fixture.read_bytes(),
        name="E2E greenness",
        description="Synthetic per-tract values for the end-to-end test.",
        boundary="Tract",
        key_col="tract",
        value_cols=_VALUE_COLS,
        year_col=None,
        value_units={"greenness": "index", "heat_index": "F"},
        uploaded_filename=fixture.name,
    )

    from app.task_manager import create_task, save_config
    meta = create_task(user_id=1, task_name="e2e-custom")
    task_dir = _config.settings.TASKS_DIR / f"task-{meta['id']}"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    shutil.copy(
        Path(__file__).parent / "fixtures" / "patients_5.csv",
        task_dir / "input.csv",
    )
    # What PUT /api/tasks/{id}/config writes after resolving the selection
    # against the caller's library.
    save_config(meta["id"], {
        "experiment": "auto",
        "variables": [manifest["variable_key"]],
        "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
        _lib.TASK_CUSTOM_KEY: {manifest["variable_key"]: manifest},
    })
    return meta["id"], task_dir, manifest


@pytest.mark.integration
def test_e2e_custom_cohort(task_with_custom_exposome):
    task_id, task_dir, manifest = task_with_custom_exposome
    from app.task_manager import start_task, _read_status

    start_task(task_id)
    deadline = time.time() + 1800
    status = {}
    while time.time() < deadline:
        status = _read_status(task_dir)
        if status.get("status") in {"finished", "error", "cancelled"}:
            break
        time.sleep(2)

    assert status.get("status") == "finished", (
        f"task ended as {status.get('status')!r}: {status.get('message')!r}"
    )

    # --- the per-experiment partial, not result.csv ---
    partial = pd.read_csv(task_dir / "output" / "result_custom.csv")
    cohort = pd.read_csv(task_dir / "input.csv")
    assert len(partial) == len(cohort), (
        f"result_custom.csv has {len(partial)} rows for {len(cohort)} cohort rows — "
        "the C4 step produced fewer episodes than the cohort has (empty join?)"
    )

    for col in _VALUE_COLS:
        assert col in partial.columns, f"{col} missing from result_custom.csv"
        filled = partial[col].notna().mean()
        assert filled >= 0.9, (
            f"{col}: only {filled:.0%} of cohort rows carry a value — the "
            "uploaded tract codes did not match the boundary layer"
        )

    # --- values land inside the fixture's bands ---
    lo, hi = _GREENNESS_RANGE
    assert partial["greenness"].min() >= lo and partial["greenness"].max() <= hi, (
        f"greenness {partial['greenness'].min()}–{partial['greenness'].max()} "
        f"outside the fixture's {lo}–{hi}: the join matched the wrong rows"
    )
    lo, hi = _HEAT_RANGE
    assert partial["heat_index"].min() >= lo and partial["heat_index"].max() <= hi

    # --- the merged result carries them too ---
    merged = pd.read_csv(task_dir / "output" / "result.csv")
    assert len(merged) == len(cohort)
    for col in _VALUE_COLS:
        assert col in merged.columns
        assert merged[col].notna().mean() >= 0.9

    # --- the runner reported the real linkage rate ---
    logs = [json.loads(line) for line in
            (task_dir / "logs.jsonl").read_text().splitlines() if line.strip()]
    linkage = [r for r in logs
               if r.get("source") == "merge" and "linked" in str(r.get("msg", ""))]
    assert linkage, "the runner logged no linkage rate for the custom columns"
    assert all("100.0%" in r["msg"] or r["level"] == "info" for r in linkage), linkage


@pytest.mark.integration
def test_custom_c3_shares_the_shipped_tract_cache(task_with_custom_exposome):
    """A custom Tract dataset must produce the same C3 cache key fara_tract
    would, or the sharing this design relies on silently never happens."""
    task_id, task_dir, _manifest = task_with_custom_exposome
    from app.experiments import custom, fara_tract
    from app.experiments.zcta5_cbp import csv_to_parquet

    csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
    config = json.loads((task_dir / "config.json").read_text())
    assert custom._cache_key(task_dir / "input.parquet", "TRACT_FARA", config) == (
        fara_tract._cache_key(task_dir / "input.parquet", fara_tract._C3_STEP, config)
    )
