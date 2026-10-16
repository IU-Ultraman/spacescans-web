"""Shared per-experiment merge utilities. Extracted from bg_ndi_wi.merge_results.

The joins live in ``spacescans.orchestrate.merge`` since tier-2 phase B (a port
of this module checked byte for byte against the web's outputs, gate A3). What
stays here is the web's file layer: which columns the catalog says a variable
has, the ``logs.jsonl`` warning, and writing ``result_<experiment>.csv``,
``result.csv`` and ``feature_dictionary.csv`` under the task's ``output/``.
Both CSVs are written from tables read as text, so values reach result.csv
exactly as the partials wrote them.

Phase D: :func:`fan_in` builds ``result.csv`` at the task's output level
(``app.output_level``): per episode as before, or one row per participant
(``pid`` + variables). It records the level in ``output/result_meta.json`` and
writes the dictionary for that level (the participant table's ``pid`` row, and
the task's custom datasets described from their definitions).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from spacescans.orchestrate import merge as _merge

from app import feature_dictionary, output_level, variable_registry


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


def episode_partial(task_dir: Path, experiment_key: str, variables: list[str],
                    parquet_map: dict[str, str], value_cols: dict[str, list[str]], *,
                    renames: dict[str, str] | None = None,
                    rewrite_in_place: bool = False):
    """``spacescans.orchestrate.merge.partial_from_dir`` with each C4 id spelled as the cohort spells it.

    The web converts the cohort with ``pid_as_str=False`` (the legacy C3 cache keys hash
    input.parquet), so an all-numeric id column reaches C4 as numbers while input.csv is
    read as text, and the package's merge cannot join the two (pandas refuses a str and an
    int64 key; zero-padded ids would also lose their zeros). Each C4 row's ``geoid`` is
    its input row (``episode_id``), so its ``PATID`` is replaced by input.csv's text for
    that row before the package's ``merge_partial`` runs. For ids that were text all
    along this changes nothing: the partial is the one partial_from_dir writes. The C4
    parquets are rewritten only for ``renames`` (FAQSD), as before.
    """
    import pandas as pd

    task_dir = Path(task_dir)
    out_dir = task_dir / "output"
    if rewrite_in_place and renames:
        for var_key in variables:
            path = out_dir / parquet_map[var_key]
            pd.read_parquet(path).rename(columns=dict(renames)).to_parquet(path, index=False)
    keys = _merge.episode_keys(pd.read_csv(task_dir / "input.csv", dtype=str))
    text_ids = keys["pid"].tolist()
    outputs = []
    for var_key in variables:
        df = pd.read_parquet(out_dir / parquet_map[var_key])
        if "PATID" in df.columns and "geoid" in df.columns:
            rows = df["geoid"].astype(int).tolist()
            df = df.assign(PATID=[text_ids[i] if 0 <= i < len(text_ids) else None
                                  for i in rows])
        outputs.append((var_key, df))
    return _merge.merge_partial(keys, outputs, value_cols, experiment=experiment_key,
                                renames=renames)


def _task_config(task_dir: Path) -> dict:
    path = Path(task_dir) / "config.json"
    if not path.is_file():
        return {}
    try:
        config = json.loads(path.read_text())
    except ValueError:
        return {}
    return config if isinstance(config, dict) else {}


def fan_in(task_dir: Path, experiment_keys: list[str]) -> Path:
    """Join every result_<key>.csv into result.csv at the task's output level.

    Episode level: left-join on (pid, episode_id) onto the cohort, as before.
    episode_id is the join key, not a result: it is just the input row index,
    and every row already carries the input columns (pid + dates + coords)
    that identify the episode. It is dropped from the deliverable — the
    per-runner result_<key>.csv partials keep it, since the joins need it.

    Participant level: the cohort's participants (first appearance) left-joined
    on pid to each partial (``output_level.participant_fan_in``).
    """
    task_dir = Path(task_dir)
    config = _task_config(task_dir)
    level = output_level.of_config(config)
    output_level.clear_result_meta(task_dir)
    if level == output_level.PARTICIPANT:
        df = output_level.participant_fan_in(task_dir, experiment_keys)
        blank = output_level.blank_id_rows(task_dir)
        if blank:
            _emit_log_warning(
                task_dir, source="merge", event="participant_rows_without_id", rows=blank,
                msg=(f"{blank} input row(s) have no participant id (pid); the "
                     "participant-level result leaves them out"))
    else:
        df = _merge.fan_in_from_dir(task_dir, experiment_keys)

    out_path = task_dir / "output" / "result.csv"
    df.to_csv(out_path, index=False)
    # Companion dictionary describing this run's exposure columns, archived
    # next to the results it documents (see app/feature_dictionary.py).
    feature_dictionary.write_csv(
        list(df.columns), task_dir / "output" / "feature_dictionary.csv",
        level=level, config=config,
    )
    output_level.write_result_meta(task_dir, level=level, rows=len(df),
                                   experiments=list(experiment_keys))
    return out_path
