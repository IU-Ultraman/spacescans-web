"""Single-experiment orchestrator: user-uploaded area-level and raster exposures.

Spawned by app.dispatcher (and the paper's scripts) as:
    python -m app.experiments.custom run <task_dir> [--variables custom_<id>,...]

Since tier-2 phase C this module is a shim: the recipe (steps, templates, cache
tag, merge table) lives in ``spacescans.catalog``, and the run loop in
``spacescans.orchestrate``; ``app.experiments._adapter`` keeps the web's task
bookkeeping (run lock, SIGTERM, status.json, logs.jsonl, result_<exp>.csv).
The module name and the three names below are the contract the dispatcher and
the paper's scripts depend on.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.experiments import _adapter

_EXPERIMENT_KEY = "custom"


def plan(config: dict) -> list:
    """The ordered pipeline steps for a task config (objects with ``.name``, ``.is_c3``)."""
    return _adapter.plan(_EXPERIMENT_KEY, config)


def run(task_dir: Path, variables: list[str] | None = None) -> int:
    """Run this experiment for ``task_dir``; ``variables`` overrides config.json's list."""
    return _adapter.run(_EXPERIMENT_KEY, task_dir, variables=variables)


def _cli_main(argv: list[str]) -> int:
    task_dir, variables = _adapter.parse_cli(_EXPERIMENT_KEY, argv)
    return run(task_dir, variables=variables)


if __name__ == "__main__":
    sys.exit(_cli_main(sys.argv))
