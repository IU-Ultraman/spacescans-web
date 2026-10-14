"""The faqsd runner shim: plan() from the catalog and the CLI (tier-2 phase C).

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

from app.experiments import faqsd

BUFFER = {"size": 270, "raster_res_m": 25}


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_faqsd"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({"variables": ["faqsd"], "buffer": BUFFER}))
    return d


def test_plan_returns_the_recipes_steps(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = faqsd.plan(config)
    assert [s.name for s in steps] == ['c3_tract_us', 'c4_tract_faqsd']
    assert [s.is_c3 for s in steps] == [True, False]


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        faqsd.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        faqsd.plan({"variables": ["ndi"]})  # belongs to another runner


def test_c3_step_has_the_runners_cache_tag(task_dir: Path) -> None:
    """The legacy key is ``<sha8>__TRACT_FARA__b<buffer>m__r25m``: the tag keeps this
    runner's weights apart from the other BG-tagged runners (TRACT_FARA is shared by fara_tract, faqsd and custom Tract uploads on purpose)."""
    steps = faqsd.plan(json.loads((task_dir / "config.json").read_text()))
    c3 = steps[0]
    assert c3.cache_tag == "TRACT_FARA"
    assert c3.uses_raster_res is True
    from spacescans.orchestrate.cache import legacy_key
    key_ = legacy_key(c3.cache_tag, "0" * 64, buffer_m=270, raster_res_m=25,
                      uses_raster_res=c3.uses_raster_res)
    assert key_ == "00000000__TRACT_FARA__b270m__r25m"


def test_cli_accepts_variables_comma_list(task_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0

    monkeypatch.setattr(faqsd, "run", fake_run)
    rc = faqsd._cli_main(["faqsd", "run", str(task_dir), "--variables", "faqsd"])
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["faqsd"]


def test_merge_renames_the_readers_columns_in_place(tmp_path: Path) -> None:
    """o3/pm25 become faqsd_o3/faqsd_pm25 (ACAG also emits pm25) and the C4 parquet is
    rewritten in place, as the 0.2.7 runner did; the paper's scripts read that parquet."""
    from app.experiments import _adapter
    task_dir = tmp_path / "task-merge"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"pid": ["p1", "p1", "p2"], "startDate": ["2017-01-01"] * 3,
                  "endDate": ["2017-12-31"] * 3, "longitude": [-87.6] * 3,
                  "latitude": [41.9] * 3}).to_csv(task_dir / "input.csv", index=False)
    parquet = task_dir / "output" / "c4_tract_faqsd.parquet"
    pd.DataFrame({"PATID": ["p1", "p1", "p2"], "geoid": [0, 1, 2],
                  "o3": [30.0, 31.0, 32.0], "pm25": [8.0, 9.0, 10.0]}).to_parquet(parquet, index=False)
    out = _adapter.merge_results("faqsd", task_dir, ["faqsd"])
    assert out == task_dir / "output" / "result_faqsd.csv"
    assert set(pd.read_parquet(parquet).columns) == {"PATID", "geoid", "faqsd_o3", "faqsd_pm25"}
    result = pd.read_csv(out)
    assert list(result.columns) == ["pid", "episode_id", "faqsd_o3", "faqsd_pm25"]
    assert result["faqsd_o3"].tolist() == [30.0, 31.0, 32.0]


def test_faqsd_shares_the_tract_weights_with_fara(task_dir: Path) -> None:
    from app.experiments import fara_tract
    ours = faqsd.plan(json.loads((task_dir / "config.json").read_text()))[0]
    theirs = fara_tract.plan({"variables": ["fara_tract"], "buffer": BUFFER})[0]
    assert ours == theirs and ours.name == "c3_tract_us"
