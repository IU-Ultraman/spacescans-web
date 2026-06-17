"""Sprint 3 T5: experiments/_merge.py — write_partial + fan_in."""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest


def _write_input_csv(task_dir: Path, n: int = 10) -> None:
    (task_dir).mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(n)],
        "startDate": ["2017-01-01"] * n,
        "endDate": ["2017-12-31"] * n,
        "longitude": [-93.0] * n,
        "latitude": [45.0] * n,
    })
    df.to_csv(task_dir / "input.csv", index=False)


def _write_variable_parquet(out_dir: Path, name: str, n: int, value_cols: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = {"PATID": [f"PID{i:07d}" for i in range(n)],
            "geoid": list(range(n))}
    for c in value_cols:
        data[c] = [float(i) for i in range(n)]
    pd.DataFrame(data).to_parquet(out_dir / f"{name}.parquet", index=False)


def test_write_partial_synthetic_10x10_match_pct_100(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-a"
    _write_input_csv(task_dir, n=10)
    _write_variable_parquet(task_dir / "output", "ndi", n=10, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    assert out == task_dir / "output" / "result_bg_ndi_wi.csv"
    df = pd.read_csv(out)
    assert set(df.columns) >= {"pid", "episode_id", "ndi"}
    assert len(df) == 10
    logs = task_dir / "logs.jsonl"
    if logs.exists():
        events = [json.loads(line) for line in logs.read_text().splitlines() if line.strip()]
        assert not any(e.get("event") == "merge_partial_low_match_pct" for e in events)


def test_write_partial_renames_patid_to_pid_and_geoid_to_episode_id(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-b"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(task_dir / "output", "ndi", n=5, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    df = pd.read_csv(out)
    assert "pid" in df.columns and "PATID" not in df.columns
    assert "episode_id" in df.columns and "geoid" not in df.columns
    assert pd.api.types.is_integer_dtype(df["episode_id"])


def test_write_partial_emits_low_match_pct_warning(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-c"
    _write_input_csv(task_dir, n=10)
    _write_variable_parquet(task_dir / "output", "ndi", n=5, value_cols=["ndi"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["ndi"]}):
        _merge.write_partial(
            task_dir=task_dir,
            experiment_key="bg_ndi_wi",
            variables=["ndi"],
            parquet_map={"ndi": "ndi.parquet"},
        )

    events = [json.loads(line) for line in (task_dir / "logs.jsonl").read_text().splitlines() if line.strip()]
    low = [e for e in events if e.get("event") == "merge_partial_low_match_pct"]
    assert len(low) == 1
    assert low[0]["experiment_key"] == "bg_ndi_wi"
    assert low[0]["match_pct"] == 50.0


def test_write_partial_value_cols_sourced_from_registry(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-d"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(task_dir / "output", "cbp_multi", n=5,
                            value_cols=["r_total", "r_food", "r_unused"])

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": ["r_total", "r_food"]}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="zcta5_cbp",
            variables=["cbp_multi"],
            parquet_map={"cbp_multi": "cbp_multi.parquet"},
        )

    df = pd.read_csv(out)
    assert "r_total" in df.columns and "r_food" in df.columns
    assert "r_unused" not in df.columns


def test_write_partial_value_cols_picks_3_tiger_columns_from_one_parquet(tmp_path):
    """Sprint 5 B3 (spec L712): tiger_proximity ships a single parquet
    carrying all three TIGER distance columns. _merge.write_partial must
    pick exactly value_cols=[dist_pri, dist_sec, dist_prisec] from the
    registry — no extra/missing columns leaking through.
    """
    from app.experiments import _merge

    task_dir = tmp_path / "task-b3-tiger-merge"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(
        task_dir / "output", "c4_tiger_roads", n=5,
        value_cols=["dist_pri", "dist_sec", "dist_prisec", "dist_unused"],
    )

    with patch("app.variable_registry.get_variable",
               return_value={
                   "value_cols": ["dist_pri", "dist_sec", "dist_prisec"]
               }):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="tiger_proximity",
            variables=["tiger_proximity"],
            parquet_map={"tiger_proximity": "c4_tiger_roads.parquet"},
        )

    assert out == task_dir / "output" / "result_tiger_proximity.csv"
    df = pd.read_csv(out)
    assert {"dist_pri", "dist_sec", "dist_prisec"}.issubset(df.columns)
    assert "dist_unused" not in df.columns


def test_write_partial_value_cols_picks_5_nhd_columns_from_one_parquet(tmp_path):
    """Sprint 7 B3: nhd_bluespace ships a single parquet carrying all five
    NHD distance columns (dist_flow_m, dist_water_m, dist_area_m,
    dist_coast_m, dist_blue_m). _merge.write_partial must pick exactly the
    five from the registry — no extra/missing columns leaking through.
    """
    from app.experiments import _merge

    nhd_cols = [
        "dist_flow_m", "dist_water_m", "dist_area_m",
        "dist_coast_m", "dist_blue_m",
    ]

    task_dir = tmp_path / "task-b3-nhd-merge"
    _write_input_csv(task_dir, n=5)
    _write_variable_parquet(
        task_dir / "output", "c4_nhd_bluespace", n=5,
        value_cols=[*nhd_cols, "dist_unused"],
    )

    with patch("app.variable_registry.get_variable",
               return_value={"value_cols": nhd_cols}):
        out = _merge.write_partial(
            task_dir=task_dir,
            experiment_key="nhd_bluespace",
            variables=["nhd_bluespace"],
            parquet_map={"nhd_bluespace": "c4_nhd_bluespace.parquet"},
        )

    assert out == task_dir / "output" / "result_nhd_bluespace.csv"
    df = pd.read_csv(out)
    assert set(nhd_cols).issubset(df.columns)
    assert "dist_unused" not in df.columns
    assert {"pid", "episode_id"}.issubset(df.columns)
    assert len(df) == 5


def test_fan_in_left_joins_two_partials_no_row_duplication(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-e"
    _write_input_csv(task_dir, n=5)
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(5)],
        "episode_id": list(range(5)),
        "ndi": [0.1 * i for i in range(5)],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(5)],
        "episode_id": list(range(5)),
        "r_total": [float(i) for i in range(5)],
    }).to_csv(out_dir / "result_zcta5_cbp.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi", "zcta5_cbp"])
    df = pd.read_csv(out)
    assert out == task_dir / "output" / "result.csv"
    assert len(df) == 5
    assert {"pid", "episode_id", "ndi", "r_total"}.issubset(df.columns)


def test_fan_in_suffix_handling_on_column_collision(tmp_path):
    from app.experiments import _merge

    task_dir = tmp_path / "task-t5-f"
    _write_input_csv(task_dir, n=3)
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(3)],
        "episode_id": list(range(3)),
        "score": [1.0, 2.0, 3.0],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    pd.DataFrame({
        "pid": [f"PID{i:07d}" for i in range(3)],
        "episode_id": list(range(3)),
        "score": [10.0, 20.0, 30.0],
    }).to_csv(out_dir / "result_zcta5_cbp.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi", "zcta5_cbp"])
    df = pd.read_csv(out)
    assert "score" in df.columns
    assert "score_zcta5_cbp_dup" in df.columns
    assert df["score"].tolist() == [1.0, 2.0, 3.0]
    assert df["score_zcta5_cbp_dup"].tolist() == [10.0, 20.0, 30.0]


def test_bg_ndi_wi_merge_results_delegates_to_write_partial(tmp_path):
    from app.experiments import bg_ndi_wi as mod

    task_dir = tmp_path / "task-t5-g"
    _write_input_csv(task_dir, n=4)
    # bg_ndi_wi maps variable->parquet via _VARIABLE_TO_STEP: ndi -> c4_ndi.parquet,
    # walkability -> c4_wi.parquet. Write fixtures at those names so the
    # delegation's parquet_map={v: f"{_VARIABLE_TO_STEP[v].name}.parquet"} resolves.
    _write_variable_parquet(task_dir / "output", "c4_ndi", n=4, value_cols=["ndi"])
    _write_variable_parquet(task_dir / "output", "c4_wi", n=4, value_cols=["NatWalkInd"])

    with patch("app.variable_registry.get_variable",
               side_effect=lambda k: {"ndi": {"value_cols": ["ndi"]},
                                      "walkability": {"value_cols": ["NatWalkInd"]}}[k]):
        mod.merge_results(task_dir=task_dir, variables=["ndi", "walkability"])

    assert (task_dir / "output" / "result_bg_ndi_wi.csv").exists()
    df = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv")
    assert {"pid", "episode_id", "ndi", "NatWalkInd"}.issubset(df.columns)


def test_fan_in_preserves_episode_pairs_with_partial_data(tmp_path):
    """F4 (Sprint 4): lock (pid, episode_id) composite join key for fan_in.

    Fixture: 10 input rows, 5 pids each appearing twice with two distinct
    global episode_ids (A,B,C,D,E -> rows 0..9). Partial CSV drops episodes
    1, 5, 9 (one missing episode for pids A, C, E). A mutation dropping
    episode_id from the join key would either duplicate rows (cartesian on
    pid) or place values on the wrong episode — both caught by the
    assertions below.
    """
    from app.experiments import _merge

    task_dir = tmp_path / "task-f4-fanin"
    task_dir.mkdir(parents=True, exist_ok=True)

    # 10 input rows: 5 pids (A..E), each twice. fan_in assigns
    # episode_id = list(range(10)) in row order, so pairs are
    # (A,0),(A,1),(B,2),(B,3),(C,4),(C,5),(D,6),(D,7),(E,8),(E,9).
    pids = ["A", "A", "B", "B", "C", "C", "D", "D", "E", "E"]
    pd.DataFrame({
        "pid": pids,
        "startDate": ["2017-01-01"] * 10,
        "endDate": ["2017-12-31"] * 10,
        "longitude": [-93.0] * 10,
        "latitude": [45.0] * 10,
    }).to_csv(task_dir / "input.csv", index=False)

    # Partial CSV: 7 rows — drop episodes 1, 5, 9 (missing for A, C, E).
    out_dir = task_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "pid": ["A", "B", "B", "C", "D", "D", "E"],
        "episode_id": [0, 2, 3, 4, 6, 7, 8],
        "value": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
    }).to_csv(out_dir / "result_bg_ndi_wi.csv", index=False)

    out = _merge.fan_in(task_dir=task_dir, experiment_keys=["bg_ndi_wi"])
    df = pd.read_csv(out)

    # (1) No row loss, no row duplication.
    assert len(df) == 10, f"expected 10 rows, got {len(df)}"

    # (2) Exactly 3 NaN rows in the value column.
    nan_rows = df[df["value"].isna()]
    assert nan_rows.shape[0] == 3, f"expected 3 NaN rows, got {nan_rows.shape[0]}"

    # (3) NaN rows are exactly (A,1), (C,5), (E,9).
    nan_pairs = set(
        zip(nan_rows["pid"].tolist(), nan_rows["episode_id"].astype(int).tolist())
    )
    assert nan_pairs == {("A", 1), ("C", 5), ("E", 9)}, (
        f"unexpected NaN pairs: {nan_pairs}"
    )

    # (4) Sorted by (pid, episode_id) matches input ordering — confirms
    # the left-join preserves composite-key row order.
    df["episode_id"] = df["episode_id"].astype(int)
    sorted_pairs = list(
        zip(
            df.sort_values(["pid", "episode_id"])["pid"].tolist(),
            df.sort_values(["pid", "episode_id"])["episode_id"].tolist(),
        )
    )
    expected_pairs = [
        ("A", 0), ("A", 1), ("B", 2), ("B", 3), ("C", 4),
        ("C", 5), ("D", 6), ("D", 7), ("E", 8), ("E", 9),
    ]
    assert sorted_pairs == expected_pairs, (
        f"composite-key ordering mismatch: {sorted_pairs}"
    )
