"""Registered datasets in the web app: each user's library, with metadata and visibility.

Phase D (PHASE_D.md section 2.2). A user's datasets live in
``DATA_DIR/custom_exposomes/user-<uid>/``, the directory that already held their uploads:

* ``<8 hex>/``: the phase-C library format (uploads made before phase D, and uploads through
  the ``/api/custom-exposomes`` alias): ``manifest.json`` (the definition a task snapshots),
  ``values.csv`` or ``rasters/``, and ``dataset.json``, the dataset's record in the
  registry's field names. :func:`migrate` writes that record for every upload made before
  phase D (private, owned by the directory's user); nothing is moved or deleted.
* ``<32 hex>/``: a dataset registered since phase D through ``spacescans.custom.register``
  (``app.dataset_registry``; the user directory is that user's registry root): the
  package's ``dataset.json`` and the prepared files.

Access, enforced here for every route:

* a user sees their own datasets plus every dataset whose ``visibility`` is
  ``"deployment"``; a dataset they cannot see is "not found" (it is not revealed);
* only the owner edits, re-shares or deletes; for a shared dataset of another user these
  are "forbidden";
* a task snapshots the definitions it uses when its config is saved
  (``config["custom_variables"]``, the runner's source of truth) and the ids
  (``config["custom_datasets"]``), so later edits never change a finished task; starting a
  task re-checks that every dataset it uses still exists and is visible to the task's user
  (:func:`unusable_in_task`);
* a dataset that a queued or running task uses cannot be deleted.

Responses carry no server path (:func:`public`, :func:`public_definition`); error messages
carry names, counts, ids and file names, never a data value.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

import app.config
from app import custom_exposomes, dataset_registry

LIBRARY = "library"
REGISTRY = "registry"
RECORD_FILE = "dataset.json"
#: Version of the library records' layout (the registry's own records carry theirs).
RECORD_FORMAT = 1
VISIBILITY = ("private", "deployment")
KINDS = ("polygon_table", "raster", "features")
#: The time structures of each kind (PHASE_D.md 2.2).
TEMPORAL = {"polygon_table": ("static", "yearly", "daily"),
            "raster": ("static", "yearly", "biweekly", "daily"),
            "features": ("static", "yearly")}
#: What the phase-C upload path (no registry in the package) can register.
LIBRARY_KINDS = {"polygon_table": ["static", "yearly"], "raster": ["static", "yearly"]}
#: File extensions accepted per kind (the package checks the content).
EXTENSIONS = {
    "polygon_table": (".csv", ".txt", ".parquet"),
    "raster": (".tif", ".tiff", ".csv"),      # a .csv here is the periods manifest
    "features": (".gpkg", ".geojson", ".json", ".zip"),
}
#: Free-text limits (the registry's).
TEXT_LIMITS = {"name": 80, "source": 400, "version": 100, "description": 2000,
               "license_note": 2000}
METADATA_TEXT = ("source", "version", "description", "license_note")
_LIBRARY_ID = re.compile(r"[0-9a-f]{8}")
_REGISTRY_ID = re.compile(r"[0-9a-f]{32}")
_USER_DIR = re.compile(r"user-(\d+)")
#: Task statuses during which a dataset the task uses cannot be deleted.
ACTIVE_STATUSES = ("running", "queued")


# ---------------------------------------------------------------------------
# errors (the router maps .status to the HTTP status)
# ---------------------------------------------------------------------------

class DatasetsError(Exception):
    status = 400

    def __init__(self, detail: str, *, issues: Sequence[Mapping[str, Any]] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.issues = [dict(i) for i in (issues or [{"field": None, "message": detail}])]


class Invalid(DatasetsError):
    status = 400


class Forbidden(DatasetsError):
    status = 403


class NotFound(DatasetsError):
    status = 404


class Conflict(DatasetsError):
    status = 409


class Unavailable(DatasetsError):
    status = 503


# ---------------------------------------------------------------------------
# one dataset
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)


@dataclass
class Dataset:
    """One dataset of one user's library, in either storage."""

    id: str
    owner: str
    storage: str
    record: dict
    directory: Path

    # -- record fields ------------------------------------------------------

    @property
    def name(self) -> str:
        return str(self.record.get("name") or self.id)

    @property
    def kind(self) -> str:
        return str(self.record.get("kind") or "")

    @property
    def temporal(self) -> str:
        return str(self.record.get("temporal") or "")

    @property
    def visibility(self) -> str:
        value = self.record.get("visibility")
        return value if value in VISIBILITY else "private"

    @property
    def variable_key(self) -> str:
        return custom_exposomes.variable_key(self.id[:8])

    def visible_to(self, uid: int | str) -> bool:
        return self.owner == str(uid) or self.visibility == "deployment"

    # -- data -----------------------------------------------------------------

    def manifest(self) -> dict:
        return json.loads((self.directory / "manifest.json").read_text())

    def definition(self) -> dict:
        """What a task snapshots under ``custom_variables[self.variable_key]``."""
        if self.storage == LIBRARY:
            return self.manifest()
        if not dataset_registry.available():
            raise Unavailable(
                f"dataset {self.name!r} was registered with a spacescans that has a dataset "
                "registry; the installed one has none")
        return dataset_registry.definition(self.id, self.directory.parent)

    def missing_files(self) -> list[str]:
        """Names of the dataset's data files that are not on disk (empty when complete)."""
        if self.storage == REGISTRY:
            return [f for f in self.record.get("files") or []
                    if not (self.directory / f).is_file()]
        try:
            manifest = self.manifest()
        except (OSError, ValueError):
            return ["manifest.json"]
        if manifest.get("geometry") == "raster":
            return [Path(r["path"]).name for r in manifest.get("rasters") or []
                    if not Path(r.get("path") or "").is_file()]
        return [] if (self.directory / "values.csv").is_file() else ["values.csv"]

    def status(self) -> tuple[str, str | None]:
        """``("ready", None)`` or ``("error", why)``: whether a task can use it now."""
        missing = self.missing_files()
        if missing:
            return "error", f"{len(missing)} data file(s) of this dataset are missing"
        if self.storage == REGISTRY and not dataset_registry.available():
            return "error", "the installed spacescans cannot link registered datasets"
        return "ready", None

    def matches(self, definition: Mapping[str, Any]) -> bool:
        """True when ``definition`` (a task snapshot) was taken from this dataset."""
        registered = definition.get("registered")
        if self.storage == REGISTRY:
            return isinstance(registered, Mapping) and registered.get("id") == self.id
        return (not registered and definition.get("dataset_id") == self.id
                and str(definition.get("owner_uid")) == self.owner)


# ---------------------------------------------------------------------------
# migration: the phase-C library records
# ---------------------------------------------------------------------------

def _record_from_manifest(uid: str, directory: Path, manifest: Mapping[str, Any]) -> dict:
    """The record of an upload made before phase D (private, owned by ``uid``)."""
    raster = manifest.get("geometry") == "raster"
    cols = [str(c) for c in manifest.get("value_cols") or []]
    labels = manifest.get("value_labels") or {}
    units = manifest.get("value_units") or {}
    bands = list(manifest.get("bands") or ([manifest["band"]] if "band" in manifest else []))
    variables = []
    for i, col in enumerate(cols):
        var: dict[str, Any] = {"name": col, "unit": units.get(col) or None,
                               "description": labels.get(col) or None}
        if raster and i < len(bands):
            var["band"] = int(bands[i])
        variables.append(var)
    if raster:
        files = [f"rasters/{Path(r['path']).name}" for r in manifest.get("rasters") or []
                 if r.get("path")]
        key = None
    else:
        files = ["values.csv"]
        boundary = manifest.get("boundary")
        key = {"boundary": dataset_registry.GEOGRAPHY_TO_BOUNDARY.get(boundary, boundary),
               "column": manifest.get("key_col")}
        if manifest.get("year_col"):
            key["year_column"] = manifest["year_col"]
    return {
        "record_format": RECORD_FORMAT,
        "id": directory.name,
        "name": manifest.get("label") or directory.name,
        "kind": "raster" if raster else "polygon_table",
        "temporal": manifest.get("temporal") or "static",
        "key": key,
        "variables": variables,
        "source": None,
        "version": None,
        "description": manifest.get("description") or None,
        "license_note": None,
        "visibility": "private",
        "owner": uid,
        "created_utc": manifest.get("created_at") or _now(),
        "files": files,
        "checksum": manifest.get("sha256") or "",
        "spacescans_version": "",
        "details": {"migrated_from": "manifest.json",
                    "uploaded_filename": manifest.get("uploaded_filename"),
                    "row_count": manifest.get("row_count"),
                    "coverage_years": manifest.get("coverage_years")},
    }


def _library_record(uid: str, directory: Path) -> dict | None:
    """The library dataset's record, written now if it predates phase D; None if unreadable."""
    record_path = directory / RECORD_FILE
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text())
            if isinstance(record, dict) and record.get("id") == directory.name:
                return record
        except ValueError:
            pass
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
    except (OSError, ValueError):
        return None          # a half-written upload: not a dataset (as before phase D)
    record = _record_from_manifest(uid, directory, manifest)
    try:
        _write_json(record_path, record)
    except OSError:
        pass                 # read-only volume: serve the derived record anyway
    return record


def migrate() -> int:
    """Write the record of every upload made before phase D; return how many were written."""
    written = 0
    for uid, udir in _user_dirs():
        for child in _children(udir, _LIBRARY_ID):
            if (child / RECORD_FILE).is_file() or not (child / "manifest.json").is_file():
                continue
            if _library_record(uid, child) is not None and (child / RECORD_FILE).is_file():
                written += 1
    return written


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _user_dirs() -> list[tuple[str, Path]]:
    root = custom_exposomes.library_root()
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        m = _USER_DIR.fullmatch(d.name)
        if m and d.is_dir():
            out.append((m.group(1), d))
    return out


def _children(udir: Path, pattern: re.Pattern) -> list[Path]:
    try:
        return sorted(p for p in udir.iterdir() if p.is_dir() and pattern.fullmatch(p.name))
    except OSError:
        return []


def _registry_records(udir: Path) -> list[dict]:
    if not _children(udir, _REGISTRY_ID):
        return []
    if dataset_registry.available():
        try:
            return dataset_registry.list_records(udir)
        except Exception:  # noqa: BLE001 - fall back to the records on disk
            pass
    out = []
    for child in _children(udir, _REGISTRY_ID):
        try:
            record = json.loads((child / RECORD_FILE).read_text())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("id") == child.name:
            out.append(record)
    return out


def _user_datasets(uid: str, udir: Path) -> list[Dataset]:
    out = []
    for child in _children(udir, _LIBRARY_ID):
        if not (child / "manifest.json").is_file():
            continue
        record = _library_record(uid, child)
        if record is not None:
            out.append(Dataset(child.name, uid, LIBRARY, record, child))
    for record in _registry_records(udir):
        rid = str(record.get("id"))
        out.append(Dataset(rid, uid, REGISTRY, record, udir / rid))
    return out


def all_datasets() -> list[Dataset]:
    """Every dataset of every user (no access check: internal use)."""
    out: list[Dataset] = []
    for uid, udir in _user_dirs():
        out.extend(_user_datasets(uid, udir))
    return out


def owned_by(uid: int | str) -> list[Dataset]:
    udir = custom_exposomes.user_dir(uid)
    return _user_datasets(str(uid), udir) if udir.is_dir() else []


def visible_to(uid: int | str) -> list[Dataset]:
    """The caller's datasets, then every other user's shared ones; each group newest first."""
    uid = str(uid)
    datasets = [d for d in all_datasets() if d.visible_to(uid)]
    own = [d for d in datasets if d.owner == uid]
    shared = [d for d in datasets if d.owner != uid]
    own.sort(key=_sort_time, reverse=True)
    shared.sort(key=_sort_time, reverse=True)
    return own + shared


def _sort_time(d: Dataset) -> str:
    return str(d.record.get("created_utc") or "")


def find(uid: int | str, dataset_id: str) -> Dataset:
    """The dataset ``dataset_id`` if the caller may see it (own first), else :class:`NotFound`."""
    uid = str(uid)
    if not isinstance(dataset_id, str) or not (
            _LIBRARY_ID.fullmatch(dataset_id) or _REGISTRY_ID.fullmatch(dataset_id)):
        raise NotFound("dataset not found")
    own = [d for d in owned_by(uid) if d.id == dataset_id]
    if own:
        return own[0]
    shared = [d for d in all_datasets()
              if d.id == dataset_id and d.owner != uid and d.visibility == "deployment"]
    if len(shared) == 1:
        return shared[0]
    raise NotFound("dataset not found")


def find_owned(uid: int | str, dataset_id: str) -> Dataset:
    """The caller's own dataset; a shared one of another user is :class:`Forbidden`."""
    ds = find(uid, dataset_id)
    if ds.owner != str(uid):
        raise Forbidden("only the owner of a dataset can change or delete it")
    return ds


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------

_PATH_KEYS = frozenset({"values_path", "root", "path", "paths", "directory"})


def _is_server_path(value: str) -> bool:
    return len(value) > 1 and (value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value)
                               is not None) and "\n" not in value


def public_definition(definition: Mapping[str, Any]) -> dict:
    """A definition without server paths (for responses).

    Keys that hold paths (``values_path``, ``root``, ``path``...) are dropped, and any
    other absolute path, under whatever key or in a list, becomes its file name, so a
    definition format this module does not know (a newer registry's) cannot leak one.
    """
    def scrub(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {k: scrub(v) for k, v in value.items() if k not in _PATH_KEYS}
        if isinstance(value, (list, tuple)):
            return [scrub(v) for v in value]
        if isinstance(value, str) and _is_server_path(value):
            if re.match(r"^[A-Za-z]:", value):
                return PureWindowsPath(value).name
            return Path(value).name
        return value

    return scrub(copy.deepcopy(dict(definition)))


def display_names(uids: Iterable[str]) -> dict[str, str]:
    """``{uid: "First Last"}`` from the users table (missing users are left out)."""
    wanted = sorted({str(u) for u in uids if str(u).isdigit()})
    if not wanted:
        return {}
    path = app.config.settings.DB_PATH
    if not Path(path).is_file():
        return {}
    try:
        conn = sqlite3.connect(str(path))
        try:
            marks = ",".join("?" * len(wanted))
            rows = conn.execute(
                f"SELECT id, first_name, last_name FROM users WHERE id IN ({marks})",
                [int(u) for u in wanted]).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return {}
    return {str(r[0]): " ".join(p for p in (r[1], r[2]) if p).strip() or f"user {r[0]}"
            for r in rows}


def _variables(ds: Dataset) -> list[dict]:
    out = []
    for v in ds.record.get("variables") or []:
        if not isinstance(v, Mapping) or not v.get("name"):
            continue
        item = {"name": v["name"], "unit": v.get("unit"), "description": v.get("description")}
        if "band" in v:
            item["band"] = v["band"]
        out.append(item)
    return out


def _entry(ds: Dataset) -> dict | None:
    """The dataset's catalog-shaped entry (label, unit, coverage...), or None if unreadable."""
    try:
        return public_definition(custom_exposomes.catalog_entry(ds.definition()))
    except Exception:  # noqa: BLE001 - a broken dataset still lists, with status "error"
        return None


def public(ds: Dataset, uid: int | str, names: Mapping[str, str] | None = None) -> dict:
    """The dataset as the API returns it (PHASE_D.md 2.2 list fields, then the details)."""
    status, why = ds.status()
    record = ds.record
    names = names or {}
    out = {
        "id": ds.id,
        "name": ds.name,
        "kind": ds.kind,
        "temporal": ds.temporal,
        "variables": _variables(ds),
        "visibility": ds.visibility,
        "owned_by_me": ds.owner == str(uid),
        "owner_display": names.get(ds.owner) or f"user {ds.owner}",
        "created_at": record.get("created_utc"),
        "status": status,
        "status_detail": why,
        "variable_key": ds.variable_key,
        "key": dataset_registry.web_key(ds.kind, record.get("key")),
        "source": record.get("source"),
        "version": record.get("version"),
        "description": record.get("description"),
        "license_note": record.get("license_note"),
        "files": [Path(f).name for f in record.get("files") or []],
        "checksum": record.get("checksum"),
        "spacescans_version": record.get("spacescans_version"),
        "created_utc": record.get("created_utc"),
        "updated_utc": record.get("updated_utc"),
        "entry": _entry(ds) if status == "ready" else None,
    }
    return out


# ---------------------------------------------------------------------------
# metadata of a new dataset
# ---------------------------------------------------------------------------

def _text(issues: list, field: str, value: Any, *, required: bool = False) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            issues.append({"field": field, "message": f"{field} is required"})
        return None
    if not isinstance(value, str):
        issues.append({"field": field, "message": f"{field} must be text"})
        return None
    value = value.strip()
    limit = TEXT_LIMITS[field]
    if len(value) > limit:
        issues.append({"field": field, "message": f"{field} is longer than {limit} characters"})
    return value


def parse_metadata(raw: Any) -> dict:
    """The upload's ``metadata`` (JSON text or a mapping), checked; :class:`Invalid` lists issues."""
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except ValueError:
            raise Invalid("metadata must be a JSON object") from None
    if not isinstance(raw, Mapping):
        raise Invalid("metadata must be a JSON object")
    issues: list[dict] = []
    known = {"name", "kind", "temporal", "key", "variables", "periods", "visibility",
             *METADATA_TEXT}
    unknown = sorted(set(raw) - known)
    if unknown:
        issues.append({"field": None, "message": f"unknown metadata field(s): {', '.join(unknown)}"})
    meta: dict[str, Any] = {"name": _text(issues, "name", raw.get("name"), required=True)}
    kind = raw.get("kind")
    if kind not in KINDS:
        issues.append({"field": "kind", "message": f"kind must be one of {', '.join(KINDS)}"})
    meta["kind"] = kind
    temporal = raw.get("temporal")
    allowed = TEMPORAL.get(kind, ("static", "yearly", "biweekly", "daily"))
    if temporal not in allowed:
        issues.append({"field": "temporal",
                       "message": f"temporal must be one of {', '.join(allowed)} for this kind"})
    meta["temporal"] = temporal
    visibility = raw.get("visibility") or "private"
    if visibility not in VISIBILITY:
        issues.append({"field": "visibility", "message": "visibility must be private or deployment"})
    meta["visibility"] = visibility
    for field in METADATA_TEXT:
        meta[field] = _text(issues, field, raw.get(field))
    key = raw.get("key")
    if key is not None and not isinstance(key, (Mapping, str)):
        issues.append({"field": "key", "message": "key must be an object"})
    meta["key"] = dict(key) if isinstance(key, Mapping) else key
    variables = raw.get("variables")
    if variables is not None:
        if not isinstance(variables, list) or not all(
                isinstance(v, (str, Mapping)) for v in variables):
            issues.append({"field": "variables",
                           "message": "variables must be a list of {name, unit, description}"})
        else:
            variables = [{"name": v} if isinstance(v, str) else dict(v) for v in variables]
            if not variables:
                variables = None
    meta["variables"] = variables
    periods = raw.get("periods")
    if periods is not None and not (isinstance(periods, list) and all(
            isinstance(p, Mapping) and isinstance(p.get("file"), str) for p in periods)):
        issues.append({"field": "periods",
                       "message": "periods must be a list of {file, year} or {file, start, end}"})
        periods = None
    meta["periods"] = [dict(p) for p in periods] if periods else None
    if issues:
        raise Invalid("the dataset's metadata was refused", issues=issues)
    return meta


def check_files(kind: str, temporal: str, names: Sequence[str]) -> None:
    """File count and extensions for ``kind``; :class:`Invalid` otherwise."""
    issues = []
    if not names:
        issues.append({"field": "files", "message": "choose at least one file"})
    exts = EXTENSIONS.get(kind, ())
    for name in names:
        if not name.lower().endswith(exts):
            issues.append({"field": "files",
                           "message": f"{name}: a {kind} dataset accepts {', '.join(exts)} files"})
    if len({n.lower() for n in names}) != len(names):
        issues.append({"field": "files", "message": "two files have the same name"})
    data = [n for n in names if not (kind == "raster" and n.lower().endswith(".csv"))]
    if temporal == "static" and kind in ("polygon_table", "raster", "features") and len(data) > 1:
        issues.append({"field": "files",
                       "message": f"a time-invariant {kind} dataset is one file ({len(data)} given)"})
    if kind == "polygon_table" and len(names) > 1:
        issues.append({"field": "files", "message": "a table dataset is one file"})
    if issues:
        raise Invalid("the dataset's files were refused", issues=issues)


def _check_name_free(uid: str, name: str, *, exclude: str | None = None) -> None:
    for ds in owned_by(uid):
        if ds.id != exclude and ds.name.casefold() == name.casefold():
            raise Conflict(f"you already have a dataset named {ds.name!r}; choose another name",
                           issues=[{"field": "name",
                                    "message": "you already have a dataset with this name"}])


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

def register(uid: int | str, files: Mapping[str, Path], meta: Mapping[str, Any]) -> Dataset:
    """Validate, prepare and store a dataset for ``uid``; ``files`` maps file name -> saved path.

    Through the package's registry when it has one; otherwise through the phase-C upload path
    for the kinds that path knows (static or yearly tables and rasters).
    """
    uid = str(uid)
    kind, temporal = meta["kind"], meta["temporal"]
    check_files(kind, temporal, list(files))
    _check_name_free(uid, meta["name"])
    udir = custom_exposomes.user_dir(uid)
    if temporal in dataset_registry.kinds().get(kind, []):
        return _register_in_registry(uid, udir, files, meta)
    if temporal in LIBRARY_KINDS.get(kind, []):
        return _register_in_library(uid, files, meta)
    raise Invalid(f"this deployment cannot register {temporal} {kind} datasets: the installed "
                  "spacescans has no dataset registry",
                  issues=[{"field": "temporal",
                           "message": "not supported by the installed spacescans"}])


def _registry_metadata(uid: str, meta: Mapping[str, Any]) -> dict[str, Any]:
    out = {field: meta.get(field) for field in METADATA_TEXT if meta.get(field)}
    out["visibility"] = meta.get("visibility") or "private"
    out["owner"] = uid
    return out


def _register_in_registry(uid: str, udir: Path, files: Mapping[str, Path],
                          meta: Mapping[str, Any]) -> Dataset:
    udir.mkdir(parents=True, exist_ok=True)
    paths = dataset_registry.registry_periods(files, meta["temporal"], meta.get("periods"))
    taken = dataset_registry.name_taken()
    try:
        record = dataset_registry.register(
            paths, name=meta["name"], kind=meta["kind"], temporal=meta["temporal"],
            key=meta.get("key"), variables=meta.get("variables"),
            metadata=_registry_metadata(uid, meta), root=udir)
    except Exception as exc:
        if taken is not None and isinstance(exc, taken):
            raise Conflict(str(exc), issues=[{"field": "name", "message": str(exc)}]) from None
        if type(exc).__name__ == "MissingExtraError":
            raise Unavailable(f"this deployment cannot read {meta['kind']} files: {exc}") from None
        if isinstance(exc, dataset_registry.errors()):
            raise Invalid(str(exc), issues=[{"field": None, "message": str(exc)}]) from None
        raise
    rid = str(record["id"])
    return Dataset(rid, uid, REGISTRY, record, udir / rid)


def _int_year(value: Any) -> int | None:
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return year if 1900 <= year <= 2100 else None


def _register_in_library(uid: str, files: Mapping[str, Path], meta: Mapping[str, Any]) -> Dataset:
    """The phase-C path (``custom_exposomes.create`` / ``create_raster``) plus the record."""
    variables = meta.get("variables") or []
    names = [str(v.get("name") or "").strip() for v in variables]
    labels = {n: str(v.get("description") or "").strip()[:80] for n, v in zip(names, variables)
              if n and v.get("description")}
    units = {n: str(v.get("unit") or "").strip() for n, v in zip(names, variables)
             if n and v.get("unit")}
    description = (meta.get("description") or "")[:400]
    try:
        if meta["kind"] == "polygon_table":
            key = meta.get("key") if isinstance(meta.get("key"), Mapping) else {}
            geography = key.get("geography") or key.get("boundary")
            geography = dataset_registry.BOUNDARY_TO_GEOGRAPHY.get(geography, geography)
            available = {b["boundary"] for b in custom_exposomes.provisioned_boundaries()
                         if b["available"]}
            if geography not in available:
                raise Invalid(f"this deployment has no {geography} boundary data provisioned, "
                              "so a dataset on it could never run",
                              issues=[{"field": "key", "message": "boundary not provisioned"}])
            if not names:
                raise Invalid("list the value columns in variables",
                              issues=[{"field": "variables", "message": "required"}])
            (filename, path), = files.items()
            year_col = key.get("time_column") or key.get("year_column")
            manifest = custom_exposomes.create(
                uid, content=path.read_bytes(), name=meta["name"], description=description,
                boundary=geography, key_col=str(key.get("column") or ""), value_cols=names,
                value_labels=labels, value_units=units,
                year_col=year_col if meta["temporal"] == "yearly" else None,
                uploaded_filename=filename)
        else:
            years = {str(p.get("file")): _int_year(p.get("year"))
                     for p in meta.get("periods") or []}
            rasters = []
            for filename, path in files.items():
                year = years.get(filename) if years else None
                if meta["temporal"] == "yearly" and year is None:
                    found = re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", filename)
                    year = int(found[0]) if len(set(found)) == 1 else None
                    if year is None:
                        raise Invalid(f"{filename}: give the file's year",
                                      issues=[{"field": "periods",
                                               "message": f"{filename}: no year"}])
                rasters.append((filename, path.read_bytes(),
                                year if meta["temporal"] == "yearly" else None))
            bands = [int(v.get("band") or i + 1) for i, v in enumerate(variables)] or [1]
            cols = names or ["value"]
            manifest = custom_exposomes.create_raster(
                uid, rasters=rasters, name=meta["name"], description=description,
                bands=bands, value_cols=cols, value_labels=labels, value_units=units)
    except custom_exposomes.CustomExposomeError as exc:
        raise Invalid(str(exc), issues=[{"field": None, "message": str(exc)}]) from None
    directory = custom_exposomes.dataset_dir(uid, manifest["dataset_id"])
    record = _record_from_manifest(uid, directory, manifest)
    record.update({field: meta.get(field) or None for field in METADATA_TEXT})
    record["description"] = meta.get("description") or record["description"]
    record["visibility"] = meta.get("visibility") or "private"
    record["details"]["migrated_from"] = None
    for var, given in zip(record["variables"], variables):
        if given.get("description"):
            var["description"] = given["description"]
    _write_json(directory / RECORD_FILE, record)
    return Dataset(directory.name, uid, LIBRARY, record, directory)


def write_library_record(uid: int | str, manifest: Mapping[str, Any]) -> None:
    """The record of an upload through the /api/custom-exposomes alias (private)."""
    directory = custom_exposomes.dataset_dir(uid, manifest["dataset_id"])
    record = _record_from_manifest(str(uid), directory, manifest)
    record["details"]["migrated_from"] = None
    _write_json(directory / RECORD_FILE, record)


# ---------------------------------------------------------------------------
# edit, share, delete
# ---------------------------------------------------------------------------

EDITABLE = ("name", "visibility", "variables", *METADATA_TEXT)


def update(uid: int | str, dataset_id: str, changes: Mapping[str, Any]) -> Dataset:
    """Owner only: name, free-text metadata, visibility, variables' unit and description."""
    ds = find_owned(uid, dataset_id)
    if not isinstance(changes, Mapping):
        raise Invalid("send the changes as a JSON object")
    issues: list[dict] = []
    unknown = sorted(set(changes) - set(EDITABLE))
    if unknown:
        issues.append({"field": None,
                       "message": f"cannot change {', '.join(unknown)} (data and kind are fixed)"})
    name = None
    if "name" in changes:
        name = _text(issues, "name", changes.get("name"), required=True)
    metadata: dict[str, Any] = {}
    for field in METADATA_TEXT:
        if field in changes:
            metadata[field] = _text(issues, field, changes.get(field))
    if "visibility" in changes:
        if changes["visibility"] not in VISIBILITY:
            issues.append({"field": "visibility",
                           "message": "visibility must be private or deployment"})
        else:
            metadata["visibility"] = changes["visibility"]
    variables = changes.get("variables")
    if variables is not None:
        known = {v["name"] for v in _variables(ds)}
        if not isinstance(variables, list) or not all(
                isinstance(v, Mapping) and v.get("name") in known for v in variables):
            issues.append({"field": "variables",
                           "message": "variables lists {name, unit, description} of the "
                                      "dataset's own variables (names cannot change)"})
        else:
            variables = [{k: v[k] for k in ("name", "unit", "description") if k in v}
                         for v in variables]
            for v in variables:
                for field, limit in (("unit", 50), ("description", 400)):
                    if v.get(field) is not None and (not isinstance(v[field], str)
                                                     or len(v[field]) > limit):
                        issues.append({"field": "variables",
                                       "message": f"{v['name']}: {field} must be text of at "
                                                  f"most {limit} characters"})
    if issues:
        raise Invalid("the changes were refused", issues=issues)
    if name is not None:
        _check_name_free(ds.owner, name, exclude=ds.id)
    if ds.storage == REGISTRY:
        try:
            record = dataset_registry.update(ds.id, root=ds.directory.parent, name=name,
                                             metadata=metadata or None, variables=variables)
        except Exception as exc:
            taken = dataset_registry.name_taken()
            if taken is not None and isinstance(exc, taken):
                raise Conflict(str(exc)) from None
            if isinstance(exc, dataset_registry.errors()):
                raise Invalid(str(exc)) from None
            raise
        ds.record = record
        return ds
    return _update_library(ds, name, metadata, variables)


def _update_library(ds: Dataset, name: str | None, metadata: Mapping[str, Any],
                    variables: Sequence[Mapping[str, Any]] | None) -> Dataset:
    from spacescans.custom import summarise_units

    record = dict(ds.record)
    manifest = ds.manifest()
    if name is not None:
        record["name"] = name
        manifest["label"] = name
    for field, value in metadata.items():
        record[field] = value
    if "description" in metadata:
        manifest["description"] = ((metadata["description"] or "").strip()[:400]
                                   or manifest.get("description"))
    if variables is not None:
        by_name = {v["name"]: dict(v) for v in record.get("variables") or []}
        labels = dict(manifest.get("value_labels") or {})
        units = dict(manifest.get("value_units") or {})
        for change in variables:
            target = by_name[change["name"]]
            if "unit" in change:
                target["unit"] = (change["unit"] or "").strip() or None
                if target["unit"]:
                    units[change["name"]] = target["unit"]
                else:
                    units.pop(change["name"], None)
            if "description" in change:
                target["description"] = (change["description"] or "").strip() or None
                if target["description"]:
                    labels[change["name"]] = target["description"][:80]
                else:
                    labels.pop(change["name"], None)
        record["variables"] = [by_name[v["name"]] for v in record.get("variables") or []]
        cols = list(manifest.get("value_cols") or [])
        manifest["value_labels"] = {c: labels[c] for c in cols if c in labels}
        manifest["value_units"] = {c: units[c] for c in cols if c in units}
        manifest["display_unit"] = summarise_units(cols, manifest["value_units"])
    record["updated_utc"] = _now()
    _write_json(ds.directory / "manifest.json", manifest)
    _write_json(ds.directory / RECORD_FILE, record)
    ds.record = record
    return ds


def _active_definitions() -> list[Mapping[str, Any]]:
    """The custom definitions snapshotted by every queued or running task."""
    from app import task_manager

    tasks_dir = app.config.settings.TASKS_DIR
    if not tasks_dir.is_dir():
        return []
    out: list[Mapping[str, Any]] = []
    for task_dir in tasks_dir.iterdir():
        if not (task_dir / "status.json").is_file():
            continue
        task_manager._reap_if_dead(task_dir)
        try:
            status = task_manager._read_status(task_dir).get("status")
        except (OSError, ValueError):
            continue
        if status not in ACTIVE_STATUSES:
            continue
        try:
            config = json.loads((task_dir / "config.json").read_text())
        except (OSError, ValueError):
            continue
        snapshot = config.get(custom_exposomes.TASK_CUSTOM_KEY) or {}
        if isinstance(snapshot, Mapping):
            out.extend(d for d in snapshot.values() if isinstance(d, Mapping))
    return out


def in_use(ds: Dataset) -> bool:
    """True when a queued or running task (of any user) uses the dataset."""
    return any(ds.matches(d) for d in _active_definitions())


def delete(uid: int | str, dataset_id: str) -> None:
    """Owner only; refused while a queued or running task uses the dataset."""
    ds = find_owned(uid, dataset_id)
    if in_use(ds):
        raise Conflict("a queued or running task uses this dataset; delete it when that task "
                       "has finished")
    if ds.storage == REGISTRY:
        try:
            dataset_registry.remove(ds.id, ds.directory.parent)
        except Exception as exc:
            if isinstance(exc, dataset_registry.not_found()):
                raise NotFound("dataset not found") from None
            raise
        return
    try:
        custom_exposomes.delete(ds.owner, ds.id)
    except KeyError:
        raise NotFound("dataset not found") from None


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------

def resolve_for_task(uid: int | str, dataset_ids: Sequence[str],
                     variable_keys: Sequence[str]) -> tuple[dict[str, dict], list[str]]:
    """The definitions a task's config snapshots, and the dataset ids they come from.

    ``dataset_ids`` are the new frontend's selection; ``variable_keys`` are the
    ``custom_<id>`` keys in ``variables`` (the phase-C frontend's). Each must name a dataset
    the caller may see (own first, then shared), else :class:`NotFound`; two datasets with
    one variable key in one selection are a :class:`Conflict`.
    """
    uid = str(uid)
    snapshot: dict[str, dict] = {}
    used: list[str] = []
    chosen: dict[str, Dataset] = {}

    def add(ds: Dataset) -> None:
        key = ds.variable_key
        prior = chosen.get(key)
        if prior is not None:
            if (prior.id, prior.owner) != (ds.id, ds.owner):
                raise Conflict(f"two selected datasets share the variable key {key}; "
                               "select one of them")
            return
        status, why = ds.status()
        if status != "ready":
            raise Conflict(f"dataset {ds.name!r} cannot be used now: {why}")
        chosen[key] = ds
        snapshot[key] = ds.definition()
        used.append(ds.id)

    for dataset_id in dataset_ids:
        if not isinstance(dataset_id, str):
            raise NotFound("custom dataset not found or not shared with you")
        try:
            add(find(uid, dataset_id))
        except NotFound:
            raise NotFound(f"custom dataset not found or not shared with you: {dataset_id}"
                           ) from None
    visible = None
    for key in variable_keys:
        if key in chosen:
            continue
        if visible is None:
            visible = visible_to(uid)
        matches = [d for d in visible if d.variable_key == key]
        own = [d for d in matches if d.owner == uid]
        pick = own[:1] or matches
        if len(pick) != 1:
            raise NotFound(f"custom exposome not found in your library or shared with you: {key}")
        add(pick[0])
    return snapshot, used


def overlay_for_keys(uid: int | str, keys: Sequence[str]) -> dict[str, dict]:
    """Definitions of the visible datasets behind ``keys`` (for the coverage pre-flight)."""
    wanted = {k for k in keys if custom_exposomes.is_custom_key(k)}
    if not wanted:
        return {}
    out: dict[str, dict] = {}
    for ds in visible_to(uid):
        if ds.variable_key in wanted and ds.variable_key not in out:
            try:
                out[ds.variable_key] = ds.definition()
            except Exception:  # noqa: BLE001 - coverage then reports the key as unknown
                continue
    return out


def unusable_in_task(uid: int | str, config: Mapping[str, Any]) -> list[str]:
    """Variable keys of the task's datasets that are gone or no longer visible to ``uid``."""
    snapshot = config.get(custom_exposomes.TASK_CUSTOM_KEY) or {}
    if not isinstance(snapshot, Mapping) or not snapshot:
        return []
    datasets = all_datasets()
    bad = []
    for key, definition in snapshot.items():
        if not isinstance(definition, Mapping):
            continue
        source = next((d for d in datasets if d.matches(definition)), None)
        if source is None or not source.visible_to(uid):
            bad.append(str(key))
    return bad
