"""Single-experiment orchestrator: user-uploaded area-level exposures.

Spawned by app.dispatcher as:
    python -m app.experiments.custom run <task_dir> [--variables custom_ab12,...]

Unlike its siblings this runner serves *many* datasets across *four* boundary
layers, so the two things every other runner hard-codes are looked up per
variable instead:

  * the C3 step — taken from the boundary the dataset attaches to, reusing the
    shipped step name, template and cache tag (``TRACT_FARA`` for Tract, ``BG``
    for Block Group, ...). Reusing the tag is the point: a user who has already
    run FARA on this cohort and buffer gets its cached tract weights for free.
    ``_cache_key`` therefore takes the tag as an argument rather than reading a
    module constant.
  * the C4 step — rendered from ``c4/custom_areal.yaml`` with the dataset's own
    join column, value columns and table path, using ``static_areal`` when the
    dataset has no year column and ``yearly_areal`` when it has one. Both
    patterns read a plain table through ``read_table`` because the rendered
    config sets no ``plugin:``.

A RASTER dataset takes the same two steps with two substitutions: its C3 is
``grid_weights`` with the uploaded GeoTIFF as the template grid (step name and
cache tag keyed by the grid's hash, so every year and every dataset on one grid
share one C3), and before its C4 renders, the runner materialises the value
table — ``(grid_id, <col>[, year])`` — from the C3 weights' grid ids and the
pixels under them. From there C4 cannot tell a raster from a polygon.

Dataset definitions come from ``config.json['custom_variables']``, a snapshot
the config endpoint writes after resolving each key against the authenticated
caller's library. The runner never reads the library directly and never needs
to know which user owns the task.

See docs/superpowers/specs/2026-09-21-custom-exposome-design.md.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import inspect
import json
import logging
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

import app.config
from app.experiments import _merge
from app.experiments.bg_ndi_wi import (
    PipelineStep,
    parse_step_progress,  # noqa: F401  (re-exported for symmetry with siblings)
    run_pipeline_step,
    _append_log,
    _is_valid_cached_parquet,
)

_log = logging.getLogger(__name__)

_EXPERIMENT_KEY = "custom"

# boundary -> (C3 step name, C3 template, cache tag). Step name and tag are the
# shipped runners' on purpose so the C3 cache is shared with them.
BOUNDARY_C3: dict[str, tuple[str, str, str]] = {
    "Tract": ("c3_tract_us", "c3/tract_us_demo.yaml", "TRACT_FARA"),
    "BG": ("c3_bg", "c3/bg_us_demo.yaml", "BG"),
    "ZCTA5": ("c3_zcta5", "c3/zcta5_us_demo.yaml", "ZCTA5"),
    "County": ("c3_county_us", "c3/county_us_demo.yaml", "COUNTY"),
}

_C4_TEMPLATE = "c4/custom_areal.yaml"
_C3_GRID_TEMPLATE = "c3/custom_grid.yaml"
_GRID_TAG_PREFIX = "CUSTOMGRID_"


def _sanity_check_pipeline_supports_areal_episode() -> None:
    """Refuse to run against a pipeline whose areal patterns ignore grouping.

    static_areal feeds resolve_output_grouping into
    DurationWeightedSpec.group_by_episode; left at the "patient" default it
    emits one row per PATID, _merge.write_partial then finds no `geoid` to
    rename to `episode_id`, and the merge raises KeyError. ACAG and FAQSD each
    hit this. Same deterministic source grep the other runners use.
    """
    from spacescans.linkage import static_areal_linkage, yearly_areal_linkage
    for module in (static_areal_linkage, yearly_areal_linkage):
        if "output_grouping" not in inspect.getsource(module):
            raise RuntimeError(
                f"custom: live spacescans.linkage.{module.__name__.split('.')[-1]} "
                "does not mention 'output_grouping' — per-episode dispatch is "
                "missing or the pipeline install is stale; refusing to run."
            )


# ---------------------------------------------------------------------------
# dataset definitions
# ---------------------------------------------------------------------------

def custom_variables(config: dict) -> dict[str, dict]:
    """The task's snapshot of the custom datasets it selected."""
    snapshot = config.get("custom_variables") or {}
    if not isinstance(snapshot, dict):
        raise ValueError("config.custom_variables is not a mapping")
    return snapshot


def _definition(config: dict, var_key: str) -> dict:
    try:
        return custom_variables(config)[var_key]
    except KeyError:
        raise ValueError(
            f"{var_key!r} has no definition in config.custom_variables — the "
            "task config was written without resolving it"
        ) from None


def is_raster(definition: dict) -> bool:
    return definition.get("geometry") == "raster"


def grid_tag(definition: dict) -> str:
    return f"{_GRID_TAG_PREFIX}{definition['grid_hash']}"


def c3_step_for(definition: dict | str) -> PipelineStep:
    """The C3 step a dataset needs. Polygons reuse the shipped boundary steps;
    a raster gets one per distinct grid, named by the grid's hash."""
    if isinstance(definition, str):            # a bare boundary name
        definition = {"boundary": definition}
    if is_raster(definition):
        return PipelineStep(
            name=f"c3_customgrid_{definition['grid_hash']}",
            template_relpath=_C3_GRID_TEMPLATE, is_c3=True,
        )
    boundary = definition["boundary"]
    try:
        name, template, _tag = BOUNDARY_C3[boundary]
    except KeyError:
        raise ValueError(
            f"custom exposome on unsupported boundary {boundary!r}; "
            f"expected one of {sorted(BOUNDARY_C3)}"
        ) from None
    return PipelineStep(name=name, template_relpath=template, is_c3=True)


def c4_step_for(var_key: str) -> PipelineStep:
    return PipelineStep(
        name=f"c4_{var_key}", template_relpath=_C4_TEMPLATE, is_c3=False
    )


def _parquet_map(variables: list[str]) -> dict[str, str]:
    return {v: f"{c4_step_for(v).name}.parquet" for v in variables}


# ---------------------------------------------------------------------------
# plan / render
# ---------------------------------------------------------------------------

def plan(config: dict) -> list[PipelineStep]:
    """One C3 per distinct boundary, then one C4 per variable.

    Two datasets on the same boundary share a single C3 step; the C4 steps run
    against the one weights parquet it produces.
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")

    steps: list[PipelineStep] = []
    seen_c3: set[str] = set()
    for var_key in variables:
        c3 = c3_step_for(_definition(config, var_key))
        if c3.name not in seen_c3:
            seen_c3.add(c3.name)
            steps.append(c3)
    for var_key in variables:
        steps.append(c4_step_for(var_key))
    return steps


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read the template, inject task- and dataset-specific fields, write it."""
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]

    if step.is_c3 and step.template_relpath == _C3_GRID_TEMPLATE:
        # A raster dataset: the uploaded GeoTIFF is the template grid. Any
        # dataset on this grid (this one, or another year of it) rendered the
        # same step, so the first raster of the first such dataset will do.
        definition = _first_definition_for_grid(user_config, step.name)
        cfg["source"]["file"] = definition["rasters"][0]["path"]
        cfg["buffer"]["grid_id_offset"] = 0
    elif step.is_c3:
        # The boundary templates are the shipped ones; source.file stays
        # relative so the pipeline CLI resolves it against --data-dir.
        # raster_res_m drives boundary_overlap_fast's rasterisation and is part
        # of the cache key, so it must be injected exactly as the shipped
        # polygon runners do or this step would both mis-render and miss their
        # cached weights.
        cfg["buffer"]["raster_res_m"] = user_config["buffer"]["raster_res_m"]
    else:
        var_key = step.name[len("c4_"):]
        definition = _definition(user_config, var_key)
        c3_name = c3_step_for(definition).name
        c3_parquet = task_dir / "output" / f"{c3_name}.parquet"

        if is_raster(definition):
            # Materialise (grid_id, <col>[, year]) from the pixels under the
            # cohort's cells; from here on C4 is identical to a polygon run.
            values_path = _materialise_raster_values(task_dir, var_key, definition, c3_parquet)
        else:
            values_path = definition["values_path"]

        cfg["linkage_pattern"] = (
            "yearly_areal" if definition.get("year_col") else "static_areal"
        )
        cfg["source"] = {
            "file": str(c3_parquet),
            "join_col": definition["join_col"],
        }
        exposure = {
            "file": str(values_path),
            "join_col": definition["key_col"],
            "value_cols": list(definition["value_cols"]),
        }
        if definition.get("year_col"):
            exposure["year_col"] = definition["year_col"]
        cfg["exposure"] = exposure

        years = definition.get("coverage_years") or [2013, 2019]
        cfg.setdefault("time", {})
        cfg["time"]["years"] = list(range(int(years[0]), int(years[1]) + 1))
        cfg["time"]["temporal_resolution"] = "yearly"
        cfg["time"]["temporal_mode"] = "yearly"

    # Never optional: "patient" collapses a patient's episodes into one row and
    # the merge then cannot find geoid to rename to episode_id.
    cfg.setdefault("time", {})
    cfg["time"]["output_grouping"] = "episode"
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def _first_definition_for_grid(config: dict, c3_step_name: str) -> dict:
    for var_key in config.get("variables", []):
        d = _definition(config, var_key)
        if is_raster(d) and c3_step_for(d).name == c3_step_name:
            return d
    raise ValueError(f"no raster dataset in the selection renders {c3_step_name}")


def _materialise_raster_values(
    task_dir: Path, var_key: str, definition: dict, c3_parquet: Path,
) -> Path:
    """Write the C4 value table for a raster dataset: one row per grid cell the
    cohort's buffers touch (per year, for a yearly dataset), with the pixel
    value under it. NaN where the pixel is nodata.

    Only the cells in the C3 weights are read, so the table is a few thousand
    rows however large the national raster is.
    """
    import numpy as np
    import pandas as pd
    from app import raster_values

    weights = pd.read_parquet(c3_parquet, columns=["grid_id"])
    grid_ids = np.sort(weights["grid_id"].dropna().astype("int64").unique())
    col = definition["value_cols"][0]
    band = int(definition.get("band", 1))
    nodata = (definition.get("grid") or {}).get("nodata")

    frames = []
    for raster in definition["rasters"]:
        vals = raster_values.extract_values(raster["path"], grid_ids, band=band, nodata=nodata)
        frame = pd.DataFrame({"grid_id": grid_ids, col: vals})
        if raster.get("year") is not None:
            frame["year"] = int(raster["year"])
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)

    out = task_dir / "output" / f"values_{var_key}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(out, index=False)
    _append_log(task_dir, "info", f"c4_{var_key}",
                f"materialised {len(table):,} (grid_id{', year' if 'year' in table else ''}) "
                f"rows from {len(definition['rasters'])} raster(s); "
                f"{int(table[col].isna().sum()):,} nodata")
    return out


# ---------------------------------------------------------------------------
# status / cache plumbing (mirrors the sibling runners)
# ---------------------------------------------------------------------------

def _write_status(task_dir: Path, **fields) -> None:
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **fields)


def _write_slot_status(task_dir: Path, **slot_fields) -> None:
    _write_status(task_dir, experiments={_EXPERIMENT_KEY: slot_fields})


def _hash_input_parquet(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, boundary_tag: str, user_config: dict) -> str:
    """``<sha8>__<boundary tag>__b<buffer>m__r<raster>m`` — byte-for-byte the
    format the shipped polygon runners use.

    Every part matters. The tag is an argument rather than a module constant
    because this runner serves four boundaries, and matching the shipped tag is
    what lets a custom Tract variable reuse FARA's cached weights. The raster
    suffix is equally load-bearing: bg_ndi_wi and fara_tract both append it, so
    omitting it here would compute a key that can never match theirs — the
    cache sharing this design is built on would silently never happen.

    The uploaded CSV deliberately does NOT enter the key: it is read only by
    C4, and C4 is never cached.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    if boundary_tag.startswith(_GRID_TAG_PREFIX):
        # grid_weights does not rasterise the buffer, so — like the shipped grid
        # runners (temis, vnl, noise) — no __r suffix. The grid hash in the tag
        # is what keeps two different uploaded grids apart.
        return f"{sha[:8]}__{boundary_tag}__b{buf}m"
    raster = user_config["buffer"]["raster_res_m"]
    return f"{sha[:8]}__{boundary_tag}__b{buf}m__r{raster}m"


def _boundary_tag_for_step(step: PipelineStep) -> str | None:
    if step.name.startswith("c3_customgrid_"):
        return _GRID_TAG_PREFIX + step.name[len("c3_customgrid_"):]
    for _boundary, (name, _template, tag) in BOUNDARY_C3.items():
        if name == step.name:
            return tag
    return None


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
    """Delegate to the shared _merge.write_partial.

    task_dir is passed through so the registry overlay resolves the custom
    keys' value_cols from the task's own snapshot.
    """
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key=_EXPERIMENT_KEY,
        variables=variables,
        parquet_map=_parquet_map(variables),
    )


def _raster_diagnosis(task_dir: Path, var_key: str, definition: dict) -> str:
    """For a raster the cells always exist; a poor rate means nodata under the
    cohort, or a cohort outside the raster's extent."""
    import pandas as pd
    try:
        table = pd.read_parquet(task_dir / "output" / f"values_{var_key}.parquet")
    except Exception as exc:  # pragma: no cover
        return f"{var_key}: could not read the materialised values ({exc!r})"
    col = definition["value_cols"][0]
    nodata_share = float(table[col].isna().mean()) if len(table) else 1.0
    b = (definition.get("grid") or {}).get("bounds_wgs84") or [None] * 4
    extent = (f"lon {b[0]:.1f}…{b[2]:.1f}, lat {b[1]:.1f}…{b[3]:.1f}"
              if None not in b else "unknown extent")
    return (
        f"{var_key}: {nodata_share:.0%} of the {table['grid_id'].nunique():,} raster "
        f"cells under the cohort's buffers are nodata (raster extent {extent}). "
        + ("The raster has no data where this cohort lives." if nodata_share > 0.5
           else "Episodes over nodata cells get no value.")
    )


def _report_linkage_rate(task_dir: Path, variables: list[str], config: dict) -> None:
    """Log the share of non-null values per column — the real linkage rate.

    Upload validation can check the shape of a geography key but not its
    membership in the national key universe; this is where the user finds out
    whether their keys actually matched.
    """
    import pandas as pd
    for var_key in variables:
        parquet = task_dir / "output" / _parquet_map([var_key])[var_key]
        if not parquet.exists():
            continue
        try:
            df = pd.read_parquet(parquet)
        except Exception as exc:  # pragma: no cover - diagnostics only
            _append_log(task_dir, "warning", "merge",
                        f"{var_key}: could not read {parquet.name}: {exc!r}")
            continue
        definition = _definition(config, var_key)
        low = False
        for col in definition["value_cols"]:
            if col not in df.columns:
                _append_log(task_dir, "warning", "merge",
                            f"{var_key}: value column {col!r} missing from output")
                continue
            matched = float(df[col].notna().mean()) if len(df) else 0.0
            level = "info" if matched >= 0.5 else "warning"
            low = low or matched < 0.5
            _append_log(
                task_dir, level, "merge",
                f"{var_key}.{col}: {matched:.1%} of episodes linked "
                f"({int(df[col].notna().sum()):,}/{len(df):,})",
            )
        if low:
            _append_log(task_dir, "warning", "merge",
                        _coverage_diagnosis(task_dir, var_key, definition))


def _coverage_diagnosis(task_dir: Path, var_key: str, definition: dict) -> str:
    """Say WHY a custom column linked poorly: which geographies the cohort's
    buffers touched versus which the uploaded file covers.

    "0 % linked" on its own reads as a bug. Almost always it is a file for one
    region run against a cohort from another — 68 Leon County tracts against a
    nationwide demo cohort — and the two sets never overlap. Both sets are at
    hand here (the task's C3 weights and the user's CSV), so name them.
    """
    import pandas as pd
    if is_raster(definition):
        return _raster_diagnosis(task_dir, var_key, definition)
    try:
        c3_name = c3_step_for(definition).name
        weights = pd.read_parquet(task_dir / "output" / f"{c3_name}.parquet")
        touched = set(weights[definition["join_col"]].astype(str))
        uploaded = pd.read_csv(definition["values_path"], dtype=str,
                               usecols=[definition["key_col"]])
        covered = set(uploaded[definition["key_col"]].str.strip())
    except Exception as exc:  # pragma: no cover - diagnostics must never fail a run
        return f"{var_key}: could not compare geographies ({exc!r})"

    def _states(codes: set[str]) -> str:
        counts = pd.Series([c[:2] for c in codes]).value_counts()
        shown = ", ".join(f"{st} ({n})" for st, n in counts.head(6).items())
        more = f", +{len(counts) - 6} more" if len(counts) > 6 else ""
        return f"{len(counts)} state{'s' if len(counts) != 1 else ''}: {shown}{more}"

    common = touched & covered
    return (
        f"{var_key}: the cohort's buffers touch {len(touched):,} distinct "
        f"{definition['boundary']} codes across {_states(touched)}; the uploaded "
        f"file covers {len(covered):,} codes across {_states(covered)}; "
        f"{len(common):,} in common. "
        + ("The file does not cover where this cohort lives — upload values for "
           "those geographies, or run it on a cohort from that region."
           if not common else
           "Episodes outside the file's geographies get no value.")
    )


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Main entry point. Mirrors temis.run, with per-boundary C3 cache tags."""
    _install_cancel_handler(task_dir)
    _sanity_check_pipeline_supports_areal_episode()

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
        dispatcher_driven = variables is not None
        if dispatcher_driven:
            config = {**config, "variables": list(variables)}
        steps = plan(config)
        total_steps = len(steps)

        if dispatcher_driven:
            _write_slot_status(
                task_dir,
                status="running",
                progress=0.0,
                current_step="csv_to_parquet",
                steps=[s.name for s in steps],
                pid=os.getpid(),
                message="Preparing input data",
            )
        else:
            _write_status(
                task_dir,
                status="running",
                progress=0.0,
                message="Preparing input data",
                started_at=datetime.now(timezone.utc).isoformat(),
                pid=os.getpid(),
                experiments={_EXPERIMENT_KEY: {
                    "status": "running",
                    "progress": 0.0,
                    "current_step": "csv_to_parquet",
                    "steps": [s.name for s in steps],
                }},
            )

        try:
            from app.experiments.zcta5_cbp import csv_to_parquet
            csv_to_parquet(task_dir / "input.csv", task_dir / "input.parquet")
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"csv_to_parquet failed: {exc!r}")
            if dispatcher_driven:
                _write_slot_status(task_dir, status="error",
                                   message=f"input conversion failed: {exc}")
            else:
                _write_status(task_dir, status="error",
                              message=f"input conversion failed: {exc}")
            return 1

        for idx, step in enumerate(steps):
            step_progress = idx / total_steps
            if dispatcher_driven:
                _write_slot_status(
                    task_dir,
                    current_step=step.name,
                    progress=step_progress,
                    message=f"Running {step.name} ({idx+1}/{total_steps})",
                )
            else:
                _write_status(
                    task_dir,
                    current_step=step.name,
                    message=f"Running {step.name} ({idx+1}/{total_steps})",
                    progress=step_progress,
                )
            out_parquet = task_dir / "output" / f"{step.name}.parquet"

            cache_path: Path | None = None
            if step.is_c3:
                try:
                    tag = _boundary_tag_for_step(step)
                    cache_key = _cache_key(task_dir / "input.parquet", tag, config)
                    cache_path = app.config.settings.C3_CACHE_DIR / f"{cache_key}.parquet"
                    if _is_valid_cached_parquet(cache_path):
                        out_parquet.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(cache_path, out_parquet)
                        _append_log(task_dir, "info", step.name,
                                    f"cache hit: {cache_key} — skipping pipeline run")
                        cached_progress = (idx + 1) / total_steps
                        if dispatcher_driven:
                            _write_slot_status(
                                task_dir,
                                current_step=step.name,
                                progress=cached_progress,
                                message=f"Reused cached {step.name}",
                            )
                        else:
                            _write_status(
                                task_dir,
                                current_step=step.name,
                                progress=cached_progress,
                                message=f"Reused cached {step.name}",
                            )
                        continue
                except Exception as exc:
                    _append_log(task_dir, "warning", step.name,
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
                    cache_path = None

            try:
                yaml_path = render_yaml(step, task_dir, config)
            except Exception as exc:
                _append_log(task_dir, "error", "runner",
                            f"render_yaml({step.name}) failed: {exc!r}")
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"render failed at {step.name}")
                else:
                    _write_status(task_dir, status="error",
                                  message=f"render failed at {step.name}")
                return 1

            def _on_step_progress(
                frac: float,
                idx=idx,
                step=step,
                dispatcher_driven=dispatcher_driven,
            ) -> None:
                slot_progress = (idx + frac) / total_steps
                msg = (f"Running {step.name} ({idx+1}/{total_steps}) "
                       f"— {int(frac*100)}%")
                if dispatcher_driven:
                    _write_slot_status(task_dir, progress=slot_progress, message=msg)
                else:
                    _write_status(task_dir, progress=slot_progress, message=msg)

            step_start = time.time()
            rc = run_pipeline_step(yaml_path, task_dir, step_name=step.name,
                                   on_progress=_on_step_progress)
            if rc != 0:
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"step {step.name} failed with exit code {rc}")
                else:
                    _write_status(task_dir, status="error",
                                  message=f"step {step.name} failed with exit code {rc}")
                return rc
            if not out_parquet.exists():
                if dispatcher_driven:
                    _write_slot_status(task_dir, status="error",
                                       message=f"step {step.name} produced no output parquet")
                else:
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
                        boundary=_boundary_tag_for_step(step),
                        buffer_m=config["buffer"]["size"],
                        input_row_count=_count_input_rows(task_dir / "input.csv"),
                        wall_clock_seconds=int(time.time() - step_start),
                        file_size_bytes=out_parquet.stat().st_size,
                    )
                    _append_log(task_dir, "info", step.name,
                                f"cache write: {cache_path.name}")
                except OSError as exc:
                    _append_log(task_dir, "warning", step.name,
                                f"cache write failed: {exc!r} — continuing")

        near_done = (total_steps - 0.1) / total_steps
        if dispatcher_driven:
            _write_slot_status(task_dir, current_step="merge",
                               message="Merging variable outputs",
                               progress=near_done)
        else:
            _write_status(task_dir, current_step="merge",
                          message="Merging variable outputs",
                          progress=near_done)
        try:
            _report_linkage_rate(task_dir, config["variables"], config)
            merge_results(task_dir, variables=config["variables"])
        except Exception as exc:
            _append_log(task_dir, "error", "runner", f"merge_results failed: {exc!r}")
            if dispatcher_driven:
                _write_slot_status(task_dir, status="error",
                                   message=f"merge failed: {exc}")
            else:
                _write_status(task_dir, status="error",
                              message=f"merge failed: {exc}")
            return 1

        if dispatcher_driven:
            _write_slot_status(task_dir, progress=1.0, current_step=None,
                               message=f"Completed {total_steps} pipeline steps")
        else:
            _write_status(task_dir, status="finished", progress=1.0,
                          message=f"Completed {total_steps} pipeline steps",
                          experiments={_EXPERIMENT_KEY: {
                              "status": "finished",
                              "progress": 1.0,
                              "current_step": None,
                          }})
        return 0
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _cli_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="custom")
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
