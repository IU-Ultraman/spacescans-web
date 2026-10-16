"""The one runner behind the 11 ``app.experiments.<exp>`` shims (tier-2 phase C, design §5 W2).

Each shim keeps its module name and three names (``plan``, ``run``, ``_cli_main``)
because the dispatcher imports the module by its experiment key and the paper's
scripts call ``python -m app.experiments.<exp> run <task_dir> --variables a,b``.
Everything the runners used to share by copy lives here, on top of the package:

* the plan comes from ``spacescans.catalog.plan`` (the recipes carry each runner's
  steps, templates, cache tags and merge table);
* the cohort is converted with ``spacescans.cohort.to_pipeline_parquet(variant=
  recipe.cohort_variant, pid_as_str=False)`` - byte for byte the web's
  ``csv_to_parquet``, which the legacy cache keys hash;
* the steps run through ``spacescans.orchestrate.run_source`` with the web's cache
  (``WeightCache(settings.C3_CACHE_DIR, key_format="legacy-v1")``) and the web's
  spawn command (``SubprocessExecutor([PIPELINE_PYTHON, PIPELINE_CLI])``), so the
  rendered YAML, the cache keys and metas and the ``spawning ...`` lines are the
  runners' own;
* the partial is ``orchestrate.partial_from_dir(..., rewrite_in_place=True)``
  written to ``output/result_<exp>.csv``;
* ``logs.jsonl`` is written by ``orchestrate.LogWriter`` (the log strings are
  defined once, in ``spacescans.orchestrate.events``), and ``status.json`` by
  :class:`StatusSink` with the runners' progress formula: start ``idx/total``,
  running ``(idx+frac)/total``, cache hit ``(idx+1)/total``, merge
  ``(total-0.1)/total``, end ``1.0``, through ``app.task_manager._write_status``.

What stays exactly as in web 3991c3b: the run lock ``DATA_DIR/.run_lock`` and its
message (``another task acquired the run lock first; retry shortly``, which the
paper's ``independent_impl_chain.sh`` greps for), the SIGTERM handler (status
``cancelled`` + ``received SIGTERM`` log line + exit 143), the status messages
and exit codes, and the order of variables (as received: ``walkability,ndi``
still works and still orders the partial's columns).

Phase D: ``config["output_level"]`` (``app.output_level``) picks one row per participant
or per location episode. Episode level is the run above, unchanged; participant level asks
the package for per-participant C4 output (``output_level.run_context`` /
``source_kwargs``, refused with a status message when the installed spacescans cannot) and
writes a per-participant partial (``output_level.participant_partial``). A config without
the key predates phase D and runs per episode.

Logs and status carry step names, counts, exit codes and cache keys, never a
cohort value. When the cohort's dates cannot be parsed, the ``csv_to_parquet
failed: ...`` log line and the ``input conversion failed: ...`` status message keep
0.2.7's form, but the "Unrecognized date format" message in them no longer quotes
the file's first date (PRIV-2, 2026-10-14; likewise the upload check's).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app.config
from app import output_level
from spacescans import catalog, cohort
from spacescans.orchestrate import (
    LOG_CACHE_CHECK_FAILED,
    LOG_COHORT_FAILED,
    LOG_MERGE_FAILED,
    LOG_RENDER_FAILED,
    LOG_SIGTERM,
    Event,
    LogWriter,
    RenderError,
    RunLock,
    RunLockBusy,
    StepFailed,
    SubprocessExecutor,
    WeightCache,
    partial_csv_name,
    partial_from_dir,
    run_source,
    tee,
)
from spacescans.orchestrate.locks import RUN_LOCK_BUSY

__all__ = [
    "RUN_LOCK_BUSY",
    "StatusSink",
    "cli_main",
    "custom_definitions",
    "install_cancel_handler",
    "merge_results",
    "parse_cli",
    "plan",
    "run",
]

#: The config key holding the task's custom-exposome definitions (``config.json``).
CUSTOM_KEY = "custom_variables"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def custom_definitions(experiment: str, config: Mapping[str, Any]) -> dict[str, dict] | None:
    """The task's custom-dataset definitions when ``experiment`` is the dynamic one, else None."""
    if not catalog.recipe(experiment).dynamic:
        return None
    from spacescans.custom import definitions_from_config

    return definitions_from_config(config)


def plan(experiment: str, config: Mapping[str, Any]) -> list:
    """The ordered steps of ``experiment`` for ``config["variables"]`` (the runner's ``plan()``).

    Same list, order and errors as web 3991c3b: ``ValueError`` for an empty
    selection (``at least one variable must be selected``) or a key the
    experiment does not run (``unknown variable(s): ...``); for ``custom``,
    the definitions come from ``config["custom_variables"]``. Each step has
    ``name``, ``is_c3`` and ``template_relpath`` as the old ``PipelineStep`` did.
    """
    return catalog.plan(experiment, list(config.get("variables") or []),
                        overlay=custom_definitions(experiment, config))


# ---------------------------------------------------------------------------
# status.json and the SIGTERM handler (the web's task bookkeeping)
# ---------------------------------------------------------------------------

def _write_status(task_dir: Path, **fields: Any) -> None:
    """The task manager's atomic, experiments-aware writer (imported when called, as the runners did)."""
    from app.task_manager import _write_status as tm_write

    tm_write(task_dir, **fields)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StatusSink:
    """Turns the run's events into the runners' ``status.json`` writes.

    ``dispatcher_driven`` (``--variables`` given) writes this runner's slot,
    ``experiments[<exp>]``, and leaves the task-level status to the dispatcher;
    a standalone run writes the top-level fields as well. Messages, progress
    values and field sets are the runners' (``bg_ndi_wi.py:436-640``).
    """

    def __init__(self, task_dir: Path, experiment: str, *, dispatcher_driven: bool):
        self.task_dir = Path(task_dir)
        self.experiment = experiment
        self.dispatcher_driven = dispatcher_driven

    # -- the two write shapes ------------------------------------------------

    def slot(self, **fields: Any) -> None:
        """Progress-type fields: into the slot when dispatched, else top level."""
        if self.dispatcher_driven:
            _write_status(self.task_dir, experiments={self.experiment: fields})
        else:
            _write_status(self.task_dir, **fields)

    # -- lifecycle -----------------------------------------------------------

    def begin(self, step_names: Sequence[str]) -> None:
        steps = list(step_names)
        if self.dispatcher_driven:
            self.slot(status="running", progress=0.0, current_step="csv_to_parquet",
                      steps=steps, pid=os.getpid(), message="Preparing input data")
        else:
            _write_status(self.task_dir, status="running", progress=0.0,
                          message="Preparing input data", started_at=_now(), pid=os.getpid(),
                          experiments={self.experiment: {
                              "status": "running", "progress": 0.0,
                              "current_step": "csv_to_parquet", "steps": steps}})

    def error(self, message: str) -> None:
        self.slot(status="error", message=message)

    def merging(self, total: int) -> None:
        self.slot(current_step="merge", message="Merging variable outputs",
                  progress=(total - 0.1) / total)

    def finish(self, total: int) -> None:
        message = f"Completed {total} pipeline steps"
        if self.dispatcher_driven:
            self.slot(progress=1.0, current_step=None, message=message)
        else:
            _write_status(self.task_dir, status="finished", progress=1.0, message=message,
                          experiments={self.experiment: {
                              "status": "finished", "progress": 1.0, "current_step": None}})

    # -- events ----------------------------------------------------------------

    def __call__(self, ev: Event) -> None:
        if ev.index is None or not ev.total:
            return
        idx, total, step = ev.index, ev.total, ev.step
        if ev.kind == "step_start":
            self.slot(current_step=step, progress=idx / total,
                      message=f"Running {step} ({idx + 1}/{total})")
        elif ev.kind == "progress" and ev.frac is not None:
            self.slot(progress=(idx + ev.frac) / total,
                      message=f"Running {step} ({idx + 1}/{total}) — {int(ev.frac * 100)}%")
        elif ev.kind == "cache_hit":
            self.slot(current_step=step, progress=(idx + 1) / total,
                      message=f"Reused cached {step}")


def install_cancel_handler(task_dir: Path) -> None:
    """SIGTERM (``task_manager.stop_task``) -> status ``cancelled``, one log line, exit 143.

    ``SystemExit`` is raised rather than ``os._exit`` so ``run()``'s ``finally``
    releases the run lock; the step executor kills the step's process group on
    the way out (the 0.2.7 runners left it running).
    """
    task_dir = Path(task_dir)

    def _handler(_signum: int, _frame: Any) -> None:
        _write_status(task_dir, status="cancelled", message="Task cancelled by user")
        LogWriter.for_run_dir(task_dir).write("info", "runner", LOG_SIGTERM)
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, _handler)


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def merge_results(experiment: str, task_dir: Path, variables: Sequence[str], *,
                  definitions: Mapping[str, Mapping[str, Any]] | None = None,
                  log: LogWriter | None = None, level: str | None = None) -> Path:
    """Write ``output/result_<experiment>.csv`` (the runner's ``merge_results``).

    Episode level: ``orchestrate.partial_from_dir``'s table (through
    ``_merge.episode_partial``, which spells numeric C4 ids as input.csv does) with
    the recipe's merge table and value columns, FAQSD's renames written back into its C4 parquet
    (``rewrite_in_place``), and the ``merge_partial_low_match_pct`` record in
    ``logs.jsonl`` when fewer than 90% of episodes got a value. Participant level:
    ``output_level.participant_partial`` with the same table, renames and record,
    counted in participants. ``level`` defaults to the task's configured level.
    """
    task_dir = Path(task_dir)
    rec = catalog.recipe(experiment)
    keys = list(variables)
    level = output_level.of_task(task_dir) if level is None else output_level.normalize(level)
    value_cols = {k: list(catalog.variable(k, overlay=definitions).value_cols) for k in keys}
    if level == output_level.PARTICIPANT:
        table, stats = output_level.participant_partial(
            task_dir, experiment, keys, rec.output_map(keys), value_cols,
            renames=dict(rec.renames) or None, rewrite_in_place=rec.rename_in_place)
    else:
        # partial_from_dir's table, with numeric cohort ids that reached C4 as numbers
        # joined back to input.csv's text (app/experiments/_merge.episode_partial).
        from app.experiments._merge import episode_partial

        table, stats = episode_partial(task_dir, experiment, keys, rec.output_map(keys),
                                       value_cols, renames=dict(rec.renames) or None,
                                       rewrite_in_place=rec.rename_in_place)
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if stats.low:
        (log or LogWriter.for_run_dir(task_dir)).record(**stats.as_log_fields())
    out = out_dir / partial_csv_name(experiment)
    table.to_csv(out, index=False)
    return out


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _check_pipeline() -> None:
    """Refuse a pipeline whose patterns ignore ``output_grouping`` (the runners' source grep, as a flag)."""
    import spacescans

    if not spacescans.capabilities().get("flags", {}).get("episode_grouping"):
        raise RuntimeError("the installed spacescans does not report per-episode output "
                           "grouping (capabilities().flags.episode_grouping); refusing to run")


def _unrenderable(steps: Sequence[Any], config: Mapping[str, Any]) -> tuple[int, Any, Exception] | None:
    """The first step the 0.2.7 runners could not key or render for ``config["buffer"]``.

    Every step's ``_cache_key`` and ``render_yaml`` read ``config["buffer"]["size"]``,
    and those of a step that uses the raster resolution read
    ``config["buffer"]["raster_res_m"]`` too, in that order. A config that lacks
    one (only a hand-written one can: the frontend always sends both) failed there
    with that lookup's exception. Returns ``(index, step, exception)`` from the
    same lookups, or None when every step can be rendered.
    """
    try:
        config["buffer"]["size"]
    except Exception as exc:  # noqa: BLE001 - KeyError or TypeError, as the runners raised it
        return 0, steps[0], exc
    for index, step in enumerate(steps):
        if step.uses_raster_res:
            try:
                config["buffer"]["raster_res_m"]
            except Exception as exc:  # noqa: BLE001
                return index, step, exc
            break
    return None


def _render_failure(experiment: str, index: int, step: Any, total: int, exc: Exception,
                    emit: Any, status: StatusSink) -> int:
    """What the runners wrote for a step they could not key or render: its start, the
    cache lookup's warning (C3 steps are looked up first), the render error, status
    ``render failed at <step>``; exit code 1."""
    common = {"step": step.name, "index": index, "total": total}
    emit(Event("step_start", experiment, **common))
    if step.is_c3:
        emit(Event("cache_warning", experiment,
                   text=LOG_CACHE_CHECK_FAILED.format(step=step.name, exc=exc), **common))
    emit(Event("warning", experiment, text=LOG_RENDER_FAILED.format(step=step.name, exc=exc),
               data={"level": "error", "source": "runner"}, **common))
    status.error(f"render failed at {step.name}")
    return 1


def run(experiment: str, task_dir: Path, variables: Sequence[str] | None = None) -> int:
    """Run one experiment for a task: the runners' ``run(task_dir, variables)``.

    Holds ``DATA_DIR/.run_lock`` for the whole run; a lock held elsewhere gives
    status ``error`` with the web's message and exit code 1. ``variables``
    (from ``--variables``) overrides ``config.json``'s list, in the order given.
    Returns 0 on success, the failing step's exit code on a step failure,
    1 on any other failure.
    """
    task_dir = Path(task_dir)
    install_cancel_handler(task_dir)
    _check_pipeline()
    settings = app.config.settings
    lock = RunLock(settings.DATA_DIR)
    try:
        lock.acquire()
    except RunLockBusy:
        _write_status(task_dir, status="error", message=RUN_LOCK_BUSY)
        return 1
    try:
        return _run_locked(experiment, task_dir, variables)
    finally:
        lock.release()


def _run_locked(experiment: str, task_dir: Path, variables: Sequence[str] | None) -> int:
    settings = app.config.settings
    config = json.loads((task_dir / "config.json").read_text())
    dispatcher_driven = variables is not None
    if dispatcher_driven:
        config = {**config, "variables": list(variables)}
    steps = plan(experiment, config)          # ValueError for no or foreign variables, as before
    keys = list(config["variables"])
    total = len(steps)
    recipe = catalog.recipe(experiment)
    definitions = custom_definitions(experiment, config)
    status = StatusSink(task_dir, experiment, dispatcher_driven=dispatcher_driven)
    log = LogWriter.for_run_dir(task_dir)
    emit = tee(log, status)
    try:
        level = output_level.of_config(config)
    except output_level.OutputLevelError as exc:
        status.error(str(exc))
        return 1

    status.begin([s.name for s in steps])

    try:
        cohort.to_pipeline_parquet(task_dir / "input.csv", task_dir / "input.parquet",
                                   variant=recipe.cohort_variant, pid_as_str=False)
    except Exception as exc:  # noqa: BLE001 - the runner reports any conversion error
        # 0.2.7 raised app.cohort_dates' plain ValueError here; the package raises its
        # ValueError subclass CohortError with the same message, so log the 0.2.7 repr.
        shown = ValueError(*exc.args) if isinstance(exc, cohort.CohortError) else exc
        log.write("error", "runner", LOG_COHORT_FAILED.format(exc=shown))
        status.error(f"input conversion failed: {exc}")
        return 1

    bad = _unrenderable(steps, config)
    if bad is not None:
        return _render_failure(experiment, bad[0], bad[1], total, bad[2], emit, status)
    buffer = config["buffer"]
    # raster_res_m as given; when absent no step reads it (_unrenderable), so the default stands.
    # The level rides on the context (or run_source) when the package takes one; at episode
    # level with a package that takes none this is the pre-phase-D call.
    try:
        ctx = output_level.run_context(task_dir, data_dir=settings.SPACESCANS_DATA_DIR,
                                       buffer_m=buffer["size"],
                                       raster_res_m=buffer.get("raster_res_m", 25),
                                       overlay=definitions, level=level)
        extra = output_level.source_kwargs(level)
    except output_level.ParticipantLevelUnsupported as exc:
        status.error(str(exc))
        return 1
    if level == output_level.PARTICIPANT and not extra:
        wrong = output_level.check_rendered(steps, ctx, level)
        if wrong is not None:
            status.error(f"participant-level output did not reach step {wrong}; the installed "
                         "spacescans renders it per episode")
            return 1
    cache = WeightCache(settings.C3_CACHE_DIR, key_format="legacy-v1")
    executor = SubprocessExecutor([settings.SPACESCANS_PIPELINE_PYTHON,
                                   settings.SPACESCANS_PIPELINE_CLI])
    try:
        run_source(experiment, keys, ctx, cache=cache, executor=executor, on_event=emit,
                   **extra)
    except RenderError as exc:
        status.error(f"render failed at {exc.step}")
        return 1
    except StepFailed as exc:
        if exc.rc != 0:
            status.error(f"step {exc.step} failed with exit code {exc.rc}")
            return int(exc.rc)
        status.error(f"step {exc.step} produced no output parquet")
        return 1

    status.merging(total)
    try:
        if recipe.linkage_report:
            from spacescans.custom import diagnostics

            for record in diagnostics(task_dir, keys, definitions or {}):
                log.write(record["level"], record["source"], record["msg"])
        merge_results(experiment, task_dir, keys, definitions=definitions, log=log,
                      level=level)
    except Exception as exc:  # noqa: BLE001 - the runner reports any merge error
        log.write("error", "runner", LOG_MERGE_FAILED.format(exc=exc))
        status.error(f"merge failed: {exc}")
        return 1

    status.finish(total)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_cli(prog: str, argv: Sequence[str]) -> tuple[Path, list[str] | None]:
    """``<prog> run <task_dir> [--variables a,b]`` -> (task_dir, variables or None)."""
    parser = argparse.ArgumentParser(prog=prog)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("task_dir", type=Path)
    p_run.add_argument("--variables", type=str, default=None,
                       help="comma-separated subset (overrides config.json)")
    args = parser.parse_args(list(argv)[1:])
    if args.cmd != "run":
        parser.error(f"unknown command: {args.cmd}")
    variables = ([v.strip() for v in args.variables.split(",") if v.strip()]
                 if args.variables else None)
    return args.task_dir, variables


def cli_main(experiment: str, argv: Sequence[str]) -> int:
    """The runners' ``_cli_main``: parse ``run <task_dir> [--variables ...]`` and run."""
    task_dir, variables = parse_cli(experiment, argv)
    return run(experiment, task_dir, variables=variables)
