"""Registered datasets (phase D, PHASE_D.md 2.2): library, migration, API, tasks, security.

Users 1 (Ada Lovelace), 2 (Bob Builder) and 3 exist; data are synthetic. Two package
modes are tested explicitly, whatever spacescans is installed:

* ``no_registry``: a spacescans without a dataset registry (0.2.x): static and yearly
  tables and rasters take the phase-C upload path, other kinds are refused;
* ``registry``: ``tests/fixtures/fake_registry.py``, a stand-in for track B's
  ``spacescans.custom`` registry (register/list/get/update/remove/definition).

The security tests are the point of the file: another user cannot see, read, edit, share,
delete or link a private dataset; a shared one is selectable but not editable by others;
no response carries a server path.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app import custom_exposomes, dataset_registry, datasets
from tests.fixtures.fake_registry import FakeRegistry

TRACT_A = "12073001100"
TRACT_B = "12073001200"
CSV = f"tract,greenness,heat\n{TRACT_A},0.41,88.2\n{TRACT_B},0.55,86.0\n".encode()
DAILY = f"GEOID,date,pm25\n{TRACT_A},2017-01-01,5.1\n{TRACT_A},2017-01-02,6.2\n".encode()
COHORT = "pid,startDate,endDate,longitude,latitude\nA1,2017-01-01,2017-12-31,-84.3,30.4\n"


# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.config
    from app.database import init_db

    data = tmp_path / "data"
    data.mkdir()
    settings = app.config.settings
    monkeypatch.setattr(settings, "DATA_DIR", data)
    monkeypatch.setattr(settings, "TASKS_DIR", data / "tasks")
    monkeypatch.setattr(settings, "DB_PATH", data / "test.db")
    (data / "tasks").mkdir()
    pipeline = tmp_path / "pipeline-data"
    (pipeline / "TRACT").mkdir(parents=True)
    (pipeline / "TRACT" / "tl_2010_12_tract10.shp").write_text("x")
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", pipeline)
    init_db(data / "test.db")
    conn = sqlite3.connect(str(data / "test.db"))
    conn.executemany(
        "INSERT INTO users (id, email, hashed_password, first_name, last_name) VALUES (?,?,?,?,?)",
        [(1, "ada@example.org", "x", "Ada", "Lovelace"), (2, "bob@example.org", "x", "Bob", "Builder"),
         (3, "cy@example.org", "x", "Cy", "")])
    conn.commit()
    conn.close()
    return data


@pytest.fixture
def no_registry(monkeypatch):
    import types

    monkeypatch.setattr(dataset_registry, "_api", lambda: types.SimpleNamespace())
    assert not dataset_registry.available()


@pytest.fixture
def registry(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(dataset_registry, "_api", lambda: fake)
    assert dataset_registry.available()
    return fake


def _client(uid: int):
    from fastapi.testclient import TestClient

    from app.auth import create_access_token
    from app.main import create_app

    token = create_access_token({"sub": str(uid), "email": f"u{uid}@example.org"})
    return TestClient(create_app(), headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def users(env):
    return {uid: _client(uid) for uid in (1, 2, 3)}


def _post(client, files, metadata):
    return client.post("/api/datasets", data={"metadata": json.dumps(metadata)},
                       files=[("files", (name, content, "application/octet-stream"))
                              for name, content in files])


def _table_meta(**kw):
    meta = {"name": "Greenness", "kind": "polygon_table", "temporal": "static",
            "key": {"geography": "Tract", "column": "tract"},
            "variables": [{"name": "greenness", "unit": "index", "description": "NDVI"},
                          {"name": "heat"}]}
    meta.update(kw)
    return meta


def _legacy_upload(uid=1, name="Old greenness"):
    """An upload made before phase D: library files, no record."""
    return custom_exposomes.create(uid, content=CSV, name=name, description="", boundary="Tract",
                                   key_col="tract", value_cols=["greenness"], year_col=None)


def _walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)
    elif isinstance(obj, str):
        yield obj


def _no_server_paths(body, data_dir: Path):
    leaked = [s for s in _walk_strings(body) if str(data_dir) in s or s.startswith("/private/")]
    assert not leaked, leaked


# ---------------------------------------------------------------------------
# migration: uploads made before phase D become private registered datasets
# ---------------------------------------------------------------------------

def test_migration_writes_a_private_record_and_moves_nothing(env, no_registry):
    m = _legacy_upload()
    ddir = custom_exposomes.dataset_dir(1, m["dataset_id"])
    before = {p.name: p.read_bytes() for p in ddir.iterdir()}
    assert datasets.migrate() == 1
    assert datasets.migrate() == 0                                   # idempotent
    record = json.loads((ddir / "dataset.json").read_text())
    assert record["id"] == m["dataset_id"] and record["owner"] == "1"
    assert record["visibility"] == "private"
    assert record["kind"] == "polygon_table" and record["temporal"] == "static"
    assert record["key"] == {"boundary": "tract", "column": "tract"}
    assert record["variables"] == [{"name": "greenness", "unit": None, "description": None}]
    assert record["files"] == ["values.csv"] and record["checksum"] == m["sha256"]
    after = {p.name: p.read_bytes() for p in ddir.iterdir() if p.name != "dataset.json"}
    assert after == before                                           # nothing lost or moved


def test_legacy_raster_upload_migrates_with_its_bands(env, no_registry, tmp_path):
    pytest.importorskip("rasterio")
    import numpy as np

    from tests.test_raster_values import write_tif

    tif = write_tif(tmp_path / "r.tif", np.stack([np.ones((4, 5)), np.ones((4, 5)) * 2]))
    m = custom_exposomes.create_raster(1, rasters=[("r.tif", tif.read_bytes(), None)],
                                       name="Two bands", description="",
                                       bands=[2, 1], value_cols=["hi", "lo"])
    datasets.migrate()
    ds = datasets.find(1, m["dataset_id"])
    assert ds.kind == "raster" and ds.record["files"] == ["rasters/static.tif"]
    assert [(v["name"], v["band"]) for v in ds.record["variables"]] == [("hi", 2), ("lo", 1)]
    assert ds.status() == ("ready", None)


def test_listing_migrates_lazily_and_skips_a_half_written_upload(env, no_registry, users):
    m = _legacy_upload()
    broken = custom_exposomes.dataset_dir(1, "deadbeef")
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{ truncated")
    body = users[1].get("/api/datasets").json()
    assert [d["id"] for d in body] == [m["dataset_id"]]
    assert body[0]["owned_by_me"] and body[0]["visibility"] == "private"
    assert body[0]["status"] == "ready" and body[0]["variable_key"] == m["variable_key"]


# ---------------------------------------------------------------------------
# POST /api/datasets without a registry (phase-C path)
# ---------------------------------------------------------------------------

def test_register_a_table_without_registry(env, no_registry, users):
    meta = _table_meta(source="County health dept.", version="2024.1",
                       license_note="CC BY 4.0", description="Synthetic greenness.")
    r = _post(users[1], [("values.csv", CSV)], meta)
    assert r.status_code == 201, r.text
    ds = r.json()["dataset"]
    assert ds["kind"] == "polygon_table" and ds["temporal"] == "static"
    assert ds["visibility"] == "private" and ds["owned_by_me"] is True
    assert ds["owner_display"] == "Ada Lovelace"
    assert (ds["source"], ds["version"], ds["license_note"]) == (
        "County health dept.", "2024.1", "CC BY 4.0")
    assert ds["key"] == {"geography": "Tract", "column": "tract"}
    assert [v["name"] for v in ds["variables"]] == ["greenness", "heat"]
    assert ds["variables"][0]["unit"] == "index"
    assert ds["status"] == "ready" and ds["entry"]["experiment"] == "custom"
    assert ds["files"] == ["values.csv"]
    _no_server_paths(r.json(), env)


def test_register_a_yearly_raster_without_registry(env, no_registry, users, tmp_path):
    pytest.importorskip("rasterio")
    import numpy as np

    from tests.test_raster_values import write_tif

    a = write_tif(tmp_path / "a.tif", np.ones((4, 5))).read_bytes()
    b = write_tif(tmp_path / "b.tif", np.ones((4, 5)) * 3).read_bytes()
    meta = {"name": "NDVI", "kind": "raster", "temporal": "yearly",
            "variables": [{"name": "ndvi", "band": 1}],
            "periods": [{"file": "first.tif", "year": 2016}, {"file": "second.tif", "year": 2017}]}
    r = _post(users[1], [("first.tif", a), ("second.tif", b)], meta)
    assert r.status_code == 201, r.text
    ds = r.json()["dataset"]
    assert ds["entry"]["coverage_years"] == [2016, 2017]
    assert sorted(ds["files"]) == ["2016.tif", "2017.tif"]


def test_new_kinds_need_a_registry(env, no_registry, users):
    r = _post(users[1], [("pm.csv", DAILY)], _table_meta(
        temporal="daily", key={"geography": "Tract", "column": "GEOID", "time_column": "date"},
        variables=[{"name": "pm25"}]))
    assert r.status_code == 400
    assert "no dataset registry" in r.json()["detail"]
    assert r.json()["issues"][0]["field"] == "temporal"


@pytest.mark.parametrize("change,field", [
    ({"name": "  "}, "name"),
    ({"kind": "shapes"}, "kind"),
    ({"temporal": "biweekly"}, "temporal"),            # not for a table
    ({"visibility": "public"}, "visibility"),
    ({"license_note": "x" * 2001}, "license_note"),
    ({"variables": "greenness"}, "variables"),
    ({"periods": [{"year": 2016}]}, "periods"),
])
def test_refused_metadata_lists_the_field(env, no_registry, users, change, field):
    r = _post(users[1], [("values.csv", CSV)], _table_meta(**change))
    assert r.status_code == 400, r.text
    assert field in [i["field"] for i in r.json()["issues"]], r.json()


def test_unknown_metadata_field_and_bad_json_are_refused(env, no_registry, users):
    r = _post(users[1], [("values.csv", CSV)], _table_meta(owner="2"))
    assert r.status_code == 400 and "unknown metadata field" in r.json()["detail"] + str(
        r.json()["issues"])
    r = users[1].post("/api/datasets", data={"metadata": "{not json"},
                      files=[("files", ("values.csv", CSV, "text/csv"))])
    assert r.status_code == 400


@pytest.mark.parametrize("files,status,needle", [
    ([("values.xlsx", CSV)], 400, "accepts"),
    ([("a.csv", CSV), ("b.csv", CSV)], 400, "one file"),
    ([("values.csv", b"")], 400, "empty"),
    ([("../../etc/x.csv", CSV)], 201, None),             # the name is reduced to x.csv
    ([(".hidden.csv", CSV)], 400, "no usable name"),
])
def test_file_checks(env, no_registry, users, files, status, needle):
    r = _post(users[1], files, _table_meta())
    assert r.status_code == status, r.text
    if needle:
        assert needle in json.dumps(r.json())


def test_size_and_count_limits(env, no_registry, users, monkeypatch):
    import app.config

    monkeypatch.setattr(app.config.settings, "MAX_DATASET_FILES", 1)
    r = _post(users[1], [("a.tif", b"x"), ("b.tif", b"y")],
              {"name": "x", "kind": "raster", "temporal": "yearly"})
    assert r.status_code == 413
    monkeypatch.setattr(app.config.settings, "MAX_UPLOAD_SIZE_MB", 0)
    r = _post(users[1], [("values.csv", CSV)], _table_meta())
    assert r.status_code == 413 and "MB limit" in r.json()["detail"]
    assert not list((custom_exposomes.library_root() / ".staging").iterdir())   # cleaned up


def test_a_name_is_unique_per_owner(env, no_registry, users):
    assert _post(users[1], [("values.csv", CSV)], _table_meta()).status_code == 201
    r = _post(users[1], [("values.csv", CSV)], _table_meta(name="GREENNESS"))
    assert r.status_code == 409 and r.json()["issues"][0]["field"] == "name"
    assert _post(users[2], [("values.csv", CSV)], _table_meta()).status_code == 201


def test_capabilities(env, no_registry, users):
    body = users[1].get("/api/datasets/capabilities").json()
    assert body["registry"] is False
    assert body["kinds"] == {"polygon_table": ["static", "yearly"], "raster": ["static", "yearly"]}
    assert body["limits"]["max_files"] == 1000


# ---------------------------------------------------------------------------
# POST /api/datasets through the registry
# ---------------------------------------------------------------------------

def test_a_daily_table_goes_to_the_registry_in_its_vocabulary(env, registry, users):
    meta = _table_meta(name="PM daily", temporal="daily",
                       key={"geography": "Tract", "column": "GEOID", "time_column": "date"},
                       variables=[{"name": "pm25", "unit": "ug/m3"}], visibility="deployment",
                       source="EPA")
    r = _post(users[1], [("pm.csv", DAILY)], meta)
    assert r.status_code == 201, r.text
    call = registry.calls[-1][1]
    assert call["kind"] == "polygon_table" and call["temporal"] == "daily"
    assert call["key"] == {"boundary": "tract", "column": "GEOID", "date_column": "date"}
    assert call["metadata"] == {"source": "EPA", "visibility": "deployment", "owner": "1"}
    assert Path(call["root"]) == custom_exposomes.user_dir(1)
    ds = r.json()["dataset"]
    assert len(ds["id"]) == 32 and ds["variable_key"] == f"custom_{ds['id'][:8]}"
    assert ds["visibility"] == "deployment" and ds["status"] == "ready"
    assert ds["key"] == {"geography": "Tract", "column": "GEOID", "time_column": "date"}
    assert ds["entry"]["temporal"] == "daily"
    _no_server_paths(r.json(), env)
    assert [d["id"] for d in users[2].get("/api/datasets").json()] == [ds["id"]]


def test_a_biweekly_raster_passes_its_periods(env, registry, users):
    meta = {"name": "PM biweekly", "kind": "raster", "temporal": "biweekly",
            "variables": [{"name": "pm25", "band": 1}],
            "periods": [{"file": "a.tif", "start": "2017-01-01", "end": "2017-01-14"},
                        {"file": "b.tif", "start": "2017-01-15", "end": "2017-01-28"}]}
    r = _post(users[1], [("a.tif", b"tif-a"), ("b.tif", b"tif-b")], meta)
    assert r.status_code == 201, r.text
    paths = registry.calls[-1][1]["paths"]
    assert sorted((Path(p).name, v) for p, v in paths.items()) == [
        ("a.tif", ("2017-01-01", "2017-01-14")), ("b.tif", ("2017-01-15", "2017-01-28"))]


def test_a_features_dataset_with_a_year_column(env, registry, users):
    meta = {"name": "Clinics", "kind": "features", "temporal": "yearly",
            "key": {"time_column": "year"}}
    r = _post(users[1], [("clinics.gpkg", b"gpkg")], meta)
    assert r.status_code == 201, r.text
    assert registry.calls[-1][1]["key"] == {"year_column": "year"}
    assert r.json()["dataset"]["variables"][0]["name"] == "feature_dist_m"


def test_registry_refusals_are_400_and_409(env, registry, users):
    r = _post(users[1], [("pm.csv", b"BAD" + DAILY)], _table_meta(
        temporal="daily", key={"geography": "Tract", "column": "GEOID", "time_column": "date"}))
    assert r.status_code == 400
    assert r.json()["issues"] == [{"field": None,
                                   "message": "pm.csv: 3 rows have no usable date in column 'date'"}]
    assert _post(users[1], [("pm.csv", DAILY)], _table_meta(name="PM")).status_code == 201
    assert _post(users[1], [("pm.csv", DAILY)], _table_meta(name="pm")).status_code == 409


def test_registry_edit_share_and_delete(env, registry, users):
    ds = _post(users[1], [("pm.csv", DAILY)], _table_meta(name="PM")).json()["dataset"]
    r = users[1].patch(f"/api/datasets/{ds['id']}",
                       json={"visibility": "deployment", "description": "Daily PM2.5",
                             "variables": [{"name": "greenness", "unit": "NDVI"}]})
    assert r.status_code == 200, r.text
    assert registry.calls[-1] == ("update", {
        "id": ds["id"], "name": None,
        "metadata": {"description": "Daily PM2.5", "visibility": "deployment"},
        "variables": [{"name": "greenness", "unit": "NDVI"}]})
    assert r.json()["dataset"]["visibility"] == "deployment"
    assert users[1].delete(f"/api/datasets/{ds['id']}").json() == {"status": "deleted"}
    assert users[1].get("/api/datasets").json() == []


# ---------------------------------------------------------------------------
# edits of a library dataset
# ---------------------------------------------------------------------------

def test_library_edit_updates_the_record_and_the_definition(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    r = users[1].patch(f"/api/datasets/{ds['id']}", json={
        "name": "Greenness v2", "version": "2", "visibility": "deployment",
        "variables": [{"name": "heat", "unit": "degF", "description": "Heat index"}]})
    assert r.status_code == 200, r.text
    out = r.json()["dataset"]
    assert out["name"] == "Greenness v2" and out["version"] == "2"
    assert out["visibility"] == "deployment" and out["updated_utc"]
    manifest = custom_exposomes.get(1, ds["id"])
    assert manifest["label"] == "Greenness v2"
    assert manifest["value_units"] == {"greenness": "index", "heat": "degF"}
    assert manifest["value_labels"]["heat"] == "Heat index"
    assert manifest["display_unit"] == "index / degF"


@pytest.mark.parametrize("patch", [
    {"kind": "raster"}, {"files": []}, {"visibility": "everyone"},
    {"variables": [{"name": "nope", "unit": "x"}]},
    {"variables": [{"name": "heat", "unit": "x" * 51}]},
])
def test_refused_edits(env, no_registry, users, patch):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    assert users[1].patch(f"/api/datasets/{ds['id']}", json=patch).status_code == 400


# ---------------------------------------------------------------------------
# tasks: selection by id or key, own or shared, snapshots
# ---------------------------------------------------------------------------

def _task(client, name="t"):
    from app import task_manager

    task_id = client.post("/api/tasks", json={"task_name": name}).json()["id"]
    (task_manager._task_dir(task_id) / "input.csv").write_text(COHORT)
    return task_id


def _config(client, task_id, **kw):
    body = {"buffer": {"shape": "circle", "size": 270, "raster_res_m": 25},
            "variables": kw.pop("variables", ["ndi"]), **kw}
    return client.put(f"/api/tasks/{task_id}/config", json=body)


def _saved_config(task_id):
    from app import task_manager

    return json.loads((task_manager._task_dir(task_id) / "config.json").read_text())


def test_select_by_id_snapshots_the_definition(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    task_id = _task(users[1])
    assert _config(users[1], task_id, custom_datasets=[ds["id"]]).status_code == 200
    cfg = _saved_config(task_id)
    assert cfg["variables"] == ["ndi", ds["variable_key"]]
    assert cfg["custom_datasets"] == [ds["id"]]
    assert cfg["custom_variables"][ds["variable_key"]]["label"] == "Greenness"
    assert cfg["output_level"] == "participant"


def test_snapshot_is_frozen_against_later_edits(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    task_id = _task(users[1])
    _config(users[1], task_id, custom_datasets=[ds["id"]])
    users[1].patch(f"/api/datasets/{ds['id']}", json={"name": "Renamed"})
    assert _saved_config(task_id)["custom_variables"][ds["variable_key"]]["label"] == "Greenness"


def test_the_phase_c_frontend_selects_by_key(env, no_registry, users):
    m = _legacy_upload()
    task_id = _task(users[1])
    assert _config(users[1], task_id, variables=[m["variable_key"]]).status_code == 200
    cfg = _saved_config(task_id)
    assert list(cfg["custom_variables"]) == [m["variable_key"]]
    assert cfg["custom_datasets"] == [m["dataset_id"]]


def test_a_client_cannot_inject_definitions(env, no_registry, users):
    m = _legacy_upload(uid=1)
    task_id = _task(users[2])
    forged = {"custom_variables": {m["variable_key"]: m}}
    r = users[2].put(f"/api/tasks/{task_id}/config", json={
        "buffer": {"size": 270}, "variables": ["ndi"], **forged})
    assert r.status_code == 200
    assert "custom_variables" not in _saved_config(task_id)


def test_a_dataset_with_missing_files_cannot_be_selected(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    (custom_exposomes.dataset_dir(1, ds["id"]) / "values.csv").unlink()
    listed = users[1].get("/api/datasets").json()[0]
    assert listed["status"] == "error" and "missing" in listed["status_detail"]
    task_id = _task(users[1])
    assert _config(users[1], task_id, custom_datasets=[ds["id"]]).status_code == 409


def test_coverage_of_a_dataset_not_yet_in_the_config(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    task_id = _task(users[1])
    r = users[1].get(f"/api/tasks/{task_id}/coverage?variables={ds['variable_key']}")
    assert r.status_code == 200, r.text
    assert r.json()["variables"][ds["variable_key"]]["temporal"] == "static"
    r = users[2].get(f"/api/tasks/{_task(users[2], 'b')}/coverage?variables={ds['variable_key']}")
    assert r.status_code == 400                         # user 2 cannot see user 1's dataset


# ---------------------------------------------------------------------------
# security
# ---------------------------------------------------------------------------

def test_a_private_dataset_is_invisible_to_others(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    other = users[2]
    assert other.get("/api/datasets").json() == []
    assert other.get("/api/custom-exposomes").json() == {"variables": {}}
    assert other.get(f"/api/datasets/{ds['id']}").status_code == 404
    assert other.patch(f"/api/datasets/{ds['id']}", json={"visibility": "deployment"}
                       ).status_code == 404
    assert other.delete(f"/api/datasets/{ds['id']}").status_code == 404
    assert other.delete(f"/api/custom-exposomes/{ds['id']}").status_code == 404
    task_id = _task(other)
    assert _config(other, task_id, custom_datasets=[ds["id"]]).status_code == 404
    assert _config(other, task_id, variables=[ds["variable_key"]]).status_code == 404
    # The owner still has it, unchanged.
    assert users[1].get(f"/api/datasets/{ds['id']}").json()["dataset"]["visibility"] == "private"


def test_a_shared_dataset_is_selectable_but_not_editable_by_others(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)],
               _table_meta(visibility="deployment")).json()["dataset"]
    other = users[2]
    listed = other.get("/api/datasets").json()
    assert [d["id"] for d in listed] == [ds["id"]]
    assert listed[0]["owned_by_me"] is False and listed[0]["owner_display"] == "Ada Lovelace"
    assert other.get(f"/api/datasets/{ds['id']}").status_code == 200
    for call in (lambda: other.patch(f"/api/datasets/{ds['id']}", json={"name": "Mine"}),
                 lambda: other.patch(f"/api/datasets/{ds['id']}", json={"visibility": "private"}),
                 lambda: other.delete(f"/api/datasets/{ds['id']}"),
                 lambda: other.delete(f"/api/custom-exposomes/{ds['id']}")):
        r = call()
        assert r.status_code == 403, r.text
    assert other.get("/api/custom-exposomes").json() == {"variables": {}}   # own only
    task_id = _task(other)
    assert _config(other, task_id, custom_datasets=[ds["id"]]).status_code == 200
    snap = _saved_config(task_id)["custom_variables"][ds["variable_key"]]
    assert snap["owner_uid"] == "1"
    assert users[1].get(f"/api/datasets/{ds['id']}").json()["dataset"]["name"] == "Greenness"


def test_unsharing_stops_new_runs_but_keeps_finished_results(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)],
               _table_meta(visibility="deployment")).json()["dataset"]
    task_id = _task(users[2])
    _config(users[2], task_id, custom_datasets=[ds["id"]])
    from app import task_manager

    out = task_manager._task_dir(task_id) / "output"
    (out / "result.csv").write_text("pid,greenness\nA1,0.5\n")
    assert users[1].patch(f"/api/datasets/{ds['id']}", json={"visibility": "private"}
                          ).status_code == 200
    r = users[2].post(f"/api/tasks/{task_id}/start")
    assert r.status_code == 409 and "no longer shared" in r.json()["detail"]
    assert users[2].get("/api/datasets").json() == []
    assert users[2].get(f"/api/tasks/{task_id}/results").status_code == 200   # kept


def test_a_deleted_dataset_stops_its_tasks_from_starting(env, no_registry, users):
    ds = _post(users[1], [("values.csv", CSV)], _table_meta()).json()["dataset"]
    task_id = _task(users[1])
    _config(users[1], task_id, custom_datasets=[ds["id"]])
    assert users[1].delete(f"/api/datasets/{ds['id']}").status_code == 200
    assert users[1].post(f"/api/tasks/{task_id}/start").status_code == 409


@pytest.mark.parametrize("status,deletable", [("running", False), ("queued", False),
                                              ("finished", True), ("error", True)])
def test_no_delete_while_a_queued_or_running_task_uses_it(env, no_registry, users, status,
                                                          deletable):
    import os

    ds = _post(users[1], [("values.csv", CSV)],
               _table_meta(visibility="deployment")).json()["dataset"]
    task_id = _task(users[2])                              # another user's task
    _config(users[2], task_id, custom_datasets=[ds["id"]])
    from app import task_manager

    task_manager._write_status(task_manager._task_dir(task_id), status=status, pid=os.getpid())
    r = users[1].delete(f"/api/datasets/{ds['id']}")
    if deletable:
        assert r.status_code == 200, r.text
    else:
        assert r.status_code == 409
        assert "queued or running task" in r.json()["detail"]
        assert task_id not in r.json()["detail"]           # nothing about the other user's task
        assert users[1].get(f"/api/datasets/{ds['id']}").status_code == 200


def test_registry_dataset_access_rules(env, registry, users):
    ds = _post(users[1], [("pm.csv", DAILY)], _table_meta(name="PM")).json()["dataset"]
    assert users[2].get(f"/api/datasets/{ds['id']}").status_code == 404
    assert users[2].delete(f"/api/datasets/{ds['id']}").status_code == 404
    assert all(c[0] != "remove" for c in registry.calls)
    users[1].patch(f"/api/datasets/{ds['id']}", json={"visibility": "deployment"})
    assert users[2].patch(f"/api/datasets/{ds['id']}", json={"name": "x"}).status_code == 403
    task_id = _task(users[2])
    assert _config(users[2], task_id, custom_datasets=[ds["id"]]).status_code == 200
    snap = _saved_config(task_id)["custom_variables"][ds["variable_key"]]
    assert snap["registered"]["id"] == ds["id"]


def test_no_response_carries_a_server_path(env, no_registry, users):
    _legacy_upload()
    ds = _post(users[1], [("values.csv", CSV)],
               _table_meta(name="Shared", visibility="deployment")).json()["dataset"]
    for client in (users[1], users[2]):
        _no_server_paths(client.get("/api/datasets").json(), env)
        _no_server_paths(client.get(f"/api/datasets/{ds['id']}").json(), env)
        _no_server_paths(client.get("/api/custom-exposomes").json(), env)


def test_every_route_needs_a_login(env, no_registry):
    from fastapi.testclient import TestClient

    from app.main import create_app

    anon = TestClient(create_app())
    for method, url in (("get", "/api/datasets"), ("get", "/api/datasets/capabilities"),
                        ("post", "/api/datasets"), ("get", "/api/datasets/0a1b2c3d"),
                        ("patch", "/api/datasets/0a1b2c3d"), ("delete", "/api/datasets/0a1b2c3d")):
        assert getattr(anon, method)(url).status_code == 401, (method, url)


def test_malformed_ids_are_not_found(env, no_registry, users):
    for bad in ("..%2F..%2Fetc", "ZZZZZZZZ", "0a1b2c3d0", "custom_0a1b2c3d"):
        assert users[1].get(f"/api/datasets/{bad}").status_code == 404
