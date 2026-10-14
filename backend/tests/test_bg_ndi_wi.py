"""The runner adapter, through the bg_ndi_wi shim and the fake pipeline CLI.

What the web keeps around ``spacescans.orchestrate.run_source`` (tier-2 phase C,
``app/experiments/_adapter.py``): the run lock and its message, the SIGTERM
handler, status.json with the runners' progress formula and messages, the
``logs.jsonl`` lines, the legacy C3 cache (keys, metas, hit/miss/corrupt/
write-failure paths) and ``result_<exp>.csv`` with the variables in request
order. ``tests/fixtures/fake_spacescans.py`` stands in for ``spacescans run``.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import sys
from pathlib import Path

import pandas as pd
import pytest

from app.experiments import _adapter, bg_ndi_wi

FIXTURES = Path(__file__).parent / "fixtures"
CSV_2 = ("pid,startDate,endDate,longitude,latitude\n"
         "P1,2017-01-01,2017-12-31,-93.0,45.0\n"
         "P2,2017-01-01,2017-12-31,-94.0,44.0\n")


@pytest.fixture
def fake_cli(monkeypatch, tmp_path):
    """Settings for a run with the fake CLI: data, lock and cache under tmp_path."""
    import app.config

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI",
                        FIXTURES / "fake_spacescans.py")
    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_PYTHON", Path(sys.executable))
    monkeypatch.setattr(app.config.settings, "SPACESCANS_DATA_DIR", data)
    monkeypatch.setattr(app.config.settings, "DATA_DIR", tmp_path / "appdata")
    monkeypatch.setattr(app.config.settings, "C3_CACHE_DIR", tmp_path / "appdata" / "c3_cache")
    return tmp_path


def _task(root: Path, name: str, variables: list[str], *, csv: str = CSV_2,
          buffer: dict | None = None) -> Path:
    task_dir = root / name
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    (task_dir / "input.csv").write_text(csv)
    (task_dir / "config.json").write_text(json.dumps({
        "experiment": "auto", "version": 1, "input_file": "input.csv",
        "variables": variables,
        "buffer": buffer or {"shape": "circle", "size": 270, "raster_res_m": 25},
    }))
    return task_dir


def _status(task_dir: Path) -> dict:
    return json.loads((task_dir / "status.json").read_text())


def _logs(task_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (task_dir / "logs.jsonl").read_text().splitlines()
            if line.strip()]


def _runner_lines(task_dir: Path) -> list[str]:
    return [e["msg"] for e in _logs(task_dir) if e.get("source") == "runner"]


# ---------------------------------------------------------------------------
# a whole run
# ---------------------------------------------------------------------------

def test_standalone_run_finishes_and_writes_the_partial(fake_cli):
    task_dir = _task(fake_cli, "task-runtest1", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 0

    status = _status(task_dir)
    assert status["status"] == "finished"
    assert status["progress"] == 1.0
    assert status["total_steps"] == 3                    # c3_bg + c3_bg_2020 + c4_ndi
    assert status["steps"] == ["c3_bg", "c3_bg_2020", "c4_ndi"]
    assert status["current_step"] is None
    assert status["message"] == "Completed 3 pipeline steps"
    assert status["experiments"]["bg_ndi_wi"] == {
        "status": "finished", "progress": 1.0, "current_step": None,
        "steps": ["c3_bg", "c3_bg_2020", "c4_ndi"]}
    assert "started_at" in status and status["pid"] == os.getpid()

    partial = task_dir / "output" / "result_bg_ndi_wi.csv"
    assert partial.exists()
    df = pd.read_csv(partial)
    assert list(df.columns) == ["pid", "episode_id"]      # the fake CLI emits no catalog column
    assert len(df) == 2
    assert not (task_dir / "output" / "result.csv").exists()   # fan-in is the dispatcher's
    assert sorted(p.name for p in (task_dir / "pipeline_configs").glob("*.yaml")) == [
        "c3_bg.yaml", "c3_bg_2020.yaml", "c4_ndi.yaml"]
    assert (task_dir / "input.parquet").exists()


def test_dispatched_run_writes_only_its_slot(fake_cli):
    task_dir = _task(fake_cli, "task-slot0001", ["ndi", "cbp_zcta5"])
    assert bg_ndi_wi.run(task_dir, variables=["walkability", "ndi"]) == 0

    status = _status(task_dir)
    assert "status" not in status                        # the dispatcher owns the task status
    slot = status["experiments"]["bg_ndi_wi"]
    assert slot["status"] == "running"                   # the dispatcher marks it finished
    assert slot["progress"] == 1.0 and slot["current_step"] is None
    assert slot["steps"] == ["c3_bg", "c3_bg_2020", "c4_ndi", "c4_wi"]
    assert slot["message"] == "Completed 4 pipeline steps"
    assert slot["pid"] == os.getpid()
    assert status["steps"] == slot["steps"] and status["total_steps"] == 4
    assert status["progress"] == 1.0


def test_log_lines_are_the_runners(fake_cli):
    """Spawn/exit lines from the runner, pipeline output and cache lines from the step."""
    import app.config

    task_dir = _task(fake_cli, "task-logs0001", ["walkability"])
    assert bg_ndi_wi.run(task_dir, variables=["walkability"]) == 0
    cli = f"{sys.executable} {app.config.settings.SPACESCANS_PIPELINE_CLI}"
    data = app.config.settings.SPACESCANS_DATA_DIR
    cfg = task_dir / "pipeline_configs"
    assert _runner_lines(task_dir) == [
        f"spawning c3_bg: {cli} run --data-dir {data} {cfg / 'c3_bg.yaml'}",
        "step c3_bg exit code 0",
        f"spawning c4_wi: {cli} run --data-dir {data} {cfg / 'c4_wi.yaml'}",
        "step c4_wi exit code 0",
    ]
    by_source = {}
    for e in _logs(task_dir):
        by_source.setdefault(e["source"], []).append(e)
    assert [e["msg"] for e in by_source["c3_bg"]][:3] == [
        "[overlap_fast] tile 1/3 ( 33.3%)", "[overlap_fast] tile 2/3 ( 66.7%)",
        "[overlap_fast] tile 3/3 (100.0%)"]
    assert by_source["c3_bg"][-1]["msg"].startswith("cache write: ") and \
        by_source["c3_bg"][-1]["msg"].endswith("__BG__b270m__r25m.parquet")
    assert all(set(e) == {"ts", "level", "source", "msg"} and e["level"] == "info"
               for e in _logs(task_dir))


def test_status_progress_follows_the_runners_formula(fake_cli, monkeypatch):
    """start idx/total, running (idx+frac)/total, merge (total-0.1)/total, end 1.0."""
    import app.task_manager as tm

    writes: list[dict] = []
    real = tm._write_status

    def recording(task_dir, **kwargs):
        writes.append(json.loads(json.dumps(kwargs)))
        return real(task_dir, **kwargs)

    monkeypatch.setattr(tm, "_write_status", recording)
    task_dir = _task(fake_cli, "task-progress1", ["ndi"])
    assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 0

    slots = [w["experiments"]["bg_ndi_wi"] for w in writes]
    total = 3
    expected = [(0.0, "Preparing input data")]
    for idx, step in enumerate(["c3_bg", "c3_bg_2020", "c4_ndi"]):
        expected.append((idx / total, f"Running {step} ({idx + 1}/{total})"))
        for frac, pct in ((1 / 3, 33), (2 / 3, 66), (1.0, 100)):
            expected.append(((idx + frac) / total, f"Running {step} ({idx + 1}/{total}) — {pct}%"))
    expected.append(((total - 0.1) / total, "Merging variable outputs"))
    expected.append((1.0, "Completed 3 pipeline steps"))
    got = [(s["progress"], s["message"]) for s in slots]
    assert [m for _p, m in got] == [m for _p, m in expected]
    assert [p for p, _m in got] == pytest.approx([p for p, _m in expected])
    assert slots[0]["current_step"] == "csv_to_parquet" and slots[0]["status"] == "running"
    assert [s["current_step"] for s in slots if "current_step" in s] == [
        "csv_to_parquet", "c3_bg", "c3_bg_2020", "c4_ndi", "merge", None]
    assert all(key in slots[0] for key in ("steps", "pid"))


# ---------------------------------------------------------------------------
# the legacy C3 cache
# ---------------------------------------------------------------------------

def test_cache_miss_writes_the_legacy_entries_and_metas(fake_cli):
    import app.config

    task_dir = _task(fake_cli, "task-cache-01", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 0
    cache_dir = app.config.settings.C3_CACHE_DIR
    from spacescans.orchestrate.cache import sha256_file
    sha8 = sha256_file(task_dir / "input.parquet")[:8]
    assert sorted(p.name for p in cache_dir.glob("*.parquet")) == [
        f"{sha8}__BG2020__b270m__r25m.parquet", f"{sha8}__BG__b270m__r25m.parquet"]
    for tag in ("BG", "BG2020"):
        meta = json.loads((cache_dir / f"{sha8}__{tag}__b270m__r25m.meta.json").read_text())
        assert list(meta) == ["sha_full", "boundary", "buffer_m", "raster_res_m",
                              "input_row_count", "wall_clock_seconds", "file_size_bytes",
                              "created_at"]
        assert meta["boundary"] == "BG"                  # bg_ndi_wi labels both vintages "BG"
        assert meta["sha_full"] == sha256_file(task_dir / "input.parquet")
        assert meta["buffer_m"] == 270 and meta["raster_res_m"] == 25
        assert meta["input_row_count"] == 2
        assert meta["file_size_bytes"] == (cache_dir / f"{sha8}__{tag}__b270m__r25m.parquet").stat().st_size
    assert (cache_dir / f"{sha8}__BG__b270m__r25m.parquet").read_bytes() == \
        (task_dir / "output" / "c3_bg.parquet").read_bytes()


def test_cache_hit_skips_the_c3_spawns_and_renders_no_c3_yaml(fake_cli):
    task_a = _task(fake_cli, "task-cache-A", ["ndi"])
    assert bg_ndi_wi.run(task_a) == 0
    task_b = _task(fake_cli, "task-cache-B", ["ndi"])
    assert bg_ndi_wi.run(task_b, variables=["ndi"]) == 0

    spawned = [m.split(":")[0] for m in _runner_lines(task_b) if m.startswith("spawning ")]
    assert spawned == ["spawning c4_ndi"]
    hits = [e for e in _logs(task_b) if e["msg"].startswith("cache hit: ")]
    assert [(e["source"], e["level"]) for e in hits] == [("c3_bg", "info"), ("c3_bg_2020", "info")]
    assert hits[0]["msg"].endswith("__BG__b270m__r25m — skipping pipeline run")
    assert sorted(p.name for p in (task_b / "pipeline_configs").glob("*.yaml")) == ["c4_ndi.yaml"]
    assert (task_b / "output" / "c3_bg.parquet").read_bytes() == \
        (task_a / "output" / "c3_bg.parquet").read_bytes()
    slot = _status(task_b)["experiments"]["bg_ndi_wi"]
    assert slot["progress"] == 1.0 and slot["message"] == "Completed 3 pipeline steps"


def test_cache_hit_progress_jumps_to_the_end_of_the_step(fake_cli, monkeypatch):
    import app.task_manager as tm

    task_a = _task(fake_cli, "task-cache-P1", ["walkability"])
    assert bg_ndi_wi.run(task_a) == 0
    writes: list[dict] = []
    real = tm._write_status
    monkeypatch.setattr(tm, "_write_status",
                        lambda td, **kw: (writes.append(json.loads(json.dumps(kw))), real(td, **kw))[1])
    task_b = _task(fake_cli, "task-cache-P2", ["walkability"])
    assert bg_ndi_wi.run(task_b, variables=["walkability"]) == 0
    slots = [w["experiments"]["bg_ndi_wi"] for w in writes]
    assert (slots[2]["progress"], slots[2]["message"], slots[2]["current_step"]) == (
        (0 + 1) / 2, "Reused cached c3_bg", "c3_bg")


def test_corrupted_cache_entry_is_recomputed(fake_cli):
    import app.config

    task_a = _task(fake_cli, "task-cache-C", ["ndi"])
    assert bg_ndi_wi.run(task_a) == 0
    cache_dir = app.config.settings.C3_CACHE_DIR
    bg = next(cache_dir.glob("*__BG__*.parquet"))
    bg.write_bytes(b"truncated!")

    task_b = _task(fake_cli, "task-cache-D", ["ndi"])
    assert bg_ndi_wi.run(task_b) == 0
    spawned = [m.split(":")[0] for m in _runner_lines(task_b) if m.startswith("spawning ")]
    assert spawned == ["spawning c3_bg", "spawning c4_ndi"]       # BG2020 still hits
    assert bg.stat().st_size > 100


def test_cache_write_failure_does_not_fail_the_run(fake_cli, monkeypatch):
    import shutil as real_shutil

    from spacescans.orchestrate import cache as cache_mod

    real_copy = real_shutil.copy

    def failing_copy(src, dst, *a, **kw):
        if "c3_cache" in str(dst):
            raise OSError(28, "No space left on device")
        return real_copy(src, dst, *a, **kw)

    monkeypatch.setattr(cache_mod.shutil, "copy", failing_copy)
    task_dir = _task(fake_cli, "task-cache-E", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 0
    assert _status(task_dir)["status"] == "finished"
    warnings = [e for e in _logs(task_dir) if e["level"] == "warning"]
    assert [(e["source"], e["msg"][:len("cache write failed: OSError")]) for e in warnings] == [
        ("c3_bg", "cache write failed: OSError"), ("c3_bg_2020", "cache write failed: OSError")]
    assert all(m.endswith(" — continuing") for m in (e["msg"] for e in warnings))


# ---------------------------------------------------------------------------
# failures, the lock and SIGTERM
# ---------------------------------------------------------------------------

def _cli_script(root: Path, body: str) -> Path:
    script = root / "cli.py"
    script.write_text(body)
    return script


def test_step_failure_reports_the_exit_code(fake_cli, monkeypatch):
    import app.config

    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI", _cli_script(
        fake_cli, "import sys\nprint('ERROR: something broke', file=sys.stderr)\nsys.exit(3)\n"))
    task_dir = _task(fake_cli, "task-fail0001", ["ndi"])
    assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 3
    slot = _status(task_dir)["experiments"]["bg_ndi_wi"]
    assert slot["status"] == "error"
    assert slot["message"] == "step c3_bg failed with exit code 3"
    exit_line = [e for e in _logs(task_dir) if e["msg"] == "step c3_bg exit code 3"]
    assert [(e["level"], e["source"]) for e in exit_line] == [("error", "runner")]
    assert not (task_dir / "output" / "result_bg_ndi_wi.csv").exists()


def test_missing_output_parquet_is_an_error(fake_cli, monkeypatch):
    import app.config

    monkeypatch.setattr(app.config.settings, "SPACESCANS_PIPELINE_CLI",
                        _cli_script(fake_cli, "print('nothing written')\n"))
    task_dir = _task(fake_cli, "task-noout001", ["ndi"])
    assert bg_ndi_wi.run(task_dir) == 1
    status = _status(task_dir)
    assert status["status"] == "error"
    assert status["message"] == "step c3_bg produced no output parquet"


def test_input_conversion_failure_is_reported(fake_cli):
    task_dir = _task(fake_cli, "task-badcsv01", ["ndi"],
                     csv="pid,startDate,endDate,longitude,latitude\nP1,not-a-date,2017-11-11,-93.0,45.0\n")
    assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 1
    slot = _status(task_dir)["experiments"]["bg_ndi_wi"]
    assert slot["status"] == "error" and slot["message"].startswith("input conversion failed: ")
    lines = _logs(task_dir)
    assert len(lines) == 1 and lines[0]["source"] == "runner" and lines[0]["level"] == "error"
    assert lines[0]["msg"].startswith("csv_to_parquet failed: ")
    assert not (task_dir / "input.parquet").exists()


def _recorded_slots(monkeypatch) -> list[dict]:
    """Every status.json write of a dispatched run, as the slot fields it wrote."""
    import app.task_manager as tm

    writes: list[dict] = []
    real = tm._write_status

    def recording(task_dir, **kwargs):
        writes.append(json.loads(json.dumps(kwargs)))
        return real(task_dir, **kwargs)

    monkeypatch.setattr(tm, "_write_status", recording)
    return writes


@pytest.mark.parametrize("buffer, exc", [
    ({"size": 270}, "KeyError('raster_res_m')"),
    ({"raster_res_m": 25}, "KeyError('size')"),
    (None, "KeyError('buffer')"),
    ("270", "TypeError(\"string indices must be integers, not 'str'\")"),
])
def test_an_unrenderable_buffer_fails_as_the_runners_did(fake_cli, monkeypatch, buffer, exc):
    """0.2.7: the first step starts, its cache lookup warns and its render fails on the
    same lookup; status ``render failed at c3_bg``, exit 1, no step runs. The expected
    lines are the 0.2.7 runner's own output for these four configs (web 31c5dc3, run
    with the templates present, 2026-10-14)."""
    task_dir = _task(fake_cli, "task-nores001", ["ndi"])
    config = json.loads((task_dir / "config.json").read_text())
    if buffer is None:
        del config["buffer"]
    else:
        config["buffer"] = buffer
    (task_dir / "config.json").write_text(json.dumps(config))
    writes = _recorded_slots(monkeypatch)

    assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 1
    assert [(e["level"], e["source"], e["msg"]) for e in _logs(task_dir)] == [
        ("warning", "c3_bg", f"cache check failed for c3_bg: {exc} — running fresh"),
        ("error", "runner", f"render_yaml(c3_bg) failed: {exc}"),
    ]
    slots = [w["experiments"]["bg_ndi_wi"] for w in writes]
    assert [(s.get("status"), s.get("current_step"), s.get("progress"), s["message"])
            for s in slots] == [
        ("running", "csv_to_parquet", 0.0, "Preparing input data"),
        (None, "c3_bg", 0.0, "Running c3_bg (1/3)"),
        ("error", None, None, "render failed at c3_bg"),
    ]
    assert not (task_dir / "pipeline_configs").exists()


def test_missing_raster_res_m_is_fine_for_a_runner_that_never_reads_it(fake_cli):
    """noise renders and keys without the raster resolution, as its 0.2.7 runner did."""
    from app.experiments import noise

    task_dir = _task(fake_cli, "task-nores002", ["noise"], buffer={"size": 270})
    assert noise.run(task_dir) == 0
    assert _status(task_dir)["status"] == "finished"


def test_a_held_run_lock_refuses_the_run(fake_cli):
    import app.config

    lock_path = app.config.settings.DATA_DIR / ".run_lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    fd = os.open(str(lock_path), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        task_dir = _task(fake_cli, "task-locked01", ["ndi"])
        assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 1
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    status = _status(task_dir)
    assert status["status"] == "error"
    assert status["message"] == "another task acquired the run lock first; retry shortly"
    assert status["experiments"] == {}                   # refused before the slot was seeded
    assert not (task_dir / "input.parquet").exists()
    # the lock is free again afterwards
    assert bg_ndi_wi.run(task_dir, variables=["ndi"]) == 0


def test_the_lock_is_released_after_a_run(fake_cli):
    task_dir = _task(fake_cli, "task-relock01", ["walkability"])
    assert bg_ndi_wi.run(task_dir) == 0
    from spacescans.orchestrate import RunLock
    import app.config
    assert RunLock(app.config.settings.DATA_DIR).is_free()


def test_sigterm_writes_cancelled_and_exits_143(tmp_path):
    task_dir = tmp_path / "task-cancel01"
    task_dir.mkdir()
    previous = signal.getsignal(signal.SIGTERM)
    try:
        _adapter.install_cancel_handler(task_dir)
        with pytest.raises(SystemExit) as exc:
            os.kill(os.getpid(), signal.SIGTERM)
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert exc.value.code == 143
    status = _status(task_dir)
    assert status["status"] == "cancelled" and status["message"] == "Task cancelled by user"
    assert _logs(task_dir) == [{"ts": _logs(task_dir)[0]["ts"], "level": "info",
                                "source": "runner", "msg": "received SIGTERM — task cancelled"}]


def test_sigterm_during_a_step_cancels_the_task_and_stops_the_step(tmp_path):
    """task_manager.stop_task's SIGTERM while a step runs, through the shim CLI in its own
    process: status ``cancelled``, the runner's line, exit 143, the run lock free again,
    and no "exit code" line (as in 0.2.7). New since phase C: the step's process group
    is killed too (0.2.7 left the step running)."""
    import subprocess
    import time

    from spacescans.orchestrate import RunLock

    hang = tmp_path / "hang_cli.py"
    pidfile = tmp_path / "step.pid"
    hang.write_text(
        "import os, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "print('[overlap_fast] tile 1/2 ( 50.0%)', flush=True)\n"
        "time.sleep(120)\n")
    (tmp_path / "data").mkdir()
    task_dir = _task(tmp_path, "task-sigterm01", ["ndi"])
    env = {**os.environ, "SPACESCANS_PIPELINE_CLI": str(hang),
           "SPACESCANS_PIPELINE_PYTHON": sys.executable,
           "SPACESCANS_DATA_DIR": str(tmp_path / "data"), "DATA_DIR": str(tmp_path / "appdata"),
           "C3_CACHE_DIR": str(tmp_path / "appdata" / "c3_cache"), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.experiments.bg_ndi_wi", "run", str(task_dir),
         "--variables", "ndi"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 60
        while True:   # the step runs and the runner has turned its progress line into status
            assert proc.poll() is None, "the runner exited before the step started"
            assert time.monotonic() < deadline, "the step never reported progress"
            if pidfile.exists() and (task_dir / "status.json").exists():
                slot = _status(task_dir)["experiments"].get("bg_ndi_wi", {})
                if slot.get("message") == "Running c3_bg (1/3) — 50%":
                    break
            time.sleep(0.05)
        step_pid = int(pidfile.read_text())
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=30) == 143
    finally:
        if proc.poll() is None:
            proc.kill()
    status = _status(task_dir)
    assert (status["status"], status["message"]) == ("cancelled", "Task cancelled by user")
    runner = _runner_lines(task_dir)
    assert runner[0].startswith("spawning c3_bg: ")
    assert runner[1:] == ["received SIGTERM — task cancelled"]
    with pytest.raises(ProcessLookupError):
        os.kill(step_pid, 0)
    assert RunLock(tmp_path / "appdata").is_free()


# ---------------------------------------------------------------------------
# the partial (merge_results)
# ---------------------------------------------------------------------------

def _seed_merge_task(root: Path, n_input=5, n_ndi=4, n_wi=3) -> Path:
    task_dir = root / "task-abcdef12"
    task_dir.mkdir()
    (task_dir / "output").mkdir()
    pids = [f"PID{i:07d}" for i in range(n_input)]
    pd.DataFrame({"pid": pids, "startDate": ["2017-01-01"] * n_input,
                  "endDate": ["2017-12-31"] * n_input, "longitude": [-93.0] * n_input,
                  "latitude": [45.0] * n_input}).to_csv(task_dir / "input.csv", index=False)
    pd.DataFrame({"PATID": pids[:n_ndi], "geoid": list(range(n_ndi)),
                  "ndi": [0.1 * i for i in range(n_ndi)]}).to_parquet(
        task_dir / "output" / "c4_ndi.parquet", index=False)
    pd.DataFrame({"PATID": pids[:n_wi], "geoid": list(range(n_wi)),
                  "NatWalkInd": [1.0 + i for i in range(n_wi)]}).to_parquet(
        task_dir / "output" / "c4_wi.parquet", index=False)
    return task_dir


def test_merge_results_outer_merges_in_request_order(tmp_path):
    task_dir = _seed_merge_task(tmp_path)
    out = _adapter.merge_results("bg_ndi_wi", task_dir, ["walkability", "ndi"])
    assert out == task_dir / "output" / "result_bg_ndi_wi.csv"
    df = pd.read_csv(out)
    assert list(df.columns) == ["pid", "episode_id", "NatWalkInd", "ndi"]
    assert len(df) == 4                                   # outer merge of 3 WI with 4 NDI rows
    assert df["ndi"].isna().sum() == 0 and df["NatWalkInd"].isna().sum() == 1
    df2 = pd.read_csv(_adapter.merge_results("bg_ndi_wi", task_dir, ["ndi", "walkability"]))
    assert list(df2.columns) == ["pid", "episode_id", "ndi", "NatWalkInd"]
    # 4 of 5 episodes got a value: 80% is under the web's 90% threshold, one record per merge
    assert [e["match_pct"] for e in _logs(task_dir)] == [80.0, 80.0]


def test_merge_results_keeps_catalog_value_columns_only(tmp_path):
    task_dir = _seed_merge_task(tmp_path, n_input=3, n_ndi=3, n_wi=0)
    pd.DataFrame({"PATID": ["PID0000000"], "geoid": [0], "ndi": [1.0], "extra": [9.0]}).to_parquet(
        task_dir / "output" / "c4_ndi.parquet", index=False)
    df = pd.read_csv(_adapter.merge_results("bg_ndi_wi", task_dir, ["ndi"]))
    assert list(df.columns) == ["pid", "episode_id", "ndi"]


def test_merge_results_warns_on_low_match(tmp_path):
    task_dir = _seed_merge_task(tmp_path, n_input=100, n_ndi=5, n_wi=0)
    _adapter.merge_results("bg_ndi_wi", task_dir, ["ndi"])
    events = _logs(task_dir)
    assert len(events) == 1
    rec = events[0]
    assert list(rec) == ["ts", "level", "experiment_key", "event", "match_pct", "cohort_n",
                         "matched_n"]
    assert isinstance(rec["ts"], float) and rec["level"] == "warning"
    assert rec["experiment_key"] == "bg_ndi_wi" and rec["event"] == "merge_partial_low_match_pct"
    assert (rec["match_pct"], rec["cohort_n"], rec["matched_n"]) == (5.0, 100, 5)


def test_merge_results_joins_on_pid_and_episode_id(tmp_path):
    task_dir = tmp_path / "task-ep-merge1"
    (task_dir / "output").mkdir(parents=True)
    pd.DataFrame({"pid": ["A", "A", "B"], "startDate": ["2017-01-01", "2018-01-01", "2017-01-01"],
                  "endDate": ["2017-12-31", "2018-12-31", "2017-12-31"],
                  "longitude": [-93.0, -94.0, -95.0], "latitude": [45.0, 41.0, 30.0]}).to_csv(
        task_dir / "input.csv", index=False)
    pd.DataFrame({"PATID": ["A", "A", "B"], "geoid": [0, 1, 2], "ndi": [3, 1, 5]}).to_parquet(
        task_dir / "output" / "c4_ndi.parquet", index=False)
    out = pd.read_csv(_adapter.merge_results("bg_ndi_wi", task_dir, ["ndi"]))
    assert len(out) == 3 and out["pid"].tolist() == ["A", "A", "B"]
    assert out["ndi"].tolist() == [3, 1, 5]


# ---------------------------------------------------------------------------
# the cohort conversion
# ---------------------------------------------------------------------------

def test_cohort_conversion_is_the_runners(fake_cli):
    """input.parquet: FIPS columns as text, dates parsed, episode_id = row number."""
    task_dir = _task(fake_cli, "task-cohort01", ["walkability"], csv=(
        "pid,startDate,endDate,longitude,latitude,state_fips,bg_geoid,episode_id\n"
        "PID0000001,8/19/2017,11/11/2017,-93.028635,45.088976,06,060372634001,999\n"
        "PID0000002,3/24/2017,6/21/2017,-95.345115,29.738952,48,482014516012,888\n"))
    assert bg_ndi_wi.run(task_dir) == 0
    df = pd.read_parquet(task_dir / "input.parquet")
    assert df["episode_id"].tolist() == [0, 1]
    assert df["state_fips"].tolist() == ["06", "48"]
    assert df["bg_geoid"].tolist() == ["060372634001", "482014516012"]
    assert pd.api.types.is_datetime64_any_dtype(df["startDate"])
    assert df["startDate"].iloc[0] == pd.Timestamp("2017-08-19")
    from spacescans import cohort
    again = fake_cli / "again.parquet"
    cohort.csv_to_parquet(task_dir / "input.csv", again, variant="bg_ndi_wi")
    assert again.read_bytes() == (task_dir / "input.parquet").read_bytes()
