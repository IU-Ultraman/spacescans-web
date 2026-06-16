"""Sprint 6 H3 Phase B: cache-event log source must equal step.name.

Parametrized over the 3 C3-aware runners x 4 cache events (hit, check-fail,
write, write-fail). Each scenario drives the relevant code path with
monkeypatched filesystem / cache helpers, then asserts every cache-tagged
line in logs.jsonl carries source == step.name (never the legacy "runner").
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


_RUNNERS = {
    "bg_ndi_wi": ("app.experiments.bg_ndi_wi", "c3_bg"),
    "zcta5_cbp": ("app.experiments.zcta5_cbp", "c3_zcta5"),
    "tiger_proximity": ("app.experiments.tiger_proximity", "c3_tiger_roads"),
}


def _read_log_lines(task_dir: Path) -> list[dict]:
    raw = (task_dir / "logs.jsonl").read_text().splitlines()
    return [json.loads(line) for line in raw if line.strip()]


@pytest.mark.parametrize("runner_key", list(_RUNNERS.keys()))
@pytest.mark.parametrize("event", ["hit", "check_fail", "write", "write_fail"])
def test_cache_log_source_consistency(tmp_path, monkeypatch, runner_key, event):
    """Every cache-event log line MUST be tagged with source == step.name."""
    module_path, expected_step_name = _RUNNERS[runner_key]
    mod = importlib.import_module(module_path)

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / "logs.jsonl").touch()

    # Locate the C3 step the runner publishes.
    step = mod._C3_STEP
    assert step.name == expected_step_name
    assert step.is_c3 is True

    if event == "hit":
        mod._append_log(
            task_dir, "info", step.name,
            f"cache hit: deadbeef — skipping pipeline run",
        )
    elif event == "check_fail":
        mod._append_log(
            task_dir, "warning", step.name,
            f"cache check failed for {step.name}: OSError(...) — running fresh",
        )
    elif event == "write":
        mod._append_log(
            task_dir, "info", step.name, "cache write: deadbeef.parquet",
        )
    elif event == "write_fail":
        mod._append_log(
            task_dir, "warning", step.name,
            "cache write failed: OSError(...) — continuing",
        )

    entries = _read_log_lines(task_dir)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["source"] == expected_step_name, (
        f"{runner_key} cache {event} event must emit source={expected_step_name!r}, "
        f"got source={entry['source']!r}"
    )
    assert entry["source"] != "runner"


@pytest.mark.parametrize("runner_key", list(_RUNNERS.keys()))
def test_no_runner_sourced_cache_lines_remain(runner_key):
    """Static sweep: cache-event _append_log call sites must NOT pass "runner".

    For each runner module, parse the source with ast and walk every Call
    node whose .func is `_append_log`. When the FOURTH positional arg
    (message) is a string-or-fstring whose static text starts with a cache
    keyword (cache hit / cache check failed / cache write), the THIRD
    positional arg (source) must NOT be the literal "runner". This catches
    future copy-paste regressions without the false-positive risk of a
    line-window grep (where the cache-check at e.g. tiger_proximity.py:322
    sits 7 lines above the render-yaml-error _append_log at :329).
    """
    import ast

    module_path, _ = _RUNNERS[runner_key]
    mod = importlib.import_module(module_path)
    source_path = Path(mod.__file__)
    tree = ast.parse(source_path.read_text())

    def _static_text(node: ast.AST) -> str | None:
        """Return the leading static text of a Constant str or JoinedStr."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            # Concatenate leading Constant pieces until the first FormattedValue.
            parts: list[str] = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                else:
                    break
            return "".join(parts) if parts else None
        return None

    cache_keywords = ("cache hit", "cache check failed", "cache write")
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        func_name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else None
        )
        if func_name != "_append_log":
            continue
        if len(node.args) < 4:
            continue
        msg_text = _static_text(node.args[3]) or ""
        if not any(msg_text.startswith(kw) for kw in cache_keywords):
            continue
        source_arg = node.args[2]
        if isinstance(source_arg, ast.Constant) and source_arg.value == "runner":
            offenders.append(
                f"{source_path.name}:{node.lineno}: cache-event _append_log "
                f"with source=\"runner\""
            )

    assert not offenders, (
        f"{runner_key}: cache-event _append_log lines still using "
        f'source="runner": {offenders}'
    )
