"""Shared per-experiment merge utilities. Extracted from bg_ndi_wi.merge_results.

The joins live in ``spacescans.orchestrate.merge`` since tier-2 phase B (a port
of this module checked byte for byte against the web's outputs, gate A3). What
stays here is the web's file layer: which columns the catalog says a variable
has, the ``logs.jsonl`` warning, and writing ``result_<experiment>.csv``,
``result.csv`` and ``feature_dictionary.csv`` under the task's ``output/``.
Both CSVs are written from tables read as text, so values reach result.csv
exactly as the partials wrote them.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from spacescans.orchestrate import merge as _merge

from app import feature_dictionary, variable_registry


def _emit_log_warning(task_dir: Path, **fields) -> None:
    log_path = task_dir / "logs.jsonl"
    record = {"ts": time.time(), "level": "warning", **fields}
    with log_path.open("a") as f:
        f.write(json.dumps(record) + "\n")


def write_partial(
    task_dir: Path,
    experiment_key: str,
    variables: list[str],
    parquet_map: dict[str, str],
) -> Path:
    """Per-runner merge step. Returns path to result_<experiment_key>.csv.

    ``task_dir`` is passed to the registry so custom exposomes resolve from
    the task's own snapshot, not the shipped catalog.
    """
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _merge.partial_csv_name(experiment_key)

    value_cols = {
        var_key: list(variable_registry.get_variable(var_key, task_dir=task_dir)["value_cols"])
        for var_key in variables
    }
    merged, stats = _merge.partial_from_dir(
        task_dir, experiment_key, variables, parquet_map, value_cols,
    )
    if stats.low:
        _emit_log_warning(task_dir, **stats.as_log_fields())

    merged.to_csv(out_path, index=False)
    return out_path


def fan_in(task_dir: Path, experiment_keys: list[str]) -> Path:
    """Left-join each result_<key>.csv on (pid, episode_id) -> result.csv.

    episode_id is the join key, not a result: it is just the input row index,
    and every row already carries the input columns (pid + dates + coords)
    that identify the episode. It is dropped from the deliverable — the
    per-runner result_<key>.csv partials keep it, since the joins need it.
    """
    df = _merge.fan_in_from_dir(task_dir, experiment_keys)

    out_path = task_dir / "output" / "result.csv"
    df.to_csv(out_path, index=False)
    # Companion dictionary describing this run's exposure columns, archived
    # next to the results it documents (see app/feature_dictionary.py).
    feature_dictionary.write_csv(
        list(df.columns), task_dir / "output" / "feature_dictionary.csv"
    )
    return out_path
