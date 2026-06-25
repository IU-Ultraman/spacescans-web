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
    """Post-B2 invariant: with the tiger_proximity + nhd_bluespace + noise +
    vnl + temis + fara_tract runner modules now present in app.experiments,
    list_experiments() returns the file-order de-duped list of experiments
    referenced by variable_metadata.json. Sprint 11 appends fara_tract as
    the eighth slot.
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
        "noise", "vnl", "temis", "fara_tract",
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
    """Post-B2: list_experiments returns the metadata-file order list.

    Sprint 5 baseline was [bg_ndi_wi, zcta5_cbp, tiger_proximity]; Sprint 7
    appended nhd_bluespace; Sprint 9 appended noise; Sprint 10 appended
    vnl + temis; Sprint 11 appends fara_tract as the eighth slot.
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
        "noise", "vnl", "temis", "fara_tract",
    ], exps


# ---------------------------------------------------------------------------
# Sprint 9 T1: noise metadata entry + registry-level guards
# ---------------------------------------------------------------------------


def test_registry_accepts_noise_entry(tmp_path, monkeypatch):
    """Sprint 9 T1: noise entry passes schema (3 value_cols, BG boundary,
    [2020, 2020] static-product coverage) once a noise experiment module
    exists.

    Mirrors test_registry_accepts_nhd_bluespace_entry (Sprint 7 B1 pattern):
    stubs _discover_experiments so it does NOT depend on T2's runner module
    landing — locks in the canonical entry shape.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "noise": {
                "label": "BTS Transportation Noise (L50 dBA)",
                "description": (
                    "Per-block-group static daytime road+aviation noise "
                    "exposure in L50 dBA (existing/imp/nat scenarios) from "
                    "the US DOT BTS Transportation Noise CONUS raster "
                    "(270 m grid, static product). l50dba_exi is the "
                    "existing-conditions surface; l50dba_imp and l50dba_nat "
                    "are alternative-scenario surfaces."
                ),
                "boundary": "BG",
                "coverage_years": [2020, 2020],
                "coverage_region": "CONUS",
                "experiment": "noise",
                "variable_type": "continuous",
                "display_unit": "dBA",
                "value_cols": ["l50dba_exi", "l50dba_imp", "l50dba_nat"],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {"bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace", "noise"},
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["noise"]
    assert entry["boundary"] == "BG"
    assert entry["experiment"] == "noise"
    assert entry["coverage_years"] == [2020, 2020]
    assert entry["display_unit"] == "dBA"
    assert entry["value_cols"] == ["l50dba_exi", "l50dba_imp", "l50dba_nat"]
    assert "BTS Transportation Noise" in entry["description"]


def test_real_metadata_file_contains_noise_with_runner_module():
    """Post-T2: the real, on-disk variable_metadata.json loads cleanly and
    exposes the noise entry now that backend/app/experiments/noise.py exists.

    Before T2 this test fails with MetadataSchemaError ("unknown experiment
    'noise'") — the spec's half-landed gate — and flips GREEN the moment T2
    lands the runner module.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "noise" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["noise"]
    assert entry["experiment"] == "noise"
    assert entry["boundary"] == "BG"
    assert entry["coverage_years"] == [2020, 2020]


# ---------------------------------------------------------------------------
# Sprint 9 T4: Noise C3 server-boot pre-flight (mirror of TIGER H2 / NHD I1)
# ---------------------------------------------------------------------------


def _make_noise_tree(root: Path, *, with_tifs: bool = True) -> Path:
    """Build a fake {root}/data/Noise/C3/ tree. with_tifs=False creates only
    the C3 parent so the TIF-missing branch can be exercised.
    """
    c3 = root / "data" / "Noise" / "C3"
    c3.mkdir(parents=True, exist_ok=True)
    if with_tifs:
        for tif in (
            "CONUS_L50dBA_sumDay_exi.tif",
            "CONUS_sumDay_L50dBA_imp.tif",
            "CONUS_sumDay_L50dBA_nat.tif",
        ):
            (c3 / tif).write_bytes(b"\x00")  # empty file is enough for exists() check
    return c3


def test_noise_preflight_passes_when_all_tifs_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # All pre-flights run on the real metadata payload — provision TIGER,
    # NHD, AND noise trees so none short-circuit and none raise.
    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "variables" in payload
    assert "noise" in payload["variables"]


def test_noise_preflight_raises_when_tif_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    # C3 root exists (no short-circuit) but the TIF files do not.
    _make_noise_tree(tmp_path, with_tifs=False)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "noise" in msg
    assert "CONUS_L50dBA_sumDay_exi.tif" in msg


# ---------------------------------------------------------------------------
# Sprint 10 T1: vnl + temis metadata entries + registry-level guards
# ---------------------------------------------------------------------------


def test_real_metadata_file_contains_vnl_with_runner_module():
    """Post-Sprint-10-B3: real metadata loads cleanly + exposes vnl entry now
    that backend/app/experiments/vnl.py exists. Pre-runner this fails with
    MetadataSchemaError ('unknown experiment vnl') — the half-landed gate.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "vnl" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["vnl"]
    assert entry["experiment"] == "vnl"
    assert entry["boundary"] == "BG"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["value_cols"] == ["value"]


def test_real_metadata_file_contains_temis_with_runner_module():
    """Post-Sprint-10-B3: real metadata loads cleanly + exposes temis entry
    once backend/app/experiments/temis.py exists.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "temis" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["temis"]
    assert entry["experiment"] == "temis"
    assert entry["boundary"] == "BG"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["value_cols"] == ["uvddc", "uvdec", "uvdvc", "uvief"]


def test_list_experiments_after_vnl_and_temis_added():
    """Sprint 11: list_experiments now contains eight entries in file order.
    bg_ndi_wi -> zcta5_cbp -> tiger_proximity -> nhd_bluespace -> noise
        -> vnl -> temis -> fara_tract.

    (Renamed from the Sprint-10 seven-entry version; the fara_tract slot
    landed at the tail when Sprint 11 added FARA at Tract boundary.)
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
        "noise", "vnl", "temis", "fara_tract",
    ], exps


# ---------------------------------------------------------------------------
# Sprint 10 T5: VNL + TEMIS server-boot pre-flight (mirror of Noise T4)
# ---------------------------------------------------------------------------


def _make_vnl_tree(root: Path, *, with_tif: bool = True) -> Path:
    """Build a fake {root}/data_full/VNL/C3/ tree. with_tif=False creates
    only the C3 parent so the TIF-missing branch can be exercised.
    """
    c3 = root / "data_full" / "VNL" / "C3"
    c3.mkdir(parents=True, exist_ok=True)
    if with_tif:
        (c3 / "VNL_v21_npp_2013_global_vcmcfg_c202205302300.average_masked.dat.tif").write_bytes(b"\x00")
    return c3


def _make_temis_tree(root: Path, *, with_subdir: bool = True) -> Path:
    """Build a fake {root}/data_full/TEMIS/C4/raw/ tree. with_subdir=False
    creates only the raw parent so the missing-UV-subdir branch can be
    exercised.
    """
    raw = root / "data_full" / "TEMIS" / "C4" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    if with_subdir:
        (raw / "uvief").mkdir(exist_ok=True)
    return raw


def test_vnl_preflight_passes_when_tif_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # Provision all five trees so no pre-flight short-circuits and none raise.
    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    _make_vnl_tree(tmp_path, with_tif=True)
    _make_temis_tree(tmp_path, with_subdir=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "vnl" in payload["variables"]


def test_vnl_preflight_raises_when_tif_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    # VNL C3 root exists (no short-circuit) but no VNL_v21_*.tif files.
    _make_vnl_tree(tmp_path, with_tif=False)
    _make_temis_tree(tmp_path, with_subdir=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "vnl" in msg
    assert "VNL_v21_*.tif" in msg


def test_temis_preflight_passes_when_subdir_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    _make_vnl_tree(tmp_path, with_tif=True)
    _make_temis_tree(tmp_path, with_subdir=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "temis" in payload["variables"]


def test_temis_preflight_raises_when_no_uv_subdir(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    _make_vnl_tree(tmp_path, with_tif=True)
    # TEMIS C4 raw root exists (no short-circuit) but no UV subdirs.
    _make_temis_tree(tmp_path, with_subdir=False)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "temis" in msg
    assert "uvief" in msg or "uvddc" in msg or "uvdec" in msg or "uvdvc" in msg


# ---------------------------------------------------------------------------
# Sprint 11 B1: fara_tract metadata entry + registry-level guards
# ---------------------------------------------------------------------------


def _make_fara_tree(root: Path, *, with_files: bool = True) -> Path:
    """Build a fake {root}/data_full/FARA/C4/ tree. with_files=False creates
    only the C4 parent so the data-missing branch can be exercised.
    """
    c4 = root / "data_full" / "FARA" / "C4"
    c4.mkdir(parents=True, exist_ok=True)
    if with_files:
        (c4 / "fara_nationwide_2010_2019_interpolated.Rda").write_bytes(b"\x00")
        (c4 / "varnameCountRemoved.csv").write_text("var,label\n")
    return c4


def test_registry_accepts_fara_tract_entry(tmp_path, monkeypatch):
    """Sprint 11 B1: fara_tract entry passes schema (4 value_cols, Tract
    boundary, [2013, 2019] coverage) once a fara_tract experiment module
    exists.

    Mirrors test_registry_accepts_temis_entry / Sprint-10 T1 pattern: stubs
    _discover_experiments so it does NOT depend on B2's runner module
    landing — locks in the canonical entry shape.
    """
    from app import variable_registry as vr

    real_schema = Path(__file__).parent.parent / "app" / "data" / "variable_metadata.schema.json"
    payload_path = tmp_path / "variable_metadata.json"
    payload_path.write_text(json.dumps({
        "schema_version": 1,
        "variables": {
            "fara_tract": {
                "label": "FARA Food Access (Tract)",
                "description": (
                    "Per-tract annual USDA Food Access Research Atlas "
                    "indicators (binary flags + share variables, "
                    "interpolated to annual 2013-2019)."
                ),
                "boundary": "Tract",
                "coverage_years": [2013, 2019],
                "coverage_region": "CONUS",
                "experiment": "fara_tract",
                "variable_type": "categorical",
                "display_unit": "binary flags",
                "value_cols": ["LILATracts_1And10", "LATracts1", "HUNVFlag", "LowIncomeTracts"],
            }
        },
    }))

    monkeypatch.setattr(vr, "_METADATA_PATH", payload_path)
    monkeypatch.setattr(vr, "_SCHEMA_PATH", real_schema)
    monkeypatch.setattr(
        vr, "_discover_experiments",
        lambda: {
            "bg_ndi_wi", "zcta5_cbp", "tiger_proximity",
            "nhd_bluespace", "noise", "vnl", "temis", "fara_tract",
        },
    )

    payload = vr.load_variables(force=True)
    entry = payload["variables"]["fara_tract"]
    assert entry["boundary"] == "Tract"
    assert entry["experiment"] == "fara_tract"
    assert entry["coverage_years"] == [2013, 2019]
    assert entry["display_unit"] == "binary flags"
    assert entry["value_cols"] == [
        "LILATracts_1And10", "LATracts1", "HUNVFlag", "LowIncomeTracts",
    ]


def test_real_metadata_file_contains_fara_tract_with_runner_module():
    """Post-Sprint-11-B2: real metadata loads cleanly + exposes fara_tract
    entry once backend/app/experiments/fara_tract.py exists.
    """
    from app import variable_registry as vr
    payload = vr.load_variables(force=True)
    assert "fara_tract" in payload["variables"], sorted(payload["variables"].keys())
    entry = payload["variables"]["fara_tract"]
    assert entry["experiment"] == "fara_tract"
    assert entry["boundary"] == "Tract"
    assert entry["coverage_years"] == [2013, 2019]


def test_list_experiments_after_fara_tract_added():
    """Sprint 11: list_experiments now contains eight entries in file order.
    bg_ndi_wi -> zcta5_cbp -> tiger_proximity -> nhd_bluespace -> noise
        -> vnl -> temis -> fara_tract.
    """
    from app import variable_registry as vr
    exps = vr.list_experiments()
    assert exps == [
        "bg_ndi_wi", "zcta5_cbp", "tiger_proximity", "nhd_bluespace",
        "noise", "vnl", "temis", "fara_tract",
    ], exps


# ---------------------------------------------------------------------------
# Sprint 11 B4: FARA C4 server-boot pre-flight (mirror of TEMIS T4 pattern)
# ---------------------------------------------------------------------------


def test_fara_preflight_passes_when_files_present(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    # Provision all six trees so no pre-flight short-circuits and none raise.
    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    _make_vnl_tree(tmp_path, with_tif=True)
    _make_temis_tree(tmp_path, with_subdir=True)
    _make_fara_tree(tmp_path, with_files=True)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    payload = vr.load_variables(force=True)  # must not raise
    assert "fara_tract" in payload["variables"]


def test_fara_preflight_raises_when_rda_missing(tmp_path, monkeypatch):
    from app import variable_registry as vr
    from app.config import settings

    _make_tiger_tree(tmp_path, range(2013, 2020))
    _make_nhd_tree(tmp_path, with_gdb=True)
    _make_noise_tree(tmp_path, with_tifs=True)
    _make_vnl_tree(tmp_path, with_tif=True)
    _make_temis_tree(tmp_path, with_subdir=True)
    # FARA C4 root exists (no short-circuit) but no .Rda / label CSV.
    _make_fara_tree(tmp_path, with_files=False)
    monkeypatch.setattr(settings, "SPACESCANS_DATA_DIR", tmp_path)

    with pytest.raises(vr.MetadataSchemaError) as exc_info:
        vr.load_variables(force=True)
    msg = str(exc_info.value)
    assert "fara_tract" in msg
    assert "fara_nationwide_2010_2019_interpolated.Rda" in msg


def test_schema_allows_optional_ontology_id():
    """The variable_metadata schema must accept an optional ontology_id and
    still validate when it is absent (additionalProperties is false, so this
    fails until ontology_id is declared in the schema)."""
    import json
    import pathlib

    import jsonschema

    schema = json.loads(
        pathlib.Path("app/data/variable_metadata.schema.json").read_text()
    )
    base_var = {
        "label": "L", "description": "D", "boundary": "BG",
        "coverage_years": [2010, 2020], "coverage_region": "CONUS",
        "experiment": "e", "variable_type": "continuous",
        "display_unit": "u", "value_cols": ["v"],
    }
    with_id = {"schema_version": 1,
               "variables": {"x": {**base_var, "ontology_id": "000289"}}}
    without_id = {"schema_version": 1, "variables": {"x": dict(base_var)}}
    jsonschema.validate(with_id, schema)      # must not raise
    jsonschema.validate(without_id, schema)   # must not raise


def test_variable_metadata_model_accepts_optional_ontology_id():
    from app.routers.variables import VariableMetadataModel

    common = dict(
        label="L", description="D", boundary="BG",
        coverage_years=(2010, 2020), coverage_region="CONUS",
        experiment="e", variable_type="continuous",
        display_unit="u", value_cols=["v"],
    )
    assert VariableMetadataModel(**common, ontology_id="000289").ontology_id == "000289"
    assert VariableMetadataModel(**common).ontology_id is None
