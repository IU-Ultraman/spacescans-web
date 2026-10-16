"""The new upload kinds against the REAL dataset registry of the installed spacescans.

Skipped until the installed spacescans has ``spacescans.custom.register`` and friends
(phase D track B); the integration step runs them against the integrated package. Each test
registers a synthetic dataset through ``POST /api/datasets`` (a daily tract table, a
biweekly raster series, a yearly raster, a point-features file), selects it in a task
(``custom_datasets``) and plans the task's custom steps from the snapshot, as the runner
does. Running the steps needs provisioned C3 data and is the container gate's.
"""
from __future__ import annotations

import json

import pytest

from app import dataset_registry

pytestmark = pytest.mark.skipif(
    not dataset_registry.available(),
    reason="the installed spacescans has no dataset registry (phase D track B not integrated)")

from tests.test_datasets import (  # noqa: E402
    _client,
    _config,
    _no_server_paths,
    _post,
    _saved_config,
    _task,
)
from tests.test_datasets import env  # noqa: E402,F401  (fixture)

TRACT_A = "12073001100"
TRACT_B = "12073001200"


@pytest.fixture
def users(env):  # noqa: F811
    return {uid: _client(uid) for uid in (1, 2)}


def _plan(task_id):
    from spacescans import catalog

    cfg = _saved_config(task_id)
    custom_keys = list(cfg["custom_variables"])
    steps = catalog.plan("custom", custom_keys, overlay=cfg["custom_variables"])
    return cfg, steps


def _register(client, files, meta):
    r = _post(client, files, meta)
    assert r.status_code == 201, r.text
    return r.json()["dataset"]


def test_daily_table(users, env):  # noqa: F811
    rows = ["GEOID,date,pm25"] + [f"{t},2017-01-{d:02d},{d + 0.5}" for t in (TRACT_A, TRACT_B)
                                  for d in range(1, 11)]
    ds = _register(users[1], [("pm_daily.csv", "\n".join(rows).encode())], {
        "name": "PM daily", "kind": "polygon_table", "temporal": "daily",
        "key": {"geography": "Tract", "column": "GEOID", "time_column": "date"},
        "variables": [{"name": "pm25", "unit": "ug/m3", "description": "Daily PM2.5"}],
        "visibility": "deployment", "source": "synthetic", "version": "1"})
    assert ds["temporal"] == "daily" and ds["status"] == "ready"
    assert ds["key"]["time_column"] == "date"
    _no_server_paths(ds, env)
    task_id = _task(users[2])                       # another user selects the shared dataset
    assert _config(users[2], task_id, custom_datasets=[ds["id"]]).status_code == 200
    cfg, steps = _plan(task_id)
    definition = cfg["custom_variables"][ds["variable_key"]]
    assert definition["temporal"] == "daily" and definition["registered"]["id"] == ds["id"]
    assert any(not s.is_c3 for s in steps)


def _tif(path, value, **kw):
    pytest.importorskip("rasterio")
    import numpy as np

    from tests.test_raster_values import write_tif

    return write_tif(path, np.full((6, 6), float(value)), west=-84.6, north=30.7, res=0.01,
                     **kw).read_bytes()


def test_biweekly_raster_series(users, env, tmp_path):  # noqa: F811
    files = [("pm_20170101.tif", _tif(tmp_path / "a.tif", 1)),
             ("pm_20170115.tif", _tif(tmp_path / "b.tif", 2))]
    ds = _register(users[1], files, {
        "name": "PM biweekly", "kind": "raster", "temporal": "biweekly",
        "variables": [{"name": "pm25", "band": 1, "unit": "ug/m3"}],
        "periods": [{"file": "pm_20170101.tif", "start": "2017-01-01", "end": "2017-01-14"},
                    {"file": "pm_20170115.tif", "start": "2017-01-15", "end": "2017-01-28"}]})
    assert ds["kind"] == "raster" and ds["temporal"] == "biweekly"
    task_id = _task(users[1])
    assert _config(users[1], task_id, custom_datasets=[ds["id"]]).status_code == 200
    _cfg, steps = _plan(task_id)
    assert steps


def test_yearly_raster_with_years_in_the_periods(users, env, tmp_path):  # noqa: F811
    files = [("first.tif", _tif(tmp_path / "a.tif", 1)), ("second.tif", _tif(tmp_path / "b.tif", 2))]
    ds = _register(users[1], files, {
        "name": "NDVI yearly", "kind": "raster", "temporal": "yearly",
        "variables": [{"name": "ndvi", "band": 1}],
        "periods": [{"file": "first.tif", "year": 2016}, {"file": "second.tif", "year": 2017}]})
    assert ds["entry"]["coverage_years"] == [2016, 2017]


def test_point_features(users, env, tmp_path):  # noqa: F811
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import Point

    frame = gpd.GeoDataFrame({"name": ["a", "b"]},
                             geometry=[Point(-84.30, 30.44), Point(-84.25, 30.46)],
                             crs="EPSG:4326")
    path = tmp_path / "clinics.geojson"
    frame.to_file(path, driver="GeoJSON")
    ds = _register(users[1], [("clinics.geojson", path.read_bytes())], {
        "name": "Clinics", "kind": "features", "temporal": "static",
        "variables": [{"name": "clinic_dist_m", "unit": "m"}]})
    assert ds["kind"] == "features" and ds["variables"][0]["name"] == "clinic_dist_m"
    task_id = _task(users[1])
    assert _config(users[1], task_id, custom_datasets=[ds["id"]]).status_code == 200
    _cfg, steps = _plan(task_id)
    assert steps


def test_refused_data_names_the_problem_without_values(users, env):  # noqa: F811
    rows = ["GEOID,date,pm25", f"{TRACT_A},not-a-date,5.0"]
    r = _post(users[1], [("bad.csv", "\n".join(rows).encode())], {
        "name": "Bad", "kind": "polygon_table", "temporal": "daily",
        "key": {"geography": "Tract", "column": "GEOID", "time_column": "date"}})
    assert r.status_code == 400, r.text
    assert "not-a-date" not in json.dumps(r.json())
