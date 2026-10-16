"""Seam to the package's dataset registry (``spacescans.custom``, PHASE_D.md section 2.2).

Since phase D the web stores a newly registered dataset with
``spacescans.custom.register``, one registry root per user
(``DATA_DIR/custom_exposomes/user-<uid>/``, the directory that already held that user's
uploads), and reads it back with ``list_datasets``, ``get_dataset``, ``update_dataset``,
``remove_dataset`` and ``dataset_definition``. Every call the web makes into the registry
goes through this module, so a package that names or shapes them differently is adapted
here alone. Records cross the seam as plain dicts (``DatasetRecord.to_dict()``).

The web's metadata vocabulary (the frontend's) is translated here as well:

* a table's ``key`` ``{"geography": "Tract" | "BG" | "ZCTA5" | "County", "column": ...,
  "time_column": ...}`` becomes the registry's ``{"boundary": "tract" | "block_group" |
  "zcta" | "county", "column": ..., "year_column" | "date_column": ...}``; a features
  dataset's ``{"time_column": ...}`` becomes ``{"year_column": ...}``;
* ``periods`` ``[{"file", "year"}]`` or ``[{"file", "start", "end"}]`` become the
  registry's ``{path: year | start | (start, end)}`` mapping.

When the installed spacescans has no registry (0.2.x), :func:`available` is False and the
web falls back to the phase-C upload path for the kinds that path knows (static or yearly
tables and rasters); see ``app.datasets``.
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

#: The registry functions the web calls.
_FUNCTIONS = ("register", "list_datasets", "get_dataset", "update_dataset", "remove_dataset",
              "dataset_definition")

#: The web's geography names (the upload form's) and the registry's.
GEOGRAPHY_TO_BOUNDARY = {"Tract": "tract", "BG": "block_group", "ZCTA5": "zcta",
                         "County": "county"}
BOUNDARY_TO_GEOGRAPHY = {v: k for k, v in GEOGRAPHY_TO_BOUNDARY.items()}


def _api() -> Any:
    """The module holding the registry functions (tests substitute a fake)."""
    import spacescans.custom as custom

    if all(hasattr(custom, name) for name in _FUNCTIONS):
        return custom
    try:
        from spacescans.custom import registry  # the module, should the package not re-export
    except ImportError:
        return custom
    return registry


def available() -> bool:
    """True when the installed spacescans can register datasets."""
    try:
        api = _api()
    except Exception:  # noqa: BLE001 - an import problem means no registry
        return False
    return all(callable(getattr(api, name, None)) for name in _FUNCTIONS)


def kinds() -> dict[str, list[str]]:
    """``{kind: [temporal, ...]}`` the registry accepts (empty without a registry)."""
    if not available():
        return {}
    temporal = getattr(_api(), "TEMPORAL", None)
    if isinstance(temporal, Mapping):
        return {str(k): [str(t) for t in v] for k, v in temporal.items()}
    return {"polygon_table": ["static", "yearly", "daily"],
            "raster": ["static", "yearly", "biweekly", "daily"],
            "features": ["static", "yearly"]}


def errors() -> tuple[type[BaseException], ...]:
    """The exceptions that mean "the user's data or request was refused" (a 400)."""
    from spacescans.custom import CustomExposomeError

    found: list[type[BaseException]] = [CustomExposomeError]
    for name in ("DatasetError",):
        exc = getattr(_api(), name, None)
        if isinstance(exc, type) and issubclass(exc, BaseException):
            found.append(exc)
    return tuple(found)


def not_found() -> type[BaseException]:
    exc = getattr(_api(), "DatasetNotFoundError", None)
    return exc if isinstance(exc, type) else LookupError


def name_taken() -> type[BaseException] | None:
    exc = getattr(_api(), "DatasetExistsError", None)
    return exc if isinstance(exc, type) else None


def _record(obj: Any) -> dict[str, Any]:
    data = obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)
    return {k: v for k, v in data.items() if k != "root"}


# ---------------------------------------------------------------------------
# metadata translation
# ---------------------------------------------------------------------------

def registry_key(kind: str, temporal: str, key: Any) -> Any:
    """The web's ``key`` in the registry's vocabulary (None stays None)."""
    if key is None or not isinstance(key, Mapping):
        return key
    out: dict[str, Any] = {}
    if kind == "polygon_table":
        geography = key.get("geography", key.get("boundary"))
        if geography is not None:
            out["boundary"] = GEOGRAPHY_TO_BOUNDARY.get(str(geography), str(geography))
        if key.get("column") is not None:
            out["column"] = key["column"]
        time_column = key.get("time_column")
        if time_column:
            out["date_column" if temporal == "daily" else "year_column"] = time_column
        for name in ("year_column", "date_column"):
            if key.get(name):
                out[name] = key[name]
        return out
    for name, value in key.items():
        if name == "time_column":
            if value:
                out["year_column"] = value
        else:
            out[name] = value
    return out


def web_key(kind: str, key: Any) -> Any:
    """A stored record's ``key`` in the web's vocabulary (what the frontend reads)."""
    if not isinstance(key, Mapping):
        return key
    out: dict[str, Any] = {}
    if kind == "polygon_table":
        boundary = key.get("boundary", key.get("geography"))
        if boundary is not None:
            out["geography"] = BOUNDARY_TO_GEOGRAPHY.get(str(boundary), str(boundary))
        if key.get("column") is not None:
            out["column"] = key["column"]
    time_column = key.get("time_column") or key.get("year_column") or key.get("date_column")
    if time_column:
        out["time_column"] = time_column
    for name, value in key.items():
        if name not in ("boundary", "geography", "column", "time_column", "year_column",
                        "date_column"):
            out[name] = value
    return out


def registry_periods(paths: Mapping[str, Path], temporal: str,
                     periods: Sequence[Mapping[str, Any]] | None) -> Any:
    """``paths`` (file name -> saved path) as the registry's ``paths`` argument.

    Without ``periods`` the registry reads each file's period from its name or a manifest:
    the list of paths. With them, ``{path: period}`` (files not listed get None).
    """
    if not periods:
        return [str(p) for p in paths.values()]
    given: dict[str, Any] = {}
    for item in periods:
        name = str(item.get("file") or "")
        if temporal == "yearly" or "year" in item:
            given[name] = item.get("year")
        elif temporal == "biweekly" and item.get("end"):
            given[name] = (item.get("start"), item.get("end"))
        else:
            given[name] = item.get("start")
    return {str(path): given.get(name) for name, path in paths.items()}


# ---------------------------------------------------------------------------
# calls
# ---------------------------------------------------------------------------

def register(paths: Any, *, name: str, kind: str, temporal: str, key: Any,
             variables: Any, metadata: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """``spacescans.custom.register`` into ``root``; the record as a dict."""
    record = _api().register(paths, name=name, kind=kind, temporal=temporal,
                             key=registry_key(kind, temporal, key), variables=variables,
                             metadata=dict(metadata), root=os.fspath(root))
    return _record(record)


def list_records(root: Path) -> list[dict[str, Any]]:
    """Every registered dataset in ``root`` (none when it does not exist)."""
    if not Path(root).is_dir():
        return []
    return [_record(r) for r in _api().list_datasets(os.fspath(root))]


def get_record(record_id: str, root: Path) -> dict[str, Any]:
    return _record(_api().get_dataset(record_id, os.fspath(root)))


def update(record_id: str, *, root: Path, name: str | None = None,
           metadata: Mapping[str, Any] | None = None,
           variables: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    return _record(_api().update_dataset(record_id, name=name, metadata=metadata,
                                         variables=variables, root=os.fspath(root)))


def remove(record_id: str, root: Path) -> None:
    _api().remove_dataset(record_id, os.fspath(root))


def definition(record_id: str, root: Path) -> dict[str, Any]:
    """The linkable definition a task snapshots (``custom_variables[variable_key]``)."""
    return dict(_api().dataset_definition(record_id, os.fspath(root)))
