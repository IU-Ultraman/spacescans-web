"""The vnl runner shim: plan() from the catalog and the CLI (tier-2 phase C).

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

from app.experiments import vnl

BUFFER = {"size": 270, "raster_res_m": 25}


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_vnl"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({"variables": ["vnl"], "buffer": BUFFER}))
    return d


def test_plan_returns_the_recipes_steps(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = vnl.plan(config)
    assert [s.name for s in steps] == ['c3_vnl', 'c4_vnl']
    assert [s.is_c3 for s in steps] == [True, False]


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        vnl.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        vnl.plan({"variables": ["ndi"]})  # belongs to another runner


def test_c3_step_has_the_runners_cache_tag(task_dir: Path) -> None:
    """The legacy key is ``<sha8>__BG_VNL1__b<buffer>m``: the tag keeps this
    runner's weights apart from the other BG-tagged runners."""
    steps = vnl.plan(json.loads((task_dir / "config.json").read_text()))
    c3 = steps[0]
    assert c3.cache_tag == "BG_VNL1"
    assert c3.uses_raster_res is False
    from spacescans.orchestrate.cache import legacy_key
    key_ = legacy_key(c3.cache_tag, "0" * 64, buffer_m=270, raster_res_m=25,
                      uses_raster_res=c3.uses_raster_res)
    assert key_ == "00000000__BG_VNL1__b270m"


def test_cli_accepts_variables_comma_list(task_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict = {}

    def fake_run(td: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = td
        called["variables"] = variables
        return 0

    monkeypatch.setattr(vnl, "run", fake_run)
    rc = vnl._cli_main(["vnl", "run", str(task_dir), "--variables", "vnl"])
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["vnl"]


def test_vnl_c3_template_offsets_grid_ids_for_the_one_based_reader():
    """The vnl reader reads flat index grid_id - 1 (R terra parity). Weights must
    therefore carry 1-based ids, as acag's do; with the default offset 0 every
    VNL value was read from the cell one column west (paper validation,
    2026-09-29). The template now comes from the package and must hash-match
    the repo copy (web-modules); both are checked here."""
    import yaml
    from spacescans import catalog
    cfg = yaml.safe_load((Path(__file__).resolve().parents[2] / "configs" / "c3" / "vnl_grid_demo.yaml").read_text())
    assert cfg["buffer"]["grid_id_offset"] == 1
    assert catalog.template("c3/vnl_grid_demo.yaml")["buffer"]["grid_id_offset"] == 1
