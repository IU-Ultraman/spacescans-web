"""Single-experiment orchestrator: BG boundaries × {NDI, Walkability}.

Spawned by app.task_manager.start_task as:
    python -m app.experiments.bg_ndi_wi run <task_dir>
"""
from __future__ import annotations

from dataclasses import dataclass
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
