"""Cache-event log lines carry source == step.name, and the log strings are the runners'.

Since tier-2 phase C the runners log through ``spacescans.orchestrate.LogWriter``;
these tests hold the web side of that contract: every cache event (hit, check
failure, write, write failure) is tagged with the step, never "runner", and the
strings the paper's timing tools and ``independent_impl_chain.sh`` grep for are
unchanged byte for byte.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from spacescans.orchestrate import (
    LOG_CACHE_CHECK_FAILED,
    LOG_CACHE_HIT,
    LOG_CACHE_WRITE,
    LOG_CACHE_WRITE_FAILED,
    LOG_EXIT,
    LOG_SIGTERM,
    LOG_SPAWN,
    Event,
    LogWriter,
)

_RUNNERS = {
    "bg_ndi_wi": ("ndi", "c3_bg"),
    "zcta5_cbp": ("cbp_zcta5", "c3_zcta5"),
    "tiger_proximity": ("tiger_proximity", "c3_tiger_roads"),
}


def _read_log_lines(task_dir: Path) -> list[dict]:
    raw = (task_dir / "logs.jsonl").read_text().splitlines()
    return [json.loads(line) for line in raw if line.strip()]


def _event(kind: str, runner_key: str, step: str, text: str) -> Event:
    return Event(kind, runner_key, step=step, index=0, total=2, text=text)


@pytest.mark.parametrize("runner_key", list(_RUNNERS.keys()))
@pytest.mark.parametrize("event", ["hit", "check_fail", "write", "write_fail"])
def test_cache_log_source_consistency(tmp_path, runner_key, event):
    """Every cache-event log line MUST be tagged with source == step.name."""
    variable, expected_step_name = _RUNNERS[runner_key]
    mod = importlib.import_module(f"app.experiments.{runner_key}")
    step = mod.plan({"variables": [variable], "buffer": {"size": 270, "raster_res_m": 25}})[0]
    assert step.name == expected_step_name
    assert step.is_c3 is True

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    log = LogWriter.for_run_dir(task_dir)
    ev = {
        "hit": _event("cache_hit", runner_key, step.name, LOG_CACHE_HIT.format(key="deadbeef")),
        "check_fail": _event("cache_warning", runner_key, step.name,
                             LOG_CACHE_CHECK_FAILED.format(step=step.name, exc=OSError("...")),),
        "write": _event("cache_write", runner_key, step.name,
                        LOG_CACHE_WRITE.format(file="deadbeef.parquet")),
        "write_fail": _event("cache_warning", runner_key, step.name,
                             LOG_CACHE_WRITE_FAILED.format(exc=OSError("..."))),
    }[event]
    log(ev)

    entries = _read_log_lines(task_dir)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == expected_step_name, (
        f"{runner_key} cache {event} event must emit source={expected_step_name!r}, "
        f"got source={entry['source']!r}"
    )
    assert entry["source"] != "runner"
    assert entry["level"] == ("warning" if event.endswith("fail") else "info")
    assert entry["msg"].startswith({"hit": "cache hit: deadbeef — skipping pipeline run",
                                    "check_fail": f"cache check failed for {step.name}: OSError",
                                    "write": "cache write: deadbeef.parquet",
                                    "write_fail": "cache write failed: OSError"}[event])


def test_runner_log_strings_are_unchanged():
    """The 0.2.7 runners' literal strings (runtime.py and independent_impl_chain.sh read them)."""
    from spacescans.orchestrate.locks import RUN_LOCK_BUSY

    assert LOG_SPAWN == "spawning {step}: {cmd}"
    assert LOG_EXIT == "step {step} exit code {rc}"
    assert LOG_CACHE_HIT == "cache hit: {key} — skipping pipeline run"
    assert LOG_CACHE_WRITE == "cache write: {file}"
    assert LOG_CACHE_CHECK_FAILED == "cache check failed for {step}: {exc!r} — running fresh"
    assert LOG_CACHE_WRITE_FAILED == "cache write failed: {exc!r} — continuing"
    assert LOG_SIGTERM == "received SIGTERM — task cancelled"
    assert RUN_LOCK_BUSY == "another task acquired the run lock first; retry shortly"


def test_spawn_and_exit_lines_come_from_the_runner(tmp_path):
    """The step's own output is tagged with the step; spawn and exit with "runner"."""
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    log = LogWriter.for_run_dir(task_dir)
    log(_event("spawn", "noise", "c3_noise", LOG_SPAWN.format(step="c3_noise", cmd="py cli run x")))
    log(_event("line", "noise", "c3_noise", "[grid_weights] 1/1 (100.0%)"))
    log(Event("step_end", "noise", step="c3_noise", index=0, total=2,
              text=LOG_EXIT.format(step="c3_noise", rc=1), data={"rc": 1}))
    assert [(e["level"], e["source"], e["msg"]) for e in _read_log_lines(task_dir)] == [
        ("info", "runner", "spawning c3_noise: py cli run x"),
        ("info", "c3_noise", "[grid_weights] 1/1 (100.0%)"),
        ("error", "runner", "step c3_noise exit code 1"),
    ]
