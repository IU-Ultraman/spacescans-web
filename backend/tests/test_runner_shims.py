"""The ten catalog runner shims (tier-2 phase C): plan() from the catalog, the CLI, nothing else.

Each ``app.experiments.<exp>`` module keeps three names: ``plan(config)`` (the
dispatcher seeds its status slot from the step names), ``run(task_dir, variables)``
and ``_cli_main(argv)`` (``python -m app.experiments.<exp> run <task_dir>
--variables a,b``, the form the paper's scripts use). Everything else moved to
``spacescans.catalog`` and ``spacescans.orchestrate`` behind ``_adapter``.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from spacescans import catalog

BUFFER = {"size": 270, "raster_res_m": 25}

# experiment -> (variables in request order, step names in run order,
#                {C3 step: (cache tag, uses the raster resolution)})
SHIMS = {
    "bg_ndi_wi": (["ndi", "walkability"], ["c3_bg", "c3_bg_2020", "c4_ndi", "c4_wi"],
                  {"c3_bg": ("BG", True), "c3_bg_2020": ("BG2020", True)}),
    "zcta5_cbp": (["cbp_zcta5"], ["c3_zcta5", "c3_county", "c4_zcta5_cbp", "c4_county_cbp"],
                  {"c3_zcta5": ("ZCTA5", True), "c3_county": ("COUNTY", True)}),
    "tiger_proximity": (["tiger_proximity"], ["c3_tiger_roads", "c4_tiger_roads"],
                        {"c3_tiger_roads": ("BG_TIGER2", False)}),
    "nhd_bluespace": (["nhd_bluespace"], ["c3_nhd_bluespace", "c4_nhd_bluespace"],
                      {"c3_nhd_bluespace": ("BG_NHD", False)}),
    "noise": (["noise"], ["c3_noise", "c4_noise"], {"c3_noise": ("BG_NOISE", False)}),
    "vnl": (["vnl"], ["c3_vnl", "c4_vnl"], {"c3_vnl": ("BG_VNL1", False)}),
    "temis": (["temis"], ["c3_temis", "c4_temis"], {"c3_temis": ("BG_TEMIS", False)}),
    "fara_tract": (["fara_tract"], ["c3_tract_us", "c4_tract_fara"],
                   {"c3_tract_us": ("TRACT_FARA", True)}),
    "acag": (["acag"], ["c3_acag", "c4_acag"], {"c3_acag": ("BG_ACAG", False)}),
    "faqsd": (["faqsd"], ["c3_tract_us", "c4_tract_faqsd"], {"c3_tract_us": ("TRACT_FARA", True)}),
}


def _mod(key: str):
    return importlib.import_module(f"app.experiments.{key}")


@pytest.mark.parametrize("key", sorted(SHIMS))
def test_plan_is_the_catalogs(key: str) -> None:
    """Same steps, order and flags as ``catalog.plan``; objects carry the old PipelineStep names."""
    variables, names, c3 = SHIMS[key]
    steps = _mod(key).plan({"variables": variables, "buffer": BUFFER})
    assert [s.name for s in steps] == names
    assert [s.is_c3 for s in steps] == [n.startswith("c3_") for n in names]
    assert all(isinstance(s.template_relpath, str) and s.template_relpath.endswith(".yaml")
               for s in steps)
    assert steps == catalog.plan(key, variables)
    for step in steps:
        if step.is_c3:
            tag, raster = c3[step.name]
            assert (step.cache_tag, step.uses_raster_res) == (tag, raster), step.name


@pytest.mark.parametrize("key", sorted(SHIMS))
def test_plan_rejects_an_empty_selection(key: str) -> None:
    with pytest.raises(ValueError, match="at least one variable"):
        _mod(key).plan({"variables": [], "buffer": BUFFER})


@pytest.mark.parametrize("key", sorted(SHIMS))
def test_plan_rejects_a_foreign_variable(key: str) -> None:
    foreign = "ndi" if key != "bg_ndi_wi" else "noise"
    with pytest.raises(ValueError, match=f"unknown variable.*{foreign}"):
        _mod(key).plan({"variables": SHIMS[key][0] + [foreign], "buffer": BUFFER})


def test_c3_cache_tags_never_collide_across_runners() -> None:
    """The R1 lock: one tag per boundary table, shared only where the weights are the same
    (TRACT_FARA by fara_tract and faqsd)."""
    tags: dict[str, set[str]] = {}
    for key, (_vars, _names, c3) in SHIMS.items():
        for step, (tag, _raster) in c3.items():
            tags.setdefault(tag, set()).add(step)
    assert all(len(steps) == 1 for steps in tags.values()), tags
    assert tags["TRACT_FARA"] == {"c3_tract_us"}


def test_bg_ndi_wi_plans_per_variable() -> None:
    plan = _mod("bg_ndi_wi").plan
    assert [s.name for s in plan({"variables": ["ndi"], "buffer": BUFFER})] == [
        "c3_bg", "c3_bg_2020", "c4_ndi"]
    assert [s.name for s in plan({"variables": ["walkability"], "buffer": BUFFER})] == [
        "c3_bg", "c4_wi"]
    # request order does not change the plan; the merge keeps it (see test_bg_ndi_wi)
    assert plan({"variables": ["walkability", "ndi"], "buffer": BUFFER}) == plan(
        {"variables": ["ndi", "walkability"], "buffer": BUFFER})


@pytest.mark.parametrize("key", sorted(SHIMS))
def test_cli_passes_the_task_dir_and_the_variables_in_order(key: str, tmp_path, monkeypatch) -> None:
    mod = _mod(key)
    called: dict = {}

    def fake_run(task_dir: Path, variables: list[str] | None = None) -> int:
        called["task_dir"] = task_dir
        called["variables"] = variables
        return 0

    monkeypatch.setattr(mod, "run", fake_run)
    variables = list(reversed(SHIMS[key][0]))
    rc = mod._cli_main([key, "run", str(tmp_path), "--variables", ",".join(variables)])
    assert rc == 0
    assert called == {"task_dir": tmp_path, "variables": variables}
    assert mod._cli_main([key, "run", str(tmp_path)]) == 0
    assert called["variables"] is None


@pytest.mark.parametrize("key", sorted(SHIMS))
def test_shim_exposes_only_plan_and_run(key: str) -> None:
    mod = _mod(key)
    public = {n for n in vars(mod) if not n.startswith("_")} - {"annotations", "sys", "Path"}
    assert public == {"plan", "run"}
    assert mod._EXPERIMENT_KEY == key


def test_dispatcher_seeds_the_slot_from_the_shims_plan() -> None:
    from app import dispatcher

    for key, (variables, names, _c3) in SHIMS.items():
        config = {"variables": variables + ["something_else"], "buffer": BUFFER}
        assert dispatcher._runner_step_names(key, variables, config) == names
