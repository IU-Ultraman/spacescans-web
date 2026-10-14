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
  * the C4 step — rendered from ``c4/custom_areal.yaml`` with the dataset's own
    join column, value columns and table path, using ``static_areal`` when the
    dataset has no year column and ``yearly_areal`` when it has one.

A RASTER dataset takes the same two steps with two substitutions: its C3 is
``grid_weights`` with the uploaded GeoTIFF as the template grid (step name and
cache tag keyed by the grid's hash), and before its C4 renders, the runner
materialises the value table ``(grid_id, <col>[, year])`` from the C3 weights'
grid ids and the pixels under them.

Since tier-2 phase B the domain of this runner lives in ``spacescans.custom``:
the steps and the plan (``catalog.plan("custom", ...)``), rendering
(``catalog.recipes.render_config``), the value table, the legacy cache key and
the diagnostics. The templates come from the package (``catalog.template``).
What stays here is the runner shell: the run lock, status.json / logs.jsonl,
the C3 cache files, and the module-level names the dispatcher, the paper's
scripts and the tests call (``plan``, ``run``, ``_cli_main``, ``render_yaml``,
``_cache_key``, ...).

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
    PipelineStep,  # noqa: F401  (the sibling runners' step type; kept for callers)
    parse_step_progress,  # noqa: F401  (re-exported for symmetry with siblings)
    run_pipeline_step,
    _append_log,
    _is_valid_cached_parquet,
)
from spacescans import catalog as _catalog
from spacescans import custom as _c

_log = logging.getLogger(__name__)

_EXPERIMENT_KEY = "custom"


def _sanity_check_pipeline_supports_areal_episode() -> None:
    """Refuse to run against a pipeline whose areal patterns ignore grouping.

    static_areal feeds resolve_output_grouping into
    DurationWeightedSpec.group_by_episode; left at the "patient" default it
    emits one row per PATID, _merge.write_partial then finds no `geoid` to
    rename to `episode_id`, and the merge raises KeyError. ACAG and FAQSD each
    hit this. The check reads the package's ``episode_grouping`` capability
    flag (what ``spacescans.capabilities()`` reports) instead of grepping the
    linkage modules' source.
    """
    try:
        from spacescans._capabilities import FLAGS
        flags = dict(FLAGS)
    except (ImportError, AttributeError):
        import spacescans
        flags = dict(spacescans.capabilities().get("flags") or {})
    if not flags.get("episode_grouping"):
        raise RuntimeError(
            "custom: the installed spacescans does not report the episode_grouping "
            "capability — per-episode dispatch is missing or the pipeline install is "
            "stale; refusing to run."
        )


# ---------------------------------------------------------------------------
# domain: spacescans.custom (the web's names, for the dispatcher and the tests)
# ---------------------------------------------------------------------------

# boundary -> (C3 step name, C3 template, cache tag). Step name and tag are the
# shipped runners' on purpose so the C3 cache is shared with them.
BOUNDARY_C3 = _c.BOUNDARY_C3
_C4_TEMPLATE = _c.C4_TEMPLATE
_C3_GRID_TEMPLATE = _c.C3_GRID_TEMPLATE
_GRID_TAG_PREFIX = _c.GRID_TAG_PREFIX

custom_variables = _c.definitions_from_config
is_raster = _c.is_raster
grid_tag = _c.grid_tag
c3_step_for = _c.c3_step_for
raster_bands = _c.raster_bands
_parquet_map = _c.parquet_map
_boundary_tag_for_step = _c.boundary_tag_for_step


def _definition(config: dict, var_key: str) -> dict:
    return _c.definition_for(custom_variables(config), var_key)


def c4_step_for(var_key: str):
    return _c.c4_step_for(var_key)


def plan(config: dict):
    """One C3 per distinct boundary or grid, then one C4 per variable.

    Two datasets on the same boundary share a single C3 step; the C4 steps run
    against the one weights parquet it produces.
    """
    return _c.plan(config.get("variables", []), custom_variables(config))


def _uses_raster_res(step) -> bool:
    """A boundary C3 step: boundary_overlap_fast rasterises the buffer at
    ``raster_res_m``, which its YAML and its cache key carry (a grid C3 and
    the C4 steps do not read it)."""
    return bool(step.is_c3) and step.template_relpath != _C3_GRID_TEMPLATE


def _context(task_dir: Path, user_config: dict, step=None):
    buffer = user_config["buffer"]
    # Read strictly where the step needs it, as the runner always did: a
    # config without raster_res_m fails such a step's render with KeyError
    # instead of rendering or keying it with a None resolution.
    raster_res_m = (buffer["raster_res_m"] if step is not None and _uses_raster_res(step)
                    else buffer.get("raster_res_m"))
    return _c.Context(run_dir=task_dir, cohort_parquet=task_dir / "input.parquet",
                      buffer_m=buffer["size"], raster_res_m=raster_res_m,
                      name_suffix=f"_task_{task_dir.name[-8:]}")


def render_yaml(step, task_dir: Path, user_config: dict) -> Path:
    """Render one step's pipeline config from the packaged template and write it.

    For a raster dataset's C4 step this first materialises the value table
    (``output/values_<key>.parquet``) from the C3 weights and logs it, as the
    web always did.
    """
    template = _catalog.template(step.template_relpath)
    ctx = _context(task_dir, user_config, step)
    definitions = custom_variables(user_config)
    for rec in _c.prepare_step(step, ctx, definitions=definitions):
        _append_log(task_dir, rec["level"], rec["source"], rec["msg"])
    cfg = _c.render(step, template, ctx, variables=user_config.get("variables", []),
                    definitions=definitions)
    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def _cache_key(input_parquet: Path, boundary_tag: str, user_config: dict) -> str:
    """``<sha8>__<boundary tag>__b<buffer>m[__r<raster>m]`` — the shipped
    polygon runners' key format (legacy-v1), so a custom Tract variable reuses
    FARA's cached weights; a grid tag gets no ``__r`` part (and needs no
    ``raster_res_m``; a boundary tag without one raises KeyError, as before)."""
    buffer = user_config["buffer"]
    raster_res_m = (None if boundary_tag.startswith(_GRID_TAG_PREFIX)
                    else buffer["raster_res_m"])
    return _c.legacy_cache_key(input_parquet, boundary_tag,
                               buffer_m=buffer["size"], raster_res_m=raster_res_m)


def _report_linkage_rate(task_dir: Path, variables: list[str], config: dict) -> None:
    """Log the share of non-null values per column — the real linkage rate."""
    for rec in _c.diagnostics(task_dir, variables, custom_variables(config)):
        _append_log(task_dir, rec["level"], rec["source"], rec["msg"])


def _coverage_diagnosis(task_dir: Path, var_key: str, definition: dict) -> str:
    return _c.coverage_diagnosis(task_dir, var_key, definition)


def _raster_diagnosis(task_dir: Path, var_key: str, definition: dict) -> str:
    return _c.raster_diagnosis(task_dir, var_key, definition)


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
