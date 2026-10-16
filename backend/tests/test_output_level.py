"""Phase D: participant-level output (the default) and episode-level output in the web app.

What is tested here, with synthetic cohorts only:

* the level rules: the app's default is participant, a config.json without the key (written
  before phase D) runs per episode, a result without ``result_meta.json`` is per episode;
* the package seam (``output_level.run_context`` / ``source_kwargs``): the level reaches a
  package that takes it on the context or on ``run_source`` and an episode run on a package
  that takes none is the pre-phase-D call; a participant run there fails with a message;
* the participant merge: one row per participant in first-appearance order (also those with
  no value), the cohort's own id spelling kept although the web's cohort conversion reads
  numeric ids as numbers, and the two guards (pooled ids, per-episode C4 output);
* a whole runner + fan-in at both levels with ``tests/fixtures/fake_spacescans_levels.py``;
* the results endpoints: ``level`` everywhere, linkage rates at the table's level, and the
  participant map rule (the state of the longest episode).

The participant VALUES (the day-weighted formula) are the package's (track A); this file
tests the web's plumbing around them.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from app import output_level
from app.experiments import _adapter, _merge, bg_ndi_wi

FIXTURES = Path(__file__).parent / "fixtures"

CSV_TEXT_IDS = (
    "pid,startDate,endDate,longitude,latitude,state_fips\n"
    "A7,2017-01-01,2017-03-31,-93.0,45.0,27\n"
    "B12,2017-01-01,2017-12-31,-90.0,40.0,17\n"
    "A7,2017-04-01,2017-12-31,-94.0,44.0,19\n"
    "C450,2017-02-01,2017-02-28,-80.0,35.0,37\n"
)

# Synthetic ids that a spreadsheet would read as numbers: the web's cohort conversion
# (pid_as_str=False, kept for the legacy cache keys) turns them into 7, 12 and 450.
CSV_NUMERIC_IDS = (
    "pid,startDate,endDate,longitude,latitude,state_fips\n"
    "007,2017-01-01,2017-03-31,-93.0,45.0,27\n"      # 90 days in MN
    "12,2017-01-01,2017-12-31,-90.0,40.0,17\n"
    "007,2017-04-01,2017-12-31,-94.0,44.0,19\n"      # 275 days in IA: the longest
    "0450,2017-02-01,2017-02-28,-80.0,35.0,37\n"
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    """A run with the level-aware fake CLI: data, lock and cache under tmp_path."""
    import app.config

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI",
                        FIXTURES / "fake_spacescans_levels.py")
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_PYTHON", Path(sys.executable))
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", data)
    monkeypatch.setattr(app.config.settings, "DATA_DIR", tmp_path / "appdata")
    monkeypatch.setattr(app.config.settings, "C3_CACHE_DIR", tmp_path / "appdata" / "c3_cache")
    monkeypatch.delenv("FAKE_SPACESCANS_GROUPING", raising=False)
    monkeypatch.delenv("FAKE_SPACESCANS_NO_VALUE", raising=False)
    return tmp_path


def _level_context_class():
    """A RunContext that takes ``output_level`` (whatever the installed package has)."""
    from spacescans.orchestrate import RunContext

    @dataclasses.dataclass(frozen=True)
    class LevelContext(RunContext):
        output_level: str = "episode"

    return LevelContext


@dataclasses.dataclass(frozen=True)
class OldContext:
    """The RunContext of spacescans d92f7a3 (deployed 2026-10-15): no output level."""

    run_dir: Path
    cohort_parquet: Path
    data_dir: Path
    buffer_m: object = 270
    raster_res_m: object = 25
    name_suffix: str = ""
    overlay: object = None
    engine: object = None

    @classmethod
    def from_task_dir(cls, task_dir, *, data_dir, buffer_m=270, raster_res_m=25, overlay=None):
        task = Path(task_dir)
        return cls(run_dir=task, cohort_parquet=task / "input.parquet", data_dir=Path(data_dir),
                   buffer_m=buffer_m, raster_res_m=raster_res_m,
                   name_suffix=f"_task_{task.name[-8:]}", overlay=overlay)


def _old_run_source(experiment, keys, ctx, *, cache, executor, on_event=None, cancel=None,
                    reuse=None):
    raise AssertionError("a run on a package without levels must not start at participant level")


@pytest.fixture
def participant_package(monkeypatch):
    """Stand in for a package whose RunContext takes ``output_level`` (track A's work).

    The real render still forces episode grouping into the YAML, so the fake CLI is told the
    grouping through its environment, and the render check is bypassed (tested on its own).
    """
    cls = _level_context_class()
    monkeypatch.setattr(output_level, "_context_class", lambda: cls)
    monkeypatch.setattr(output_level, "check_rendered", lambda steps, ctx, level: None)
    monkeypatch.setenv("FAKE_SPACESCANS_GROUPING", "patient")
    return cls


@pytest.fixture
def no_level_package(monkeypatch):
    """A package that takes no output level anywhere (spacescans d92f7a3)."""
    monkeypatch.setattr(output_level, "_context_class", lambda: OldContext)
    monkeypatch.setattr(output_level, "_run_source", lambda: _old_run_source)


def _task(root: Path, name: str, variables: list[str], *, csv: str = CSV_NUMERIC_IDS,
          level: str | None = "participant") -> Path:
    task_dir = root / name
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "input.csv").write_text(csv)
    config = {"experiment": "auto", "version": 1, "input_file": "input.csv",
              "variables": variables,
              "buffer": {"shape": "circle", "size": 270, "raster_res_m": 25}}
    if level is not None:
        config["output_level"] = level
    (task_dir / "config.json").write_text(json.dumps(config))
    return task_dir


def _status(task_dir: Path) -> dict:
    return json.loads((task_dir / "status.json").read_text())


# ---------------------------------------------------------------------------
# level rules
# ---------------------------------------------------------------------------

def test_default_is_participant_and_a_config_without_the_key_is_episode():
    assert output_level.DEFAULT_LEVEL == "participant"
    assert output_level.normalize(None) == "participant"
    assert output_level.of_config({}) == "episode"          # written before phase D
    assert output_level.of_config({"output_level": "participant"}) == "participant"
    assert output_level.of_config({"output_level": " Episode "}) == "episode"


@pytest.mark.parametrize("bad", ["patient", "person", "", 1, ["episode"]])
def test_an_unknown_level_is_refused(bad):
    with pytest.raises(output_level.OutputLevelError):
        output_level.normalize(bad)


def test_result_level_comes_from_the_meta_file(tmp_path):
    assert output_level.result_level(tmp_path) == "episode"             # pre-phase-D result
    output_level.write_result_meta(tmp_path, level="participant", rows=3, experiments=["x"])
    assert output_level.result_level(tmp_path) == "participant"
    meta = output_level.read_result_meta(tmp_path)
    assert meta["row_unit"] == "participants" and meta["rows"] == 3
    output_level.clear_result_meta(tmp_path)
    assert output_level.result_level(tmp_path) == "episode"


def test_save_config_states_the_level(monkeypatch, tmp_path):
    import app.config
    from app import task_manager

    monkeypatch.setattr(app.config.settings, "TASKS_DIR", tmp_path / "tasks")
    meta = task_manager.create_task(1, "levels")
    task_manager.save_config(meta["id"], {"variables": ["ndi"], "buffer": {"size": 270}})
    cfg = json.loads((tmp_path / "tasks" / f"task-{meta['id']}" / "config.json").read_text())
    assert cfg["output_level"] == "participant"
    task_manager.save_config(meta["id"], {"variables": ["ndi"], "buffer": {"size": 270},
                                          "output_level": "episode"})
    cfg = json.loads((tmp_path / "tasks" / f"task-{meta['id']}" / "config.json").read_text())
    assert cfg["output_level"] == "episode"
    assert task_manager.get_task(meta["id"])["output_level"] == "episode"


# ---------------------------------------------------------------------------
# package seam
# ---------------------------------------------------------------------------

def test_the_level_rides_on_a_context_that_takes_it(monkeypatch, tmp_path):
    cls = _level_context_class()
    monkeypatch.setattr(output_level, "_context_class", lambda: cls)
    assert output_level.package_support() == ("context", "output_level")
    ctx = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                   overlay=None, level="participant")
    assert ctx.output_level == "participant" and ctx.buffer_m == 270
    assert ctx.name_suffix == f"_task_{tmp_path.name[-8:]}"       # still from_task_dir's
    ctx = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                   overlay=None, level="episode")
    assert ctx.output_level == "episode"                          # stated, not defaulted
    assert output_level.source_kwargs("participant") == {}


def test_the_level_rides_on_run_source_as_output_grouping(monkeypatch, tmp_path):
    def run_source(experiment, keys, ctx, *, cache, executor, on_event=None,
                   output_grouping="patient"):
        return None

    monkeypatch.setattr(output_level, "_context_class", lambda: OldContext)
    monkeypatch.setattr(output_level, "_run_source", lambda: run_source)
    assert output_level.package_support() == ("run_source", "output_grouping")
    assert output_level.source_kwargs("participant") == {"output_grouping": "patient"}
    assert output_level.source_kwargs("episode") == {"output_grouping": "episode"}
    ctx = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                   overlay=None, level="participant")
    assert isinstance(ctx, OldContext)


def test_a_package_without_levels_runs_episodes_as_before_and_refuses_participants(
        no_level_package, tmp_path):
    assert output_level.package_support() is None
    assert not output_level.supports_participant()
    ctx = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                   overlay=None, level="episode")
    assert ctx == OldContext.from_task_dir(tmp_path, data_dir=tmp_path, buffer_m=270,
                                           raster_res_m=25, overlay=None)
    assert output_level.source_kwargs("episode") == {}
    with pytest.raises(output_level.ParticipantLevelUnsupported, match="episode-level"):
        output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                 overlay=None, level="participant")


def test_check_rendered_names_a_c4_step_rendered_per_episode(monkeypatch):
    import spacescans.orchestrate.render as render_mod

    class Step:
        def __init__(self, name, is_c3, grouping):
            self.name, self.is_c3, self.grouping = name, is_c3, grouping

    def fake_render(step, ctx):
        if step.grouping is None:
            return {"name": step.name}                     # no time block: nothing to check
        return {"time": {"output_grouping": step.grouping}}

    monkeypatch.setattr(render_mod, "render", fake_render)
    good = [Step("c3_bg", True, "episode"), Step("c4_a", False, "patient"),
            Step("c4_static", False, None)]
    assert output_level.check_rendered(good, object(), "participant") is None
    bad = good + [Step("c4_b", False, "episode")]
    assert output_level.check_rendered(bad, object(), "participant") == "c4_b"


def test_installed_package_renders_participant_level_when_it_says_it_can(tmp_path):
    """Against the real installed spacescans: skipped until the package takes a level
    (track A); then the seam must put ``patient`` into every C4 step's time block."""
    if not output_level.supports_participant():
        pytest.skip("the installed spacescans takes no output level (phase D track A "
                    "not integrated yet)")
    from spacescans import catalog

    steps = catalog.plan("bg_ndi_wi", ["ndi", "walkability"])
    ctx = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270, raster_res_m=25,
                                   overlay=None, level="participant")
    if output_level.package_support()[0] == "context":
        assert output_level.check_rendered(steps, ctx, "participant") is None
        ctx_ep = output_level.run_context(tmp_path, data_dir=tmp_path, buffer_m=270,
                                          raster_res_m=25, overlay=None, level="episode")
        assert output_level.check_rendered(steps, ctx_ep, "episode") is None


# ---------------------------------------------------------------------------
# participant merge
# ---------------------------------------------------------------------------

def _pipeline_input(task_dir: Path) -> None:
    """input.parquet as the web's runner writes it (numeric ids read as numbers)."""
    from spacescans import cohort

    cohort.to_pipeline_parquet(task_dir / "input.csv", task_dir / "input.parquet",
                               variant="bg_ndi_wi", pid_as_str=False)


def test_ids_map_back_to_the_cohorts_spelling(tmp_path):
    task_dir = _task(tmp_path, "task-ids00001", ["ndi"])
    _pipeline_input(task_dir)
    assert pd.read_parquet(task_dir / "input.parquet")["pid"].tolist() == [7, 12, 7, 450]
    lookup = output_level.id_lookup(task_dir)
    assert lookup == {"7": "007", "12": "12", "450": "0450"}
    assert output_level.participants(task_dir)["pid"].tolist() == ["007", "12", "0450"]


def test_rows_without_an_id_are_left_out_of_the_participant_table(fake_cli,
                                                                    participant_package):
    csv = ("pid,startDate,endDate,longitude,latitude\n"
           "A7,2017-01-01,2017-12-31,-93.0,45.0\n"
           ",2017-01-01,2017-12-31,-94.0,44.0\n"
           " ,2017-01-01,2017-12-31,-94.0,44.0\n"
           "B12,2017-01-01,2017-12-31,-90.0,40.0\n")
    task_dir = _task(fake_cli, "task-blank001", ["ndi"], csv=csv)
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)
    result = pd.read_csv(_merge.fan_in(task_dir, ["bg_ndi_wi"]), dtype={"pid": str})
    assert result["pid"].tolist() == ["A7", "B12"]
    records = [json.loads(line) for line in (task_dir / "logs.jsonl").read_text().splitlines()]
    blank = [r for r in records if r.get("event") == "participant_rows_without_id"]
    assert blank and blank[0]["rows"] == 2 and blank[0]["level"] == "warning"


def test_two_spellings_of_one_number_are_refused(tmp_path):
    csv = ("pid,startDate,endDate,longitude,latitude\n"
           "007,2017-01-01,2017-12-31,-93.0,45.0\n"
           "7,2017-01-01,2017-12-31,-94.0,44.0\n")
    task_dir = _task(tmp_path, "task-ids00002", ["ndi"], csv=csv)
    _pipeline_input(task_dir)
    with pytest.raises(output_level.OutputLevelError) as exc:
        output_level.id_lookup(task_dir)
    assert "1 row(s)" in str(exc.value)
    assert "007" not in str(exc.value)                   # no cohort value in the message


def _c4(task_dir: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(task_dir / "output" / name, index=False)


def test_participant_partial_merges_variables_in_request_order(tmp_path):
    task_dir = _task(tmp_path, "task-part0001", ["ndi", "walkability"])
    _pipeline_input(task_dir)
    _c4(task_dir, "c4_ndi.parquet", pd.DataFrame({"PATID": [7, 12], "ndi": [1.5, 2.0]}))
    _c4(task_dir, "c4_wi.parquet",
        pd.DataFrame({"PATID": [450, 7], "NatWalkInd": [9.0, 8.0], "ndi": [0.0, 0.0]}))
    table, stats = output_level.participant_partial(
        task_dir, "bg_ndi_wi", ["ndi", "walkability"],
        {"ndi": "c4_ndi.parquet", "walkability": "c4_wi.parquet"},
        {"ndi": ["ndi"], "walkability": ["NatWalkInd", "ndi"]})
    by_pid = table.set_index("pid")
    assert set(by_pid.index) == {"007", "12", "0450"}
    assert list(table.columns) == ["pid", "ndi", "NatWalkInd"]      # first variable wins "ndi"
    assert by_pid.loc["007", "ndi"] == 1.5 and by_pid.loc["007", "NatWalkInd"] == 8.0
    assert pd.isna(by_pid.loc["0450", "ndi"]) and by_pid.loc["0450", "NatWalkInd"] == 9.0
    assert (stats.cohort_n, stats.matched_n, stats.match_pct) == (3, 3, 100.0)
    assert stats.as_log_fields()["output_level"] == "participant"


def test_participant_partial_counts_participants_without_a_value(tmp_path):
    task_dir = _task(tmp_path, "task-part0002", ["ndi"])
    _pipeline_input(task_dir)
    _c4(task_dir, "c4_ndi.parquet", pd.DataFrame({"PATID": [7], "ndi": [1.5]}))
    _table, stats = output_level.participant_partial(
        task_dir, "bg_ndi_wi", ["ndi"], {"ndi": "c4_ndi.parquet"}, {"ndi": ["ndi"]})
    assert (stats.cohort_n, stats.matched_n, stats.match_pct) == (3, 1, 33.33)
    assert stats.low


def test_participant_partial_refuses_per_episode_output(tmp_path):
    task_dir = _task(tmp_path, "task-part0003", ["ndi"])
    _pipeline_input(task_dir)
    _c4(task_dir, "c4_ndi.parquet",
        pd.DataFrame({"PATID": [7, 12, 7, 450], "geoid": [0, 1, 2, 3], "ndi": [1.0] * 4}))
    with pytest.raises(output_level.OutputLevelError, match="more than one row per participant"):
        output_level.participant_partial(task_dir, "bg_ndi_wi", ["ndi"],
                                         {"ndi": "c4_ndi.parquet"}, {"ndi": ["ndi"]})


def test_participant_partial_applies_and_writes_back_renames(tmp_path):
    task_dir = _task(tmp_path, "task-part0004", ["faqsd"])
    _pipeline_input(task_dir)
    _c4(task_dir, "c4_faqsd.parquet", pd.DataFrame({"PATID": [7, 12, 450], "o3": [1.0, 2.0, 3.0]}))
    table, _stats = output_level.participant_partial(
        task_dir, "faqsd", ["faqsd"], {"faqsd": "c4_faqsd.parquet"}, {"faqsd": ["faqsd_o3"]},
        renames={"o3": "faqsd_o3"}, rewrite_in_place=True)
    assert list(table.columns) == ["pid", "faqsd_o3"]
    assert "faqsd_o3" in pd.read_parquet(task_dir / "output" / "c4_faqsd.parquet").columns


def test_participant_fan_in_keeps_every_participant_once_in_order(tmp_path):
    task_dir = _task(tmp_path, "task-fan00001", ["ndi", "cbp_zcta5"])
    (task_dir / "output" / "result_bg_ndi_wi.csv").write_text("pid,ndi\n0450,4.0\n007,1.5\n")
    (task_dir / "output" / "result_zcta5_cbp.csv").write_text("pid,ndi,cbp\n12,9,2\n")
    df = output_level.participant_fan_in(task_dir, ["bg_ndi_wi", "zcta5_cbp"])
    assert df["pid"].tolist() == ["007", "12", "0450"]            # first appearance
    assert list(df.columns) == ["pid", "ndi", "ndi_zcta5_cbp_dup", "cbp"]
    assert df["ndi"].tolist()[0] == "1.5" and pd.isna(df["ndi"].tolist()[1])
    assert df["cbp"].tolist() == [None, "2", None] or df["cbp"].isna().tolist() == [True, False, True]


# ---------------------------------------------------------------------------
# a whole run at each level (runner + fan-in)
# ---------------------------------------------------------------------------

def test_participant_run_writes_one_row_per_participant(fake_cli, participant_package):
    task_dir = _task(fake_cli, "task-run00001", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)
    partial = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv", dtype={"pid": str})
    assert list(partial.columns) == ["pid", "ndi"]
    assert sorted(partial["pid"]) == ["007", "0450", "12"]

    out = _merge.fan_in(task_dir, ["bg_ndi_wi"])
    result = pd.read_csv(out, dtype={"pid": str})
    assert list(result.columns) == ["pid", "ndi"]                 # no dates, coordinates, ids
    assert result["pid"].tolist() == ["007", "12", "0450"]
    # The fake's per-participant value: the mean of (episode_id + 1) over the episodes.
    assert result["ndi"].tolist() == [2.0, 2.0, 4.0]
    assert output_level.result_level(task_dir) == "participant"
    dictionary = pd.read_csv(task_dir / "output" / "feature_dictionary.csv")
    assert dictionary["feature_name"].tolist()[0] == "pid"
    assert "ndi" in dictionary["feature_name"].tolist()


def test_participant_without_a_contributing_day_keeps_a_row(fake_cli, participant_package,
                                                             monkeypatch):
    monkeypatch.setenv("FAKE_SPACESCANS_NO_VALUE", "450")
    task_dir = _task(fake_cli, "task-run00002", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)
    result = pd.read_csv(_merge.fan_in(task_dir, ["bg_ndi_wi"]), dtype={"pid": str})
    assert result["pid"].tolist() == ["007", "12", "0450"]
    assert pd.isna(result["ndi"].tolist()[2])


def test_participant_run_on_a_package_without_levels_fails_with_a_message(
        fake_cli, no_level_package):
    task_dir = _task(fake_cli, "task-run00003", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 1
    status = _status(task_dir)
    assert status["status"] == "error"
    assert "episode-level output" in status["message"]
    assert not (task_dir / "pipeline_configs").exists()           # no step ran


def test_dispatcher_refuses_a_participant_task_up_front_without_levels(
        fake_cli, no_level_package, monkeypatch):
    from app import dispatcher

    task_dir = _task(fake_cli, "task-disp0001", ["ndi"])
    spawned = []
    monkeypatch.setattr(dispatcher.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a) or None)
    result = dispatcher.dispatch(str(task_dir))
    assert result["failed"] == ["bg_ndi_wi"] and not spawned
    status = _status(task_dir)
    assert status["status"] == "error" and "episode-level output" in status["message"]


def test_pooled_ids_fail_the_merge_without_quoting_them(fake_cli, participant_package):
    csv = ("pid,startDate,endDate,longitude,latitude\n"
           "007,2017-01-01,2017-12-31,-93.0,45.0\n"
           "7,2017-01-01,2017-12-31,-94.0,44.0\n")
    task_dir = _task(fake_cli, "task-run00004", ["ndi"], csv=csv)
    assert bg_ndi_wi.run(task_dir) == 1
    status = _status(task_dir)
    assert status["message"].startswith("merge failed: participant-level output")
    assert "007" not in status["message"]
    assert "007" not in (task_dir / "logs.jsonl").read_text()


def test_a_config_without_the_key_runs_per_episode(fake_cli, participant_package, monkeypatch):
    """Pre-phase-D configs (old tasks, the paper's scripts) keep their episode output even
    when the package can do participants; the level is stated to the package."""
    monkeypatch.delenv("FAKE_SPACESCANS_GROUPING")
    seen = []
    real = output_level.run_context

    def spy(*args, **kwargs):
        ctx = real(*args, **kwargs)
        seen.append(ctx.output_level)
        return ctx

    monkeypatch.setattr(output_level, "run_context", spy)
    task_dir = _task(fake_cli, "task-run00005", ["ndi"], level=None, csv=CSV_TEXT_IDS)
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)
    assert seen == ["episode"]
    partial = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv", dtype={"pid": str})
    assert list(partial.columns) == ["pid", "episode_id", "ndi"] and len(partial) == 4

    out = _merge.fan_in(task_dir, ["bg_ndi_wi"])
    from spacescans.orchestrate import merge as pkg_merge

    expected = pkg_merge.fan_in_from_dir(task_dir, ["bg_ndi_wi"])
    assert pd.read_csv(out, dtype=str).equals(expected)            # the pre-phase-D table
    assert output_level.result_level(task_dir) == "episode"
    assert output_level.read_result_meta(task_dir)["row_unit"] == "episodes"


def test_episode_run_with_all_numeric_ids(fake_cli, participant_package, monkeypatch):
    """Web 0.2.7 and d92f7a3 failed this merge ("merge on str and int64 columns"): the web
    converts the cohort with pid_as_str=False, so all-numeric ids reach C4 as numbers."""
    monkeypatch.delenv("FAKE_SPACESCANS_GROUPING")
    task_dir = _task(fake_cli, "task-run00006", ["ndi"], level="episode")
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)["message"]
    partial = pd.read_csv(task_dir / "output" / "result_bg_ndi_wi.csv", dtype={"pid": str})
    assert partial["pid"].tolist() == ["007", "12", "007", "0450"]
    result = pd.read_csv(_merge.fan_in(task_dir, ["bg_ndi_wi"]), dtype={"pid": str})
    assert result["pid"].tolist() == ["007", "12", "007", "0450"]
    assert result["ndi"].tolist() == [1.0, 2.0, 3.0, 4.0]          # every episode linked


def test_episode_partial_equals_the_packages_for_text_ids(tmp_path):
    from spacescans.orchestrate import merge as pkg_merge

    task_dir = _task(tmp_path, "task-epi00001", ["ndi", "walkability"], csv=CSV_TEXT_IDS)
    _pipeline_input(task_dir)
    ids = ["A7", "B12", "A7", "C450"]
    _c4(task_dir, "c4_ndi.parquet",
        pd.DataFrame({"PATID": ids, "geoid": [0, 1, 2, 3], "ndi": [1.0, None, 3.0, 4.0]}))
    _c4(task_dir, "c4_wi.parquet",
        pd.DataFrame({"PATID": ids[:3], "geoid": [0, 1, 2], "NatWalkInd": [5.0, 6.0, 7.0]}))
    args = (task_dir, "bg_ndi_wi", ["ndi", "walkability"],
            {"ndi": "c4_ndi.parquet", "walkability": "c4_wi.parquet"},
            {"ndi": ["ndi"], "walkability": ["NatWalkInd"]})
    ours, our_stats = _merge.episode_partial(*args)
    theirs, their_stats = pkg_merge.partial_from_dir(*args)
    assert ours.to_csv(index=False) == theirs.to_csv(index=False)
    assert our_stats == their_stats


def test_participant_run_with_the_installed_package(fake_cli, monkeypatch):
    """The real seam and render (no stand-ins): the fake CLI follows the YAML's grouping.
    Skipped until the installed spacescans takes an output level (track A)."""
    if not output_level.supports_participant():
        pytest.skip("the installed spacescans takes no output level")
    task_dir = _task(fake_cli, "task-real0001", ["ndi", "walkability"])
    assert bg_ndi_wi.run(task_dir) == 0, _status(task_dir)
    import yaml

    for name in ("c4_ndi.yaml", "c4_wi.yaml"):
        cfg = yaml.safe_load((task_dir / "pipeline_configs" / name).read_text())
        assert cfg["time"]["output_grouping"] == "patient", name
    result = pd.read_csv(_merge.fan_in(task_dir, ["bg_ndi_wi"]), dtype={"pid": str})
    assert result["pid"].tolist() == ["007", "12", "0450"]
    assert list(result.columns)[0] == "pid" and "startDate" not in result.columns


def test_episode_dictionary_bytes_are_unchanged_for_shipped_columns(tmp_path):
    from app import feature_dictionary
    from spacescans.catalog import write_feature_csv

    cols = ["pid", "startDate", "ndi", "NatWalkInd", "something_else"]
    a = write_feature_csv(cols, tmp_path / "a.csv")
    b = feature_dictionary.write_csv(cols, tmp_path / "b.csv", level="episode",
                                     config={"variables": ["ndi", "walkability"]})
    assert a.read_bytes() == b.read_bytes()


def test_custom_columns_are_described_from_their_definition(tmp_path):
    from app import feature_dictionary

    definition = {"label": "My greenness", "description": "Synthetic.",
                  "value_cols": ["greenness", "ndi"], "value_labels": {"greenness": "Green"},
                  "value_units": {"greenness": "index"}}
    config = {"variables": ["ndi", "custom_0a1b2c3d"],
              "custom_variables": {"custom_0a1b2c3d": definition}}
    out = feature_dictionary.write_csv(["pid", "ndi", "greenness"], tmp_path / "d.csv",
                                       level="participant", config=config)
    rows = pd.read_csv(out).set_index("feature_name")
    assert list(rows.index) == ["pid", "ndi", "greenness"]
    assert rows.loc["greenness", "short_description"] == "Green"
    assert rows.loc["greenness", "detailed_description"] == "Synthetic. Unit: index."
    # "ndi" is the shipped variable's column here, so it keeps the catalog's description.
    assert rows.loc["ndi", "short_description"] != "My greenness (ndi)"


# ---------------------------------------------------------------------------
# results endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def api(monkeypatch, tmp_path):
    import app.config
    from fastapi.testclient import TestClient

    from app.auth import create_access_token
    from app.main import app as fastapi_app

    monkeypatch.setattr(app.config.settings, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(app.config.settings, "DATA_DIR", tmp_path)
    token = create_access_token({"sub": "1", "email": "t@example.com"})
    return TestClient(fastapi_app, headers={"Authorization": f"Bearer {token}"})


def _finished_task(tmp_path, *, level: str | None, result: str, csv: str = CSV_NUMERIC_IDS):
    from app import task_manager

    meta = task_manager.create_task(1, f"t-{level}-{len(result)}")
    task_dir = tmp_path / "tasks" / f"task-{meta['id']}"
    (task_dir / "input.csv").write_text(csv)
    (task_dir / "output" / "result.csv").write_text(result)
    if level is not None:
        output_level.write_result_meta(task_dir, level=level, rows=result.count("\n") - 1,
                                       experiments=["bg_ndi_wi"])
    return meta["id"], task_dir


def test_preview_reports_the_level_and_linkage_per_participant(api, tmp_path):
    task_id, _ = _finished_task(tmp_path, level="participant",
                                result="pid,ndi,NatWalkInd\n007,1.5,\n12,2.0,3\n0450,,\n")
    body = api.get(f"/api/tasks/{task_id}/results/preview").json()
    assert body["level"] == "participant" and body["row_unit"] == "participants"
    assert body["total_rows"] == 3
    assert body["rows"][0][0] == "007"                            # the id as written
    assert body["linkage"] == {
        "ndi": {"linked": 2, "total": 3, "rate_pct": 66.67},
        "NatWalkInd": {"linked": 1, "total": 3, "rate_pct": 33.33},
    }


def test_participant_linkage_counts_a_column_named_like_a_cohort_column(api, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude,ndi\nA,2017-01-01,2017-03-31,-93,45,x\n"
    task_id, _ = _finished_task(tmp_path, level="participant", result="pid,ndi\nA,1.5\n",
                                csv=csv)
    body = api.get(f"/api/tasks/{task_id}/results/preview").json()
    assert body["linkage"] == {"ndi": {"linked": 1, "total": 1, "rate_pct": 100.0}}


def test_preview_of_a_pre_phase_d_result_is_per_episode(api, tmp_path):
    result = ("pid,startDate,endDate,longitude,latitude,state_fips,ndi\n"
              "007,2017-01-01,2017-03-31,-93.0,45.0,27,1\n"
              "12,2017-01-01,2017-12-31,-90.0,40.0,17,\n")
    task_id, _ = _finished_task(tmp_path, level=None, result=result)
    body = api.get(f"/api/tasks/{task_id}/results/preview").json()
    assert body["level"] == "episode" and body["row_unit"] == "episodes"
    assert body["linkage"] == {"ndi": {"linked": 1, "total": 2, "rate_pct": 50.0}}


def test_histogram_and_download_carry_the_level(api, tmp_path):
    task_id, _ = _finished_task(tmp_path, level="participant",
                                result="pid,ndi\n007,1.5\n12,2.0\n0450,4\n")
    body = api.get(f"/api/tasks/{task_id}/results/histogram").json()
    assert body["level"] == "participant"
    assert [h["name"] for h in body["histograms"]] == ["ndi"]
    resp = api.get(f"/api/tasks/{task_id}/results")
    assert resp.status_code == 200 and resp.headers["x-output-level"] == "participant"


def test_participant_map_uses_the_state_of_the_longest_episode(api, tmp_path):
    task_id, _ = _finished_task(tmp_path, level="participant",
                                result="pid,ndi\n007,2.0\n12,3.0\n0450,5.0\n")
    body = api.get(f"/api/tasks/{task_id}/results/geo?value_col=ndi").json()
    assert body["level"] == "participant" and body["state_rule"] == "longest_episode"
    by_state = {b["state_fips"]: b for b in body["by_state"]}
    # 007 lived 90 days in 27 and 275 days in 19: placed in 19, once.
    assert by_state == {
        "19": {"state_fips": "19", "count": 1, "mean": 2.0},
        "17": {"state_fips": "17", "count": 1, "mean": 3.0},
        "37": {"state_fips": "37", "count": 1, "mean": 5.0},
    }


def test_state_rule_ties_go_to_the_most_recent_start_then_the_earlier_row(tmp_path):
    csv = ("pid,startDate,endDate,longitude,latitude,state_fips\n"
           "A,2016-01-01,2016-01-10,0,0,01\n"        # 10 days
           "A,2017-01-01,2017-01-10,0,0,02\n"        # 10 days, later start: wins
           "B,2017-01-01,2017-01-10,0,0,04\n"        # same length and start: earlier row wins
           "B,2017-01-01,2017-01-10,0,0,05\n"
           "C,,,0,0,06\n"                            # undated ranks below any dated episode
           "C,2017-01-01,2017-01-01,0,0,08\n"
           "D,2017-01-01,2017-12-31,0,0,\n"          # longest has no state: not placed
           "D,2017-01-01,2017-01-02,0,0,09\n")
    task_dir = tmp_path / "t"
    task_dir.mkdir()
    (task_dir / "input.csv").write_text(csv)
    states = output_level.participant_states(task_dir)
    assert dict(zip(states["pid"], states["state_fips"])) == {"A": "02", "B": "04", "C": "08"}


def test_no_state_column_means_no_map_at_either_level(api, tmp_path):
    csv = "pid,startDate,endDate,longitude,latitude\n007,2017-01-01,2017-03-31,-93.0,45.0\n"
    task_id, _ = _finished_task(tmp_path, level="participant", result="pid,ndi\n007,1\n",
                                csv=csv)
    body = api.get(f"/api/tasks/{task_id}/results/geo?value_col=ndi").json()
    assert body["by_state"] == [] and body["level"] == "participant"


def test_coverage_counts_episodes(api, tmp_path):
    from app import task_manager

    meta = task_manager.create_task(1, "cov")
    task_dir = tmp_path / "tasks" / f"task-{meta['id']}"
    (task_dir / "input.csv").write_text(CSV_NUMERIC_IDS)

    def fake(task_id, keys, **_kw):
        return {"row_count": 4, "variables": {}}

    import app.task_manager as tm

    original = tm.compute_coverage
    tm.compute_coverage = fake
    try:
        body = api.get(f"/api/tasks/{meta['id']}/coverage?variables=ndi").json()
    finally:
        tm.compute_coverage = original
    assert body["level"] == "episode" and body["row_count"] == 4


def test_put_config_defaults_to_participant_and_refuses_an_unknown_level(api, tmp_path):
    from app import task_manager

    meta = task_manager.create_task(1, "cfg")
    base = {"buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": ["ndi"]}
    assert api.put(f"/api/tasks/{meta['id']}/config", json=base).status_code == 200
    cfg = json.loads((tmp_path / "tasks" / f"task-{meta['id']}" / "config.json").read_text())
    assert cfg["output_level"] == "participant"
    resp = api.put(f"/api/tasks/{meta['id']}/config", json={**base, "output_level": "patient"})
    assert resp.status_code == 422
    resp = api.put(f"/api/tasks/{meta['id']}/config", json={**base, "output_level": "episode"})
    assert resp.status_code == 200
    task = api.get(f"/api/tasks/{meta['id']}").json()
    assert task["output_level"] == "episode"
