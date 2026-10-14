"""The fara_tract runner shim: plan() from the catalog and the CLI (tier-2 phase C).

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

from app.experiments import fara_tract

BUFFER = {"size": 270, "raster_res_m": 25}


@pytest.fixture()
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "task_fara_tract"
    d.mkdir()
    (d / "input.csv").write_text(
        "pid,startDate,endDate,long,lat\n"
        "p1,2017-01-01,2017-12-31,-87.6,41.9\n"
        "p1,2018-01-01,2018-12-31,-87.7,41.8\n"
        "p2,2017-06-01,2018-05-31,-86.2,39.8\n"
    )
    (d / "config.json").write_text(json.dumps({"variables": ["fara_tract"], "buffer": BUFFER}))
    return d


def test_plan_returns_the_recipes_steps(task_dir: Path) -> None:
    config = json.loads((task_dir / "config.json").read_text())
    steps = fara_tract.plan(config)
    assert [s.name for s in steps] == ['c3_tract_us', 'c4_tract_fara']
    assert [s.is_c3 for s in steps] == [True, False]


def test_plan_rejects_empty_variables() -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        fara_tract.plan({"variables": []})


def test_plan_rejects_unknown_variable() -> None:
    with pytest.raises(ValueError, match="unknown variable"):
        fara_tract.plan({"variables": ["ndi"]})  # belongs to another runner


def test_c3_step_has_the_runners_cache_tag(task_dir: Path) -> None:
    """The legacy key is ``<sha8>__TRACT_FARA__b<buffer>m__r25m``: the tag keeps this
    runner's weights apart from the other BG-tagged runners (TRACT_FARA is shared by fara_tract, faqsd and custom Tract uploads on purpose)."""
    steps = fara_tract.plan(json.loads((task_dir / "config.json").read_text()))
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

    monkeypatch.setattr(fara_tract, "run", fake_run)
    rc = fara_tract._cli_main(["fara_tract", "run", str(task_dir), "--variables", "fara_tract"])
    assert rc == 0
    assert called["task_dir"] == task_dir
    assert called["variables"] == ["fara_tract"]


def test_merge_keeps_the_four_headline_columns(tmp_path: Path) -> None:
    """The C4 output carries the full label set; the partial keeps the catalog's value_cols."""
    from app.experiments import _adapter
    from spacescans import catalog
    cols = list(catalog.variable("fara_tract").value_cols)
    task_dir = tmp_path / "task-merge"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"pid": ["p1"], "startDate": ["2017-01-01"], "endDate": ["2017-12-31"],
                  "longitude": [-87.6], "latitude": [41.9]}).to_csv(task_dir / "input.csv", index=False)
    pd.DataFrame({"PATID": ["p1"], "geoid": [0], **{c: [1.0] for c in cols}, "extra_label": [2.0]}
                 ).to_parquet(task_dir / "output" / "c4_tract_fara.parquet", index=False)
    out = pd.read_csv(_adapter.merge_results("fara_tract", task_dir, ["fara_tract"]))
    assert list(out.columns) == ["pid", "episode_id"] + cols
