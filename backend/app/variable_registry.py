"""Single source of truth for variable definitions.

Loads backend/app/data/variable_metadata.json, validates against
variable_metadata.schema.json on every reload, and exposes typed
query helpers used by the API layer, the dispatch loop, and the
coverage endpoint.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import jsonschema

_DATA_DIR = Path(__file__).parent / "data"
_METADATA_PATH = _DATA_DIR / "variable_metadata.json"
_SCHEMA_PATH = _DATA_DIR / "variable_metadata.schema.json"
_SUPPORTED_SCHEMA_VERSIONS = {1}

_CACHE: dict[str, Any] = {"mtime": None, "payload": None}


class MetadataSchemaError(RuntimeError):
    """Raised when variable_metadata.json fails registry-level validation
    (schema_version gate or experiment whitelist). jsonschema.ValidationError
    propagates as-is for raw schema violations."""


_PROBE_DONE: bool = False


def _assert_pipeline_version_compatible() -> None:
    """Defensive boot-time check. Raises MetadataSchemaError on drift.

    Runs once per process — guarded by module-level _PROBE_DONE flag.
    Verifies the editable-installed spacescans pipeline has:
      1. A working `pyreadr` extra (Sprint 3 ZCTA5xCBP .Rda reader).
      2. `TimeConfig.output_grouping` field (Sprint 2 episode-dimension contract).
    """
    global _PROBE_DONE
    if _PROBE_DONE:
        return
    try:
        from spacescans._extras import require as _require_extra
        _require_extra("rda", "pyreadr")
        from spacescans.models.config import TimeConfig
    except Exception as exc:
        raise MetadataSchemaError(
            f"pipeline import failed: {exc}. "
            "Install/upgrade spacescans-pipeline >= 0.2 "
            "(Sprint 2 episode-dimension contract)."
        ) from exc
    if "output_grouping" not in TimeConfig.model_fields:
        raise MetadataSchemaError(
            "pipeline missing TimeConfig.output_grouping — install/upgrade "
            "spacescans-pipeline >= 0.2 (Sprint 2 episode-dimension contract)."
        )
    _PROBE_DONE = True


def _discover_experiments() -> set[str]:
    exp_dir = Path(__file__).parent / "experiments"
    return {
        p.stem for p in exp_dir.glob("*.py")
        if p.stem not in {"__init__", "_merge"}
    }


def load_variables(*, force: bool = False) -> dict[str, Any]:
    _assert_pipeline_version_compatible()
    mtime = _METADATA_PATH.stat().st_mtime
    if not force and _CACHE["mtime"] == mtime and _CACHE["payload"]:
        return _CACHE["payload"]

    with _METADATA_PATH.open() as f:
        payload = json.load(f, object_pairs_hook=OrderedDict)
    with _SCHEMA_PATH.open() as f:
        schema = json.load(f)

    jsonschema.validate(payload, schema)

    if payload["schema_version"] not in _SUPPORTED_SCHEMA_VERSIONS:
        raise MetadataSchemaError(
            f"unsupported schema_version: {payload['schema_version']} "
            f"(supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)})"
        )

    known_experiments = _discover_experiments()
    for key, m in payload["variables"].items():
        if m["experiment"] not in known_experiments:
            raise MetadataSchemaError(
                f"variable {key!r} references unknown experiment "
                f"{m['experiment']!r} (known: {sorted(known_experiments)})"
            )

    _CACHE["mtime"] = mtime
    _CACHE["payload"] = payload
    return payload


def get_variable(key: str) -> dict[str, Any]:
    payload = load_variables()
    try:
        return payload["variables"][key]
    except KeyError:
        raise KeyError(key)


def variables_by_experiment(keys: list[str]) -> "OrderedDict[str, list[str]]":
    """Group variable keys by their experiment, preserving metadata file order."""
    payload = load_variables()
    out: OrderedDict[str, list[str]] = OrderedDict()
    for var_key, m in payload["variables"].items():
        if var_key not in keys:
            continue
        out.setdefault(m["experiment"], []).append(var_key)
    return out


def list_experiments() -> list[str]:
    payload = load_variables()
    seen: list[str] = []
    for m in payload["variables"].values():
        if m["experiment"] not in seen:
            seen.append(m["experiment"])
    return seen
