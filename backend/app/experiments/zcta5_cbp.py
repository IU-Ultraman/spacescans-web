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

        # When invoked by the Sprint 3 dispatcher (variables override supplied),
        # leave the top-level ``status`` to the dispatcher: it must own the
        # task-level lifecycle so a polling client doesn't observe a transient
        # ``finished`` between the per-experiment runner finishing and the
        # dispatcher's fan_in writing the merged result.csv.
        if variables is None:
            _write_status(task_dir, status="finished", progress=1.0,
                          message=f"Completed {total_steps} pipeline steps")
        else:
            _write_status(task_dir, progress=1.0,
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
