"""A stand-in for ``spacescans.custom``'s dataset registry (phase D track B), for web tests.

It follows the registry's contract as the web uses it (PHASE_D.md 2.2 and track B's
``registry.py``): ``register / list_datasets / get_dataset / update_dataset /
remove_dataset / dataset_definition``, records in ``<root>/<32 hex>/dataset.json``, names
unique per root ignoring case, the variable key ``custom_<first 8 hex of the id>``, and a
definition that names the record it came from (``registered.id``) and carries absolute
paths (so the web's scrubbing is tested). It does not read the data: a file whose content
starts with ``BAD`` is refused with a message naming the file and a count, never a value.
Every call is recorded in ``calls``.
"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from spacescans.custom import CustomExposomeError

TEMPORAL = {"polygon_table": ("static", "yearly", "daily"),
            "raster": ("static", "yearly", "biweekly", "daily"),
            "features": ("static", "yearly")}


class DatasetError(CustomExposomeError):
    pass


class DatasetNotFoundError(DatasetError, LookupError):
    pass


class DatasetExistsError(DatasetError):
    pass


class Record:
    def __init__(self, data: dict, root: Path):
        self.data = data
        self.root = Path(root)

    def to_dict(self) -> dict:
        return dict(self.data)


class FakeRegistry:
    TEMPORAL = TEMPORAL
    DatasetError = DatasetError
    DatasetNotFoundError = DatasetNotFoundError
    DatasetExistsError = DatasetExistsError

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    # -- storage --------------------------------------------------------------

    def _records(self, root: Path) -> list[Record]:
        root = Path(root)
        if not root.is_dir():
            return []
        out = []
        for d in sorted(root.iterdir()):
            if d.is_dir() and len(d.name) == 32 and (d / "dataset.json").is_file():
                out.append(Record(json.loads((d / "dataset.json").read_text()), root))
        return out

    def _find(self, ref: str, root: Path) -> Record:
        for r in self._records(root):
            if ref in (r.data["id"], r.data["name"]) or ref.casefold() == r.data["name"].casefold():
                return r
        raise DatasetNotFoundError(f"no dataset named {ref!r}")

    # -- API -------------------------------------------------------------------

    def register(self, paths: Any, *, name: str, kind: str, temporal: str, key: Any = None,
                 variables: Any = None, metadata: dict | None = None, root: Any = None,
                 overwrite: bool = False) -> Record:
        self.calls.append(("register", {"paths": paths, "name": name, "kind": kind,
                                        "temporal": temporal, "key": key,
                                        "variables": variables, "metadata": metadata,
                                        "root": root}))
        if temporal not in TEMPORAL[kind]:
            raise DatasetError(f"temporal must be one of {TEMPORAL[kind]} for a {kind}")
        root = Path(root)
        if any(r.data["name"].casefold() == name.casefold() for r in self._records(root)):
            raise DatasetExistsError(f"a dataset named {name!r} already exists")
        files = list(paths) if not isinstance(paths, dict) else list(paths)
        for f in files:
            if Path(f).read_bytes().startswith(b"BAD"):
                raise DatasetError(f"{Path(f).name}: 3 rows have no usable date in column 'date'")
        rid = uuid.uuid4().hex
        directory = root / rid
        (directory / "prepared").mkdir(parents=True)
        prepared = []
        for f in files:
            shutil.copy(f, directory / "prepared" / Path(f).name)
            prepared.append(f"prepared/{Path(f).name}")
        if variables:
            variables = [{"name": v["name"], "unit": v.get("unit"),
                          "description": v.get("description")} for v in variables]
        elif kind == "features":
            variables = [{"name": "feature_dist_m", "unit": "m", "description": None}]
        else:
            variables = [{"name": "value", "unit": None, "description": None}]
        meta = dict(metadata or {})
        data = {
            "record_format": 1, "id": rid, "name": name, "kind": kind, "temporal": temporal,
            "key": key, "variables": variables, "source": meta.get("source"),
            "version": meta.get("version"), "description": meta.get("description"),
            "license_note": meta.get("license_note"),
            "visibility": meta.get("visibility") or "private", "owner": meta.get("owner"),
            "created_utc": datetime.now(timezone.utc).isoformat(), "files": prepared,
            "checksum": "0" * 64, "spacescans_version": "0.3.0-fake",
            "details": {"originals": [{"name": Path(f).name} for f in files]},
        }
        (directory / "dataset.json").write_text(json.dumps(data))
        return Record(data, root)

    def list_datasets(self, root: Any = None) -> list[Record]:
        return self._records(Path(root))

    def get_dataset(self, name_or_id: str, root: Any = None) -> Record:
        return self._find(name_or_id, Path(root))

    def update_dataset(self, name_or_id: str, *, name: str | None = None,
                       metadata: dict | None = None, variables: Any = None,
                       root: Any = None) -> Record:
        self.calls.append(("update", {"id": name_or_id, "name": name, "metadata": metadata,
                                      "variables": variables}))
        record = self._find(name_or_id, Path(root))
        data = dict(record.data)
        if name is not None:
            if any(r.data["id"] != data["id"] and r.data["name"].casefold() == name.casefold()
                   for r in self._records(Path(root))):
                raise DatasetExistsError(f"a dataset named {name!r} already exists")
            data["name"] = name
        for k, v in (metadata or {}).items():
            data[k] = v
        if variables is not None:
            by = {v["name"]: dict(v) for v in data["variables"]}
            for change in variables:
                by[change["name"]].update({k: change[k] for k in ("unit", "description")
                                           if k in change})
            data["variables"] = [by[v["name"]] for v in data["variables"]]
        (Path(root) / data["id"] / "dataset.json").write_text(json.dumps(data))
        return Record(data, Path(root))

    def remove_dataset(self, name_or_id: str, root: Any = None) -> Record:
        self.calls.append(("remove", {"id": name_or_id}))
        record = self._find(name_or_id, Path(root))
        shutil.rmtree(Path(root) / record.data["id"])
        return record

    def dataset_definition(self, name_or_id: str, root: Any = None) -> dict:
        record = self._find(name_or_id, Path(root))
        d = record.data
        cols = [v["name"] for v in d["variables"]]
        units = {v["name"]: v["unit"] for v in d["variables"] if v.get("unit")}
        geometry = {"polygon_table": "polygon", "raster": "raster",
                    "features": "features"}[d["kind"]]
        return {
            "label": d["name"], "description": d.get("description") or "Registered.",
            "boundary": "Point" if geometry != "polygon" else "Tract",
            "spatial_method": {"polygon": "areal", "raster": "grid",
                               "features": "proximity"}[geometry],
            "coverage_years": [2013, 2019], "coverage_region": "CONUS",
            "experiment": "custom", "data_source": d.get("source") or "Registered by user",
            "temporal": d["temporal"], "variable_type": "continuous",
            "display_unit": " / ".join(units.values()) or "unitless", "value_cols": cols,
            "geometry": geometry, "dataset_id": d["id"][:8],
            "variable_key": f"custom_{d['id'][:8]}", "owner_uid": d.get("owner"),
            "value_labels": {}, "value_units": units,
            "registered": {"id": d["id"], "name": d["name"], "version": d.get("version"),
                           "root": str(record.root), "checksum": d["checksum"]},
            "values_path": str(record.root / d["id"] / d["files"][0]),
            "created_at": d["created_utc"],
        }
