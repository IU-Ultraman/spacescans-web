"""Single-experiment orchestrator: BG boundaries × {NDI, Walkability}.

Spawned by app.task_manager.start_task as:
    python -m app.experiments.bg_ndi_wi run <task_dir>
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import yaml

import app.config

_log = logging.getLogger(__name__)


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
# NDI is dual-vintage: it also needs 2020-Census BG weights (TIGER 2024
# shapefiles) for exposure rows tagged bg_vintage=2020. Walkability does not.
_C3_STEP_2020 = PipelineStep(name="c3_bg_2020", template_relpath="c3/bg_us_2020_demo.yaml", is_c3=True)

# Sprint 3 B15: per-runner boundary tag baked into the C3 cache key.
_BOUNDARY = "BG"


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
    if "ndi" in variables:
        steps.append(_C3_STEP_2020)  # NDI dual-vintage: also build 2020 BG weights
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
    - Adds a deterministic ``episode_id = range(len(df))`` column so the
      pipeline's ``_adapt_demo_conus`` can use it as the per-row geoid and
      ``merge_results`` can later reconstruct the same id to join back. If the
      uploaded CSV already carries an ``episode_id`` column, it is overwritten
      and a warning is logged.
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
    if "episode_id" in df.columns:
        _log.warning(
            "input.csv carried an episode_id column; overwriting with "
            "deterministic row-index ids (Sprint 2 invariant)."
        )
    df["episode_id"] = range(len(df))
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
    else:
        # C4: rewrite source.file (the C3 weights table) to THIS task's C3
        # output, so C4 area-weights the uploaded cohort's episodes — not the
        # pre-built demo weight table the template ships with. Parity fix:
        # matches the noise/fara/nhd/vnl/temis runners; bg_ndi_wi previously
        # left source.file pointing at the demo weights (wrong for real cohorts).
        # NOTE: source_2020 (NDI dual-vintage) is handled separately.
        if not isinstance(cfg.get("source"), dict):
            raise RuntimeError(
                "bg_ndi_wi.render_yaml: unexpected source shape in C4 template"
            )
        cfg["source"]["file"] = str(task_dir / "output" / f"{_C3_STEP.name}.parquet")
        # NDI's dual-vintage C4 also reads source_2020 (the 2020 BG weights);
        # rewrite it to the per-task 2020 C3 output.
        if isinstance(cfg.get("source_2020"), dict):
            cfg["source_2020"]["file"] = str(
                task_dir / "output" / f"{_C3_STEP_2020.name}.parquet"
            )
    if "time" in cfg:
        cfg["time"]["output_grouping"] = "episode"  # Sprint 2: keep per-episode rows; web pipes episode_id via _adapt_demo_conus
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


def run_pipeline_step(
    yaml_path: Path,
    task_dir: Path,
    step_name: str,
    on_progress: "Callable[[float], None] | None" = None,
) -> int:
    """Run a single `spacescans run` subprocess, streaming stdout into logs.jsonl.

    Each output line is appended to task_dir/logs.jsonl as a JSON record with
    source=step_name so the UI can filter logs by step. If `on_progress` is
    provided, it is called whenever a stdout line parses as a progress fraction
    via parse_step_progress — the caller (typically run()) maps that to a
    global progress update in status.json.

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
            if on_progress is not None:
                frac = parse_step_progress(line)
                if frac is not None:
                    on_progress(frac)
    rc = proc.wait()
    _append_log(task_dir, "info" if rc == 0 else "error", "runner",
                f"step {step_name} exit code {rc}")
    return rc


_VARIABLE_PARQUET = {
    "ndi": "c4_ndi.parquet",
    "walkability": "c4_wi.parquet",
}


def merge_results(task_dir: Path, variables: list[str]) -> Path:
    """Delegate to shared _merge.write_partial; return the partial path.

    Sprint 4 F6: dropped the inline _merge.fan_in safety net. The dispatcher's
    post-experiment loop (dispatcher.py:168-174) runs the final fan_in over the
    completed experiment list, so result.csv is produced exactly once per task.
    Both runners' merge_results are now symmetric (zcta5_cbp.merge_results
    likewise returns write_partial's path).
    """
    from app.experiments import _merge
    parquet_map = {v: f"{_VARIABLE_TO_STEP[v].name}.parquet" for v in variables}
    return _merge.write_partial(
        task_dir=task_dir,
        experiment_key="bg_ndi_wi",
        variables=variables,
        parquet_map=parquet_map,
    )


def _write_status(task_dir: Path, **fields) -> None:
    """Delegates to the atomic task_manager._write_status (Sprint 3 T8).

    Sprint 3 final-review fix: this used to be a private non-atomic write
    that competed with the dispatcher's _write_status and produced corrupt
    status.json under contention. Both runners now go through the same
    flock-protected writer that derives the flat top-level fields from
    each experiment slot.
    """
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, **fields)


# Sprint 3 final-review fix: when invoked by the dispatcher (variables override),
# this runner is exactly one slot in status.json["experiments"][_EXPERIMENT_KEY].
# Its progress / current_step writes must land in that slot (not at the
# top-level) so _derive_flat_fields can aggregate across all experiments.
_EXPERIMENT_KEY = "bg_ndi_wi"


def _write_slot_status(task_dir: Path, **slot_fields) -> None:
    """Write per-experiment-slot fields (progress / current_step / status / message).

    Used in dispatcher-driven runs to populate experiments[bg_ndi_wi].* so the
    atomic writer's _derive_flat_fields produces correct top-level progress
    + current_step instead of clobbering them with 0.0 / None.
    """
    from app.task_manager import _write_status as tm_write
    tm_write(task_dir, experiments={_EXPERIMENT_KEY: slot_fields})


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
    boundary = "BG2020" if step.name == _C3_STEP_2020.name else _BOUNDARY
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


def _install_cancel_handler(task_dir: Path) -> None:
    """Install a SIGTERM handler that writes status="cancelled" before exit.

    task_manager.stop_task sends SIGTERM to this orchestrator's process group.
    Without this handler the process would die silently and recover_orphaned_tasks
    would later mistakenly mark the task as "error" — but the user actively
    cancelled, so the correct terminal status is "cancelled".

    We raise SystemExit (rather than calling os._exit) so the `finally` block in
    run() that releases .run_lock still executes.
    """
    def _handler(_signum, _frame):
        _write_status(
            task_dir,
            status="cancelled",
            message="Task cancelled by user",
        )
        _append_log(task_dir, "info", "runner", "received SIGTERM — task cancelled")
        # Re-raise so subprocess + cleanup finally{} blocks still run.
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, _handler)


def _write_cache_meta(path: Path, **fields) -> None:
    """Write a JSON sidecar describing a cache entry."""
    fields.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(fields, indent=2))


def _count_input_rows(input_csv: Path) -> int:
    """Cheap row count — used only for the meta sidecar."""
    with open(input_csv) as f:
        next(f, None)  # header
        return sum(1 for _ in f)


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Main entry point for an experiment run.

    Holds .run_lock for the duration of the run so concurrent task spawns are
    blocked. The kernel releases the lock when this process exits, so a
    sequential second task can acquire it without waiting for any cleanup in
    the parent FastAPI process.

    Reads task_dir/config.json, drives the C3 + C4 pipeline steps, merges the
    per-variable outputs, and writes status.json + logs.jsonl + output/result.csv.
    Returns 0 on success, non-zero on any step failure.

    When ``variables`` is provided (by the Sprint 3 dispatcher), it overrides
    the config-file variables list so a multi-experiment dispatch routes only
    this runner's subset here. This lets the dispatcher pass a config with
    foreign variables (e.g. ``cbp_zcta5``) without ``plan()`` rejecting them.
    """
    # Install SIGTERM handler first — must be in place before any blocking work
    # so that stop_task can cleanly cancel us at any point during the run.
    _install_cancel_handler(task_dir)
    # Acquire .run_lock for the lifetime of this orchestrator process.
    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lock_fd = os.open(str(lock_path), os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Should not normally happen — task_manager.start_task pre-checks the
        # lock — but handle the TOCTOU race by failing loudly.
        _write_status(
            task_dir,
            status="error",
            message="another task acquired the run lock first; retry shortly",
        )
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
            # Dispatcher already seeded experiments[bg_ndi_wi].steps; we only
            # update our own slot's status / current_step / progress so the
            # atomic writer's _derive_flat_fields produces the right
            # task-level steps + progress.
            _write_slot_status(
                task_dir,
                status="running",
                progress=0.0,
                current_step="csv_to_parquet",
                steps=[step.name for step in steps],
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
                    "steps": [step.name for step in steps],
                }},
            )

        try:
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

            # C3 cache check
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
                        continue  # skip subprocess entirely
                except Exception as exc:
                    _append_log(task_dir, "warning", step.name,
                                f"cache check failed for {step.name}: {exc!r} — running fresh")
                    cache_path = None  # disable write-back too

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
                # Map the step's internal [0,1] progress to the global
                # progress bar position (this step's slot + frac within it).
                slot_progress = (idx + frac) / total_steps
                msg = (f"Running {step.name} ({idx+1}/{total_steps}) "
                       f"— {int(frac*100)}%")
                if dispatcher_driven:
                    _write_slot_status(task_dir, progress=slot_progress,
                                       message=msg)
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

        # When invoked by the Sprint 3 dispatcher (variables override supplied),
        # leave the top-level ``status`` to the dispatcher: it must own the
        # task-level lifecycle so a polling client doesn't observe a transient
        # ``finished`` between the per-experiment runner finishing and the
        # dispatcher's fan_in writing the merged result.csv. We DO populate our
        # own slot's progress=1.0 + current_step=None so the atomic writer can
        # aggregate a correct top-level progress + steps[] from the per-slot
        # fields.
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
        # Kernel releases the lock on process exit, but be explicit on the
        # success path too so a long-lived test runner (e.g. pytest) that
        # imports this module and calls run() in-process doesn't leak the fd.
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _cli_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="bg_ndi_wi")
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
