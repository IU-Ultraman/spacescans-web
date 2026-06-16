"""Shared per-experiment merge utilities. Extracted from bg_ndi_wi.merge_results."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from app import variable_registry


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
    """Per-runner merge step. Returns path to result_<experiment_key>.csv."""
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"result_{experiment_key}.csv"

    input_df = pd.read_csv(task_dir / "input.csv", dtype=str)
    input_df["episode_id"] = list(range(len(input_df)))
    input_df["episode_id"] = input_df["episode_id"].astype(int)
    if "pid" not in input_df.columns:
        input_df = input_df.rename(columns={"PATID": "pid"})
    input_keys = input_df[["pid", "episode_id"]]

    merged: pd.DataFrame | None = None
    for var_key in variables:
        parquet_path = out_dir / parquet_map[var_key]
        df = pd.read_parquet(parquet_path)

        df = df.rename(columns={"PATID": "pid", "geoid": "episode_id"})
        df["episode_id"] = df["episode_id"].astype(int)

        meta = variable_registry.get_variable(var_key)
        value_cols = [c for c in meta["value_cols"] if c in df.columns]
        df = df[["pid", "episode_id"] + value_cols]

        if merged is None:
            merged = df
        else:
            new_cols = [c for c in df.columns
                        if c in ("pid", "episode_id") or c not in merged.columns]
            df = df[new_cols]
            merged = merged.merge(df, on=["pid", "episode_id"], how="outer")

    if merged is None:
        merged = input_keys.copy()

    joined = input_keys.merge(merged, on=["pid", "episode_id"], how="left")
    value_only = joined.drop(columns=["pid", "episode_id"])
    if value_only.shape[1] == 0:
        match_pct = 100.0
        matched = len(input_keys)
    else:
        matched = int(value_only.notna().any(axis=1).sum())
        match_pct = round(100.0 * matched / max(len(input_keys), 1), 2)

    if match_pct < 90.0:
        _emit_log_warning(
            task_dir,
            experiment_key=experiment_key,
            event="merge_partial_low_match_pct",
            match_pct=match_pct,
            cohort_n=len(input_keys),
            matched_n=int(matched),
        )

    merged.to_csv(out_path, index=False)
    return out_path


def fan_in(task_dir: Path, experiment_keys: list[str]) -> Path:
    """Left-join each result_<key>.csv on (pid, episode_id) -> result.csv."""
    df = pd.read_csv(task_dir / "input.csv", dtype=str)
    if "pid" not in df.columns:
        df = df.rename(columns={"PATID": "pid"})
    df["episode_id"] = list(range(len(df)))
    df["episode_id"] = df["episode_id"].astype(int)

    for exp_key in experiment_keys:
        partial = pd.read_csv(
            task_dir / "output" / f"result_{exp_key}.csv",
            dtype=str,
        )
        partial["episode_id"] = partial["episode_id"].astype(int)
        df = df.merge(
            partial,
            on=["pid", "episode_id"],
            how="left",
            suffixes=("", f"_{exp_key}_dup"),
        )

    out_path = task_dir / "output" / "result.csv"
    df.to_csv(out_path, index=False)
    return out_path
