"""Single-experiment orchestrator: BG-tagged NHD blue-feature proximity.

Spawned by app.dispatcher as:
    python -m app.experiments.nhd_bluespace run <task_dir> [--variables nhd_bluespace]

Cloned from tiger_proximity.py with the spec-mandated deltas (Sprint 7):
  * _BOUNDARY = 'BG_NHD' (avoids collision with BG / BG_TIGER caches)
  * C3 step c3_nhd_bluespace -> c3/nhd_demo.yaml
  * C4 step c4_nhd_bluespace -> c4/nhd_bluespace_demo.yaml
  * sanity probe greps precomputed_static_linkage for output_grouping
    (Sprint 7 Phase A contract; tiger_proximity grepped precomputed_areal_linkage)
  * render_yaml writes no raster_res_m (NHD is line/poly geometry, no raster).
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

_BOUNDARY = "BG_NHD"
_EXPERIMENT_KEY = "nhd_bluespace"

_C3_STEP = PipelineStep(
    name="c3_nhd_bluespace",
    template_relpath="c3/nhd_demo.yaml",
    is_c3=True,
)

_VARIABLE_TO_STEP = {
    "nhd_bluespace": PipelineStep(
        name="c4_nhd_bluespace",
        template_relpath="c4/nhd_bluespace_demo.yaml",
        is_c3=False,
    ),
}

_PARQUET_MAP = {"nhd_bluespace": "c4_nhd_bluespace.parquet"}


def _sanity_check_pipeline_supports_precomputed_static_episode() -> None:
    """Spec R3 layer (b): grep live pipeline source for episode dispatch.

    Sprint 7 Phase A added output_grouping dispatch (via resolve_output_grouping)
    to precomputed_static_linkage.py. If the editable-installed wheel is stale
    and still hard-codes ``GROUP BY PATID``, the runner would silently emit
    patient-level rows and _merge.write_partial would collapse one-to-many on
    episode_id. Detect that drift at runner start with a deterministic
    substring grep.

    Note: we grep for "output_grouping" (the dispatch keyword) rather than
    "episode" (which appears in many docstrings) — mirroring the tiger_proximity
    Sprint 5 probe style (T6 fix pattern).
    """
    from spacescans.linkage import precomputed_static_linkage
    src = inspect.getsource(precomputed_static_linkage)
    if "output_grouping" not in src:
        raise RuntimeError(
            "nhd_bluespace: live spacescans.linkage.precomputed_static_linkage "
            "does not mention 'output_grouping' — Phase A output_grouping dispatch "
            "is missing or pipeline editable install is stale; refusing to run."
        )


def plan(config: dict) -> list[PipelineStep]:
    """Always emits [c3_nhd_bluespace, c4_nhd_bluespace].

    nhd_bluespace has a single variable with five value_cols emitted by a
    single C4 parquet — so the plan is deterministic.
    """
    variables = config.get("variables", [])
    if not variables:
        raise ValueError("at least one variable must be selected")
    unknown = [v for v in variables if v not in _VARIABLE_TO_STEP]
    if unknown:
        raise ValueError(f"unknown variable(s): {', '.join(unknown)}")
    return [_C3_STEP, _VARIABLE_TO_STEP["nhd_bluespace"]]


def render_yaml(step: PipelineStep, task_dir: Path, user_config: dict) -> Path:
    """Read pipeline YAML template, inject task-specific fields, write to task dir.

    Two structural divergences from bg_ndi_wi.render_yaml / zcta5_cbp.render_yaml:
      1. No raster_res_m write — NHD templates have no such key (line/poly).
      2. On the C4 step only, rewrite cfg['exposure']['file'] to point at the
         per-task C3 parquet output (precomputed_static reads it as the
         exposure table). The C3 step needs no source.file rewrite — the
         pipeline CLI's --data-dir SPACESCANS_DATA_DIR arg resolves the
         relative data_full/NHD/C4/... path.
    """
    template_path = (
        app.config.settings.SPACESCANS_CONFIG_TEMPLATES_DIR / step.template_relpath
    )
    cfg = yaml.safe_load(template_path.read_text())

    task_id_short = task_dir.name[-8:]
    cfg["name"] = f"{cfg['name']}_task_{task_id_short}"
    cfg["buffer"]["patient_file"] = str(task_dir / "input.parquet")
    cfg["buffer"]["buffer_m"] = user_config["buffer"]["size"]
    # NOTE: no raster_res_m write (NHD is line/poly geometry).

    if step.is_c3:
        # C3: pipeline CLI --data-dir resolves source.file; no rewrite here.
        pass
    else:
        # C4: rewrite exposure.file to point at this task's C3 output.
        # Spec R4 mitigation: guard against unexpected exposure shape.
        if not isinstance(cfg.get("exposure"), dict):
            raise RuntimeError(
                "nhd_bluespace.render_yaml: unexpected exposure: shape in C4 template"
            )
        cfg["exposure"]["file"] = str(
            task_dir / "output" / f"{_C3_STEP.name}.parquet"
        )

    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"  # Sprint 7 Phase A contract
    cfg["output"]["path"] = str(task_dir / "output" / f"{step.name}.parquet")

    out = task_dir / "pipeline_configs" / f"{step.name}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def _write_status(task_dir: Path, **fields) -> None:
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **fields)


def _write_slot_status(task_dir: Path, **slot_fields) -> None:
    """Write per-experiment-slot fields (progress / current_step / status / message)."""
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, experiments={_EXPERIMENT_KEY: slot_fields})


def _hash_input_parquet(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(input_parquet: Path, step: PipelineStep, user_config: dict) -> str:
    """Format: ``<sha8>__BG_NHD__b<buffer>m`` — no raster suffix, no year.

    Boundary tag BG_NHD avoids collision with bg_ndi_wi's BG cache and
    tiger_proximity's BG_TIGER cache for the same input parquet + buffer.
    """
    sha = _hash_input_parquet(input_parquet)
    buf = user_config["buffer"]["size"]
    return f"{sha[:8]}__{_BOUNDARY}__b{buf}m"


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

    _PARQUET_MAP has a single entry (nhd_bluespace -> one parquet); the
    merge picks up all five value_cols (dist_flow_m, dist_water_m, dist_area_m,
    dist_coast_m, dist_blue_m) from variable_registry.get_variable.
    """
    parquet_map = {v: _PARQUET_MAP[v] for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="nhd_bluespace",
        variables=variables,
        parquet_map=parquet_map,
    )


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Main entry point. Mirrors tiger_proximity.run with an override `variables`."""
    _install_cancel_handler(task_dir)
    _sanity_check_pipeline_supports_precomputed_static_episode()

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
            # csv_to_parquet handled by zcta5_cbp's shared implementation —
            # nhd_bluespace has no FIPS-string columns beyond the BG/ZCTA5
            # set already covered there. Import locally to avoid a module
            # cycle at boot time.
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
                    cache_key = _cache_key(task_dir / "input.parquet", step, config)
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
                        boundary=_BOUNDARY,
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
    parser = argparse.ArgumentParser(prog="nhd_bluespace")
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
