"""raster_values: what an uploaded GeoTIFF must satisfy, and reading pixels back
by the pipeline's grid_id convention.

Every rejection here is a run that would otherwise fail late or link nothing:
no CRS -> grid_weights cannot reproject the buffers; bottom-up -> exactextract
refuses it ("Incompatible extents", the ACAG incident); off-CONUS -> 0 % linked.
"""
from __future__ import annotations

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402

from app import raster_values as rv  # noqa: E402


def write_tif(path, array, *, west=-85.0, north=31.0, res=0.01, crs="EPSG:4326",
              nodata=None, bottom_up=False, count=1):
    """A small GeoTIFF. `array` is (rows, cols) for one band, or (bands, rows, cols)."""
    arr = np.asarray(array, dtype="float32")
    if arr.ndim == 2:
        arr = arr[None, ...]
    bands, rows, cols = arr.shape
    if bottom_up:
        transform = rasterio.Affine(res, 0, west, 0, res, north - rows * res)
    else:
        transform = from_origin(west, north, res, res)
    with rasterio.open(
        path, "w", driver="GTiff", width=cols, height=rows, count=bands,
        dtype="float32", crs=crs, transform=transform, nodata=nodata,
    ) as dst:
        dst.write(arr)
    return path


def _grid(rows=4, cols=5):
    """value = row * 10 + col, so a pixel's value says where it is."""
    return np.array([[r * 10 + c for c in range(cols)] for r in range(rows)])


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------

def test_inspect_describes_a_good_raster(tmp_path):
    p = write_tif(tmp_path / "ok.tif", _grid(), nodata=-9999)
    meta = rv.inspect(p.read_bytes())
    assert (meta["width"], meta["height"], meta["cells"]) == (5, 4, 20)
    assert meta["crs"] == "EPSG:4326"
    assert meta["band_count"] == 1
    assert meta["nodata"] == -9999.0
    assert meta["resolution_label"] == "0.01°"
    w, s, e, n = meta["bounds_wgs84"]
    assert (round(w, 2), round(n, 2)) == (-85.0, 31.0)
    assert len(meta["grid_hash"]) == 8


def test_inspect_accepts_a_path_as_well_as_bytes(tmp_path):
    p = write_tif(tmp_path / "ok.tif", _grid())
    assert rv.inspect(p) == rv.inspect(p.read_bytes())


def test_inspect_rejects_a_raster_without_crs(tmp_path):
    p = write_tif(tmp_path / "nocrs.tif", _grid(), crs=None)
    with pytest.raises(rv.RasterError, match="no coordinate reference system"):
        rv.inspect(p.read_bytes())


def test_inspect_rejects_a_bottom_up_raster(tmp_path):
    """exactextract refuses these — the ACAG ascending-latitude failure."""
    p = write_tif(tmp_path / "south.tif", _grid(), bottom_up=True)
    with pytest.raises(rv.RasterError, match="bottom-up"):
        rv.inspect(p.read_bytes())


def test_inspect_rejects_a_raster_off_the_continental_us(tmp_path):
    p = write_tif(tmp_path / "europe.tif", _grid(), west=10.0, north=50.0)
    with pytest.raises(rv.RasterError, match="does not touch the continental US"):
        rv.inspect(p.read_bytes())


def test_inspect_rejects_something_that_is_not_a_raster():
    with pytest.raises(rv.RasterError, match="not a raster"):
        rv.inspect(b"tract,value\n12073001100,0.4\n")


def test_inspect_lists_bands(tmp_path):
    p = write_tif(tmp_path / "multi.tif", np.stack([_grid(), _grid() + 100, _grid() + 200]))
    meta = rv.inspect(p.read_bytes())
    assert meta["band_count"] == 3
    assert [b["index"] for b in meta["bands"]] == [1, 2, 3]


def test_projected_resolution_label(tmp_path):
    # 1 km cells in a projected CRS read as "1 km"; 250 m as "250 m".
    p = write_tif(tmp_path / "km.tif", _grid(), west=-2_000_000, north=1_000_000,
                  res=1000, crs="EPSG:5070")
    assert rv.inspect(p.read_bytes())["resolution_label"] == "1 km"
    p = write_tif(tmp_path / "m.tif", _grid(), west=-2_000_000, north=1_000_000,
                  res=250, crs="EPSG:5070")
    assert rv.inspect(p.read_bytes())["resolution_label"] == "250 m"


# --------------------------------------------------------------------------
# grid identity
# --------------------------------------------------------------------------

def test_grid_hash_ignores_pixel_values(tmp_path):
    """Two years of one dataset differ in every pixel and share one C3."""
    a = rv.inspect(write_tif(tmp_path / "a.tif", _grid()).read_bytes())
    b = rv.inspect(write_tif(tmp_path / "b.tif", _grid() * 7 + 3).read_bytes())
    assert rv.same_grid(a, b)
    assert a["grid_hash"] == b["grid_hash"]


@pytest.mark.parametrize("change", [
    dict(res=0.02), dict(west=-85.01), dict(north=31.5), dict(crs="EPSG:4269"),
])
def test_grid_hash_changes_with_the_grid(tmp_path, change):
    base = rv.inspect(write_tif(tmp_path / "a.tif", _grid()).read_bytes())
    other = rv.inspect(write_tif(tmp_path / "b.tif", _grid(), **change).read_bytes())
    assert not rv.same_grid(base, other)


def test_grid_hash_changes_with_shape(tmp_path):
    base = rv.inspect(write_tif(tmp_path / "a.tif", _grid(4, 5)).read_bytes())
    other = rv.inspect(write_tif(tmp_path / "b.tif", _grid(4, 6)).read_bytes())
    assert not rv.same_grid(base, other)


# --------------------------------------------------------------------------
# extract_values
# --------------------------------------------------------------------------

def test_extract_follows_the_row_major_grid_id_convention(tmp_path):
    """grid_id = row * width + col, 0-based — what grid_weights emits with
    grid_id_offset 0 and what the noise reader inverts."""
    p = write_tif(tmp_path / "g.tif", _grid(4, 5))
    ids = np.array([0, 4, 5, 13, 19])            # (0,0) (0,4) (1,0) (2,3) (3,4)
    vals = rv.extract_values(p, ids)
    assert vals.tolist() == [0.0, 4.0, 10.0, 23.0, 34.0]


def test_extract_turns_nodata_into_nan(tmp_path):
    g = _grid(4, 5).astype(float)
    g[1, 2] = -9999
    p = write_tif(tmp_path / "nd.tif", g, nodata=-9999)
    vals = rv.extract_values(p, np.array([7, 8]))    # (1,2) is nodata, (1,3) is 13
    assert np.isnan(vals[0]) and vals[1] == 13.0


def test_extract_gives_nan_outside_the_raster(tmp_path):
    p = write_tif(tmp_path / "g.tif", _grid(4, 5))
    vals = rv.extract_values(p, np.array([-1, 0, 20, 10_000]))
    assert np.isnan(vals[0]) and vals[1] == 0.0 and np.isnan(vals[2]) and np.isnan(vals[3])


def test_extract_reads_the_requested_band(tmp_path):
    p = write_tif(tmp_path / "multi.tif", np.stack([_grid(), _grid() + 100]))
    assert rv.extract_values(p, np.array([13]), band=1).tolist() == [23.0]
    assert rv.extract_values(p, np.array([13]), band=2).tolist() == [123.0]
    with pytest.raises(rv.RasterError, match="band 3 does not exist"):
        rv.extract_values(p, np.array([0]), band=3)


def test_extract_with_no_ids_returns_empty(tmp_path):
    p = write_tif(tmp_path / "g.tif", _grid())
    assert rv.extract_values(p, np.array([], dtype="int64")).shape == (0,)


def test_blockwise_read_matches_full_read(tmp_path, monkeypatch):
    """Force the block path on a small raster and compare against the simple
    full read — the two must agree cell for cell, including nodata."""
    import rasterio
    g = _grid(40, 50).astype(float)
    g[7, 9] = -1
    p = tmp_path / "tiled.tif"
    arr = g.astype("float32")[None]
    with rasterio.open(
        p, "w", driver="GTiff", width=50, height=40, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(-85.0, 31.0, 0.01, 0.01),
        nodata=-1, tiled=True, blockxsize=16, blockysize=16,
    ) as dst:
        dst.write(arr)
    ids = np.array([0, 49, 7 * 50 + 9, 20 * 50 + 33, 39 * 50 + 49, 5000])
    full = rv.extract_values(p, ids)
    monkeypatch.setattr(rv, "FULL_READ_MAX_CELLS", 10)     # 2,000 cells > 10 -> blocks
    blocks = rv.extract_values(p, ids)
    assert np.array_equal(np.isnan(full), np.isnan(blocks))
    assert np.allclose(full[~np.isnan(full)], blocks[~np.isnan(blocks)])
    assert np.isnan(blocks[2]) and np.isnan(blocks[5])       # nodata and out of range
    assert blocks[3] == 20 * 10 + 33
