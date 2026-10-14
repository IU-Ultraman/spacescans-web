"""The zcta5_cbp runner shim: plan() from the catalog and the CLI (tier-2 phase C).

Rendering, cache keys and the start-up probe moved into ``spacescans``
(``catalog``, ``orchestrate``, ``capabilities()``); ``tests/test_runner_shims.py``
and ``tests/test_bg_ndi_wi.py`` hold the shared adapter. Here: what is specific
to this runner's recipe.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.experiments import zcta5_cbp

BUFFER = {"size": 270, "raster_res_m": 25}


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_zcta5_cbp"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({"variables": ["cbp_zcta5"], "buffer": BUFFER}))
    return d


def test_plan_returns_the_recipes_steps(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = zcta5_cbp.plan(config)
    assert [s.name for s in steps] == ['c3_zcta5', 'c3_county', 'c4_zcta5_cbp', 'c4_county_cbp']
    assert [s.is_c3 for s in steps] == [True, True, False, False]


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        zcta5_cbp.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        zcta5_cbp.plan({"variables": ["ndi"]})  # belongs to another runner


def test_c3_step_has_the_runners_cache_tag(task_dir: Path) -> None:
    """The legacy key is ``<sha8>__ZCTA5__b<buffer>m__r25m``: the tag keeps this
    runner's weights apart from the other BG-tagged runners."""
    steps = zcta5_cbp.plan(json.loads((task_dir / "config.json").read_text()))
    c3 = steps[0]
    assert c3.cache_tag == "ZCTA5"
    assert c3.uses_raster_res is True
    from spacescans.orchestrate.cache import legacy_key
    key_ = legacy_key(c3.cache_tag, "0" * 64, buffer_m=270, raster_res_m=25,
                      uses_raster_res=c3.uses_raster_res)
    assert key_ == "00000000__ZCTA5__b270m__r25m"


def test_cli_accepts_variables_comma_list(task_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0

    monkeypatch.setattr(zcta5_cbp, "run", fake_run)
    rc = zcta5_cbp._cli_main(["zcta5_cbp", "run", str(task_dir), "--variables", "cbp_zcta5"])
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["cbp_zcta5"]


def test_c3_county_step_has_its_own_tag(task_dir: Path) -> None:
    steps = zcta5_cbp.plan(json.loads((task_dir / "config.json").read_text()))
    assert (steps[1].name, steps[1].cache_tag, steps[1].uses_raster_res) == ("c3_county", "COUNTY", True)


def test_cohort_conversion_reads_zcta5_as_text(task_dir: Path) -> None:
    """The zcta5 variant every runner but bg_ndi_wi uses: ZCTA5 codes keep their zeros."""
    from spacescans import cohort
    src = task_dir / "input.csv"
    src.write_text("pid,startDate,endDate,longitude,latitude,zcta5\n"
                   "p1,2017-01-01,2017-12-31,-87.6,41.9,02134\n")
    dst = task_dir / "input.parquet"
    cohort.csv_to_parquet(src, dst, variant="zcta5")
    df = pd.read_parquet(dst)
    assert df["episode_id"].tolist() == [0]
    assert df["zcta5"].tolist() == ["02134"]


def test_merge_reads_the_county_fallback_output(tmp_path: Path) -> None:
    """The final cbp_zcta5 value is the fallback C4's: ZBP where it exists, county CBP otherwise."""
    from app.experiments import _adapter
    from spacescans import catalog
    assert catalog.recipe("zcta5_cbp").output_for("cbp_zcta5") == "c4_county_cbp.parquet"
    task_dir = tmp_path / "task-merge"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"pid": ["p1"], "startDate": ["2017-01-01"], "endDate": ["2017-12-31"],
                  "longitude": [-87.6], "latitude": [41.9]}).to_csv(task_dir / "input.csv", index=False)
    cols = list(catalog.variable("cbp_zcta5").value_cols)
    pd.DataFrame({"PATID": ["p1"], "geoid": [0], **{c: [1.0] for c in cols}}).to_parquet(
        task_dir / "output" / "c4_county_cbp.parquet", index=False)
    out = pd.read_csv(_adapter.merge_results("zcta5_cbp", task_dir, ["cbp_zcta5"]))
    assert list(out.columns) == ["pid", "episode_id"] + cols
