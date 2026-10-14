"""The nhd_bluespace runner shim: plan() from the catalog and the CLI (tier-2 phase C).

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

from app.experiments import nhd_bluespace

BUFFER = {"size": 270, "raster_res_m": 25}


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_nhd_bluespace"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({"variables": ["nhd_bluespace"], "buffer": BUFFER}))
    return d


def test_plan_returns_the_recipes_steps(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = nhd_bluespace.plan(config)
    assert [s.name for s in steps] == ['c3_nhd_bluespace', 'c4_nhd_bluespace']
    assert [s.is_c3 for s in steps] == [True, False]


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        nhd_bluespace.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        nhd_bluespace.plan({"variables": ["ndi"]})  # belongs to another runner


def test_c3_step_has_the_runners_cache_tag(task_dir: Path) -> None:
    """The legacy key is ``<sha8>__BG_NHD__b<buffer>m``: the tag keeps this
    runner's weights apart from the other BG-tagged runners."""
    steps = nhd_bluespace.plan(json.loads((task_dir / "config.json").read_text()))
    c3 = steps[0]
    assert c3.cache_tag == "BG_NHD"
    assert c3.uses_raster_res is False
    from spacescans.orchestrate.cache import legacy_key
    key_ = legacy_key(c3.cache_tag, "0" * 64, buffer_m=270, raster_res_m=25,
                      uses_raster_res=c3.uses_raster_res)
    assert key_ == "00000000__BG_NHD__b270m"


def test_cli_accepts_variables_comma_list(task_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0

    monkeypatch.setattr(nhd_bluespace, "run", fake_run)
    rc = nhd_bluespace._cli_main(["nhd_bluespace", "run", str(task_dir), "--variables", "nhd_bluespace"])
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["nhd_bluespace"]
