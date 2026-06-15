"""Single-experiment orchestrator: BG boundaries × {NDI, Walkability}.

Spawned by app.task_manager.start_task as:
    python -m app.experiments.bg_ndi_wi run <task_dir>
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

import app.config


@dataclass(frozen=True)
class PipelineStep:
    name: str                # used as filename stem + log "source"
    template_relpath: str    # relative to SPACESCANS_CONFIG_TEMPLATES_DIR
    is_c3: bool              # controls whether to inject raster_res_m


_VARIABLE_TO_STEP = {
    "ndi": PipelineStep(name="c4_ndi", template_relpath="c4/bg_ndi_demo.yaml", is_c3=False),
    "walkability": PipelineStep(name="c4_wi", template_relpath="c4/bg_wi_demo.yaml", is_c3=False),
}

_C3_STEP = PipelineStep(name="c3_bg", template_relpath="c3/bg_us_demo.yaml", is_c3=True)


def plan(config: dict) -> list[PipelineStep]:
    """Compute the ordered pipeline steps for a task.

    The single C3 step always runs first; each selected variable adds one C4
    step in a deterministic order (NDI before Walkability).
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    steps = [_C3_STEP]
    for v in ("ndi", "walkability"):
        if v in variables:
            steps.append(_VARIABLE_TO_STEP[v])
    return steps


# FIPS columns must remain string to preserve leading zeros (e.g. "06" for CA).
_FIPS_STR_COLS = ("state_fips", "county_fips", "tract_geoid", "bg_geoid")


def csv_to_parquet(src: Path, dst: Path) -> None:
    """Convert uploaded CSV to parquet with explicit dtype handling.

    - FIPS columns (state_fips, county_fips, tract_geoid, bg_geoid) are read as
      string to preserve leading zeros that the pipeline's GEOID joins need.
    - startDate / endDate are parsed to datetime64 so downstream code does not
      need to coerce them again.
    - No column renames here; the pipeline's `demo_conus` adapter performs
      renames at runtime (see spacescans/linkage/helpers.py:_adapt_demo_conus).
    """
    # Read header first to determine which optional FIPS columns are present.
    header = pd.read_csv(src, nrows=0).columns.tolist()
    # Use plain `str` (not the "string" extension dtype) so the resulting
    # parquet columns round-trip as object — matches what downstream pipeline
    # code expects for GEOID joins.
    fips_dtypes = {c: str for c in _FIPS_STR_COLS if c in header}

    df = pd.read_csv(src, dtype=fips_dtypes)
    # Parse dates explicitly with errors="raise" so malformed values fail loudly
    # instead of being silently coerced to NaT.
    df["startDate"] = pd.to_datetime(df["startDate"], format="%Y-%m-%d", errors="raise")
    df["endDate"] = pd.to_datetime(df["endDate"], format="%Y-%m-%d", errors="raise")
    dst.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dst, index=False)


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read a pipeline YAML template, inject task-specific fields, write to task dir.

    Only five keys are overwritten; everything else (source.file, exposure.file,
    time.years, engine.backend, etc.) is preserved as-is so the rendered config
    behaves identically to the canonical experiment pipeline.
    """
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    # patient_adapter "demo_conus" stays as-is: our upload schema mirrors the
    # demo cohort's columns, so the adapter's rename + synthetic-geoid logic
    # applies unchanged.
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    if step.is_c3:
        cfg["buffer"]["raster_res_m"] = user_config["buffer"]["raster_res_m"]
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


# Matches both:
#   [overlap_fast] tile 7460/14938 ( 49.9%) ...
#   [overlap]   1600/3221 ( 49.7%)  ...
_PROGRESS_RE = re.compile(
    r"\[(?:overlap|overlap_fast)\]\s+(?:tile\s+)?(\d+)/(\d+)"
)


def parse_step_progress(line: str) -> float | None:
    """Return progress fraction in [0,1] if line contains a tile/iteration count.

    Returns None for non-progress lines (SUMMARY, errors, empty lines, etc.).
    """
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    cur = int(m.group(1))
    total = int(m.group(2))
    if total <= 0:
        return None
    return cur / total


def _append_log(task_dir: Path, level: str, source: str, msg: str) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "source": source,
        "msg": msg,
    }
    with open(task_dir / "logs.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_pipeline_step(yaml_path: Path, task_dir: Path, step_name: str) -> int:
    """Run a single `spacescans run` subprocess, streaming stdout into logs.jsonl.

    Each output line is appended to task_dir/logs.jsonl as a JSON record with
    source=step_name so the UI can filter logs by step. Progress lines are
    parsed for the running step's fractional progress (callers can read the
    most recent value via parse_step_progress).

    Returns the subprocess's exit code.
    """
    cmd = [
        str(app.config.settings.SPACESCANS_PIPELINE_PYTHON),
        str(app.config.settings.SPACESCANS_PIPELINE_CLI),
        "run",
        "--data-dir", str(app.config.settings.SPACESCANS_DATA_DIR),
        str(yaml_path),
    ]
    _append_log(task_dir, "info", "runner", f"spawning {step_name}: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # for clean kill via killpg later
    )

    # Stream stdout line by line.
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line:
            _append_log(task_dir, "info", step_name, line)
    rc = proc.wait()
    _append_log(task_dir, "info" if rc == 0 else "error", "runner",
                f"step {step_name} exit code {rc}")
    return rc


_VARIABLE_PARQUET = {
    "ndi": "c4_ndi.parquet",
    "walkability": "c4_wi.parquet",
}


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Left-join each per-variable parquet onto the original input CSV by PATID.

    Returns the path to the written result.csv. The input CSV is loaded as-is
    so all original metadata columns (startDate, endDate, lon/lat, FIPS) are
    preserved alongside the new exposure columns.
    """
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    for var in variables:
        parquet_name = _VARIABLE_PARQUET[var]
        var_df = pd.read_parquet(task_dir / "output" / parquet_name)
        var_df = var_df.rename(columns={"PATID": "pid"})
        df = df.merge(var_df, on="pid", how="left")

        match_pct = var_df["pid"].isin(df["pid"]).mean() * 100
        if match_pct < 90.0:
            _append_log(task_dir, "warning", "runner",
                        f"merge: {var} matched only {match_pct:.1f}% of patients")

    out = task_dir / "output" / "result.csv"
    df.to_csv(out, index=False)
    return out
