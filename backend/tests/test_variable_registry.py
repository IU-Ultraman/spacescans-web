"""Sprint 3 T2: variable_registry — load, validate, cache, query helpers."""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_registry_cache():
    """Force fresh load each test so mtime / payload state does not leak."""
    from app import variable_registry as vr
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None
    vr._PROBE_DONE = False
    yield
    vr._CACHE["mtime"] = None
    vr._CACHE["payload"] = None
    vr._PROBE_DONE = False


def test_load_variables_passes_schema_validation():
    from app import variable_registry as vr
    payload = vr.load_variables()
    assert payload["schema_version"] == 1
    assert set(payload["variables"].keys()) >= {"ndi", "walkability", "cbp_zcta5"}


def test_get_variable_returns_metadata_dict():
    from app import variable_registry as vr
    m = vr.get_variable("ndi")
    assert m["experiment"] == "bg_ndi_wi"
    assert m["boundary"] == "BG"
    assert m["value_cols"] == ["ndi"]


def test_get_variable_unknown_key_raises_keyerror():
    from app import variable_registry as vr
    with pytest.raises(KeyError):
        vr.get_variable("does_not_exist")


def test_missing_required_field_rejected(tmp_path, monkeypatch):
    """A variable lacking a required field must fail jsonschema validation."""
    from app import variable_registry as vr

    bad = {
        "schema_version": 1,
        "variables": {
            "ndi": {
                # missing "label"
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }
    bad_path = tmp_path / "variable_metadata.json"
    bad_path.write_text(json.dumps(bad))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_path)

    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        vr.load_variables(force=True)


def test_unknown_experiment_rejected(tmp_path, monkeypatch):
    """Variable referencing an experiment with no module in app/experiments/ must fail."""
    from app import variable_registry as vr

    bad = {
        "schema_version": 1,
        "variables": {
            "ndi": {
                "label": "NDI",
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "ghost_runner",  # no such module
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }
    bad_path = tmp_path / "variable_metadata.json"
    bad_path.write_text(json.dumps(bad))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_path)

    with pytest.raises(vr.MetadataSchemaError, match="unknown experiment"):
        vr.load_variables(force=True)


def test_schema_version_mismatch_rejected(tmp_path, monkeypatch):
    """schema_version not in supported set raises MetadataSchemaError."""
    from app import variable_registry as vr

    bad_payload = tmp_path / "variable_metadata.json"
    bad_schema = tmp_path / "variable_metadata.schema.json"
    bad_payload.write_text(json.dumps({
        "schema_version": 2,
        "variables": {
            "ndi": {
                "label": "NDI",
                "description": "x",
                "boundary": "BG",
                "coverage_years": [2012, 2022],
                "coverage_region": "CONUS",
                "experiment": "bg_ndi_wi",
                "variable_type": "continuous",
                "display_unit": "z-score",
                "value_cols": ["ndi"],
            }
        },
    }))
    # Permissive schema so jsonschema.validate passes and the version gate fires.
    bad_schema.write_text(json.dumps({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["schema_version", "variables"],
    }))
    monkeypatch.setattr(vr, "_METADATA_PATH", bad_payload)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", bad_schema)

    with pytest.raises(vr.MetadataSchemaError, match="unsupported schema_version"):
        vr.load_variables(force=True)


def test_mtime_cache_reloads_on_file_change(tmp_path, monkeypatch):
    """Touching the metadata file (new mtime) must trigger a reload."""
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"

    def write(label_for_ndi: str) -> None:
        payload_path.write_text(json.dumps({
            "schema_version": 1,
            "variables": {
                "ndi": {
                    "label": label_for_ndi,
                    "description": "x",
                    "boundary": "BG",
                    "coverage_years": [2012, 2022],
                    "coverage_region": "CONUS",
                    "experiment": "bg_ndi_wi",
                    "variable_type": "continuous",
                    "display_unit": "z-score",
                    "value_cols": ["ndi"],
                }
            },
        }))

    write("first")
    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)

    first = vr.load_variables(force=True)
    assert first["variables"]["ndi"]["label"] == "first"

    # Ensure new mtime is distinct (filesystem mtime resolution >= 1s on some FSes).
    time.sleep(1.1)
    write("second")
    second = vr.load_variables()  # no force — relies on mtime cache invalidation
    assert second["variables"]["ndi"]["label"] == "second"


def test_variables_by_experiment_preserves_file_order(tmp_path, monkeypatch):
    """Reordering the JSON file inverts the OrderedDict iteration order."""
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"

    def variable(label: str, experiment: str, boundary: str) -> dict:
        return {
            "label": label, "description": "x",
            "boundary": boundary, "coverage_years": [2012, 2022],
            "coverage_region": "CONUS", "experiment": experiment,
            "variable_type": "continuous", "display_unit": "u",
            "value_cols": ["c"],
        }

    p = tmp_path / "variable_metadata.json"
    monkeypatch.setattr(vr, "_METADATA_PATH", p)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)

    # bg_ndi_wi first in file → first in dispatch
    p.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "ndi": variable("NDI", "bg_ndi_wi", "BG"),
            "cbp_zcta5": variable("CBP", "zcta5_cbp", "ZCTA5"),
        },
    }))
    grouped = vr.variables_by_experiment(["ndi", "cbp_zcta5"])
    assert isinstance(grouped, OrderedDict)
    assert list(grouped.keys()) == ["bg_ndi_wi", "zcta5_cbp"]

    # Invert order — must invert dispatch
    time.sleep(1.1)
    p.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "cbp_zcta5": variable("CBP", "zcta5_cbp", "ZCTA5"),
            "ndi": variable("NDI", "bg_ndi_wi", "BG"),
        },
    }))
    grouped = vr.variables_by_experiment(["ndi", "cbp_zcta5"])
    assert list(grouped.keys()) == ["zcta5_cbp", "bg_ndi_wi"]


def test_list_experiments_dedupes_in_file_order():
    """Post-B2 invariant: with the tiger_proximity + nhd_bluespace runner
    modules now present in app.experiments, list_experiments() returns the
    file-order de-duped list of experiments referenced by
    variable_metadata.json. Sprint 7 appends nhd_bluespace as the fourth slot.
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
    ], exps


def test_registry_accepts_tiger_proximity_entry(tmp_path, monkeypatch):
    """Sprint 5 B1: tiger_proximity entry passes schema (3 value_cols, BG boundary,
    2013-2019 coverage) once a tiger_proximity experiment module exists.

    This test stubs the experiment discovery so it does NOT depend on B2's
    runner module landing. It locks in the canonical entry shape from spec L570-582.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "tiger_proximity": {
                "label": "TIGER Road Proximity",
                "description": (
                    "Per-block-group annual distance (meters) to the nearest "
                    "TIGER/Line primary road (S1100), secondary road (S1200), "
                    "and primary+secondary combined, from US Census TIGER/Line "
                    "shapefiles."
                ),
                "boundary": "BG",
                "coverage_years": [2013, 2019],
                "coverage_region": "CONUS",
                "experiment": "tiger_proximity",
                "variable_type": "continuous",
                "display_unit": "meters",
                "value_cols": ["dist_pri", "dist_sec", "dist_prisec"],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    # Pretend the tiger_proximity module exists so the whitelist passes — B2
    # will make this real.
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity"},
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["tiger_proximity"]
    assert entry["boundary"] == "BG"
    assert entry["experiment"] == "tiger_proximity"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["display_unit"] == "meters"
    assert entry["value_cols"] == ["dist_pri", "dist_sec", "dist_prisec"]
    assert "US Census TIGER/Line shapefiles" in entry["description"]


def test_real_metadata_file_contains_tiger_proximity_with_runner_module():
    """Post-B2: the real, on-disk variable_metadata.json loads cleanly and
    exposes the tiger_proximity entry now that
    backend/app/experiments/tiger_proximity.py exists.

    Before B2 this test asserted MetadataSchemaError ("unknown experiment") —
    the spec's deliberate half-landed gate (L683-685) — and was flipped to a
    positive assertion the moment B2 landed the runner module.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "tiger_proximity" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["tiger_proximity"]
    assert entry["experiment"] == "tiger_proximity"
    assert entry["boundary"] == "BG"


# ----- Sprint 4 F3: startup probe -----

def test_startup_probe_passes_in_env():
    """In a correctly-installed env, the probe is a no-op (no raise)."""
    from app import variable_registry as vr
    vr._PROBE_DONE = False
    vr._assert_pipeline_version_compatible()
    assert vr._PROBE_DONE is True


def test_startup_probe_raises_on_missing_field(monkeypatch):
    """Drop output_grouping from TimeConfig.model_fields — probe must raise."""
    from app import variable_registry as vr
    import spacescans.models.config as _cfg

    vr._PROBE_DONE = False
    patched = {k: v for k, v in _cfg.TimeConfig.model_fields.items() if k != "output_grouping"}

    class _StubTimeConfig:
        model_fields = patched

    monkeypatch.setattr(_cfg, "TimeConfig", _StubTimeConfig)

    with pytest.raises(vr.MetadataSchemaError) as exc:
        vr._assert_pipeline_version_compatible()
    assert "output_grouping" in str(exc.value)
    assert vr._PROBE_DONE is False


def test_startup_probe_runs_once(monkeypatch):
    """Once _PROBE_DONE is True, the probe must short-circuit before re-entering imports."""
    from app import variable_registry as vr
    import spacescans._extras as _extras

    vr._PROBE_DONE = True

    def _boom(*_a, **_kw):
        raise RuntimeError("probe should not have re-entered require()")

    monkeypatch.setattr(_extras, "require", _boom)
    # No raise expected — second invocation must short-circuit.
    vr._assert_pipeline_version_compatible()
    assert vr._PROBE_DONE is True


# ---------------------------------------------------------------------------
# Sprint 6 T5 (H2): TIGER C4 server-boot pre-flight
# ---------------------------------------------------------------------------


def _make_tiger_tree(root: Path, years: range) -> Path:
    """Build a fake {root}/data_full/TIGER/C4/tiger{year}_roads/ tree."""
    c4 = root / "data_full" / "TIGER" / "C4"
    c4.mkdir(parents=True, exist_ok=True)
    for year in years:
        (c4 / f"tiger{year}_roads").mkdir()
    return c4


def test_tiger_preflight_passes_when_all_years_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))  # 2013..2019 inclusive
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "variables" in payload


def test_tiger_preflight_raises_on_missing_year(tmp_path, monkeypatch):
    import shutil
    from app import variable_registry as vr
    from app.config import settings

    c4 = _make_tiger_tree(tmp_path, range(2013, 2020))
    shutil.rmtree(c4 / "tiger2017_roads")
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "2017" in msg
    assert "tiger2017_roads" in msg


def test_tiger_preflight_skips_when_root_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # tmp_path has no data_full/TIGER/ tree at all
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # short-circuit, no raise
    assert "variables" in payload


# ---------------------------------------------------------------------------
# Sprint 8 I1: NHD C4 server-boot pre-flight (mirror of TIGER H2 pattern)
# ---------------------------------------------------------------------------


def _make_nhd_tree(root: Path, *, with_gdb: bool = True) -> Path:
    """Build a fake {root}/data_full/NHD/C4/NHDPlus_H_National_Release_2_GDB.gdb/
    tree. with_gdb=False creates only the C4 parent so the GDB-missing
    branch can be exercised.
    """
    c4 = root / "data_full" / "NHD" / "C4"
    c4.mkdir(parents=True, exist_ok=True)
    if with_gdb:
        (c4 / "NHDPlus_H_National_Release_2_GDB.gdb").mkdir()
    return c4


def test_nhd_preflight_passes_when_gdb_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # Both pre-flights run on the real metadata payload — provision
    # both the TIGER tree and the NHD GDB so neither short-circuits.
    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "variables" in payload
    assert "nhd_bluespace" in payload["variables"]


def test_nhd_preflight_raises_when_gdb_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    # C4 root exists (no short-circuit) but the GDB subdir does not.
    _make_nhd_tree(tmp_path, with_gdb=False)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "nhd_bluespace" in msg
    assert "NHDPlus_H_National_Release_2_GDB.gdb" in msg


# ---------------------------------------------------------------------------
# Sprint 7 B1: nhd_bluespace metadata entry + registry-level guards
# ---------------------------------------------------------------------------


def test_registry_accepts_nhd_bluespace_entry(tmp_path, monkeypatch):
    """Sprint 7 B1: nhd_bluespace entry passes schema (5 value_cols, BG boundary,
    [2024, 2024] static-product coverage) once an nhd_bluespace experiment
    module exists.

    Mirrors test_registry_accepts_tiger_proximity_entry (Sprint 5 B1 pattern):
    stubs _discover_experiments so it does NOT depend on B2's runner module
    landing — locks in the canonical entry shape.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "nhd_bluespace": {
                "label": "NHD Bluespace (water-body distance)",
                "description": (
                    "Per-block-group static distance (meters) to the nearest "
                    "NHD flowline (dist_flow_m), waterbody (dist_water_m), "
                    "area-feature (dist_area_m), coastline (dist_coast_m; "
                    "99999 for inland addresses), and combined blue-feature "
                    "(dist_blue_m), from NHDPlus_H National Release 2 GDB "
                    "(US Census-aligned block group geography, static product, "
                    "2024 vintage)."
                ),
                "boundary": "BG",
                "coverage_years": [2024, 2024],
                "coverage_region": "CONUS",
                "experiment": "nhd_bluespace",
                "variable_type": "continuous",
                "display_unit": "meters",
                "value_cols": [
                    "dist_flow_m", "dist_water_m", "dist_area_m",
                    "dist_coast_m", "dist_blue_m",
                ],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace"},
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["nhd_bluespace"]
    assert entry["boundary"] == "BG"
    assert entry["experiment"] == "nhd_bluespace"
    assert entry["coverage_years"] == [2024, 2024]
    assert entry["display_unit"] == "meters"
    assert entry["value_cols"] == [
        "dist_flow_m", "dist_water_m", "dist_area_m",
        "dist_coast_m", "dist_blue_m",
    ]
    assert "NHDPlus_H National Release 2 GDB" in entry["description"]
    assert "US Census" in entry["description"]


def test_real_metadata_file_contains_nhd_bluespace_with_runner_module():
    """Post-B2: the real, on-disk variable_metadata.json loads cleanly and
    exposes the nhd_bluespace entry now that
    backend/app/experiments/nhd_bluespace.py exists.

    Before B2 this test fails with MetadataSchemaError ("unknown experiment
    'nhd_bluespace'") — the spec's deliberate half-landed gate (L920) — and
    flips GREEN the moment B2 lands the runner module.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "nhd_bluespace" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["nhd_bluespace"]
    assert entry["experiment"] == "nhd_bluespace"
    assert entry["boundary"] == "BG"
    assert entry["coverage_years"] == [2024, 2024]


def test_list_experiments_after_nhd_bluespace_added():
    """Post-B2: list_experiments returns the 4-experiment metadata-file order.

    Sprint 5 baseline was [bg_ndi_wi, zcta5_cbp, tiger_proximity]; Sprint 7
    appends nhd_bluespace as the fourth slot.
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
    ], exps
